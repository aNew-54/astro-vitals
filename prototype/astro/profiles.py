"""Simulated environment profiles for tuning thresholds and rates in ASTRO-VITALS."""

from __future__ import annotations

import copy
from typing import Any

PROFILES: dict[str, dict[str, Any]] = {
    "transit": {
        "id": "transit",
        "name": "Deep-space transit",
        "description": "Pressurized module on a deep-space trajectory outside the magnetosphere.",
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
        "help_text": "Guidance hypothesis (simulated scenario): in deep-space transit the baseline environmental exposure is higher than in station; monitor dose rate and module ventilation.",
    },
    "station": {
        "id": "station",
        "name": "Orbital station",
        "description": "Reference orbital habitat with larger cabin volume and partial geomagnetic protection.",
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
        "help_text": "Guidance hypothesis (simulated scenario): baseline orbital-station profile; verify declared activity, CO₂ scrubbers, and simulated dosimeter coverage.",
    },
    "rover": {
        "id": "rover",
        "name": "Pressurized rover",
        "description": "Exploration vehicle with compact cabin volume and higher thermal dynamics.",
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
        "help_text": "Guidance hypothesis (simulated scenario): reduced cabin volume where CO₂ rises faster than in station; review scrubbing and activity breaks.",
    },
    "base": {
        "id": "base",
        "name": "Surface base",
        "description": "Planetary or lunar surface habitat with large interior volume and elevated surface environmental exposure.",
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
        "help_text": "Guidance hypothesis (simulated scenario): base environment with a strict threshold for environmental dose rate; prioritize simulated shelter checks during solar spikes.",
    },
}


def get_profile(profile_id: str = "station") -> dict[str, Any]:
    """Return a copy of the requested profile or raise ValueError if it does not exist."""
    if profile_id not in PROFILES:
        raise ValueError(f"Unknown environment profile: {profile_id!r}")
    return copy.deepcopy(PROFILES[profile_id])


def list_profiles() -> list[dict[str, Any]]:
    """Return all available environment profiles in the prototype."""
    return [copy.deepcopy(profile) for profile in PROFILES.values()]
