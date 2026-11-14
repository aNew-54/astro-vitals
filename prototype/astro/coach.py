"""Rutinas periódicas, gamificación por participación y check-in conductual no clínico."""

from __future__ import annotations

import copy
import math
import statistics
from datetime import datetime, timezone
from typing import Any

DEFAULT_ROUTINES: dict[str, dict[str, Any]] = {
    "checkin": {
        "id": "checkin",
        "title": "Check-in de alerta y reacción",
        "description": "Prueba breve de atención/reacción y registro voluntario de sueño y ánimo.",
        "interval_demo_s": 180,
        "active": True,
        "due": True,
        "completed_count": 0,
        "last_completed_at": None,
    },
    "hydration": {
        "id": "hydration",
        "title": "Hidratación de protocolo",
        "description": "Ingesta periódica de agua según protocolo operativo de cabina.",
        "interval_demo_s": 240,
        "active": True,
        "due": True,
        "completed_count": 0,
        "last_completed_at": None,
    },
    "exercise": {
        "id": "exercise",
        "title": "Contramedida física",
        "description": "Sesión programada de ejercicio preventivo durante el tramo simulado.",
        "interval_demo_s": 300,
        "active": True,
        "due": False,
        "completed_count": 0,
        "last_completed_at": None,
    },
    "co2_check": {
        "id": "co2_check",
        "title": "Revisión de sensor/depurador CO₂",
        "description": "Inspección visual de la lectura de CO₂ y del estado del depurador.",
        "interval_demo_s": 240,
        "active": True,
        "due": False,
        "completed_count": 0,
        "last_completed_at": None,
    },
    "shelter_checklist": {
        "id": "shelter_checklist",
        "title": "Lista de verificación de refugio",
        "description": "Protocolo de preparación de refugio activado ante evento solar simulado.",
        "interval_demo_s": 120,
        "active": False,
        "due": False,
        "completed_count": 0,
        "last_completed_at": None,
    },
}

SCORING_POLICY = (
    "Puntos y rachas otorgados únicamente por participación, "
    "nunca por resultados fisiológicos o velocidad."
)


def _normalize_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


