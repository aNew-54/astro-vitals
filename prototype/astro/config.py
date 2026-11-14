"""Parámetros de configuración y procedencia para el prototipo ASTRO-VITALS."""

from __future__ import annotations

from typing import Any

CONFIG_VERSION = "v0.2-demo"

PARAMETERS: dict[str, dict[str, Any]] = {
    "co2_nasa_1h": {
        "value": 3.0,
        "unit": "mmHg",
        "origin": "nasa_ref",
        "note": "Promedio de 1 hora (NASA OCHMO-TB-004); síntomas de cefalea reportados desde ~2.3 mmHg.",
    },
    "hr_watch": {
        "value": 105.0,
        "unit": "bpm",
        "origin": "demo",
        "note": "Umbral de demostración para pulso fuera de ejercicio.",
    },
    "co2_alert": {
        "value": 4.0,
        "unit": "mmHg",
        "origin": "demo",
        "note": "Umbral instantáneo de demostración para CO₂.",
    },
    "rr_alert": {
        "value": 23.0,
        "unit": "resp/min",
        "origin": "demo",
        "note": "Umbral instantáneo de demostración para frecuencia respiratoria.",
    },
    "dose_rate_alert": {
        "value": 40.0,
        "unit": "μSv/h",
        "origin": "demo",
        "note": "Umbral de demostración para tasa de dosis.",
    },
    "shelter_factor": {
        "value": 0.15,
        "unit": "ratio",
        "origin": "demo",
        "note": "Factor de atenuación de tasa de dosis en refugio simulado.",
    },
    "stale_seconds": {
        "value": 5.0,
        "unit": "s",
        "origin": "demo",
        "note": "Edad máxima de telemetría antes de marcarla como desactualizada.",
    },
    "reaction_drift_ms": {
        "value": 60.0,
        "unit": "ms",
        "origin": "demo",
        "note": "Incremento sobre mediana base de reacción para señalar deriva orientativa.",
    },
    "baseline_window_s": {
        "value": 120.0,
        "unit": "s",
        "origin": "demo",
        "note": "Ventana de reposo válido para calibrar línea base personal.",
    },
}


def get_param(name: str) -> float:
    """Retorna el valor numérico de un parámetro configurado."""
    return float(PARAMETERS[name]["value"])


def get_parameter_spec(name: str) -> dict[str, Any]:
    """Retorna una copia completa de la especificación de un parámetro."""
    return dict(PARAMETERS[name])
