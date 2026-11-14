"""Motor de reglas, calibración personal, sensibilidad al CO₂, proyecciones y modelos ML."""

from __future__ import annotations

import copy
import math
import statistics
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any

from .coach import Coach
from .config import CONFIG_VERSION, get_param
from .contracts import (
    ActivityDeclaration,
    CheckInRequest,
    ContextEventRequest,
    Telemetry,
)
from .donki import get_solar_context
from .ml_models import HYPOTHESIS_PREFIX, ModelRunner
from .profiles import get_profile
from .report import build_episode_report

METHOD = "Reglas de demostración v0.1 · sin modelo entrenado"
FORECAST_METHOD = "Persistencia a 60 s: conservar el último pulso válido"
RULES_VERSION = "0.2.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConflictError(ValueError):
    pass


def _normalize_now(now: datetime | None) -> datetime:
    if now is None:
        return utc_now()
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _get_field(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def _compute_mad(values: list[float], center: float) -> float:
    return round(float(statistics.median(abs(v - center) for v in values)), 2)


def compute_co2_sensitivity(
    samples: Iterable[Any],
    *,
    rr_alert: float = 23.0,
    window_s: float = 300.0,
) -> dict[str, Any]:
    """Estima la sensibilidad respiratoria personal al CO₂ mediante OLS en ventana de hasta 5 min."""
    raw_items = list(samples)
    if not raw_items:
        return {
            "status": "insufficient_data",
            "slope": None,
            "r2": None,
            "co2_personal": None,
            "personal_threshold_mmhg": None,
            "sample_count": 0,
            "co2_range": None,
            "reason": "Sin muestras disponibles para estimar sensibilidad al CO₂.",
        }

    # Deduplicar por marca temporal cuando esté disponible, preservando orden cronológico.
    has_timestamps = any(_parse_ts(_get_field(item, "measured_at")) is not None for item in raw_items)
    if has_timestamps:
        by_ts: dict[datetime, Any] = {}
        for item in raw_items:
            ts = _parse_ts(_get_field(item, "measured_at"))
            if ts is not None:
                by_ts[ts] = item
        ordered_ts = sorted(by_ts)
        latest_ts = ordered_ts[-1]
        cutoff = latest_ts - timedelta(seconds=window_s)
        window_items = [by_ts[ts] for ts in ordered_ts if ts >= cutoff]
    else:
        window_items = raw_items

    valid_pairs: list[tuple[float, float]] = []
    for item in window_items:
        source = _get_field(item, "source")
        activity = _get_field(item, "activity")
        hr = _get_field(item, "hr")
        rr = _get_field(item, "rr")
        co2 = _get_field(item, "co2")
        if source == "bidmc" or activity == "exercise":
            continue
        if _is_finite_number(hr) and _is_finite_number(rr) and _is_finite_number(co2):
            valid_pairs.append((float(co2), float(rr)))

    if len(valid_pairs) < 24:
        co2_vals = [pair[0] for pair in valid_pairs]
        co2_range = round(max(co2_vals) - min(co2_vals), 4) if co2_vals else None
        return {
            "status": "insufficient_data",
            "slope": None,
            "r2": None,
            "co2_personal": None,
            "personal_threshold_mmhg": None,
            "sample_count": len(valid_pairs),
            "co2_range": co2_range,
            "reason": (
                f"Datos insuficientes para sensibilidad al CO₂ "
                f"({len(valid_pairs)}/24 muestras válidas sin ejercicio en 5 min)."
            ),
        }

    co2_vals = [pair[0] for pair in valid_pairs]
    rr_vals = [pair[1] for pair in valid_pairs]
    co2_range = max(co2_vals) - min(co2_vals)
    if co2_range < 0.4:
        return {
            "status": "insufficient_data",
            "slope": None,
            "r2": None,
            "co2_personal": None,
            "personal_threshold_mmhg": None,
            "sample_count": len(valid_pairs),
            "co2_range": round(co2_range, 4),
            "reason": (
                f"Variación de CO₂ insuficiente ({co2_range:.2f} < 0.40 mmHg) "
                "para calibrar sensibilidad."
            ),
        }

    x_mean = statistics.fmean(co2_vals)
    y_mean = statistics.fmean(rr_vals)
    ss_xx = sum((x - x_mean) ** 2 for x in co2_vals)
    ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(co2_vals, rr_vals))
    ss_yy = sum((y - y_mean) ** 2 for y in rr_vals)

    if ss_xx <= 0:
        return {
            "status": "insufficient_data",
            "slope": None,
            "r2": None,
            "co2_personal": None,
            "personal_threshold_mmhg": None,
            "sample_count": len(valid_pairs),
            "co2_range": round(co2_range, 4),
            "reason": "Sin varianza suficiente en CO₂ para ajustar regresión.",
        }

    slope = ss_xy / ss_xx
    r2 = max(0.0, min(1.0, (ss_xy ** 2) / (ss_xx * ss_yy))) if ss_yy > 0 else 0.0

    if slope <= 0 or r2 < 0.6:
        return {
            "status": "low_r2",
            "slope": None,
            "r2": round(r2, 4),
            "co2_personal": None,
            "personal_threshold_mmhg": None,
            "sample_count": len(valid_pairs),
            "co2_range": round(co2_range, 4),
            "reason": (
                f"Ajuste lineal insuficiente para sensibilidad al CO₂ "
                f"(r²={r2:.2f}; requiere pendiente > 0 y r² ≥ 0.60)."
            ),
        }

    co2_actual = co2_vals[-1]
    rr_actual = rr_vals[-1]
    co2_personal = round(co2_actual + (float(rr_alert) - rr_actual) / slope, 2)
    return {
        "status": "ready",
        "slope": round(slope, 4),
        "r2": round(r2, 4),
        "co2_personal": co2_personal,
        "personal_threshold_mmhg": co2_personal,
        "sample_count": len(valid_pairs),
        "co2_range": round(co2_range, 4),
        "reason": None,
        "assumption": (
            "Regresión lineal OLS en ventana de hasta 5 min sin ejercicio "
            "(indicador orientativo, no diagnóstico)."
        ),
    }


