"""NASA CCMC DONKI historical solar context and compressed demo timeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_DONKI_PATH = Path(__file__).resolve().parents[2] / "data" / "donki" / "evento.json"

SOLAR_PHASES: tuple[str, ...] = ("watch", "arrival", "peak", "decay")

_BASE_RATES_USVH: dict[str, float] = {
    "watch": 1.2,
    "arrival": 42.0,
    "peak": 85.0,
    "decay": 18.0,
}

_SOURCE_LABEL = "NASA CCMC DONKI (local backup)"
_HISTORICAL_NOTE = (
    "Historical SEP event from May 11, 2024; external context, not personal dosimetry."
)
_TIMELINE_LABEL = "Compressed demo timeline"


def load_donki_event(path: str | Path | None = None) -> dict[str, Any]:
    """Load and normalize the NASA DONKI SEP event from a local JSON backup."""
    event_path = Path(path) if path is not None else DEFAULT_DONKI_PATH
    raw = json.loads(event_path.read_text(encoding="utf-8"))

    if isinstance(raw, list):
        if not raw:
            raise ValueError(f"DONKI file '{event_path}' is empty.")
        raw = raw[0]
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid format in DONKI file '{event_path}'.")

    raw_instruments = raw.get("instruments") or []
    instruments = [
        item["displayName"] if isinstance(item, dict) and "displayName" in item else str(item)
        for item in raw_instruments
    ]

    raw_linked = raw.get("linkedEvents") or raw.get("linked_events") or []
    linked_events = [
        item["activityID"] if isinstance(item, dict) and "activityID" in item else str(item)
        for item in raw_linked
    ]

    raw_notifications = raw.get("sentNotifications") or raw.get("notifications") or []
    notifications = [
        {
            "message_id": note.get("messageID") or note.get("message_id"),
            "issued_at": note.get("messageIssueTime") or note.get("issued_at"),
            "url": note.get("messageURL") or note.get("url"),
        }
        for note in raw_notifications
        if isinstance(note, dict)
    ]

    return {
        "sep_id": raw.get("sepID") or raw.get("sep_id"),
        "event_time": raw.get("eventTime") or raw.get("event_time"),
        "instruments": instruments,
        "link": raw.get("link"),
        "linked_events": linked_events,
        "notifications": notifications,
        "submission_time": raw.get("submissionTime") or raw.get("submission_time"),
        "version_id": raw.get("versionId") or raw.get("version_id"),
        "source": _SOURCE_LABEL,
        "historical_note": _HISTORICAL_NOTE,
    }


def phase_at_elapsed(elapsed_s: float) -> str:
    """Return the solar storm phase in the compressed demo timeline."""
    if elapsed_s < 15.0:
        return "watch"
    if elapsed_s < 30.0:
        return "arrival"
    if elapsed_s < 50.0:
        return "peak"
    return "decay"


def get_solar_context(
    phase: str = "watch",
    *,
    shelter: bool = False,
    shelter_factor: float = 0.15,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Build phase-based solar context separating historical event from simulated rate."""
    normalized_phase = phase.strip().lower()
    if normalized_phase not in SOLAR_PHASES:
        raise ValueError(
            f"Unknown solar phase: {phase!r}. Valid phases: {', '.join(SOLAR_PHASES)}."
        )
    if shelter_factor < 0 or shelter_factor > 1:
        raise ValueError("shelter_factor must be between 0 and 1.")

    event = load_donki_event(path)
    base_rate = _BASE_RATES_USVH[normalized_phase]
    simulated_rate = round(base_rate * shelter_factor, 4) if shelter else base_rate

    if normalized_phase == "watch":
        level = "watch"
        title = "Solar event under observation (NASA DONKI context)"
        activates_checklist = True
        next_step = "Review shelter checklist before estimated arrival (simulated scenario)."
    elif normalized_phase == "arrival":
        level = "watch" if shelter else "alert"
        title = "Estimated solar particle arrival (simulated scenario)"
        activates_checklist = True
        next_step = (
            "Remain in shelter and monitor the simulated dosimeter rate."
            if shelter
            else "Activate shelter protocol and monitor the simulated dosimeter."
        )
    elif normalized_phase == "peak":
        level = "watch" if shelter else "alert"
        title = "Simulated solar event peak (NASA DONKI context)"
        activates_checklist = True
        next_step = (
            "Remain in shelter until a sustained rate decrease is observed."
            if shelter
            else "Move to a protected area and monitor simulated accumulated dose."
        )
    else:
        level = "watch"
        title = "Gradual solar event decay (simulated scenario)"
        activates_checklist = False
        next_step = "Confirm rate stability before concluding sheltering."

    return {
        "phase": normalized_phase,
        "level": level,
        "title": title,
        "activates_shelter_checklist": activates_checklist,
        "next_step": next_step,
        "simulated_dose_rate_usvh": simulated_rate,
        "base_dose_rate_usvh": base_rate,
        "shelter": shelter,
        "shelter_factor": shelter_factor,
        "timeline_label": _TIMELINE_LABEL,
        "dosimetry_source": "Local simulated dosimeter (scenario independent from DONKI)",
        **event,
        "event": event,
    }
