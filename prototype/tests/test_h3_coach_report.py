from datetime import datetime, timedelta, timezone

import pytest

from astro.coach import Coach, DEFAULT_ROUTINES
from astro.report import build_episode_report


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def test_routines_due_and_completion():
    assert set(DEFAULT_ROUTINES) == {
        "checkin",
        "hydration",
        "exercise",
        "co2_check",
        "shelter_checklist",
    }
    assert DEFAULT_ROUTINES["checkin"]["interval_demo_s"] == 180
    assert DEFAULT_ROUTINES["hydration"]["interval_demo_s"] == 240
    assert DEFAULT_ROUTINES["exercise"]["interval_demo_s"] == 300
    assert DEFAULT_ROUTINES["co2_check"]["interval_demo_s"] == 240
    assert DEFAULT_ROUTINES["shelter_checklist"]["interval_demo_s"] == 120
    assert DEFAULT_ROUTINES["shelter_checklist"]["active"] is False

    coach = Coach(now=NOW)
    initial = coach.state(NOW)
    assert initial["points"] == 0
    assert initial["streak"] == 0
    assert initial["badges"] == []
    assert initial["demo_time_label"] == "Intervalo de demostración (escala acelerada)"
    assert "participación" in initial["scoring_policy"]

    assert coach.routines["checkin"]["due"] is True
    assert coach.routines["hydration"]["due"] is True
    assert coach.routines["exercise"]["due"] is False
    assert coach.routines["co2_check"]["due"] is False
    assert coach.routines["shelter_checklist"]["due"] is False

    # Avance temporal en escala de demostración
    coach.refresh_due(NOW + timedelta(seconds=240))
    assert coach.routines["co2_check"]["due"] is True
    assert coach.routines["exercise"]["due"] is False
    assert coach.routines["shelter_checklist"]["due"] is False

    coach.refresh_due(NOW + timedelta(seconds=300))
    assert coach.routines["exercise"]["due"] is True

    # Completar funciona tanto con due=True como con due=False
    res1 = coach.complete_routine("checkin", now=NOW + timedelta(seconds=305))
    assert res1["points"] == 10
    assert res1["streak"] == 1
    assert res1["badges"] == ["primera_rutina"]
    assert coach.routines["checkin"]["due"] is False
    assert coach.routines["checkin"]["completed_count"] == 1
    assert coach.routines["checkin"]["last_completed_at"] == (
        NOW + timedelta(seconds=305)
    ).isoformat()

    coach.mark_due("hydration", False)
    assert coach.routines["hydration"]["due"] is False
    res2 = coach.complete_routine("hydration", now=NOW + timedelta(seconds=310))
    assert res2["points"] == 20
    assert res2["streak"] == 2
    assert res2["badges"] == ["primera_rutina"]

    # Tercer completado desbloquea racha_3 sin duplicar primera_rutina
    res3 = coach.complete_routine("exercise", now=NOW + timedelta(seconds=315))
    assert res3["points"] == 30
    assert res3["streak"] == 3
    assert res3["badges"] == ["primera_rutina", "racha_3"]

    # Evento solar activa shelter_checklist y completarla desbloquea lista_refugio
    activated = coach.activate_solar_checklist(True)
    assert activated["active"] is True
    assert activated["due"] is True
    res4 = coach.complete_routine("shelter_checklist", now=NOW + timedelta(seconds=320))
    assert res4["points"] == 40
    assert res4["streak"] == 4
    assert res4["badges"] == ["primera_rutina", "racha_3", "lista_refugio"]

    deactivated = coach.activate_solar_checklist(False)
    assert deactivated["active"] is False
    assert deactivated["due"] is False

    # Reconocimiento de alerta otorga +5 puntos fijos sin alterar racha
    ack = coach.record_ack(now=NOW + timedelta(seconds=325))
    assert ack == {"points": 45, "streak": 4, "awarded": 5}

    # La rutina vuelve a estar pendiente solo tras cumplirse interval_demo_s desde su último completado
    coach.refresh_due(NOW + timedelta(seconds=305 + 179))
    assert coach.routines["checkin"]["due"] is False
    coach.refresh_due(NOW + timedelta(seconds=305 + 180))
    assert coach.routines["checkin"]["due"] is True

    with pytest.raises(ValueError, match="Rutina desconocida"):
        coach.complete_routine("rutina_inexistente")
    with pytest.raises(ValueError, match="Rutina desconocida"):
        coach.mark_due("rutina_inexistente", True)