class Engine:
    def __init__(
        self,
        environment: str = "station",
        model_runner: ModelRunner | None = None,
        on_ingest: Callable[[Telemetry], Any] | None = None,
    ):
        self._lock = RLock()
        self.environment_profile: dict[str, Any] = get_profile(environment)
        self.environment: str = self.environment_profile["id"]
        self.model_runner: ModelRunner = (
            model_runner if model_runner is not None else ModelRunner()
        )
        self.on_ingest = on_ingest

        self.history: deque[Telemetry] = deque(maxlen=120)
        self.long_history: deque[Telemetry] = deque(maxlen=720)
        self.events: deque[dict[str, str]] = deque(maxlen=50)
        self._seen: dict[str, dict[str, Any]] = {}
        self.dose_total: float = 0.0
        self.dose_complete: bool = True
        self.received_count: int = 0
        self._last_pattern: tuple[str, str, str] | None = None
        self._revision: int = 0
        self._ack_revision: int | None = None

        self.baseline: dict[str, Any] = {
            "status": "calibrando",
            "hr": None,
            "rr": None,
            "hr_mad": None,
            "rr_mad": None,
            "source": None,
        }
        self._baseline_rest_samples: list[Telemetry] = []

        self.coach = Coach()
        self.share_behavioral: bool = False
        self.external_event: dict[str, Any] | None = None
        self.shelter_active: bool = False
        self.activity_declaration: dict[str, Any] | None = None
        self._activity_override_source_activity: str | None = None
        self._activity_phase: str | None = None
        self._activity_phase_started_at: datetime | None = None
        self._activity_phase_source: str | None = None

    def _event(self, text: str, now: datetime) -> None:
        self.events.append({"at": now.isoformat(), "text": text})

    def _effective_activity_for(self, sample: Telemetry) -> str:
        if sample.activity == "unknown":
            if self.activity_declaration is not None:
                return str(self.activity_declaration["activity"])
            return "unknown"
        if (
            self.activity_declaration is not None
            and self._activity_override_source_activity is not None
            and sample.activity == self._activity_override_source_activity
        ):
            return str(self.activity_declaration["activity"])
        return sample.activity

    def _combined_history(self, *, contiguous_source: str | None = None) -> list[Telemetry]:
        by_ts: dict[datetime, Telemetry] = {}
        for item in self.long_history:
            by_ts[item.measured_at] = item
        for item in self.history:
            by_ts[item.measured_at] = item
        ordered = [by_ts[ts] for ts in sorted(by_ts)]
        if contiguous_source is None or not ordered:
            return ordered
        target_source = contiguous_source
        block: list[Telemetry] = []
        for item in reversed(ordered):
            if item.source != target_source:
                break
            block.append(item)
        block.reverse()
        return block

    def _update_baseline_from_sample(self, sample: Telemetry) -> None:
        if self.baseline["status"] == "ready":
            return
        if (
            sample.source == "bidmc"
            or sample.activity != "rest"
            or sample.hr is None
            or sample.rr is None
        ):
            return

        self._baseline_rest_samples.append(sample)
        count = len(self._baseline_rest_samples)
        window_s = get_param("baseline_window_s")
        # Calcular duración cubierta en reposo evitando falsos positivos ante huecos largos.
        covered_s = 0.0
        for prev, curr in zip(self._baseline_rest_samples, self._baseline_rest_samples[1:]):
            gap = (curr.measured_at - prev.measured_at).total_seconds()
            if 0 < gap <= 15.0:
                covered_s += gap

        if count >= 120 or (covered_s >= window_s and count >= 12):
            hrs = [float(item.hr) for item in self._baseline_rest_samples if item.hr is not None]
            rrs = [float(item.rr) for item in self._baseline_rest_samples if item.rr is not None]
            hr_med = round(float(statistics.median(hrs)), 2)
            rr_med = round(float(statistics.median(rrs)), 2)
            self.baseline = {
                "status": "ready",
                "hr": hr_med,
                "rr": rr_med,
                "hr_mad": _compute_mad(hrs, hr_med),
                "rr_mad": _compute_mad(rrs, rr_med),
                "source": "rest_window",
            }

    def set_baseline(
        self,
        hr: float,
        rr: float,
        source: str = "calibration_file",
        *,
        hr_mad: float | None = None,
        rr_mad: float | None = None,
    ) -> dict[str, Any]:
        """Fija explícitamente la línea base personal y la bloquea para el episodio."""
        if not _is_finite_number(hr) or not (0 < float(hr) <= 300):
            raise ValueError("La frecuencia cardíaca base debe ser finita y estar en (0, 300].")
        if not _is_finite_number(rr) or not (0 < float(rr) <= 100):
            raise ValueError("La frecuencia respiratoria base debe ser finita y estar en (0, 100].")
        if hr_mad is not None and (not _is_finite_number(hr_mad) or float(hr_mad) < 0):
            raise ValueError("hr_mad debe ser finito y >= 0.")
        if rr_mad is not None and (not _is_finite_number(rr_mad) or float(rr_mad) < 0):
            raise ValueError("rr_mad debe ser finito y >= 0.")

        with self._lock:
            self.baseline = {
                "status": "ready",
                "hr": round(float(hr), 2),
                "rr": round(float(rr), 2),
                "hr_mad": round(float(hr_mad), 2) if hr_mad is not None else None,
                "rr_mad": round(float(rr_mad), 2) if rr_mad is not None else None,
                "source": source,
            }
            return copy.deepcopy(self.baseline)

    def _sustained_baseline_elevation_s(self, sample: Telemetry, effective_activity: str) -> float:
        if (
            self.baseline.get("status") != "ready"
            or self.baseline.get("hr") is None
            or sample.source == "bidmc"
            or effective_activity == "exercise"
            or sample.hr is None
        ):
            return 0.0
        limit = float(self.baseline["hr"]) + 25.0
        if sample.hr <= limit:
            return 0.0

        streak_start = sample.measured_at
        prev_ts = sample.measured_at
        for item in reversed(self.history):
            if item.source != sample.source:
                break
            item_activity = self._effective_activity_for(item)
            if item_activity == "exercise" or item.hr is None or item.hr <= limit:
                break
            if item is not sample and (prev_ts - item.measured_at).total_seconds() > 15.0:
                break
            streak_start = item.measured_at
            prev_ts = item.measured_at
        return max(0.0, (sample.measured_at - streak_start).total_seconds())

    def _phase_duration_s(self, latest: Telemetry | None) -> float:
        if latest is None or self._activity_phase_started_at is None:
            return 0.0
        return max(0.0, (latest.measured_at - self._activity_phase_started_at).total_seconds())

    @staticmethod
    def _assessment_for(
        sample: Telemetry | None,
        now: datetime,
        *,
        environment_profile: dict[str, Any] | None = None,
        external_event: dict[str, Any] | None = None,
        baseline: dict[str, Any] | None = None,
        forecast_info: dict[str, Any] | None = None,
        pattern_info: dict[str, Any] | None = None,
        effective_activity: str | None = None,
        sustained_baseline_s: float = 0.0,
    ) -> dict[str, Any]:
        profile = environment_profile or get_profile("station")
        thresholds = profile["thresholds"]
        stale_seconds = get_param("stale_seconds")

        result: dict[str, Any] = {
            "level": "unknown",
            "title": "Esperando telemetría",
            "hypothesis": f"{HYPOTHESIS_PREFIX}: esperando telemetría inicial.",
            "evidence": ["La API está lista; todavía no hay mediciones."],
            "next_step": "Iniciar el simulador o la reproducción BIDMC.",
            "method": METHOD,
            "forecast_hr": None,
            "forecast_method": FORECAST_METHOD,
        }
        if sample is None:
            return result

        age = max(0.0, (now - sample.measured_at).total_seconds())
        if age > stale_seconds:
            result.update(
                title="Telemetría desactualizada",
                hypothesis=(
                    f"{HYPOTHESIS_PREFIX}: telemetría desactualizada; "
                    "no se emite evaluación actual."
                ),
                evidence=[
                    f"Última medición hace {age:.0f} s; el límite de demo es {stale_seconds:g} s."
                ],
                next_step=(
                    "Revisar conexión con la pasarela. No interpretar el último valor como actual."
                ),
            )
            return result

        if sample.hr is not None:
            result["forecast_hr"] = sample.hr
        if (
            forecast_info
            and forecast_info.get("available")
            and sample.hr is not None
            and forecast_info.get("forecast_hr") is not None
        ):
            result["forecast_hr"] = forecast_info["forecast_hr"]
            result["forecast_method"] = str(forecast_info.get("method") or FORECAST_METHOD)

        activity = effective_activity if effective_activity is not None else sample.activity

        if sample.hr is None or sample.rr is None:
            absent = ", ".join(
                name
                for name, value in (("pulso", sample.hr), ("respiración", sample.rr))
                if value is None
            )
            result.update(
                title="Evaluación fisiológica incompleta",
                hypothesis=(
                    f"{HYPOTHESIS_PREFIX}: evaluación fisiológica incompleta "
                    f"por ausencia de {absent}."
                ),
                evidence=[f"Sin lectura de {absent}; no se reemplaza por cero."],
                next_step="Revisar señal y conexión del sensor.",
            )
        elif sample.source == "bidmc":
            result.update(
                title="Registro real · contexto limitado",
                hypothesis=(
                    f"{HYPOTHESIS_PREFIX}: reproducción de registro clínico terrestre BIDMC "
                    "con contexto ambiental y de actividad ausente."
                ),
                evidence=[
                    f"Pulso {sample.hr:.0f} bpm · respiración {sample.rr:.0f}/min.",
                    "BIDMC: registro clínico terrestre, sin CO₂, dosímetro ni actividad conocida.",
                    "Reproducción histórica; no se asigna una hipótesis espacial.",
                ],
                next_step="Explorar las señales reales; agregar contexto antes de interpretar.",
            )
        elif (
            sample.co2 is not None
            and sample.co2 >= float(thresholds["co2_alert"])
            and sample.rr >= float(thresholds["rr_alert"])
        ):
            result.update(
                level="alert",
                title="Hipótesis: cambio respiratorio y ambiental",
                hypothesis=(
                    f"{HYPOTHESIS_PREFIX}: coincidencia de CO₂ elevado y "
                    "aumento respiratorio en cabina."
                ),
                evidence=[
                    f"CO₂ {sample.co2:.2f} mmHg y respiración {sample.rr:.0f}/min.",
                    "Coinciden dos cambios del escenario; no demuestra causalidad.",
                    (
                        f"Límites del entorno ({profile['name']}): "
                        f"CO₂ ≥ {thresholds['co2_alert']:g} mmHg y "
                        f"respiración ≥ {thresholds['rr_alert']:g}/min."
                    ),
                ],
                next_step="Verificar sensores y contexto de cabina; registrar la observación.",
            )
        elif activity == "exercise":
            result.update(
                level="normal",
                title="Patrón compatible con actividad simulada",
                hypothesis=(
                    f"{HYPOTHESIS_PREFIX}: respuesta fisiológica compatible "
                    "con actividad física declarada."
                ),
                evidence=[
                    f"Actividad declarada: ejercicio · pulso {sample.hr:.0f} bpm.",
                    "El contexto de actividad explica la interpretación de esta regla de demo.",
                ],
                next_step="Observar la tendencia al cambiar a recuperación.",
            )
        elif activity == "unknown":
            result.update(
                title="Actividad desconocida",
                hypothesis=(
                    f"{HYPOTHESIS_PREFIX}: falta contexto de actividad para "
                    "interpretar las señales fisiológicas."
                ),
                evidence=["Hay señales fisiológicas, pero falta el contexto de actividad."],
                next_step="Confirmar la actividad antes de interpretar el pulso.",
            )
        elif sample.hr >= float(thresholds["hr_watch"]):
            result.update(
                level="watch",
                title="Hipótesis: recuperación o pulso fuera del patrón de demo",
                hypothesis=(
                    f"{HYPOTHESIS_PREFIX}: pulso elevado respecto al umbral de demo "
                    "sin ejercicio declarado."
                ),
                evidence=[
                    f"Pulso {sample.hr:.0f} bpm sin actividad de ejercicio declarada.",
                    (
                        f"El umbral del entorno es {thresholds['hr_watch']:g} bpm; "
                        "no es una referencia personal."
                    ),
                    "Alternativas: cambio de actividad, variación individual o señal incorrecta.",
                ],
                next_step="Confirmar actividad y calidad; observar si el pulso disminuye.",
            )
        else:
            result.update(
                level="normal",
                title="Sin cambios señalados por las reglas de demo",
                hypothesis=(
                    f"{HYPOTHESIS_PREFIX}: señales dentro de los rangos de demostración "
                    "para el contexto actual."
                ),
                evidence=[
                    f"Pulso {sample.hr:.0f} bpm · respiración {sample.rr:.0f}/min.",
                    "Esta comprobación no equivale a una evaluación completa de salud.",
                ],
                next_step="Continuar observando las señales y su contexto.",
            )
            if (
                baseline
                and baseline.get("status") == "ready"
                and baseline.get("hr") is not None
                and activity != "exercise"
                and sustained_baseline_s >= 30.0
                and sample.hr > float(baseline["hr"]) + 25.0
            ):
                result.update(
                    level="watch",
                    title="Hipótesis: pulso sostenido sobre línea base personal",
                    hypothesis=(
                        f"{HYPOTHESIS_PREFIX}: pulso sostenido por encima de la línea base "
                        "personal fuera de ejercicio."
                    ),
                    evidence=[
                        (
                            f"Pulso {sample.hr:.0f} bpm (> línea base {float(baseline['hr']):.0f} + 25 bpm) "
                            f"sostenido durante {sustained_baseline_s:.0f} s."
                        ),
                        "Alternativas: recuperación prolongada, cambio de actividad o ruido del sensor.",
                    ],
                    next_step="Confirmar actividad y observar si el pulso regresa hacia la línea base.",
                )

        if (
            external_event
            and external_event.get("phase") == "watch"
            and result["level"] == "normal"
            and (
                sample.dose_rate is None
                or sample.dose_rate < float(thresholds["dose_rate_alert"])
            )
        ):
            donki_source = external_event.get("source") or "NASA CCMC DONKI"
            sep_id = external_event.get("sep_id") or "SEP"
            hist_note = external_event.get("historical_note") or (
                "Contexto histórico externo de referencia; no constituye dosimetría personal."
            )
            result["level"] = "watch"
            result["title"] = "Evento solar en observación"
            result["hypothesis"] = (
                f"{HYPOTHESIS_PREFIX}: evento solar externo en observación (contexto NASA DONKI)."
            )
            result["evidence"] = [
                *result["evidence"],
                f"Contexto externo {donki_source} ({sep_id}): fase watch.",
                hist_note,
            ]
            result["next_step"] = (
                external_event.get("next_step")
                or "Revisar lista de verificación de refugio antes de la llegada estimada."
            )

        # La tasa ambiental se interpreta por separado de las señales fisiológicas.
        if sample.dose_rate is not None and sample.dose_rate >= float(thresholds["dose_rate_alert"]):
            physiology = result["title"]
            rad_evidence = [
                (
                    f"Dosímetro simulado: {sample.dose_rate:.1f} μSv/h; "
                    f"umbral del entorno ({profile['name']}): {thresholds['dose_rate_alert']:g} μSv/h."
                ),
                f"Evaluación fisiológica separada: {physiology}.",
                "La tasa no permite diagnosticar una lesión ni confirma un evento solar real.",
            ]
            if external_event:
                rad_evidence.append(
                    f"Contexto externo {external_event.get('source', 'NASA DONKI')} "
                    f"(fase {external_event.get('phase', 'activa')}): "
                    f"{external_event.get('historical_note', '')}".strip()
                )
            result.update(
                level="alert",
                title="Radiación simulada · revisar exposición",
                hypothesis=(
                    f"{HYPOTHESIS_PREFIX}: tasa de radiación simulada por encima del umbral; "
                    "revisar exposición y refugio."
                ),
                evidence=rad_evidence,
                next_step="Probar el refugio del simulador y observar la tasa y el acumulado.",
            )

        if (
            pattern_info
            and pattern_info.get("available")
            and pattern_info.get("hypothesis")
            and sample.source != "bidmc"
            and sample.hr is not None
            and sample.rr is not None
        ):
            pat_hyp = str(pattern_info["hypothesis"])
            if pat_hyp not in result["evidence"]:
                result["evidence"] = [*result["evidence"], pat_hyp]
            result["pattern"] = pattern_info.get("pattern")

        return result

    def _evaluate(self, now: datetime) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        latest = self.history[-1] if self.history else None
        source_history = (
            self._combined_history(contiguous_source=latest.source)
            if latest is not None
            else []
        )
        effective_activity = (
            self._effective_activity_for(latest) if latest is not None else "unknown"
        )
        phase_duration_s = self._phase_duration_s(latest)

        raw_forecast = self.model_runner.predict_forecast(source_history, now=now)
        raw_pattern = self.model_runner.predict_pattern(
            source_history,
            now=now,
            baseline=self.baseline,
            activity=effective_activity,
            phase_duration_s=phase_duration_s,
        )

        forecast_payload = {
            **raw_forecast,
            "value_bpm": raw_forecast.get("forecast_hr"),
            "persistence_bpm": raw_forecast.get("persistence_hr"),
        }
        pattern_payload = {
            **raw_pattern,
            "hypothesis_text": raw_pattern.get("hypothesis"),
            "label": raw_pattern.get("pattern"),
        }

        sustained_s = (
            self._sustained_baseline_elevation_s(latest, effective_activity)
            if latest is not None
            else 0.0
        )
        assessment = self._assessment_for(
            latest,
            now,
            environment_profile=self.environment_profile,
            external_event=self.external_event,
            baseline=self.baseline,
            forecast_info=forecast_payload,
            pattern_info=pattern_payload,
            effective_activity=effective_activity,
            sustained_baseline_s=sustained_s,
        )
        return forecast_payload, pattern_payload, assessment

    def _assessment(self, now: datetime) -> dict[str, Any]:
        _, _, assessment = self._evaluate(now)
        return assessment

    def compute_co2_sensitivity(self, samples: Iterable[Any] | None = None) -> dict[str, Any]:
        """Calcula sensibilidad personal al CO₂ usando historial reciente o muestras dadas."""
        with self._lock:
            rr_alert = float(self.environment_profile["thresholds"]["rr_alert"])
            if samples is None:
                latest = self.history[-1] if self.history else None
                target_samples = (
                    self._combined_history(contiguous_source=latest.source)
                    if latest is not None
                    else []
                )
            else:
                target_samples = list(samples)
        return compute_co2_sensitivity(target_samples, rr_alert=rr_alert)

    def compute_projections(self, now: datetime | None = None) -> dict[str, Any]:
        """Calcula proyecciones de CO₂ (promedio 1 h + ETA) y dosis a 1 h con/sin refugio."""
        current = _normalize_now(now)
        with self._lock:
            stale_seconds = get_param("stale_seconds")
            shelter_factor = get_param("shelter_factor")
            co2_alert = float(self.environment_profile["thresholds"]["co2_alert"])
            nasa_1h_ref = get_param("co2_nasa_1h")
            latest = self.history[-1] if self.history else None
            age = max(0.0, (current - latest.measured_at).total_seconds()) if latest else None
            is_fresh = latest is not None and age is not None and age <= stale_seconds
            source_samples = (
                self._combined_history(contiguous_source=latest.source)
                if latest is not None
                else []
            )
            dose_total = float(self.dose_total)

        # Promedio móvil 60 min y cobertura
        cutoff_1h = current - timedelta(seconds=3600)
        co2_1h = [
            item
            for item in source_samples
            if item.measured_at >= cutoff_1h
            and item.measured_at <= current
            and item.co2 is not None
        ]
        buckets_1h = {
            min(719, max(0, int((current - item.measured_at).total_seconds() // 5)))
            for item in co2_1h
        }
        coverage_pct = round(min(100.0, (len(buckets_1h) / 720.0) * 100.0), 2)
        moving_avg_1h = round(statistics.fmean([float(item.co2) for item in co2_1h]), 3) if co2_1h else None

        # Tendencia lineal en últimos 120 s de CO₂
        assumption = "Tendencia lineal constante en los últimos 120 s (no es predicción médica)"
        slope_s: float | None = None
        r2_co2: float | None = None
        eta_s: float | None = None
        eta_minutes: float | None = None
        co2_reason: str | None = None

        if not is_fresh or latest is None:
            co2_reason = "datos_antiguos" if latest is not None else "sin_datos"
        elif latest.co2 is None:
            co2_reason = "sin_lectura_co2"
        else:
            cutoff_120 = latest.measured_at - timedelta(seconds=120)
            co2_120 = [
                item
                for item in source_samples
                if item.measured_at >= cutoff_120
                and item.measured_at <= latest.measured_at
                and item.co2 is not None
            ]
            if len(co2_120) < 5:
                co2_reason = "cobertura_insuficiente_120s"
            else:
                t0 = co2_120[0].measured_at
                times = [(item.measured_at - t0).total_seconds() for item in co2_120]
                values = [float(item.co2) for item in co2_120]
                t_mean = statistics.fmean(times)
                y_mean = statistics.fmean(values)
                ss_tt = sum((t - t_mean) ** 2 for t in times)
                ss_ty = sum((t - t_mean) * (y - y_mean) for t, y in zip(times, values))
                ss_yy = sum((y - y_mean) ** 2 for y in values)

                if ss_tt <= 0:
                    co2_reason = "cobertura_insuficiente_120s"
                else:
                    slope_val = ss_ty / ss_tt
                    r2_val = (
                        max(0.0, min(1.0, (ss_ty ** 2) / (ss_tt * ss_yy)))
                        if ss_yy > 0
                        else 0.0
                    )
                    slope_s = round(slope_val, 6)
                    r2_co2 = round(r2_val, 4)
                    if slope_val <= 0:
                        co2_reason = "tendencia_no_ascendente"
                    elif r2_val < 0.6:
                        co2_reason = "baja_correlacion_lineal"
                    elif float(latest.co2) >= co2_alert:
                        eta_s = 0.0
                        eta_minutes = 0.0
                        co2_reason = None
                    else:
                        eta_s = round((co2_alert - float(latest.co2)) / slope_val, 1)
                        eta_minutes = round(eta_s / 60.0, 2)
                        co2_reason = None

        co2_proj = {
            "moving_avg_1h_mmhg": moving_avg_1h,
            "coverage_pct": coverage_pct,
            "nasa_1h_ref_mmhg": nasa_1h_ref,
            "above_nasa_1h_ref": (moving_avg_1h > nasa_1h_ref) if moving_avg_1h is not None else None,
            "slope_mmhg_per_s": slope_s,
            "slope_mmhg_per_min": round(slope_s * 60.0, 4) if slope_s is not None else None,
            "r2": r2_co2,
            "threshold_mmhg": co2_alert,
            "eta_s": eta_s,
            "eta_minutes": eta_minutes,
            "assumption": assumption,
            "reason": co2_reason,
        }

        if is_fresh and latest is not None and latest.dose_rate is not None:
            rate = float(latest.dose_rate)
            projected_without_shelter = round(dose_total + rate * 1.0, 4)
            projected_with_shelter = round(dose_total + (rate * shelter_factor) * 1.0, 4)
            rad_reason = None
        else:
            rate = None
            projected_without_shelter = None
            projected_with_shelter = None
            rad_reason = "datos_antiguos" if (latest is not None and not is_fresh) else "sin_lectura_dosimetria"

        radiation_proj = {
            "horizon_hours": 1.0,
            "dose_total_usv": round(dose_total, 4),
            "current_rate_usvh": round(rate, 4) if rate is not None else None,
            "sheltered_rate_usvh": round(rate * shelter_factor, 4) if rate is not None else None,
            "shelter_factor": shelter_factor,
            "projected_without_shelter": projected_without_shelter,
            "projected_with_shelter": projected_with_shelter,
            "reason": rad_reason,
        }

        return {"co2": co2_proj, "radiation": radiation_proj}

    def _build_questions(self, now: datetime, assessment: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.history:
            return []
        sample = self.history[-1]
        stale_seconds = get_param("stale_seconds")
        age = max(0.0, (now - sample.measured_at).total_seconds())
        if age > stale_seconds:
            return []
        effective_activity = self._effective_activity_for(sample)
        if effective_activity != "unknown" or sample.hr is None or sample.rr is None:
            return []

        options = []
        for value, label in (("rest", "Reposo"), ("exercise", "Ejercicio")):
            hypothetical = self._assessment_for(
                sample.model_copy(update={"activity": value}),
                now,
                environment_profile=self.environment_profile,
                external_event=self.external_event,
                baseline=self.baseline,
                forecast_info=None,
                pattern_info=None,
                effective_activity=value,
                sustained_baseline_s=0.0,
            )
            options.append(
                {
                    "value": value,
                    "label": label,
                    "hypothetical_level": hypothetical["level"],
                    "hypothetical_title": hypothetical["title"],
                }
            )
        return [
            {
                "id": "activity_context",
                "prompt": "¿Cuál es la actividad actual?",
                "options": options,
            }
        ]

    def ingest(self, sample: Telemetry, now: datetime | None = None) -> dict[str, Any]:
        current = _normalize_now(now)
        payload = sample.model_dump(mode="json")
        with self._lock:
            if sample.sample_id in self._seen:
                if self._seen[sample.sample_id] != payload:
                    raise ConflictError("sample_id ya existe con otro contenido.")
                return {"accepted": True, "duplicate": True}
            if (sample.measured_at - current).total_seconds() > 5:
                raise ValueError("La medición está más de 5 s en el futuro.")
            previous = self.history[-1] if self.history else None
            if previous and sample.measured_at <= previous.measured_at:
                raise ConflictError("La medición no es posterior a la última aceptada.")

            if sample.dose_rate is None:
                self.dose_complete = False
            if previous:
                elapsed = (sample.measured_at - previous.measured_at).total_seconds()
                if (
                    previous.dose_rate is not None
                    and sample.dose_rate is not None
                    and elapsed <= 5
                    and previous.source == sample.source
                ):
                    self.dose_total += (
                        (previous.dose_rate + sample.dose_rate) / 2 * elapsed / 3600
                    )
                else:
                    self.dose_complete = False

            if (
                sample.activity != "unknown"
                and self._activity_override_source_activity is not None
                and sample.activity != self._activity_override_source_activity
            ):
                self._activity_override_source_activity = None
                self.activity_declaration = None

            self.history.append(sample)
            if (
                not self.long_history
                or (sample.measured_at - self.long_history[-1].measured_at).total_seconds() >= 5.0
                or sample.source != self.long_history[-1].source
            ):
                self.long_history.append(sample)

            self._seen[sample.sample_id] = payload
            self.received_count += 1

            effective_activity = self._effective_activity_for(sample)
            if (
                self._activity_phase != effective_activity
                or self._activity_phase_source != sample.source
                or self._activity_phase_started_at is None
            ):
                self._activity_phase = effective_activity
                self._activity_phase_started_at = sample.measured_at
                self._activity_phase_source = sample.source

            self._update_baseline_from_sample(sample)

            _, _, assessment = self._evaluate(current)
            pattern = (assessment["level"], assessment["title"], sample.source)
            if pattern != self._last_pattern:
                self._revision += 1
                self._last_pattern = pattern
                self._event(assessment["title"], current)

            if self.on_ingest is not None:
                self.on_ingest(sample)
            return {"accepted": True, "duplicate": False}

    def set_environment(self, env_id: str) -> dict[str, Any]:
        """Actualiza el perfil de entorno simulado activo y sus umbrales."""
        profile = get_profile(env_id)
        with self._lock:
            self.environment_profile = profile
            self.environment = profile["id"]
            return copy.deepcopy(self.environment_profile)

    def set_activity_declaration(
        self,
        decl: ActivityDeclaration | Mapping[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Registra una declaración manual de actividad del tripulante."""
        parsed = decl if isinstance(decl, ActivityDeclaration) else ActivityDeclaration(**decl)
        current = _normalize_now(now)
        started_at = parsed.started_at or current
        with self._lock:
            latest = self.history[-1] if self.history else None
            self.activity_declaration = {
                "activity": parsed.activity,
                "started_at": started_at.isoformat(),
                "declared_at": current.isoformat(),
                "note": parsed.note,
            }
            if latest is not None and latest.activity != "unknown":
                self._activity_override_source_activity = latest.activity
            else:
                self._activity_override_source_activity = None

            self._activity_phase = parsed.activity
            self._activity_phase_started_at = started_at
            self._activity_phase_source = latest.source if latest is not None else None
            return copy.deepcopy(self.activity_declaration)

    def set_external_event(
        self,
        req: ContextEventRequest | Mapping[str, Any] | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Activa o limpia el evento solar externo (contexto NASA DONKI)."""
        if req is None:
            parsed = ContextEventRequest(kind="clear")
        elif isinstance(req, ContextEventRequest):
            parsed = req
        elif isinstance(req, Mapping) and "sep_id" in req and "phase" in req:
            parsed = ContextEventRequest(
                kind=str(req.get("kind", "solar")),
                phase=str(req["phase"]),
                shelter=bool(req.get("shelter", False)),
            )
        else:
            parsed = ContextEventRequest(**req)
        current = _normalize_now(now)
        with self._lock:
            if parsed.kind == "clear":
                self.external_event = None
                self.shelter_active = False
                self.coach.activate_solar_checklist(False)
                return {
                    "accepted": True,
                    "kind": "clear",
                    "external_event": None,
                    "shelter_active": False,
                }

            ctx = get_solar_context(
                phase=parsed.phase,
                shelter=parsed.shelter,
                shelter_factor=get_param("shelter_factor"),
            )
            self.coach.activate_solar_checklist(True)
            self.shelter_active = bool(parsed.shelter)
            self.external_event = {
                **ctx,
                "kind": "solar",
                "event_id": ctx.get("sep_id"),
                "start_time": ctx.get("event_time"),
                "summary": f"{ctx['historical_note']} {ctx['next_step']}",
                "note": ctx.get("historical_note"),
                "updated_at": current.isoformat(),
            }
            return {
                "accepted": True,
                "kind": "solar",
                "external_event": copy.deepcopy(self.external_event),
                "shelter_active": self.shelter_active,
            }

    def set_privacy(self, share_behavioral: bool) -> dict[str, bool]:
        """Actualiza la preferencia de privacidad conductual para informes SBAR."""
        with self._lock:
            self.share_behavioral = bool(share_behavioral)
            return {"share_behavioral": self.share_behavioral}

    def submit_checkin(
        self,
        req: CheckInRequest | Mapping[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Registra un check-in conductual asociando el último CO₂ disponible (si no es null)."""
        parsed = req if isinstance(req, CheckInRequest) else CheckInRequest(**req)
        with self._lock:
            latest = self.history[-1] if self.history else None
            co2_mmhg = latest.co2 if (latest is not None and latest.co2 is not None) else None
            return self.coach.record_checkin(
                reaction_ms=parsed.reaction_ms,
                false_starts=parsed.false_starts,
                lapses=parsed.lapses,
                sleep_hours=parsed.sleep_hours,
                mood=parsed.mood,
                source=parsed.source,
                co2_mmhg=co2_mmhg,
                now=now,
            )

    def complete_routine(self, routine_id: str, now: datetime | None = None) -> dict[str, Any]:
        """Marca una rutina como completada en el Coach de participación."""
        with self._lock:
            return self.coach.complete_routine(routine_id, now=now)

    def trends(self, window_s: int = 3600, now: datetime | None = None) -> dict[str, Any]:
        """Devuelve resumen y serie de tendencias en la ventana solicitada (sin rellenar faltantes con 0)."""
        if window_s <= 0:
            raise ValueError("window_s debe ser mayor que 0.")
        current = _normalize_now(now)
        cutoff = current - timedelta(seconds=window_s)
        with self._lock:
            combined = self._combined_history()
            window_samples = [
                item
                for item in combined
                if cutoff <= item.measured_at <= current
            ]

        signal_names = (
            "hr",
            "rr",
            "co2",
            "dose_rate",
            "spo2",
            "bp_sys",
            "bp_dia",
            "temp_c",
            "hydration_pct",
        )
        signals_summary: dict[str, dict[str, Any]] = {}
        for name in signal_names:
            values = [
                float(getattr(item, name))
                for item in window_samples
                if getattr(item, name) is not None
            ]
            if values:
                signals_summary[name] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": round(statistics.fmean(values), 3),
                    "latest": values[-1],
                }
            else:
                signals_summary[name] = {
                    "count": 0,
                    "min": None,
                    "max": None,
                    "mean": None,
                    "latest": None,
                }

        bucket_total = max(1, math.ceil(window_s / 5.0))
        buckets = {
            min(bucket_total - 1, max(0, int((current - item.measured_at).total_seconds() // 5)))
            for item in window_samples
        }
        coverage_pct = round(min(100.0, (len(buckets) / bucket_total) * 100.0), 2)

        return {
            "window_s": window_s,
            "from": cutoff.isoformat(),
            "to": current.isoformat(),
            "sample_count": len(window_samples),
            "coverage_pct": coverage_pct,
            "signals": signals_summary,
            "points": [item.model_dump(mode="json") for item in window_samples],
        }

    def state(self, now: datetime | None = None) -> dict[str, Any]:
        current = _normalize_now(now)
        stale_seconds = get_param("stale_seconds")
        with self._lock:
            latest = self.history[-1] if self.history else None
            age = max(0.0, (current - latest.measured_at).total_seconds()) if latest else None
            forecast, pattern, assessment = self._evaluate(current)
            co2_sensitivity = self.compute_co2_sensitivity()
            projections = self.compute_projections(now=current)
            questions = self._build_questions(current, assessment)
            ml_status = pattern["status"] if not pattern["available"] else forecast["status"]
            ml_reason = pattern["reason"] if not pattern["available"] else forecast["reason"]
            acknowledged = bool(
                self._ack_revision is not None
                and self._ack_revision == self._revision
                and assessment["level"] in {"watch", "alert"}
            )
            return {
                "latest": latest.model_dump(mode="json") if latest else None,
                "history": [item.model_dump(mode="json") for item in self.history],
                "assessment": assessment,
                "dose_total": self.dose_total,
                "dose_complete": self.dose_complete and (age is None or age <= stale_seconds),
                "age_s": age,
                "events": list(self.events),
                "received_count": self.received_count,
                "environment": copy.deepcopy(self.environment_profile),
                "baseline": copy.deepcopy(self.baseline),
                "co2_sensitivity": co2_sensitivity,
                "projections": projections,
                "ml": {
                    "forecast": forecast,
                    "pattern": pattern,
                    "status": ml_status,
                    "reason": ml_reason,
                },
                "questions": questions,
                "coach": self.coach.state(current),
                "external_event": copy.deepcopy(self.external_event),
                "privacy": {"share_behavioral": self.share_behavioral},
                "shelter_active": self.shelter_active,
                "acknowledged": acknowledged,
                "rules_version": RULES_VERSION,
                "config_version": CONFIG_VERSION,
            }

    def report(
        self,
        share_behavioral: bool | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Genera el informe SBAR del episodio respetando el filtro de privacidad."""
        return build_episode_report(self.state(now), share_behavioral=share_behavioral)

    def acknowledge(self, now: datetime | None = None) -> dict[str, Any]:
        current = _normalize_now(now)
        with self._lock:
            assessment = self._assessment(current)
            if assessment["level"] not in {"watch", "alert"}:
                raise ConflictError("No hay una alerta vigente que reconocer.")
            if self._ack_revision == self._revision:
                return {
                    "accepted": True,
                    "duplicate": True,
                    "detail": "Ya reconocida; condición sin resolver.",
                }
            self._ack_revision = self._revision
            self._event("Alerta reconocida por el usuario; la condición continúa activa.", current)
            self.coach.record_ack(now=current)
            return {
                "accepted": True,
                "duplicate": False,
                "detail": "Reconocida; la condición continúa activa.",
            }
