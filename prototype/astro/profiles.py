"""Perfiles de entorno simulado para ajustar umbrales y tasas en ASTRO-VITALS."""

from __future__ import annotations

import copy
from typing import Any

PROFILES: dict[str, dict[str, Any]] = {
    "transit": {
        "id": "transit",
        "name": "Tránsito espacial",
        "description": "Módulo presurizado en trayecto de espacio profundo fuera de la magnetosfera.",
        "origin": "demo",
        "rest_targets": {
            "hr": 73.0,
            "rr": 14.5,
            "co2": 2.0,
            "dose_rate": 1.2,
        },
        "thresholds": {
            "hr_watch": 104.0,
            "co2_alert": 3.8,
            "rr_alert": 22.5,
            "dose_rate_alert": 30.0,
        },
        "co2_ramp_rate_mmhg_min": 0.8,
        "radiation_multiplier": 2.0,
        "help_text": "Hipótesis orientativa (escenario simulado): en tránsito profundo la exposición ambiental de base es mayor que en estación; vigilar tasa de dosis y ventilación del módulo.",
    },
    "station": {
        "id": "station",
        "name": "Estación orbital",
        "description": "Hábitat orbital de referencia con volumen amplio de cabina y protección geomagnética parcial.",
        "origin": "demo",
        "rest_targets": {
            "hr": 72.0,
            "rr": 14.0,
            "co2": 2.0,
            "dose_rate": 0.5,
        },
        "thresholds": {
            "hr_watch": 105.0,
            "co2_alert": 4.0,
            "rr_alert": 23.0,
            "dose_rate_alert": 40.0,
        },
        "co2_ramp_rate_mmhg_min": 0.6,
        "radiation_multiplier": 1.0,
        "help_text": "Hipótesis orientativa (escenario simulado): perfil base de estación orbital; comprobar actividad declarada, depuradores de CO₂ y cobertura del dosímetro simulado.",
    },
    "rover": {
        "id": "rover",
        "name": "Rover presurizado",
        "description": "Vehículo de exploración de cabina compacta con menor volumen de aire y mayor dinámica térmica.",
        "origin": "demo",
        "rest_targets": {
            "hr": 74.0,
            "rr": 15.0,
            "co2": 2.2,
            "dose_rate": 0.8,
        },
        "thresholds": {
            "hr_watch": 102.0,
            "co2_alert": 3.5,
            "rr_alert": 22.0,
            "dose_rate_alert": 35.0,
        },
        "co2_ramp_rate_mmhg_min": 1.2,
        "radiation_multiplier": 1.4,
        "help_text": "Hipótesis orientativa (escenario simulado): cabina reducida donde el CO₂ asciende con mayor rapidez que en estación; revisar depuración y pausas de actividad.",
    },
    "base": {
        "id": "base",
        "name": "Base superficial",
        "description": "Hábitat de superficie planetaria o lunar con gran volumen interior y exposición ambiental elevada en superficie.",
        "origin": "demo",
        "rest_targets": {
            "hr": 71.0,
            "rr": 14.0,
            "co2": 1.8,
            "dose_rate": 1.0,
        },
        "thresholds": {
            "hr_watch": 105.0,
            "co2_alert": 4.0,
            "rr_alert": 23.0,
            "dose_rate_alert": 25.0,
        },
        "co2_ramp_rate_mmhg_min": 0.45,
        "radiation_multiplier": 1.5,
        "help_text": "Hipótesis orientativa (escenario simulado): entorno de base con umbral estricto para tasa de dosis ambiental; priorizar verificación de refugio simulado ante picos solares.",
    },
}


def get_profile(profile_id: str = "station") -> dict[str, Any]:
    """Retorna una copia del perfil solicitado o lanza ValueError si no existe."""
    if profile_id not in PROFILES:
        raise ValueError(f"Perfil de entorno desconocido: {profile_id!r}")
    return copy.deepcopy(PROFILES[profile_id])


def list_profiles() -> list[dict[str, Any]]:
    """Retorna todos los perfiles de entorno disponibles en el prototipo."""
    return [copy.deepcopy(profile) for profile in PROFILES.values()]
