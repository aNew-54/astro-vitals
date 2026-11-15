"""Window feature extraction and local ML inference for ASTRO-VITALS."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

import joblib
import numpy as np

_REPO_MODELS_ROOT = Path(__file__).resolve().parents[2] / "ASTRO-VITALS-AI-Modelos-v1"
_PARENT_MODELS_ROOT = Path(__file__).resolve().parents[3] / "ASTRO-VITALS-AI-Modelos-v1"
DEFAULT_MODELS_ROOT = _REPO_MODELS_ROOT if _REPO_MODELS_ROOT.is_dir() else _PARENT_MODELS_ROOT
FORECAST_MODEL_VERSION = "heart_rate_forecast/colab-v1"
PATTERN_MODEL_VERSION = "physiological_patterns/colab-v1"
PERSISTENCE_METHOD = "60 s persistence: keep the last valid pulse"
HYPOTHESIS_PREFIX = "Orientative hypothesis (simulated scenario)"
STALE_LIMIT_S = 5.0
DEFAULT_PATTERN_THRESHOLD = 0.6


def _is_valid_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _get_field(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _parse_timestamp(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, str):
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError(f"Unsupported timestamp type: {type(value)!r}")
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _contiguous_source_block(items: list[Any]) -> list[Any]:
    latest_source = _get_field(items[-1], "source")
    block: list[Any] = []
    for item in reversed(items):
        if _get_field(item, "source") != latest_source:
            break
        block.append(item)
    block.reverse()
    return block


def _normalize_samples(
    samples: Mapping[int, Mapping[str, Any]] | Iterable[Any] | None,
    now: int | datetime | str | None,
    channels: tuple[str, ...],
) -> tuple[dict[int, dict[str, float | None]] | None, int | None, str | None]:
    if samples is None:
        return None, None, "sin_datos"

    if isinstance(samples, Mapping):
        if not samples:
            return None, None, "sin_datos"
        if now is None:
            t = max(samples)
        elif isinstance(now, int) and not isinstance(now, bool):
            t = now
        else:
            raise TypeError("In dict[int, dict] mode, 'now' must be int or None.")
        samples_by_sec: dict[int, dict[str, float | None]] = {}
        for sec, row in samples.items():
            if not isinstance(sec, int) or isinstance(sec, bool) or sec > t:
                continue
            samples_by_sec[sec] = {
                ch: float(val) if _is_valid_number(val) else None
                for ch in channels
                for val in (_get_field(row, ch),)
            }
        if not samples_by_sec:
            return None, None, "sin_datos"
        return samples_by_sec, t, None

    if isinstance(samples, (str, bytes)):
        raise TypeError("'samples' must be dict[int, dict] or a telemetry sequence.")

    items = list(samples)
    if not items:
        return None, None, "sin_datos"

    block = _contiguous_source_block(items)
    latest_ts = _parse_timestamp(_get_field(block[-1], "measured_at"))
    now_ts = latest_ts if now is None else _parse_timestamp(now)
    if (now_ts - latest_ts).total_seconds() > STALE_LIMIT_S:
        return None, None, "datos_antiguos"

    by_sec_meta: dict[int, tuple[datetime, int, dict[str, float | None]]] = {}
    for idx, item in enumerate(block):
        sample_ts = _parse_timestamp(_get_field(item, "measured_at"))
        sec = round((sample_ts - latest_ts).total_seconds())
        existing = by_sec_meta.get(sec)
        if existing is None or (sample_ts, idx) >= (existing[0], existing[1]):
            row = {
                ch: float(val) if _is_valid_number(val) else None
                for ch in channels
                for val in (_get_field(item, ch),)
            }
            by_sec_meta[sec] = (sample_ts, idx, row)

    samples_by_sec = {
        sec: payload for sec, (_, _, payload) in by_sec_meta.items() if sec <= 0
    }
    if not samples_by_sec:
        return None, None, "sin_datos"
    return samples_by_sec, 0, None


def extract_window_features(
    samples: Mapping[int, Mapping[str, Any]] | Iterable[Any] | None,
    now: int | datetime | str | None = None,
    channels: tuple[str, ...] = ("hr", "rr"),
) -> tuple[dict[str, float] | None, str | None]:
    """Compute causal 30 s and 120 s window features matching preparar_bidmc.features_at."""
    samples_by_sec, t, norm_error = _normalize_samples(samples, now, channels)
    if norm_error is not None or samples_by_sec is None or t is None:
        return None, norm_error or "sin_datos"

    relevant_secs = sorted(samples_by_sec)
    window_secs = [sec for sec in relevant_secs if sec >= t - 119]
    check_secs = window_secs or relevant_secs

    for signal in channels:
        if all(samples_by_sec[sec].get(signal) is None for sec in check_secs):
            return None, f"falta_{signal}"

    if t - relevant_secs[0] < 119:
        return None, "calibrando"

    features: dict[str, float] = {}
    for signal in channels:
        for width in (30, 120):
            points = [
                (sec, samples_by_sec[sec][signal])
                for sec in range(t - width + 1, t + 1)
                if sec in samples_by_sec and samples_by_sec[sec].get(signal) is not None
            ]
            if len(points) < math.ceil(0.8 * width) or t - points[-1][0] > STALE_LIMIT_S:
                if width == 120 and len(relevant_secs) < 96:
                    return None, "calibrando"
                return None, "cobertura_insuficiente"

            times, values = zip(*points)
            center_t = fmean(times)
            mean = fmean(values)
            denom = sum((sec - center_t) ** 2 for sec in times)
            slope = (
                sum((sec - center_t) * (val - mean) for sec, val in points) / denom
                if denom
                else 0.0
            )
            sd = pstdev(values)
            features[f"{signal}_last"] = values[-1]
            for stat, value in (("mean", mean), ("sd", sd), ("slope", slope)):
                features[f"{signal}_{stat}_{width}s"] = round(value, 8)

    return features, None


def _persistence_hr(
    samples: Mapping[int, Mapping[str, Any]] | Iterable[Any] | None,
    now: int | datetime | str | None,
) -> float | None:
    if samples is None or isinstance(samples, (str, bytes)):
        return None

    if isinstance(samples, Mapping):
        if not samples:
            return None
        t = max(samples) if now is None else now
        if not isinstance(t, int) or isinstance(t, bool):
            return None
        relevant = [sec for sec in samples if isinstance(sec, int) and not isinstance(sec, bool) and sec <= t]
        if not relevant:
            return None
        last_sec = max(relevant)
        if t - last_sec > STALE_LIMIT_S:
            return None
        val = _get_field(samples[last_sec], "hr")
        return float(val) if _is_valid_number(val) else None

    items = list(samples)
    if not items:
        return None
    latest = items[-1]
    latest_ts = _parse_timestamp(_get_field(latest, "measured_at"))
    now_ts = latest_ts if now is None else _parse_timestamp(now)
    if (now_ts - latest_ts).total_seconds() > STALE_LIMIT_S:
        return None
    val = _get_field(latest, "hr")
    return float(val) if _is_valid_number(val) else None


def _map_window_status(reason: str | None) -> str:
    if reason == "datos_antiguos":
        return "datos_antiguos"
    if reason == "calibrando":
        return "calibrando"
    return "no_evaluable"


class ModelRunner:
    """Loads and runs the offline-trained heart rate forecast and pattern models."""

    ACTIVITY_CODES = {"rest": 0, "exercise": 1, "recovery": 2}
    PATTERN_HYPOTHESES = {
        "baseline_expected": (
            f"{HYPOTHESIS_PREFIX}: signals compatible with stable rest "
            "relative to the personal baseline."
        ),
        "activity_expected": (
            f"{HYPOTHESIS_PREFIX}: physiological response compatible with the "
            "declared activity."
        ),
        "persistent_recovery_deviation": (
            f"{HYPOTHESIS_PREFIX}: persistent deviation during recovery "
            "relative to the personal baseline."
        ),
        "combined_cabin_physiology_pattern": (
            f"{HYPOTHESIS_PREFIX}: combined pattern of cabin CO₂ change "
            "and physiological response."
        ),
    }

    def __init__(self, models_root: Path | str | None = None):
        self.models_root = Path(models_root) if models_root is not None else DEFAULT_MODELS_ROOT
        self.forecast_error: str | None = None
        self.pattern_error: str | None = None

        self._forecast_model: Any = None
        self._forecast_features: list[str] = []
        self._forecast_radius: float | None = None
        self._forecast_version: str = FORECAST_MODEL_VERSION

        self._pattern_model: Any = None
        self._pattern_features: list[str] = []
        self._pattern_threshold: float = DEFAULT_PATTERN_THRESHOLD
        self._pattern_version: str = PATTERN_MODEL_VERSION

        self._load_forecast()
        self._load_pattern()

    @staticmethod
    def _read_artifact_triplet(model_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        manifest_path = model_dir / "manifest.json"
        metrics_path = model_dir / "metrics.json"
        bundle_path = model_dir / "model.joblib"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        bundle = joblib.load(bundle_path)
        if not isinstance(bundle, Mapping) or "model" not in bundle:
            raise ValueError(f"Invalid artifact at {bundle_path}")
        return bundle, manifest, metrics

    def _load_forecast(self) -> None:
        model_dir = self.models_root / "heart_rate_forecast" / "colab-v1"
        try:
            bundle, manifest, metrics = self._read_artifact_triplet(model_dir)
            features = manifest.get("feature_order") or bundle.get("features")
            if not features:
                raise ValueError("Missing feature_order in heart_rate_forecast.")
            radius = bundle.get("interval_radius")
            if radius is None:
                radius = metrics.get("empirical_interval", {}).get("validation_absolute_error_q90_bpm")
            if radius is None:
                raise ValueError("Missing interval_radius in heart_rate_forecast.")
            self._forecast_model = bundle["model"]
            self._forecast_features = [str(name) for name in features]
            self._forecast_radius = float(radius)
            name = manifest.get("name", "heart_rate_forecast")
            version = manifest.get("version", "colab-v1")
            self._forecast_version = f"{name}/{version}"
        except Exception as exc:
            self._forecast_model = None
            self.forecast_error = str(exc)

    def _load_pattern(self) -> None:
        model_dir = self.models_root / "physiological_patterns" / "colab-v1"
        try:
            bundle, manifest, metrics = self._read_artifact_triplet(model_dir)
            features = manifest.get("feature_order") or bundle.get("features")
            if not features:
                raise ValueError("Missing feature_order in physiological_patterns.")
            threshold = metrics.get("uncertainty", {}).get("selected_threshold")
            if threshold is None:
                threshold = bundle.get("threshold")
            if threshold is None:
                threshold = DEFAULT_PATTERN_THRESHOLD
            self._pattern_model = bundle["model"]
            self._pattern_features = [str(name) for name in features]
            self._pattern_threshold = float(threshold)
            name = manifest.get("name", "physiological_patterns")
            version = manifest.get("version", "colab-v1")
            self._pattern_version = f"{name}/{version}"
        except Exception as exc:
            self._pattern_model = None
            self.pattern_error = str(exc)

    def _forecast_unavailable(
        self,
        status: str,
        reason: str | None,
        persistence_hr: float | None,
    ) -> dict[str, Any]:
        radius = round(self._forecast_radius, 2) if self._forecast_radius is not None else None
        method = PERSISTENCE_METHOD if persistence_hr is not None else "No forecast available"
        return {
            "available": False,
            "status": status,
            "reason": reason,
            "forecast_hr": persistence_hr,
            "ml_forecast_hr": None,
            "persistence_hr": persistence_hr,
            "interval_radius_bpm": radius,
            "horizon_s": 60,
            "method": method,
            "model_version": self._forecast_version,
        }

    def predict_forecast(
        self,
        samples: Mapping[int, Mapping[str, Any]] | Iterable[Any] | None,
        now: int | datetime | str | None = None,
    ) -> dict[str, Any]:
        """Predict +60 s heart rate when the 120 s window is valid, else fall back to persistence."""
        persistence_hr = _persistence_hr(samples, now)
        if self._forecast_model is None:
            return self._forecast_unavailable("no_evaluable", "modelo_no_disponible", persistence_hr)

        features, reason = extract_window_features(samples, now=now, channels=("hr", "rr"))
        if features is None:
            return self._forecast_unavailable(_map_window_status(reason), reason, persistence_hr)

        vector = np.asarray([[float(features[name]) for name in self._forecast_features]], dtype=float)
        ml_pred = round(float(self._forecast_model.predict(vector)[0]), 2)
        radius = round(self._forecast_radius, 2) if self._forecast_radius is not None else None
        return {
            "available": True,
            "status": "ok",
            "reason": None,
            "forecast_hr": ml_pred,
            "ml_forecast_hr": ml_pred,
            "persistence_hr": persistence_hr,
            "interval_radius_bpm": radius,
            "horizon_s": 60,
            "method": (
                f"{HYPOTHESIS_PREFIX}: RandomForest +60 s ({self._forecast_version})"
            ),
            "model_version": self._forecast_version,
        }

    def _pattern_abstain(
        self,
        status: str,
        reason: str | None,
        hypothesis: str,
        score: float | None = None,
    ) -> dict[str, Any]:
        return {
            "available": False,
            "status": status,
            "reason": reason,
            "pattern": None,
            "score": score,
            "threshold": self._pattern_threshold,
            "probabilities": None,
            "hypothesis": hypothesis,
            "model_version": self._pattern_version,
        }

    def predict_pattern(
        self,
        samples: Mapping[int, Mapping[str, Any]] | Iterable[Any] | None,
        now: int | datetime | str | None = None,
        baseline: Mapping[str, Any] | None = None,
        activity: str = "unknown",
        phase_duration_s: float | None = 0.0,
    ) -> dict[str, Any]:
        """Classify the 120 s physiological/cabin pattern or abstain cleanly with reason."""
        if self._pattern_model is None:
            return self._pattern_abstain(
                "no_evaluable",
                "modelo_no_disponible",
                f"{HYPOTHESIS_PREFIX}: pattern model not available.",
            )

        if activity not in self.ACTIVITY_CODES:
            return self._pattern_abstain(
                "no_evaluable",
                "actividad_desconocida",
                f"{HYPOTHESIS_PREFIX}: pattern not evaluable because the known activity is missing.",
            )

        if (
            not baseline
            or not _is_valid_number(baseline.get("hr"))
            or not _is_valid_number(baseline.get("rr"))
        ):
            return self._pattern_abstain(
                "calibrando",
                "sin_linea_base",
                f"{HYPOTHESIS_PREFIX}: calibrating personal baseline.",
            )

        features, reason = extract_window_features(samples, now=now, channels=("hr", "rr", "co2"))
        if features is None:
            status = _map_window_status(reason)
            return self._pattern_abstain(
                status,
                reason,
                f"{HYPOTHESIS_PREFIX}: {status} ({reason}).",
            )

        enriched = dict(features)
        enriched["activity"] = float(self.ACTIVITY_CODES[activity])
        enriched["phase_duration_s"] = float(phase_duration_s or 0.0)
        enriched["hr_delta"] = round(features["hr_last"] - float(baseline["hr"]), 5)
        enriched["rr_delta"] = round(features["rr_last"] - float(baseline["rr"]), 5)

        vector = np.asarray([[float(enriched[name]) for name in self._pattern_features]], dtype=float)
        proba = self._pattern_model.predict_proba(vector)[0]
        max_idx = int(np.argmax(proba))
        max_prob = float(proba[max_idx])
        pred_label = str(self._pattern_model.classes_[max_idx])

        if max_prob < self._pattern_threshold:
            return self._pattern_abstain(
                "no_evaluable",
                "confianza_insuficiente",
                f"{HYPOTHESIS_PREFIX}: abstention due to insufficient confidence.",
                score=round(max_prob, 4),
            )

        return {
            "available": True,
            "status": "ok",
            "reason": None,
            "pattern": pred_label,
            "score": round(max_prob, 4),
            "threshold": self._pattern_threshold,
            "probabilities": {
                str(cls): round(float(prob), 4)
                for cls, prob in zip(self._pattern_model.classes_, proba)
            },
            "hypothesis": self.PATTERN_HYPOTHESES.get(
                pred_label,
                f"{HYPOTHESIS_PREFIX}: classified pattern ({pred_label}).",
            ),
            "model_version": self._pattern_version,
        }
