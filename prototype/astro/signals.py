"""Catálogo unificado de señales fisiológicas y ambientales de ASTRO-VITALS."""

from __future__ import annotations

from typing import Any

SIGNALS: dict[str, dict[str, Any]] = {
    "hr": {
        "key": "hr",
        "label": "Frecuencia cardíaca",
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
        "label": "Frecuencia respiratoria",
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
        "label": "CO₂ de cabina",
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
        "label": "Tasa de dosis",
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
        "label": "Saturación de oxígeno (SpO₂)",
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
        "label": "Presión arterial sistólica",
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
        "label": "Presión arterial diastólica",
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
        "label": "Temperatura corporal",
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
        "label": "Hidratación",
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
    """Retorna una copia de la especificación de la señal o None si no existe."""
    spec = SIGNALS.get(key)
    return dict(spec) if spec is not None else None


def list_signals() -> list[dict[str, Any]]:
    """Retorna la lista de especificaciones de todas las señales registradas."""
    return [dict(spec) for spec in SIGNALS.values()]
