"""Unified catalog of physiological and environmental signals for ASTRO-VITALS."""

from __future__ import annotations

from typing import Any

SIGNALS: dict[str, dict[str, Any]] = {
    "hr": {
        "key": "hr",
        "label": "Heart rate",
        "unit": "bpm",
        "min": 0.0,
        "max": 300.0,
        "plausible_range": (30.0, 220.0),
        "used_in_forecast": True,
        "used_in_classifier": True,
        "used_in_rules": True,
    },
    "rr": {
        "key": "rr",
        "label": "Respiratory rate",
        "unit": "resp/min",
        "min": 0.0,
        "max": 100.0,
        "plausible_range": (4.0, 60.0),
        "used_in_forecast": True,
        "used_in_classifier": True,
        "used_in_rules": True,
    },
    "co2": {
        "key": "co2",
        "label": "Cabin CO₂",
        "unit": "mmHg",
        "min": 0.0,
        "max": 100.0,
        "plausible_range": (0.0, 30.0),
        "used_in_forecast": False,
        "used_in_classifier": True,
        "used_in_rules": True,
    },
    "dose_rate": {
        "key": "dose_rate",
        "label": "Dose rate",
        "unit": "μSv/h",
        "min": 0.0,
        "max": 1000.0,
        "plausible_range": (0.0, 500.0),
        "used_in_forecast": False,
        "used_in_classifier": False,
        "used_in_rules": True,
    },
    "spo2": {
        "key": "spo2",
        "label": "Oxygen saturation (SpO₂)",
        "unit": "%",
        "min": 0.0,
        "max": 100.0,
        "plausible_range": (50.0, 100.0),
        "used_in_forecast": False,
        "used_in_classifier": False,
        "used_in_rules": False,
    },
    "bp_sys": {
        "key": "bp_sys",
        "label": "Systolic blood pressure",
        "unit": "mmHg",
        "min": 0.0,
        "max": 300.0,
        "plausible_range": (50.0, 250.0),
        "used_in_forecast": False,
        "used_in_classifier": False,
        "used_in_rules": False,
    },
    "bp_dia": {
        "key": "bp_dia",
        "label": "Diastolic blood pressure",
        "unit": "mmHg",
        "min": 0.0,
        "max": 200.0,
        "plausible_range": (30.0, 150.0),
        "used_in_forecast": False,
        "used_in_classifier": False,
        "used_in_rules": False,
    },
    "temp_c": {
        "key": "temp_c",
        "label": "Body temperature",
        "unit": "°C",
        "min": 25.0,
        "max": 45.0,
        "plausible_range": (32.0, 42.0),
        "used_in_forecast": False,
        "used_in_classifier": False,
        "used_in_rules": False,
    },
    "hydration_pct": {
        "key": "hydration_pct",
        "label": "Hydration",
        "unit": "%",
        "min": 0.0,
        "max": 100.0,
        "plausible_range": (20.0, 100.0),
        "used_in_forecast": False,
        "used_in_classifier": False,
        "used_in_rules": False,
    },
}


def get_signal(key: str) -> dict[str, Any] | None:
    """Return a copy of the signal specification, or None if it does not exist."""
    spec = SIGNALS.get(key)
    return dict(spec) if spec is not None else None


def list_signals() -> list[dict[str, Any]]:
    """Return the list of specifications for all registered signals."""
    return [dict(spec) for spec in SIGNALS.values()]