def test_points_only_for_participation():
    slow_low = Coach(now=NOW)
    fast_high = Coach(now=NOW)

    r_slow = slow_low.record_checkin(
        reaction_ms=[740.0, 750.0, 760.0],
        false_starts=2,
        sleep_hours=3.5,
        mood=1,
        source="declared",
        now=NOW,
    )
    r_fast = fast_high.record_checkin(
        reaction_ms=[205.0, 210.0, 215.0],
        false_starts=0,
        sleep_hours=8.5,
        mood=5,
        source="declared",
        now=NOW,
    )

    assert r_slow["points_awarded"] == 15
    assert r_fast["points_awarded"] == 15
    assert slow_low.points == fast_high.points == 15
    assert slow_low.streak == fast_high.streak == 1
    assert slow_low.badges == fast_high.badges == ["primer_checkin"]

    # Validaciones de entrada
    with pytest.raises(ValueError):
        slow_low.record_checkin(reaction_ms=[])
    with pytest.raises(ValueError):
        slow_low.record_checkin(reaction_ms=[220.0, -5.0])
    with pytest.raises(ValueError):
        slow_low.record_checkin(reaction_ms=[220.0], mood=6)
    with pytest.raises(ValueError):
        slow_low.record_checkin(reaction_ms=[220.0], sleep_hours=25.0)
    with pytest.raises(ValueError):
        slow_low.record_checkin(reaction_ms=[220.0], false_starts=-1)


def test_checkin_baseline_and_drift():
    coach = Coach(now=NOW)

    # Calibración automática con 3 check-ins iniciales
    c1 = coach.record_checkin([220.0, 230.0, 240.0], now=NOW)
    assert c1["median_ms"] == 230.0
    assert c1["delta_ms"] == 0.0
    assert c1["drift_detected"] is False
    assert coach.reaction_baseline_ms == 230.0

    c2 = coach.record_checkin([235.0, 240.0, 245.0], now=NOW + timedelta(minutes=3))
    assert c2["median_ms"] == 240.0
    assert c2["delta_ms"] == 10.0
    assert coach.reaction_baseline_ms == 235.0

    c3 = coach.record_checkin([245.0, 250.0, 255.0], now=NOW + timedelta(minutes=6))
    assert c3["median_ms"] == 250.0
    assert coach.reaction_baseline_ms == 240.0
    assert "racha_3" in coach.badges

    # Luego de 3 check-ins la referencia personal permanece fija durante el episodio
    c4_stable = coach.record_checkin([240.0, 245.0, 250.0], now=NOW + timedelta(minutes=9))
    assert coach.reaction_baseline_ms == 240.0
    assert c4_stable["drift_detected"] is False
    assert c4_stable["interpretation"].startswith(
        "Hipótesis orientativa (escenario simulado):"
    )
    assert "estable" in c4_stable["interpretation"].lower()

    # Deriva con lapsos > 500 ms y cruce orientativo con CO2 sin causalidad
    c5_drift = coach.record_checkin(
        reaction_ms=[330.0, 520.0, 560.0],
        false_starts=1,
        sleep_hours=5.5,
        mood=2,
        co2_mmhg=5.12,
        now=NOW + timedelta(minutes=12),
    )
    assert coach.reaction_baseline_ms == 240.0
    assert c5_drift["median_ms"] == 520.0
    assert c5_drift["lapses"] == 2
    assert c5_drift["delta_ms"] == 280.0
    assert c5_drift["drift_detected"] is True
    interp = c5_drift["interpretation"]
    assert interp.startswith("Hipótesis orientativa (escenario simulado):")
    assert "+280.0 ms" in interp
    assert "2 lapsos > 500 ms" in interp
    assert "CO₂ observado: 5.12 mmHg" in interp
    assert "Alternativas: horas de sueño, fatiga acumulada, distracción o latencia del dispositivo; no demuestra causalidad." in interp
    assert "[IA PREDICTION]" not in interp
    assert "diagnóstico" not in interp.lower()

    # Línea base fijada manualmente + override de lapses
    manual = Coach(now=NOW)
    manual.set_reaction_baseline(220.0)
    assert manual.reaction_baseline_ms == 220.0
    c_manual = manual.record_checkin([280.0, 285.0, 290.0], lapses=1, now=NOW)
    assert manual.reaction_baseline_ms == 220.0
    assert c_manual["delta_ms"] == 65.0
    assert c_manual["lapses"] == 1
    assert c_manual["drift_detected"] is True


