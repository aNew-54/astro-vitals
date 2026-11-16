"""Configuration parameters and provenance for the ASTRO-VITALS prototype."""

from __future__ import annotations

from typing import Any

CONFIG_VERSION = "v0.2-demo"

PARAMETERS: dict[str, dict[str, Any]] = {
    "co2_nasa_1h": {
        "value": 3.0,
        "unit": "mmHg",
        "origin": "nasa_ref",
        "note": "1-hour average (NASA OCHMO-TB-004); headache symptoms reported from ~2.3 mmHg.",
    },
    "hr_watch": {
        "value": 105.0,
        "unit": "bpm",
        "origin": "demo",
        "note": "Demo threshold for elevated pulse outside of exercise.",
    },
    "co2_alert": {
        "value": 4.0,
        "unit": "mmHg",
        "origin": "demo",
        "note": "Instantaneous demo threshold for CO₂.",
    },
    "rr_alert": {
        "value": 23.0,
        "unit": "resp/min",
        "origin": "demo",
        "note": "Instantaneous demo threshold for respiratory rate.",
    },
    "dose_rate_alert": {
        "value": 40.0,
        "unit": "μSv/h",
        "origin": "demo",
        "note": "Demo threshold for dose rate.",
    },
    "shelter_factor": {
        "value": 0.15,
        "unit": "fraction",
        "origin": "demo",
        "note": "Dose-rate attenuation factor in the simulated shelter.",
    },
    "freshness_s": {
        "value": 10.0,
        "unit": "s",
        "origin": "demo",
        "note": "Maximum telemetry age before marking it as stale.",
    },
    "reaction_drift_ms": {
        "value": 60.0,
        "unit": "ms",
        "origin": "demo",
        "note": "Increase over baseline reaction median to flag orientative drift.",
    },
    "reaction_baseline_rest_s": {
        "value": 300.0,
        "unit": "s",
        "origin": "demo",
        "note": "Valid rest window used to calibrate personal baseline.",
    },
}


def get_param(name: str) -> float:
    """Return the numeric value of a configured parameter."""
    return float(PARAMETERS[name]["value"])


def get_param_spec(name: str) -> dict[str, Any]:
    """Return a full copy of a parameter specification."""
    return dict(PARAMETERS[name])
