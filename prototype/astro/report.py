"""SBAR episode report generation with behavioral privacy filtering."""

from __future__ import annotations

import math
import re
from typing import Any

NON_CLINICAL_PREFIX = "Guidance hypothesis (simulated scenario)"
PRIVACY_NOTICE = (
    "Behavioral data: retained onboard for crew privacy "
    "(share_behavioral=False)"
)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _finite_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def _sanitize_text(text: str) -> str:
    cleaned = re.sub(r"\[IA\s*PREDICTION\]\s*:?\s*", "", text, flags=re.IGNORECASE).strip()
    return cleaned


def _format_hypothesis(raw_text: str | None) -> str:
    cleaned = _sanitize_text(raw_text or "")
    if not cleaned:
        return f"{NON_CLINICAL_PREFIX}: no active hypothesis with the available data."
    if cleaned.lower().startswith(NON_CLINICAL_PREFIX.lower()):
        return cleaned
    # Remove short redundant prefixes such as "Hypothesis:" if present.
    stripped = re.sub(r"^(guidance\s+hypothesis|hypothesis)\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    return f"{NON_CLINICAL_PREFIX}: {stripped or cleaned}"


def _format_value(value: Any, unit: str = "") -> str:
    if value is None:
        return "no reading (null)"
    suffix = f" {unit}" if unit else ""
    return f"{value}{suffix}"


def _format_environment_label(environment: Any) -> str:
    if isinstance(environment, dict):
        return str(
            environment.get("name")
            or environment.get("label")
            or environment.get("title")
            or environment.get("id")
            or "not specified"
        )
    if isinstance(environment, str) and environment.strip():
        return environment.strip()
    return "not specified"


def _build_behavioral_summary(coach: dict[str, Any]) -> dict[str, Any]:
    latest_checkin = _as_dict(coach.get("latest_checkin"))
    if not latest_checkin:
        return {
            "checkins_count": coach.get("checkins_count", 0),
            "reaction_baseline_ms": coach.get("reaction_baseline_ms"),
            "status": "No behavioral check-ins recorded in this episode.",
            "note": "Summary shared by crew authorization; orientative non-clinical use.",
        }
    return {
        "checkins_count": coach.get("checkins_count", 1),
        "at": latest_checkin.get("at"),
        "median_ms": latest_checkin.get("median_ms"),
        "reaction_baseline_ms": coach.get(
            "reaction_baseline_ms", latest_checkin.get("baseline_ms")
        ),
        "delta_ms": latest_checkin.get("delta_ms"),
        "lapses": latest_checkin.get("lapses"),
        "false_starts": latest_checkin.get("false_starts"),
        "sleep_hours": latest_checkin.get("sleep_hours"),
        "mood": latest_checkin.get("mood"),
        "drift_detected": latest_checkin.get("drift_detected"),
        "interpretation": _sanitize_text(str(latest_checkin.get("interpretation") or "")),
        "note": "Summary shared by crew authorization; orientative non-clinical use.",
    }


def _collect_unknowns(
    latest: dict[str, Any],
    baseline: dict[str, Any],
    assessment: dict[str, Any],
    dose_complete: Any,
    ml: dict[str, Any],
) -> list[str]:
    unknowns: list[str] = []
    for item in _as_list(assessment.get("unknowns")):
        text = _sanitize_text(str(item))
        if text and text not in unknowns:
            unknowns.append(text)

    if not latest:
        unknowns.append("No recent telemetry available.")
    else:
        signal_labels = (
            ("hr", "pulse (HR)"),
            ("rr", "respiration (RR)"),
            ("co2", "cabin CO₂"),
            ("dose_rate", "dose rate"),
        )
        for key, label in signal_labels:
            if latest.get(key) is None:
                unknowns.append(
                    f"No reading for {label} (null value; not replaced with zero)."
                )
        if latest.get("activity") in (None, "unknown"):
            unknowns.append("Crew activity unknown or not declared.")

    if dose_complete is False:
        unknowns.append("Incomplete coverage for accumulated dosimetry in this episode.")
    if not baseline:
        unknowns.append("Personal baseline pending or calibrating.")

    ml_status = ml.get("status")
    ml_reason = ml.get("reason")
    if ml_status in {"calibrating", "not_evaluable", "abstained"} or ml_reason:
        reason_text = ml_reason or ml_status
        unknowns.append(f"ML module abstaining/waiting: {reason_text}.")

    if not unknowns:
        unknowns.append("No critical signal gaps reported in the latest sample.")
    return unknowns


def build_episode_report(
    state: dict[str, Any] | None,
    share_behavioral: bool | None = None,
) -> dict[str, Any]:
    """Build the structured SBAR report (dict + Markdown) with privacy control."""
    safe_state = _as_dict(state)
    privacy = _as_dict(safe_state.get("privacy"))
    effective_share = (
        bool(share_behavioral)
        if share_behavioral is not None
        else bool(privacy.get("share_behavioral", False))
    )

    assessment = _as_dict(safe_state.get("assessment"))
    latest = _as_dict(safe_state.get("latest"))
    baseline = _as_dict(safe_state.get("baseline"))
    projections = _as_dict(safe_state.get("projections"))
    environment_raw = safe_state.get("environment")
    external_event = _as_dict(safe_state.get("external_event"))
    coach = _as_dict(safe_state.get("coach"))
    events = _as_list(safe_state.get("events"))
    ml = _as_dict(safe_state.get("ml"))
    state_provenance = _as_dict(safe_state.get("provenance"))

    dose_total_val = _finite_or_none(safe_state.get("dose_total"))
    dose_total_usv = round(dose_total_val, 4) if dose_total_val is not None else None
    dose_complete = (
        bool(safe_state.get("dose_complete"))
        if safe_state.get("dose_complete") is not None
        else None
    )

    timeline = [
        dict(ev) if isinstance(ev, dict) else {"text": str(ev)}
        for ev in events
    ]

    timestamp = (
        latest.get("measured_at")
        or assessment.get("timestamp")
        or safe_state.get("generated_at")
        or (timeline[-1].get("at") if timeline else None)
    )
    environment_value = (
        dict(environment_raw)
        if isinstance(environment_raw, dict)
        else (environment_raw if isinstance(environment_raw, str) and environment_raw else "not specified")
    )

    situacion: dict[str, Any] = {
        "level": assessment.get("level") or "unknown",
        "title": _sanitize_text(str(assessment.get("title") or "No assessment available")),
        "timestamp": timestamp,
        "environment": environment_value,
    }

    behavioral_summary = _build_behavioral_summary(coach) if effective_share else None
    antecedentes: dict[str, Any] = {
        "baseline": dict(baseline) if baseline else None,
        "dose_total_usv": dose_total_usv,
        "dose_complete": dose_complete,
        "activity": latest.get("activity") or safe_state.get("activity") or "unknown",
        "external_event": dict(external_event) if external_event else None,
        "behavioral_summary": behavioral_summary,
    }

    evidence = [
        _sanitize_text(str(item))
        for item in _as_list(assessment.get("evidence"))
        if item is not None
    ]
    if not evidence:
        evidence = ["No additional evidence recorded."]

    raw_alternatives = assessment.get("alternatives")
    if isinstance(raw_alternatives, str) and raw_alternatives.strip():
        alternatives = [_sanitize_text(raw_alternatives)]
    elif isinstance(raw_alternatives, (list, tuple)) and raw_alternatives:
        alternatives = [_sanitize_text(str(item)) for item in raw_alternatives]
    else:
        alternatives = [
            "Individual physiological variation or undeclared activity change.",
            "Sensor noise, latency, or partial signal loss.",
            "Concurrent environmental factors (coincidences do not demonstrate causality).",
        ]

    co2_sensitivity = (
        safe_state.get("co2_sensitivity")
        or baseline.get("co2_sensitivity")
        or projections.get("co2_sensitivity")
    )

    eval_projections: dict[str, Any] | None
    if projections:
        eval_projections = dict(projections)
    elif assessment.get("forecast_hr") is not None or assessment.get("forecast_method"):
        eval_projections = {
            "forecast_hr": assessment.get("forecast_hr"),
            "forecast_method": assessment.get("forecast_method"),
        }
    else:
        eval_projections = None

    evaluacion: dict[str, Any] = {
        "hypothesis": _format_hypothesis(
            str(assessment.get("hypothesis") or assessment.get("title") or "")
        ),
        "evidence": evidence,
        "unknowns": _collect_unknowns(latest, baseline, assessment, dose_complete, ml),
        "alternatives": alternatives,
        "co2_sensitivity": co2_sensitivity,
        "projections": eval_projections,
    }

    next_step = _sanitize_text(
        str(
            assessment.get("next_step")
            or "Continue observing signals, confirm activity context, and verify sensors."
        )
    )
    steps: list[str] = [next_step]
    for step in _as_list(assessment.get("steps")):
        cleaned = _sanitize_text(str(step))
        if cleaned and cleaned not in steps:
            steps.append(cleaned)
    default_steps = [
        "Verify sensor quality and connection before interpreting variations.",
        "Record observations and operational context; steps are illustrative only.",
    ]
    for step in default_steps:
        if step not in steps:
            steps.append(step)

    recomendacion: dict[str, Any] = {
        "next_step": next_step,
        "illustratives_only": True,
        "steps": steps,
    }

    provenance: dict[str, Any] = {
        "source": (
            state_provenance.get("source")
            or latest.get("source")
            or safe_state.get("source")
            or "no_data"
        ),
        "rules_version": (
            state_provenance.get("rules_version")
            or assessment.get("method")
            or "Demo rules v0.1"
        ),
        "config_version": (
            state_provenance.get("config_version")
            or safe_state.get("config_version")
            or "demo-config-v1"
        ),
        "ml_models": (
            state_provenance.get("ml_models")
            or ml.get("models")
            or (ml if ml else {"status": "not_available"})
        ),
    }

    markdown = _render_markdown(
        situacion=situacion,
        antecedentes=antecedentes,
        evaluacion=evaluacion,
        recomendacion=recomendacion,
        provenance=provenance,
        timeline=timeline,
        latest=latest,
        effective_share=effective_share,
    )

    return {
        "situacion": situacion,
        "antecedentes": antecedentes,
        "evaluacion": evaluacion,
        "recomendacion": recomendacion,
        "provenance": provenance,
        "timeline": timeline,
        "share_behavioral": effective_share,
        "markdown": markdown,
    }


def _render_markdown(
    *,
    situacion: dict[str, Any],
    antecedentes: dict[str, Any],
    evaluacion: dict[str, Any],
    recomendacion: dict[str, Any],
    provenance: dict[str, Any],
    timeline: list[dict[str, Any]],
    latest: dict[str, Any],
    effective_share: bool,
) -> str:
    env_label = _format_environment_label(situacion["environment"])
    ts_label = situacion["timestamp"] or "no timestamp"

    lines: list[str] = [
        "# Episode Report (SBAR)",
        "",
        "## 1. Situation",
        f"- **Level:** {situacion['level']}",
        f"- **Title:** {situacion['title']}",
        f"- **Timestamp:** {ts_label}",
        f"- **Environment:** {env_label}",
    ]
    if latest:
        lines.append(
            "- **Latest reading:** "
            f"HR={_format_value(latest.get('hr'), 'bpm')} · "
            f"RR={_format_value(latest.get('rr'), 'resp/min')} · "
            f"CO₂={_format_value(latest.get('co2'), 'mmHg')} · "
            f"Dose rate={_format_value(latest.get('dose_rate'), 'μSv/h')}"
        )

    lines.extend([
        "",
        "## 2. Background",
        f"- **Declared activity:** {antecedentes['activity']}",
        f"- **Accumulated dose (μSv):** {_format_value(antecedentes['dose_total_usv'], 'μSv')}",
        f"- **Dose coverage complete:** {_format_value(antecedentes['dose_complete'])}",
        f"- **Personal baseline:** {antecedentes['baseline'] if antecedentes['baseline'] is not None else 'calibrating / not available'}",
        f"- **External event:** {antecedentes['external_event'] if antecedentes['external_event'] is not None else 'none'}",
    ])

    if effective_share:
        summary = antecedentes["behavioral_summary"] or {}
        if "median_ms" in summary:
            mood_val = summary.get("mood")
            mood_label = f"{mood_val}/5" if mood_val is not None else "no reading (null)"
            lines.extend([
                "- **Behavioral data (shared by crew):**",
                f"  - Median reaction time: {_format_value(summary.get('median_ms'), 'ms')} "
                f"(reference: {_format_value(summary.get('reaction_baseline_ms'), 'ms')}, "
                f"delta: {_format_value(summary.get('delta_ms'), 'ms')}, "
                f"lapses > 500 ms: {_format_value(summary.get('lapses'))})",
                f"  - Declared sleep: {_format_value(summary.get('sleep_hours'), 'h')} · "
                f"Declared mood: {mood_label}",
                f"  - Orientative reading: {summary.get('interpretation') or 'no interpretation'}",
            ])
        else:
            lines.append(
                f"- **Behavioral data:** {summary.get('status', 'shared with no records.')}"
            )
    else:
        lines.append(f"- {PRIVACY_NOTICE}")

    lines.extend([
        "",
        "## 3. Assessment",
        f"- **Hypothesis:** {evaluacion['hypothesis']}",
        "- **Evidence:**",
    ])
    for item in evaluacion["evidence"]:
        lines.append(f"  - {item}")
    lines.append("- **Unknowns / data quality:**")
    for item in evaluacion["unknowns"]:
        lines.append(f"  - {item}")
    lines.append("- **Alternatives considered (without assuming causality):**")
    for item in evaluacion["alternatives"]:
        lines.append(f"  - {item}")
    if evaluacion["co2_sensitivity"] is not None:
        lines.append(f"- **CO₂ sensitivity:** {evaluacion['co2_sensitivity']}")
    if evaluacion["projections"] is not None:
        lines.append(f"- **Projections (under explicit assumptions):** {evaluacion['projections']}")

    lines.extend([
        "",
        "## 4. Recommendation",
        f"- **Suggested next step (illustrative only):** {recomendacion['next_step']}",
        f"- **Review steps (`illustratives_only={recomendacion['illustratives_only']}`):**",
    ])
    for step in recomendacion["steps"]:
        lines.append(f"  - {step}")

    lines.extend([
        "",
        "## Provenance and Traceability",
        f"- **Source:** {provenance['source']}",
        f"- **Rules version:** {provenance['rules_version']}",
        f"- **Config version:** {provenance['config_version']}",
        f"- **ML models:** {provenance['ml_models']}",
        f"- **Behavioral privacy shared (`share_behavioral`):** {effective_share}",
        "- **Episode timeline:**",
    ])
    if timeline:
        for ev in timeline:
            at = ev.get("at", "no time")
            text = _sanitize_text(str(ev.get("text", ev)))
            lines.append(f"  - [{at}] {text}")
    else:
        lines.append("  - No events recorded in the timeline.")

    return "\n".join(lines) + "\n"