def test_sbar_report_and_privacy_filter():
    coach = Coach(now=NOW)
    coach.set_reaction_baseline(230.0)
    coach.record_checkin(
        reaction_ms=[740.0, 750.0, 760.0],
        false_starts=2,
        sleep_hours=4.5,
        mood=1,
        co2_mmhg=5.2,
        now=NOW,
    )

    state = {
        "latest": {
            "measured_at": NOW.isoformat(),
            "hr": 98.0,
            "rr": 26.0,
            "co2": 5.2,
            "dose_rate": 1.2,
            "activity": "rest",
            "source": "simulated",
        },
        "assessment": {
            "level": "alert",
            "title": "[IA PREDICTION] Hipótesis: cambio respiratorio y ambiental",
            "evidence": ["CO₂ 5.20 mmHg y respiración 26/min."],
            "next_step": "Verificar sensores y contexto de cabina.",
            "method": "Reglas de demostración v0.1",
            "forecast_hr": 98.0,
            "forecast_method": "Persistencia a 60 s",
        },
        "baseline": {"hr_median": 72.0, "rr_median": 14.0},
        "projections": {"co2_eta_min": 12.5, "assumption": "tendencia lineal constante"},
        "co2_sensitivity": {"slope": 2.4, "r2": 0.85},
        "environment": {"id": "rover", "name": "Vehículo explorador"},
        "external_event": {"id": "DONKI-2024-05-11", "phase": "watch"},
        "coach": coach.state(NOW),
        "events": [{"at": NOW.isoformat(), "text": "Cambio respiratorio y ambiental"}],
        "ml": {"status": "abstained", "reason": "calibrando"},
        "dose_total": 0.42,
        "dose_complete": True,
        "privacy": {"share_behavioral": False},
    }

    # Privacidad retenida por defecto (share_behavioral=False en state)
    private_report = build_episode_report(state)
    assert private_report["share_behavioral"] is False
    assert private_report["antecedentes"]["behavioral_summary"] is None

    for key in ("situacion", "antecedentes", "evaluacion", "recomendacion", "provenance", "timeline", "markdown"):
        assert key in private_report

    assert private_report["evaluacion"]["hypothesis"].startswith(
        "Hipótesis orientativa (escenario simulado)"
    )
    assert private_report["recomendacion"]["illustratives_only"] is True
    assert private_report["provenance"]["source"] == "simulated"
    assert private_report["provenance"]["rules_version"] == "Reglas de demostración v0.1"
    assert private_report["provenance"]["config_version"]
    assert private_report["provenance"]["ml_models"]

    md_private = private_report["markdown"]
    for heading in (
        "# Informe de Episodio (SBAR)",
        "## 1. Situación",
        "## 2. Antecedentes",
        "## 3. Evaluación",
        "## 4. Recomendación",
        "## Procedencia y Trazabilidad",
    ):
        assert heading in md_private

    assert (
        "Datos conductuales: retenidos a bordo por privacidad del tripulante (share_behavioral=False)"
        in md_private
    )
    assert "[IA PREDICTION]" not in md_private
    assert "[IA PREDICTION]" not in private_report["evaluacion"]["hypothesis"]
    # Ningún dato conductual sensible debe filtrarse con share_behavioral=False
    for secret in ("750.0", "4.5", "sleep_hours", "median_ms", "Sueño declarado", "Ánimo declarado"):
        assert secret not in md_private

    # Con share_behavioral=True sí se incluye el resumen conductual seguro
    shared_report = build_episode_report(state, share_behavioral=True)
    assert shared_report["share_behavioral"] is True
    summary = shared_report["antecedentes"]["behavioral_summary"]
    assert summary is not None
    assert summary["sleep_hours"] == 4.5
    assert summary["mood"] == 1
    assert summary["median_ms"] == 750.0
    assert "750.0 ms" in shared_report["markdown"]
    assert "4.5 h" in shared_report["markdown"]
    assert "1/5" in shared_report["markdown"]

    # Tolerancia defensiva ante estado vacío o campos None (no rellena faltantes con 0)
    empty_report = build_episode_report(
        {"assessment": None, "latest": None, "events": None, "privacy": None, "dose_total": None}
    )
    assert empty_report["share_behavioral"] is False
    assert empty_report["antecedentes"]["dose_total_usv"] is None
    assert empty_report["antecedentes"]["behavioral_summary"] is None
    assert empty_report["timeline"] == []
    assert empty_report["evaluacion"]["hypothesis"].startswith(
        "Hipótesis orientativa (escenario simulado)"
    )

    # Registro real BIDMC conserva null en CO2 y dosimetría sin rellenar con 0
    bidmc_report = build_episode_report({
        "latest": {
            "measured_at": NOW.isoformat(),
            "hr": 82.0,
            "rr": 18.0,
            "co2": None,
            "dose_rate": None,
            "activity": "unknown",
            "source": "bidmc",
        },
        "dose_total": None,
        "dose_complete": False,
    })
    assert bidmc_report["antecedentes"]["dose_total_usv"] is None
    assert "CO₂=sin lectura (null)" in bidmc_report["markdown"]
    assert "Tasa dosis=sin lectura (null)" in bidmc_report["markdown"]
