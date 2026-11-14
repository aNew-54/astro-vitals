"""Contexto solar histórico NASA CCMC DONKI y línea de tiempo comprimida de demo."""

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

_SOURCE_LABEL = "NASA CCMC DONKI (respaldo local)"
_HISTORICAL_NOTE = (
    "Evento histórico SEP del 11 de mayo de 2024; contexto externo, no dosimetría personal."
)
_TIMELINE_LABEL = "Línea de tiempo comprimida de demostración"


def load_donki_event(path: str | Path | None = None) -> dict[str, Any]:
    """Carga y normaliza el evento SEP de NASA DONKI desde respaldo JSON local."""
    event_path = Path(path) if path is not None else DEFAULT_DONKI_PATH
    raw = json.loads(event_path.read_text(encoding="utf-8"))

    if isinstance(raw, list):
        if not raw:
            raise ValueError(f"El archivo DONKI '{event_path}' está vacío.")
        raw = raw[0]
    if not isinstance(raw, dict):
        raise ValueError(f"Formato inválido en el archivo DONKI '{event_path}'.")

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
    """Devuelve la fase de la tormenta solar en la línea de tiempo comprimida de demo."""
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
    """Construye el contexto solar por fase separando evento histórico de tasa simulada."""
    normalized_phase = phase.strip().lower()
    if normalized_phase not in SOLAR_PHASES:
        raise ValueError(
            f"Fase solar desconocida: {phase!r}. Fases válidas: {', '.join(SOLAR_PHASES)}."
        )
    if shelter_factor < 0 or shelter_factor > 1:
        raise ValueError("shelter_factor debe estar entre 0 y 1.")

    event = load_donki_event(path)
    base_rate = _BASE_RATES_USVH[normalized_phase]
    simulated_rate = round(base_rate * shelter_factor, 4) if shelter else base_rate

    if normalized_phase == "watch":
        level = "watch"
        title = "Evento solar en observación (contexto NASA DONKI)"
        activates_checklist = True
        next_step = "Revisar lista de refugio antes de la llegada estimada (escenario simulado)."
    elif normalized_phase == "arrival":
        level = "watch" if shelter else "alert"
        title = "Llegada estimada de partículas solares (escenario simulado)"
        activates_checklist = True
        next_step = (
            "Mantener refugio y vigilar tasa del dosímetro simulado."
            if shelter
            else "Activar protocolo de refugio y vigilar el dosímetro simulado."
        )
    elif normalized_phase == "peak":
        level = "watch" if shelter else "alert"
        title = "Pico de evento solar simulado (contexto NASA DONKI)"
        activates_checklist = True
        next_step = (
            "Permanecer en refugio hasta observar descenso sostenido de tasa."
            if shelter
            else "Trasladarse a zona protegida y vigilar dosis acumulada simulada."
        )
    else:
        level = "watch"
        title = "Descenso gradual de evento solar (escenario simulado)"
        activates_checklist = False
        next_step = "Confirmar estabilidad de tasa antes de concluir el resguardo."

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
        "dosimetry_source": "Dosímetro simulado local (escenario independiente de DONKI)",
        **event,
        "event": event,
    }
