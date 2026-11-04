"""Reglas explícitas de demo. No es un modelo clínico ni entrenado."""

from collections import deque
from datetime import datetime, timezone
from threading import RLock

from .contracts import Telemetry


METHOD = "Reglas de demostración v0.1 · sin modelo entrenado"
FORECAST_METHOD = "Persistencia a 60 s: conservar el último pulso válido"


def utc_now():
    return datetime.now(timezone.utc)


class ConflictError(ValueError):
    pass


class Engine:
    def __init__(self):
        self._lock = RLock()
        self.history = deque(maxlen=120)
        self.events = deque(maxlen=50)
        self._seen = {}
        self.dose_total = 0.0
        self.dose_complete = True
        self.received_count = 0
        self._last_pattern = None
        self._revision = 0
        self._ack_revision = None

    def _event(self, text, now):
        self.events.append({"at": now.isoformat(), "text": text})

    def ingest(self, sample: Telemetry, now=None):
        now = now or utc_now()
        payload = sample.model_dump(mode="json")
        with self._lock:
            if sample.sample_id in self._seen:
                if self._seen[sample.sample_id] != payload:
                    raise ConflictError("sample_id ya existe con otro contenido.")
                return {"accepted": True, "duplicate": True}
            if (sample.measured_at - now).total_seconds() > 5:
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

            self.history.append(sample)
            self._seen[sample.sample_id] = payload
            self.received_count += 1
            assessment = self._assessment(now)
            pattern = (assessment["level"], assessment["title"], sample.source)
            if pattern != self._last_pattern:
                self._revision += 1
                self._last_pattern = pattern
                self._event(assessment["title"], now)
            return {"accepted": True, "duplicate": False}

    def _assessment(self, now):
        result = {
            "level": "unknown",
            "title": "Esperando telemetría",
            "evidence": ["La API está lista; todavía no hay mediciones."],
            "next_step": "Iniciar el simulador o la reproducción BIDMC.",
            "method": METHOD,
            "forecast_hr": None,
            "forecast_method": FORECAST_METHOD,
        }
        if not self.history:
            return result
        sample = self.history[-1]
        age = max(0, (now - sample.measured_at).total_seconds())
        if age > 5:
            result.update(
                title="Telemetría desactualizada",
                evidence=[f"Última medición hace {age:.0f} s; el límite de demo es 5 s."],
                next_step="Revisar conexión con la pasarela. No interpretar el último valor como actual.",
            )
            return result

        if sample.hr is not None:
            result["forecast_hr"] = sample.hr
        if sample.hr is None or sample.rr is None:
            absent = ", ".join(
                name for name, value in (("pulso", sample.hr), ("respiración", sample.rr))
                if value is None
            )
            result.update(
                title="Evaluación fisiológica incompleta",
                evidence=[f"Sin lectura de {absent}; no se reemplaza por cero."],
                next_step="Revisar señal y conexión del sensor.",
            )
        elif sample.source == "bidmc":
            result.update(
                title="Registro real · contexto limitado",
                evidence=[
                    f"Pulso {sample.hr:.0f} bpm · respiración {sample.rr:.0f}/min.",
                    "BIDMC: registro clínico terrestre, sin CO₂, dosímetro ni actividad conocida.",
                    "Reproducción histórica; no se asigna una hipótesis espacial.",
                ],
                next_step="Explorar las señales reales; agregar contexto antes de interpretar.",
            )
        elif sample.co2 is not None and sample.co2 >= 4 and sample.rr >= 23:
            result.update(
                level="alert",
                title="Hipótesis: cambio respiratorio y ambiental",
                evidence=[
                    f"CO₂ {sample.co2:.2f} mmHg y respiración {sample.rr:.0f}/min.",
                    "Coinciden dos cambios del escenario; no demuestra causalidad.",
                    "Límites de demo: CO₂ ≥ 4 mmHg y respiración ≥ 23/min.",
                ],
                next_step="Verificar sensores y contexto de cabina; registrar la observación.",
            )
        elif sample.activity == "exercise":
            result.update(
                level="normal",
                title="Patrón compatible con actividad simulada",
                evidence=[
                    f"Actividad declarada: ejercicio · pulso {sample.hr:.0f} bpm.",
                    "El contexto de actividad explica la interpretación de esta regla de demo.",
                ],
                next_step="Observar la tendencia al cambiar a recuperación.",
            )
        elif sample.activity == "unknown":
            result.update(
                title="Actividad desconocida",
                evidence=["Hay señales fisiológicas, pero falta el contexto de actividad."],
                next_step="Confirmar la actividad antes de interpretar el pulso.",
            )
        elif sample.hr >= 105:
            result.update(
                level="watch",
                title="Hipótesis: recuperación o pulso fuera del patrón de demo",
                evidence=[
                    f"Pulso {sample.hr:.0f} bpm sin actividad de ejercicio declarada.",
                    "El umbral de demostración es 105 bpm; no es una referencia personal.",
                    "Alternativas: cambio de actividad, variación individual o señal incorrecta.",
                ],
                next_step="Confirmar actividad y calidad; observar si el pulso disminuye.",
            )
        else:
            result.update(
                level="normal",
                title="Sin cambios señalados por las reglas de demo",
                evidence=[
                    f"Pulso {sample.hr:.0f} bpm · respiración {sample.rr:.0f}/min.",
                    "Esta comprobación no equivale a una evaluación completa de salud.",
                ],
                next_step="Continuar observando las señales y su contexto.",
            )

        # La tasa ambiental se interpreta por separado de las señales fisiológicas.
        if sample.dose_rate is not None and sample.dose_rate >= 40:
            physiology = result["title"]
            result.update(
                level="alert",
                title="Radiación simulada · revisar exposición",
                evidence=[
                    f"Dosímetro simulado: {sample.dose_rate:.1f} μSv/h; umbral de demo: 40 μSv/h.",
                    f"Evaluación fisiológica separada: {physiology}.",
                    "La tasa no permite diagnosticar una lesión ni confirma un evento solar real.",
                ],
                next_step="Probar el refugio del simulador y observar la tasa y el acumulado.",
            )
        return result

    def state(self, now=None):
        now = now or utc_now()
        with self._lock:
            latest = self.history[-1] if self.history else None
            age = max(0, (now - latest.measured_at).total_seconds()) if latest else None
            return {
                "latest": latest.model_dump(mode="json") if latest else None,
                "history": [item.model_dump(mode="json") for item in self.history],
                "assessment": self._assessment(now),
                "dose_total": self.dose_total,
                "dose_complete": self.dose_complete and (age is None or age <= 5),
                "age_s": age,
                "events": list(self.events),
                "received_count": self.received_count,
            }

    def acknowledge(self, now=None):
        now = now or utc_now()
        with self._lock:
            assessment = self._assessment(now)
            if assessment["level"] not in {"watch", "alert"}:
                raise ConflictError("No hay una alerta vigente que reconocer.")
            if self._ack_revision == self._revision:
                return {"accepted": True, "duplicate": True, "detail": "Ya reconocida; condición sin resolver."}
            self._ack_revision = self._revision
            self._event("Alerta reconocida por el usuario; la condición continúa activa.", now)
            return {"accepted": True, "duplicate": False, "detail": "Reconocida; la condición continúa activa."}
