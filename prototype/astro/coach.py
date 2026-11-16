"""Periodic routines, participation gamification, and non-clinical behavioral check-ins."""

from __future__ import annotations

import copy
import math
import statistics
from datetime import datetime, timezone
from typing import Any

DEFAULT_ROUTINES: dict[str, dict[str, Any]] = {
    "checkin": {
        "id": "checkin",
        "title": "Alertness and reaction check-in",
        "description": "Brief attention/reaction test and voluntary sleep and mood log.",
        "interval_demo_s": 180,
        "active": True,
        "due": True,
        "completed_count": 0,
        "last_completed_at": None,
    },
    "hydration": {
        "id": "hydration",
        "title": "Protocol hydration",
        "description": "Periodic water intake according to cabin operating protocol.",
        "interval_demo_s": 240,
        "active": True,
        "due": True,
        "completed_count": 0,
        "last_completed_at": None,
    },
    "exercise": {
        "id": "exercise",
        "title": "Physical countermeasure",
        "description": "Scheduled preventive exercise session during the simulated segment.",
        "interval_demo_s": 300,
        "active": True,
        "due": False,
        "completed_count": 0,
        "last_completed_at": None,
    },
    "co2_check": {
        "id": "co2_check",
        "title": "CO₂ sensor/scrubber check",
        "description": "Visual inspection of the CO₂ reading and scrubber status.",
        "interval_demo_s": 240,
        "active": True,
        "due": False,
        "completed_count": 0,
        "last_completed_at": None,
    },
    "shelter_checklist": {
        "id": "shelter_checklist",
        "title": "Shelter checklist",
        "description": "Shelter preparation protocol activated during a simulated solar event.",
        "interval_demo_s": 120,
        "active": False,
        "due": False,
        "completed_count": 0,
        "last_completed_at": None,
    },
}