class Coach:
    """Gestor de rutinas, puntos por participación y check-ins de reacción."""

    def __init__(self, now: datetime | None = None) -> None:
        self.points: int = 0
        self.streak: int = 0
        self.badges: list[str] = []
        self.routines: dict[str, dict[str, Any]] = copy.deepcopy(DEFAULT_ROUTINES)
        self.checkins: list[dict[str, Any]] = []
        self.reaction_baseline_ms: float | None = None
        self.demo_time_label: str = "Intervalo de demostración (escala acelerada)"
        self._baseline_samples: list[float] = []
        self._manual_baseline: bool = False
        self._uses_explicit_clock: bool = now is not None
        self._created_at: datetime = _normalize_now(now)

    def _unlock_badge(self, badge: str) -> None:
        if badge not in self.badges:
            self.badges.append(badge)

    def _require_routine(self, routine_id: str) -> dict[str, Any]:
        if routine_id not in self.routines:
            raise ValueError(f"Rutina desconocida: {routine_id}")
        return self.routines[routine_id]

    def refresh_due(self, now: datetime | None = None) -> dict[str, dict[str, Any]]:
        """Actualiza `due=True` en rutinas activas cuando transcurre `interval_demo_s`."""
        if now is not None:
            self._uses_explicit_clock = True
        current = _normalize_now(now)
        for routine in self.routines.values():
            if not routine["active"]:
                routine["due"] = False
                continue
            if routine["due"]:
                continue
            last_completed = routine["last_completed_at"]
            reference = (
                _normalize_now(datetime.fromisoformat(last_completed))
                if last_completed
                else self._created_at
            )
            elapsed = (current - reference).total_seconds()
            if elapsed >= routine["interval_demo_s"]:
                routine["due"] = True
        return copy.deepcopy(self.routines)

    def mark_due(self, routine_id: str, due: bool = True) -> dict[str, Any]:
        """Permite fijar manualmente el estado pendiente (`due`) de una rutina."""
        routine = self._require_routine(routine_id)
        routine["due"] = bool(due)
        return dict(routine)

    def complete_routine(self, routine_id: str, now: datetime | None = None) -> dict[str, Any]:
        """Registra participación en una rutina y otorga +10 puntos fijos."""
        routine = self._require_routine(routine_id)
        if now is not None:
            self._uses_explicit_clock = True
        current = _normalize_now(now)

        self.points += 10
        self.streak += 1
        routine["completed_count"] += 1
        routine["due"] = False
        routine["last_completed_at"] = current.isoformat()

        self._unlock_badge("primera_rutina")
        if self.streak >= 3:
            self._unlock_badge("racha_3")
        if routine_id == "shelter_checklist":
            self._unlock_badge("lista_refugio")

        summary = self.state(now=current if now is not None else None)
        summary["routine_id"] = routine_id
        summary["points_awarded"] = 10
        summary["routine"] = dict(routine)
        return summary

    def record_ack(self, now: datetime | None = None) -> dict[str, int]:
        """Otorga +5 puntos fijos por participación al reconocer una alerta."""
        if now is not None:
            self._uses_explicit_clock = True
        _normalize_now(now)
        self.points += 5
        return {"points": self.points, "streak": self.streak, "awarded": 5}

    def activate_solar_checklist(self, active: bool = True) -> dict[str, Any]:
        """Activa o desactiva la lista de verificación de refugio ante evento solar."""
        routine = self.routines["shelter_checklist"]
        routine["active"] = bool(active)
        routine["due"] = bool(active)
        return dict(routine)

    def set_reaction_baseline(self, baseline_ms: float) -> None:
        """Fija manualmente la línea base personal de tiempo de reacción (ms)."""
        if not _is_finite_number(baseline_ms) or baseline_ms <= 0:
            raise ValueError("La línea base de reacción debe ser finita y mayor que 0.")
        self.reaction_baseline_ms = float(baseline_ms)
        self._manual_baseline = True

    def record_checkin(
        self,
        reaction_ms: list[float],
        false_starts: int = 0,
        lapses: int | None = None,
        sleep_hours: float = 7.0,
        mood: int = 3,
        source: str = "declared",
        co2_mmhg: float | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Registra un check-in conductual y calcula deriva sin lenguaje clínico ni penalización."""
        if reaction_ms is None:
            raise ValueError("reaction_ms no puede estar vacío.")
        try:
            raw_rx = list(reaction_ms)
        except TypeError as exc:
            raise ValueError("reaction_ms debe ser una secuencia numérica no vacía.") from exc
        if not raw_rx:
            raise ValueError("reaction_ms no puede estar vacío.")
        cleaned_rx: list[float] = []
        for value in raw_rx:
            if not _is_finite_number(value) or value <= 0:
                raise ValueError("Todos los valores de reaction_ms deben ser finitos y mayores que 0.")
            cleaned_rx.append(float(value))

        if isinstance(false_starts, bool) or not isinstance(false_starts, int) or false_starts < 0:
            raise ValueError("false_starts debe ser un entero mayor o igual que 0.")
        if lapses is not None and (
            isinstance(lapses, bool) or not isinstance(lapses, int) or lapses < 0
        ):
            raise ValueError("lapses debe ser un entero mayor o igual que 0.")
        if not _is_finite_number(sleep_hours) or not (0 <= sleep_hours <= 24):
            raise ValueError("sleep_hours debe estar entre 0 y 24.")
        if isinstance(mood, bool) or not isinstance(mood, int) or not (1 <= mood <= 5):
            raise ValueError("mood debe estar entre 1 y 5.")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source debe ser una cadena no vacía.")
        if co2_mmhg is not None and (not _is_finite_number(co2_mmhg) or co2_mmhg < 0):
            raise ValueError("co2_mmhg debe ser finito y mayor o igual que 0.")

        if now is not None:
            self._uses_explicit_clock = True
        current = _normalize_now(now)

        median_ms = round(float(statistics.median(cleaned_rx)), 1)
        computed_lapses = sum(1 for value in cleaned_rx if value > 500.0)
        lapses_count = (
            max(computed_lapses, int(lapses)) if lapses is not None else computed_lapses
        )

        # Comparar contra la referencia previa antes de incorporar la muestra actual.
        if self.reaction_baseline_ms is not None:
            delta_ms = round(median_ms - self.reaction_baseline_ms, 1)
        else:
            delta_ms = 0.0

        manual_override = self._manual_baseline or (
            self.reaction_baseline_ms is not None and len(self._baseline_samples) == 0
        )
        if not manual_override and (
            self.reaction_baseline_ms is None or len(self._baseline_samples) < 3
        ):
            self._baseline_samples.append(median_ms)
            self.reaction_baseline_ms = round(
                float(statistics.median(self._baseline_samples)), 1
            )

        self.points += 15
        self.streak += 1
        self._unlock_badge("primer_checkin")
        if self.streak >= 3:
            self._unlock_badge("racha_3")

        drift_detected = (delta_ms >= 60.0) or (lapses_count >= 2)
        if drift_detected:
            sign = "+" if delta_ms >= 0 else ""
            parts = [
                "Hipótesis orientativa (escenario simulado): se observa deriva de reacción "
                f"({sign}{delta_ms} ms respecto a la referencia personal; "
                f"{lapses_count} lapsos > 500 ms)."
            ]
            if co2_mmhg is not None:
                parts.append(f"CO₂ observado: {co2_mmhg:.2f} mmHg.")
            parts.append(
                "Alternativas: horas de sueño, fatiga acumulada, distracción o latencia "
                "del dispositivo; no demuestra causalidad."
            )
            interpretation = " ".join(parts)
        else:
            interpretation = (
                "Hipótesis orientativa (escenario simulado): rendimiento de reacción "
                "estable respecto a su referencia personal; seguimiento orientativo no clínico."
            )

        entry: dict[str, Any] = {
            "at": current.isoformat(),
            "median_ms": median_ms,
            "false_starts": false_starts,
            "lapses": lapses_count,
            "sleep_hours": float(sleep_hours),
            "mood": mood,
            "source": source.strip(),
            "co2_mmhg": float(co2_mmhg) if co2_mmhg is not None else None,
            "baseline_ms": self.reaction_baseline_ms,
            "delta_ms": delta_ms,
            "drift_detected": drift_detected,
            "interpretation": interpretation,
            "points_awarded": 15,
        }
        self.checkins.append(entry)
        return dict(entry)

    def state(self, now: datetime | None = None) -> dict[str, Any]:
        """Devuelve el estado completo del coach para API/UI/informes."""
        if now is not None:
            self.refresh_due(now)
        elif not self._uses_explicit_clock:
            self.refresh_due()
        return {
            "points": self.points,
            "streak": self.streak,
            "badges": list(self.badges),
            "routines": [dict(routine) for routine in self.routines.values()],
            "latest_checkin": dict(self.checkins[-1]) if self.checkins else None,
            "reaction_baseline_ms": self.reaction_baseline_ms,
            "checkins_count": len(self.checkins),
            "scoring_policy": SCORING_POLICY,
            "demo_time_label": self.demo_time_label,
        }
