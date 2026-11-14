"""Generación de informes de episodio SBAR con filtro de privacidad conductual."""

from __future__ import annotations

import math
import re
from typing import Any

NON_CLINICAL_PREFIX = "Hipótesis orientativa (escenario simulado)"
PRIVACY_NOTICE = (
    "Datos conductuales: retenidos a bordo por privacidad del tripulante "
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
        return f"{NON_CLINICAL_PREFIX}: sin hipótesis activa con los datos disponibles."
    if cleaned.lower().startswith(NON_CLINICAL_PREFIX.lower()):
        return cleaned
    # Elimina prefijos cortos redundantes como "Hipótesis:" si existen.
    stripped = re.sub(r"^hip[óo]tesis\s*:\s*", "", cleaned, flags=re.IGNORECASE).strip()
    return f"{NON_CLINICAL_PREFIX}: {stripped or cleaned}"


def _format_value(value: Any, unit: str = "") -> str:
    if value is None:
        return "sin lectura (null)"
    suffix = f" {unit}" if unit else ""
    return f"{value}{suffix}"


def _format_environment_label(environment: Any) -> str:
    if isinstance(environment, dict):
        return str(
            environment.get("name")
            or environment.get("label")
            or environment.get("title")
            or environment.get("id")
            or "no especificado"
        )
    if isinstance(environment, str) and environment.strip():
        return environment.strip()
    return "no especificado"


def _build_behavioral_summary(coach: dict[str, Any]) -> dict[str, Any]:
    latest_checkin = _as_dict(coach.get("latest_checkin"))
    if not latest_checkin:
        return {
            "checkins_count": coach.get("checkins_count", 0),
            "reaction_baseline_ms": coach.get("reaction_baseline_ms"),
            "status": "Sin check-ins conductuales registrados en este episodio.",
            "note": "Resumen compartido por autorización del tripulante; uso orientativo no clínico.",
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
        "note": "Resumen compartido por autorización del tripulante; uso orientativo no clínico.",
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
        unknowns.append("Sin telemetría reciente disponible.")
    else:
        signal_labels = (
            ("hr", "pulso (HR)"),
            ("rr", "respiración (RR)"),
            ("co2", "CO₂ de cabina"),
            ("dose_rate", "tasa de dosis"),
        )
        for key, label in signal_labels:
            if latest.get(key) is None:
                unknowns.append(
                    f"Sin lectura de {label} (valor null; no se sustituye por cero)."
                )
        if latest.get("activity") in (None, "unknown"):
            unknowns.append("Actividad del tripulante desconocida o no declarada.")

    if dose_complete is False:
        unknowns.append("Cobertura incompleta de dosimetría acumulada en el episodio.")
    if not baseline:
        unknowns.append("Línea base personal pendiente o en calibración.")

    ml_status = ml.get("status")
    ml_reason = ml.get("reason")
    if ml_status in {"calibrando", "no_evaluable", "abstained"} or ml_reason:
        reason_text = ml_reason or ml_status
        unknowns.append(f"Módulo ML en abstención/espera: {reason_text}.")

    if not unknowns:
        unknowns.append("Sin brechas críticas de señal reportadas en la última muestra.")
    return unknowns


def build_episode_report(
    state: dict[str, Any] | None,
    share_behavioral: bool | None = None,
) -> dict[str, Any]:
    """Construye el informe estructurado SBAR (dict + Markdown) con control de privacidad."""
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
        else (environment_raw if isinstance(environment_raw, str) and environment_raw else "no especificado")
    )

    situacion: dict[str, Any] = {
        "level": assessment.get("level") or "unknown",
        "title": _sanitize_text(str(assessment.get("title") or "Sin evaluación disponible")),
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
        evidence = ["Sin evidencia adicional registrada."]

    raw_alternatives = assessment.get("alternatives")
    if isinstance(raw_alternatives, str) and raw_alternatives.strip():
        alternatives = [_sanitize_text(raw_alternatives)]
    elif isinstance(raw_alternatives, (list, tuple)) and raw_alternatives:
        alternatives = [_sanitize_text(str(item)) for item in raw_alternatives]
    else:
        alternatives = [
            "Variación fisiológica individual o cambio de actividad no declarado.",
            "Ruido, latencia o pérdida parcial de señal del sensor.",
            "Factores ambientales concurrentes (las coincidencias no demuestran causalidad).",
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
            or "Continuar observando señales, confirmar contexto de actividad y verificar sensores."
        )
    )
    steps: list[str] = [next_step]
    for step in _as_list(assessment.get("steps")):
        cleaned = _sanitize_text(str(step))
        if cleaned and cleaned not in steps:
            steps.append(cleaned)
    default_steps = [
        "Verificar calidad y conexión de sensores antes de interpretar variaciones.",
        "Registrar observaciones y contexto operativo; los pasos son únicamente ilustrativos.",
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
            or "sin_datos"
        ),
        "rules_version": (
            state_provenance.get("rules_version")
            or assessment.get("method")
            or "Reglas de demostración v0.1"
        ),
        "config_version": (
            state_provenance.get("config_version")
            or safe_state.get("config_version")
            or "demo-config-v1"
        ),
        "ml_models": (
            state_provenance.get("ml_models")
            or ml.get("models")
            or (ml if ml else {"status": "no_disponible"})
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
    ts_label = situacion["timestamp"] or "sin marca de tiempo"

    lines: list[str] = [
        "# Informe de Episodio (SBAR)",
        "",
        "## 1. Situación",
        f"- **Nivel:** {situacion['level']}",
        f"- **Título:** {situacion['title']}",
        f"- **Marca de tiempo:** {ts_label}",
        f"- **Entorno:** {env_label}",
    ]
    if latest:
        lines.append(
            "- **Última lectura:** "
            f"FC={_format_value(latest.get('hr'), 'bpm')} · "
            f"FR={_format_value(latest.get('rr'), 'resp/min')} · "
            f"CO₂={_format_value(latest.get('co2'), 'mmHg')} · "
            f"Tasa dosis={_format_value(latest.get('dose_rate'), 'μSv/h')}"
        )

    lines.extend([
        "",
        "## 2. Antecedentes",
        f"- **Actividad declarada:** {antecedentes['activity']}",
        f"- **Dosis acumulada (μSv):** {_format_value(antecedentes['dose_total_usv'], 'μSv')}",
        f"- **Cobertura de dosis completa:** {_format_value(antecedentes['dose_complete'])}",
        f"- **Línea base personal:** {antecedentes['baseline'] if antecedentes['baseline'] is not None else 'calibrando / no disponible'}",
        f"- **Evento externo:** {antecedentes['external_event'] if antecedentes['external_event'] is not None else 'ninguno'}",
    ])

    if effective_share:
        summary = antecedentes["behavioral_summary"] or {}
        if "median_ms" in summary:
            mood_val = summary.get("mood")
            mood_label = f"{mood_val}/5" if mood_val is not None else "sin lectura (null)"
            lines.extend([
                "- **Datos conductuales (compartidos por el tripulante):**",
                f"  - Tiempo de reacción mediano: {_format_value(summary.get('median_ms'), 'ms')} "
                f"(referencia: {_format_value(summary.get('reaction_baseline_ms'), 'ms')}, "
                f"delta: {_format_value(summary.get('delta_ms'), 'ms')}, "
                f"lapsos > 500 ms: {_format_value(summary.get('lapses'))})",
                f"  - Sueño declarado: {_format_value(summary.get('sleep_hours'), 'h')} · "
                f"Ánimo declarado: {mood_label}",
                f"  - Lectura orientativa: {summary.get('interpretation') or 'sin interpretación'}",
            ])
        else:
            lines.append(
                f"- **Datos conductuales:** {summary.get('status', 'compartidos sin registros.')}"
            )
    else:
        lines.append(f"- {PRIVACY_NOTICE}")

    lines.extend([
        "",
        "## 3. Evaluación",
        f"- **Hipótesis:** {evaluacion['hypothesis']}",
        "- **Evidencia:**",
    ])
    for item in evaluacion["evidence"]:
        lines.append(f"  - {item}")
    lines.append("- **Qué no se sabe / calidad:**")
    for item in evaluacion["unknowns"]:
        lines.append(f"  - {item}")
    lines.append("- **Alternativas consideradas (sin asumir causalidad):**")
    for item in evaluacion["alternatives"]:
        lines.append(f"  - {item}")
    if evaluacion["co2_sensitivity"] is not None:
        lines.append(f"- **Sensibilidad CO₂:** {evaluacion['co2_sensitivity']}")
    if evaluacion["projections"] is not None:
        lines.append(f"- **Proyecciones (bajo supuestos explícitos):** {evaluacion['projections']}")

    lines.extend([
        "",
        "## 4. Recomendación",
        f"- **Siguiente paso sugerido (solo ilustrativo):** {recomendacion['next_step']}",
        f"- **Pasos de revisión (`illustratives_only={recomendacion['illustratives_only']}`):**",
    ])
    for step in recomendacion["steps"]:
        lines.append(f"  - {step}")

    lines.extend([
        "",
        "## Procedencia y Trazabilidad",
        f"- **Fuente:** {provenance['source']}",
        f"- **Versión de reglas:** {provenance['rules_version']}",
        f"- **Versión de configuración:** {provenance['config_version']}",
        f"- **Modelos ML:** {provenance['ml_models']}",
        f"- **Privacidad conductual compartida (`share_behavioral`):** {effective_share}",
        "- **Línea de tiempo del episodio:**",
    ])
    if timeline:
        for ev in timeline:
            at = ev.get("at", "sin hora")
            text = _sanitize_text(str(ev.get("text", ev)))
            lines.append(f"  - [{at}] {text}")
    else:
        lines.append("  - Sin eventos registrados en la línea de tiempo.")

    return "\n".join(lines) + "\n"