SCORING_POLICY = (
    "Points and streaks are awarded only for participation, "
    "never for physiological results or speed."
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
    """Manager for routines, participation points, and reaction check-ins."""

    def __init__(self, now: datetime | None = None) -> None:
        self.points: int = 0
        self.streak: int = 0
        self.badges: list[str] = []
        self.routines: dict[str, dict[str, Any]] = copy.deepcopy(DEFAULT_ROUTINES)
        self.checkins: list[dict[str, Any]] = []
        self.reaction_baseline_ms: float | None = None
        self.demo_time_label: str = "Demo interval (accelerated scale)"
        self._baseline_samples: list[float] = []
        self._manual_baseline: bool = False
        self._uses_explicit_clock: bool = now is not None
        self._created_at: datetime = _normalize_now(now)

    def _unlock_badge(self, badge: str) -> None:
        if badge not in self.badges:
            self.badges.append(badge)

    def _require_routine(self, routine_id: str) -> dict[str, Any]:
        if routine_id not in self.routines:
            raise ValueError(f"Unknown routine: {routine_id}")
        return self.routines[routine_id]

    def refresh_due(self, now: datetime | None = None) -> dict[str, dict[str, Any]]:
        """Set `due=True` on active routines when `interval_demo_s` has elapsed."""
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
        """Manually set the pending (`due`) state of a routine."""
        routine = self._require_routine(routine_id)
        routine["due"] = bool(due)
        return dict(routine)

    def complete_routine(self, routine_id: str, now: datetime | None = None) -> dict[str, Any]:
        """Record participation in a routine and award +10 fixed points."""
        routine = self._require_routine(routine_id)
        if now is not None:
            self._uses_explicit_clock = True
        current = _normalize_now(now)

        self.points += 10
        self.streak += 1
        routine["completed_count"] += 1
        routine["due"] = False
        routine["last_completed_at"] = current.isoformat()

        self._unlock_badge("first_routine")
        if self.streak >= 3:
            self._unlock_badge("streak_3")
        if routine_id == "shelter_checklist":
            self._unlock_badge("shelter_checklist")

        summary = self.state(now=current if now is not None else None)
        summary["routine_id"] = routine_id
        summary["points_awarded"] = 10
        summary["routine"] = dict(routine)
        return summary

    def record_ack(self, now: datetime | None = None) -> dict[str, int]:
        """Award +5 fixed participation points for acknowledging an alert."""
        if now is not None:
            self._uses_explicit_clock = True
        _normalize_now(now)
        self.points += 5
        return {"points": self.points, "streak": self.streak, "awarded": 5}

    def activate_solar_checklist(self, active: bool = True) -> dict[str, Any]:
        """Activate or deactivate the shelter checklist during a solar event."""
        routine = self.routines["shelter_checklist"]
        routine["active"] = bool(active)
        routine["due"] = bool(active)
        return dict(routine)

    def set_reaction_baseline(self, baseline_ms: float) -> None:
        """Manually set the personal reaction-time baseline (ms)."""
        if not _is_finite_number(baseline_ms) or baseline_ms <= 0:
            raise ValueError("Reaction baseline must be finite and greater than 0.")
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
        """Record a behavioral check-in and compute drift without clinical language or penalties."""
        if reaction_ms is None:
            raise ValueError("reaction_ms cannot be empty.")
        try:
            raw_rx = list(reaction_ms)
        except TypeError as exc:
            raise ValueError("reaction_ms must be a non-empty numeric sequence.") from exc
        if not raw_rx:
            raise ValueError("reaction_ms cannot be empty.")
        cleaned_rx: list[float] = []
        for value in raw_rx:
            if not _is_finite_number(value) or value <= 0:
                raise ValueError("All reaction_ms values must be finite and greater than 0.")
            cleaned_rx.append(float(value))

        if isinstance(false_starts, bool) or not isinstance(false_starts, int) or false_starts < 0:
            raise ValueError("false_starts must be an integer greater than or equal to 0.")
        if lapses is not None and (
            isinstance(lapses, bool) or not isinstance(lapses, int) or lapses < 0
        ):
            raise ValueError("lapses must be an integer greater than or equal to 0.")
        if not _is_finite_number(sleep_hours) or not (0 <= sleep_hours <= 24):
            raise ValueError("sleep_hours must be between 0 and 24.")
        if isinstance(mood, bool) or not isinstance(mood, int) or not (1 <= mood <= 5):
            raise ValueError("mood must be between 1 and 5.")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be a non-empty string.")
        if co2_mmhg is not None and (not _is_finite_number(co2_mmhg) or co2_mmhg < 0):
            raise ValueError("co2_mmhg must be finite and greater than or equal to 0.")

        if now is not None:
            self._uses_explicit_clock = True
        current = _normalize_now(now)

        median_ms = round(float(statistics.median(cleaned_rx)), 1)
        computed_lapses = sum(1 for value in cleaned_rx if value > 500.0)
        lapses_count = (
            max(computed_lapses, int(lapses)) if lapses is not None else computed_lapses
        )

        # Compare against the previous reference before incorporating the current sample.
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
        self._unlock_badge("first_checkin")
        if self.streak >= 3:
            self._unlock_badge("streak_3")

        drift_detected = (delta_ms >= 60.0) or (lapses_count >= 2)
        if drift_detected:
            sign = "+" if delta_ms >= 0 else ""
            parts = [
                "Guidance hypothesis (simulated scenario): reaction drift observed "
                f"({sign}{delta_ms} ms relative to personal reference; "
                f"{lapses_count} lapses > 500 ms)."
            ]
            if co2_mmhg is not None:
                parts.append(f"Observed CO₂: {co2_mmhg:.2f} mmHg.")
            parts.append(
                "Alternatives: hours of sleep, accumulated fatigue, distraction, or device "
                "latency; this does not demonstrate causality."
            )
            interpretation = " ".join(parts)
        else:
            interpretation = (
                "Guidance hypothesis (simulated scenario): reaction performance "
                "is stable relative to your personal reference; orientative non-clinical monitoring."
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
        """Return the full coach state for API/UI/reports."""
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
