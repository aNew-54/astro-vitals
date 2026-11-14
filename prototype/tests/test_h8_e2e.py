"""Pruebas de integración E2E (H8): Gateway -> API/Engine -> SQLite/WebBridge -> /v1/* y UI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run as runner
from astro.api import create_app
from astro.engine import Engine
from astro.gateway import Gateway
from astro.storage import Storage


def _sample_packet(
    at: datetime,
    *,
    hr: float | None = 72.0,
    rr: float | None = 15.0,
    co2: float | None = 2.0,
    dose_rate: float | None = 0.3,
    spo2: float | None = 98.2,
    bp_sys: float | None = 116.0,
    bp_dia: float | None = 74.0,
    temp_c: float | None = 36.6,
    hydration_pct: float | None = 84.0,
    activity: str = "rest",
    source: str = "simulated",
    original_time_s: float | None = None,
) -> dict:
    return {
        "sample_id": str(uuid4()),
        "measured_at": at.isoformat(),
        "hr": hr,
        "rr": rr,
        "co2": co2,
        "dose_rate": dose_rate,
        "spo2": spo2,
        "bp_sys": bp_sys,
        "bp_dia": bp_dia,
        "temp_c": temp_c,
        "hydration_pct": hydration_pct,
        "activity": activity,
        "source": source,
        "original_time_s": original_time_s,
    }


def _make_e2e_client() -> tuple[TestClient, Engine, Storage, Gateway]:
    engine = Engine()
    storage = Storage(":memory:")
    gateway = Gateway()
    app = create_app(engine=engine, storage=storage, gateway=gateway)
    return TestClient(app), engine, storage, gateway


def test_e2e_gateway_to_engine_storage_rest_and_websocket():
    client, _engine, _storage, gateway = _make_e2e_client()

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    base_ts = datetime.now(timezone.utc) - timedelta(seconds=20)
    for idx in range(5):
        pkt = gateway.make_packet()
        assert pkt is not None
        pkt["measured_at"] = (base_ts + timedelta(seconds=idx)).isoformat()
        resp = client.post("/api/v1/telemetry", json=pkt)
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True
        assert resp.json()["duplicate"] is False

        # Reenvío idéntico: idempotente en Engine y sin duplicar fila en SQLite.
        dup = client.post("/api/v1/telemetry", json=pkt)
        assert dup.status_code == 200
        assert dup.json()["duplicate"] is True

    state_resp = client.get("/api/v1/state")
    assert state_resp.status_code == 200
    state_data = state_resp.json()
    assert state_data["received_count"] == 5
    assert state_data["latest"] is not None
    assert "[IA PREDICTION]" not in state_data["assessment"]["hypothesis"]

    measurements = client.get("/api/measurements/?limit=20").json()
    assert len(measurements) == 5

    latest_list = client.get("/api/measurements/latest").json()
    assert len(latest_list) == 1
    assert latest_list[0]["heart_rate_bpm"] is not None
    assert latest_list[0]["ambient_co2_mmhg"] is not None

    with client.websocket_connect("/telemetry") as ws:
        ws_msg = ws.receive_json()
        assert ws_msg["type"] == "telemetry"
        assert ws_msg["measurement_id"] == latest_list[0]["id"]
        assert ws_msg["hr"] == latest_list[0]["heart_rate_bpm"]
        assert ws_msg["co2"] == latest_list[0]["ambient_co2_mmhg"]


def test_e2e_bidmc_null_preservation_across_stack():
    client, _engine, _storage, gateway = _make_e2e_client()

    ctrl = client.post("/api/control", json={"scenario": "bidmc"})
    assert ctrl.status_code == 200
    assert ctrl.json()["scenario"] == "bidmc"
    assert ctrl.json()["source"] == "bidmc"

    # POST /api/control emite 1 muestra inmediata en `now`; enviamos 2 más posteriores (<= 5 s futuro).
    base_ts = datetime.now(timezone.utc)
    for idx in range(2):
        pkt = gateway.make_packet()
        assert pkt is not None
        pkt["measured_at"] = (base_ts + timedelta(milliseconds=200 * (idx + 1))).isoformat()
        gateway._consume(pkt, gateway._epoch)
        res = client.post("/api/v1/telemetry", json=pkt)
        assert res.status_code == 200

    state = client.get("/api/v1/state").json()
    assert state["latest"]["source"] == "bidmc"
    assert state["latest"]["co2"] is None
    assert state["latest"]["dose_rate"] is None
    assert state["latest"]["spo2"] is None
    assert state["latest"]["bp_sys"] is None
    assert state["latest"]["bp_dia"] is None
    assert state["latest"]["temp_c"] is None
    assert state["latest"]["hydration_pct"] is None
    assert state["assessment"]["level"] == "unknown"

    latest = client.get("/api/measurements/latest").json()[0]
    assert latest["source"] == "bidmc"
    assert latest["ambient_co2_mmhg"] is None
    assert latest["radiation_usvh"] is None
    assert latest["spo2_percent"] is None

    with client.websocket_connect("/telemetry") as ws:
        ws_msg = ws.receive_json()
        assert ws_msg["source"] == "bidmc"
        assert ws_msg["co2"] is None
        assert ws_msg["dose"] is None
        assert ws_msg["spo2"] is None


def test_e2e_v1_endpoints_routines_checkin_context_privacy_report_glossary_trends():
    client, _engine, _storage, _gateway = _make_e2e_client()

    glossary = client.get("/api/v1/glossary")
    assert glossary.status_code == 200
    g_data = glossary.json()
    assert "signals" in g_data and "co2" in g_data["signals"]
    assert "levels" in g_data and "normal" in g_data["levels"]
    assert "3.0 mmHg" in g_data["signals"]["co2"]["why_it_matters"]

    env_resp = client.post("/api/v1/context/environment", json={"environment": "rover"})
    assert env_resp.status_code == 200
    assert env_resp.json()["id"] == "rover"
    assert client.get("/api/control").json()["environment"] == "rover"

    now = datetime.now(timezone.utc)
    for idx in range(3):
        pkt = _sample_packet(now - timedelta(seconds=3 - idx), co2=5.1, rr=27.0, activity="unknown")
        assert client.post("/api/v1/telemetry", json=pkt).status_code == 200

    act_resp = client.post(
        "/api/v1/context/activity",
        json={"activity": "exercise", "note": "EVA de prueba"},
    )
    assert act_resp.status_code == 200
    assert act_resp.json()["activity"] == "exercise"

    evt_resp = client.post(
        "/api/v1/context/event",
        json={"kind": "solar", "phase": "peak", "shelter": True},
    )
    assert evt_resp.status_code == 200
    assert evt_resp.json()["kind"] == "solar"
    assert evt_resp.json()["shelter_active"] is True

    trends = client.get("/api/v1/trends?window_s=600")
    assert trends.status_code == 200
    assert len(trends.json()["points"]) == 3
    assert client.get("/api/v1/trends?window_s=0").status_code == 422

    routines_before = client.get("/api/v1/routines")
    assert routines_before.status_code == 200
    routine_ids = {item["id"]: item for item in routines_before.json()["routines"]}
    assert routine_ids["shelter_checklist"]["active"] is True

    done = client.post("/api/v1/routines/hydration/done")
    assert done.status_code == 200
    assert done.json()["points_awarded"] == 10
    assert client.post("/api/v1/routines/no_existe/done").status_code == 404

    # Calibración + deriva conductual en check-in.
    c1 = client.post(
        "/api/v1/checkin",
        json={"reaction_ms": [260, 270, 265], "sleep_hours": 7.5, "mood": 4},
    )
    assert c1.status_code == 200
    c2 = client.post(
        "/api/v1/checkin",
        json={"reaction_ms": [410, 530, 560], "sleep_hours": 5.0, "mood": 2},
    )
    assert c2.status_code == 200
    assert c2.json()["drift_detected"] is True
    assert "Hipótesis orientativa (escenario simulado)" in c2.json()["interpretation"]

    # Privacidad por defecto (False) oculta métricas conductuales en SBAR.
    rep_private = client.get("/api/v1/report").json()
    assert rep_private["share_behavioral"] is False
    assert "530" not in rep_private["markdown"]
    assert "retenidos a bordo" in rep_private["markdown"].lower()

    priv = client.post("/api/v1/privacy", json={"share_behavioral": True})
    assert priv.status_code == 200
    assert priv.json()["share_behavioral"] is True

    rep_shared = client.get("/api/v1/report").json()
    assert rep_shared["share_behavioral"] is True
    assert "[IA PREDICTION]" not in rep_shared["markdown"]
    assert "Hipótesis orientativa (escenario simulado)" in rep_shared["markdown"]

    # Muestra fresca con CO₂ elevado -> alerta vigente para ACK, bitácora y puntuación.
    fresh_alert = _sample_packet(
        datetime.now(timezone.utc) + timedelta(milliseconds=100),
        co2=5.5,
        rr=28.0,
        activity="rest",
    )
    assert client.post("/api/v1/telemetry", json=fresh_alert).status_code == 200
    ack = client.post("/api/v1/ack")
    assert ack.status_code == 200
    assert ack.json()["accepted"] is True
    assert client.get("/api/v1/state").json()["acknowledged"] is True
    assert len(client.get("/api/logs/").json()) >= 1


def test_e2e_control_sync_only():
    client, _engine, _storage, _gateway = _make_e2e_client()

    assert client.get("/").status_code == 404
    assert client.get("/ui/").status_code == 404

    ctrl = client.post(
        "/api/control",
        json={
            "environment": "base",
            "scenario": "solar_event",
            "solar_phase": "peak",
            "shelter": True,
        },
    )
    assert ctrl.status_code == 200
    ctrl_data = ctrl.json()
    assert ctrl_data["environment"] == "base"
    assert ctrl_data["scenario"] == "solar_event"
    assert ctrl_data["solar_phase"] == "peak"
    assert ctrl_data["shelter"] is True

    state = client.get("/api/v1/state").json()
    assert state["environment"]["id"] == "base"
    assert state["shelter_active"] is True
    assert state["external_event"] is not None
    assert state["external_event"]["phase"] == "peak"


def test_cli_run_parser_flags():
    import pytest

    parser = runner.build_parser()
    args_sim = parser.parse_args(
        ["--simulator", "--environment", "base", "--onboard-port", "8100", "--gateway-port", "8102"]
    )
    assert args_sim.simulator is True
    assert args_sim.tui is False
    assert args_sim.services_only is False
    assert args_sim.environment == "base"
    assert args_sim.onboard_port == 8100
    assert args_sim.gateway_port == 8102

    assert parser.parse_args(["--sim"]).simulator is True
    assert parser.parse_args(["--sim-tui"]).simulator is True
    assert parser.parse_args(["--ui-only"]).tui is True

    args_replay = parser.parse_args(["--tui", "--replay", "muestra.csv"])
    assert args_replay.tui is True
    assert args_replay.simulator is False
    assert args_replay.replay == Path("muestra.csv")

    with pytest.raises(SystemExit):
        parser.parse_args(["--web"])


def test_operational_tui_headless():
    import asyncio
    from textual.widgets import Button, Static, TabPane
    from astro.tui import AstroVitalsApp, MetricCard

    async def _run() -> None:
        app = AstroVitalsApp(onboard_url="http://127.0.0.1:8999")
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()

            cards = list(app.query(MetricCard))
            assert len(cards) == 8

            tab_ids = [pane.id for pane in app.query(TabPane)]
            assert tab_ids == [
                "tab-monitor",
                "tab-trends",
                "tab-checkin",
                "tab-routines",
                "tab-report",
                "tab-glossary",
            ]

            demo_btns = [btn.id for btn in app.query(Button) if (btn.id or "").startswith("scn-")]
            assert demo_btns == []

            bidmc_state = {
                "latest": {
                    "sample_id": "bidmc-test-1",
                    "measured_at": "2026-11-14T12:00:00+00:00",
                    "source": "bidmc",
                    "activity": "rest",
                    "hr": 76.0,
                    "rr": 16.0,
                    "spo2": 98.2,
                    "co2": None,
                    "dose_rate": None,
                    "bp_sys": None,
                    "bp_dia": None,
                    "temp_c": None,
                    "hydration_pct": None,
                },
                "history": [],
                "age_s": 1.0,
                "assessment": {
                    "level": "normal",
                    "hypothesis": "Hipótesis orientativa (escenario simulado): señal BIDMC parcial.",
                    "evidence": ["Canales ambientales sin señal en BIDMC."],
                    "next_step": "Mantener observación.",
                },
                "environment": {"id": "station", "name": "Estación"},
                "shelter_active": False,
                "acknowledged": False,
                "privacy": {"share_behavioral": False},
                "coach": {
                    "points": 0,
                    "streak": 0,
                    "badges": [],
                    "scoring_policy": "Solo participación",
                    "routines": [],
                },
                "ml": {"forecast": {}, "pattern": {}},
                "baseline": {},
                "co2_sensitivity": {},
                "projections": {"co2": {}, "radiation": {}},
                "events": [],
                "questions": [],
            }
            app.render_state(bidmc_state)
            await pilot.pause()

            for key in ("hr", "rr", "spo2", "temp_c", "bp_sys", "co2", "hydration_pct", "dose_rate"):
                assert app.query_one(f"#gauge-{key}", Static) is not None

            for widget_id in (
                "#oscilloscope-box",
                "#ml-braille-box",
                "#body-scanner-box",
                "#report-visual-cards",
                "#rxn-Visual-chart",
                "#braille-trend-hr",
                "#braille-trend-rr",
                "#braille-trend-co2",
                "#braille-trend-dose_rate",
            ):
                assert app.query_one(widget_id, Static) is not None

            for key in ("co2", "dose_rate", "bp_sys", "temp_c", "hydration_pct"):
                txt = str(app.query_one(f"#value-{key}", Static).render())
                assert "SIN SEÑAL (—)" in txt
                gauge_txt = str(app.query_one(f"#gauge-{key}", Static).render())
                assert "SIN SEÑAL" in gauge_txt

            hr_txt = str(app.query_one("#value-hr", Static).render())
            assert "76" in hr_txt
            assert "SIN SEÑAL" not in hr_txt

            osc_txt = str(app.query_one("#oscilloscope-box", Static).render())
            assert "BIO-LEAD II" in osc_txt
            assert "[IA PREDICTION]" not in osc_txt

            scan_txt = str(app.query_one("#body-scanner-box", Static).render())
            assert "BIO-SUIT 7 ZONAS" in scan_txt
            assert "SIN SEÑAL (—)" in scan_txt
            assert "[IA PREDICTION]" not in scan_txt

            hyp_txt = str(app.query_one("#hypothesis", Static).render())
            assert "[IA PREDICTION]" not in hyp_txt

            # Predicción y estado en lenguaje sencillo para el astronauta (sin nombres de modelo o slugs con '_')
            ml_active_state = dict(bidmc_state)
            ml_active_state["assessment"] = {
                "level": "normal",
                "hypothesis": "Hipótesis orientativa (escenario simulado): señales dentro de los rangos de demostración para el contexto actual.",
                "evidence": [
                    "Pulso 76 bpm · respiración 16/min.",
                    "Esta comprobación no equivale a una evaluación completa de salud.",
                    "Hipótesis orientativa (escenario simulado): señales compatibles con reposo estable respecto a la línea base personal.",
                ],
                "next_step": "Continuar observando las señales y su contexto.",
            }
            ml_active_state["ml"] = {
                "forecast": {
                    "available": True,
                    "status": "ok",
                    "forecast_hr": 80.2,
                    "persistence_hr": 76.0,
                    "interval_radius_bpm": 4.6,
                    "method": "Hipótesis orientativa (escenario simulado): RandomForest +60 s (heart_rate_forecast/colab-v1)",
                },
                "pattern": {
                    "available": True,
                    "status": "ok",
                    "pattern": "baseline_expected",
                    "score": 0.95,
                    "hypothesis": "Hipótesis orientativa (escenario simulado): señales compatibles con reposo estable respecto a la línea base personal.",
                },
            }
            ml_active_state["baseline"] = {"status": "ready", "hr": 72.0, "rr": 14.0}
            ml_active_state["co2_sensitivity"] = {
                "status": "insufficient_data",
                "reason": "Variación de CO₂ insuficiente (0.00 < 0.40 mmHg) para calibrar sensibilidad.",
            }
            ml_active_state["projections"] = {
                "co2": {"moving_avg_1h_mmhg": 2.0, "nasa_1h_ref_mmhg": 3.0, "reason": "tendencia_no_ascendente"},
                "radiation": {"dose_total_usv": 0.5, "projected_without_shelter": 1.2, "projected_with_shelter": 0.42},
            }
            app.render_state(ml_active_state)
            await pilot.pause()
            ml_txt = str(app.query_one("#ml-summary", Static).render())
            ev_txt = str(app.query_one("#evidence", Static).render())
            proj_txt = str(app.query_one("#projections-box", Static).render())
            hyp_clean_txt = str(app.query_one("#hypothesis", Static).render())
            assert "AHORA:" in ml_txt and "EN 1M:" in ml_txt
            assert "EN REPOSO NORMAL" in ml_txt
            for panel_txt in (ml_txt, ev_txt, proj_txt, hyp_clean_txt):
                for forbidden in (
                    "heart_rate_forecast",
                    "colab-v1",
                    "baseline_expected",
                    "RandomForest",
                    "tendencia_no_ascendente",
                    "reglas de demostración",
                    "no equivale a una evaluación completa de salud",
                ):
                    assert forbidden not in panel_txt
            # Restaurar estado BIDMC previo para seguir probando sensores ausentes
            app.render_state(bidmc_state)
            await pilot.pause()

            # Hover y tooltips interactivos en consola operacional
            assert app.query_one("#hover-inspector", Static) is not None
            hr_tip = str(app.query_one("#card-hr").tooltip or "")
            assert "Frecuencia cardíaca" in hr_tip
            assert "76" in hr_tip
            assert "null" not in hr_tip.lower()
            co2_tip = str(app.query_one("#card-co2").tooltip or "")
            assert "SIN SEÑAL" in co2_tip
            assert "OCHMO-TB-004" in co2_tip
            assert "null" not in co2_tip.lower()
            await pilot.hover("#card-co2")
            await pilot.pause()
            insp_txt = str(app.query_one("#hover-inspector", Static).render())
            assert "ppCO₂" in insp_txt or "CO₂" in insp_txt
            assert "null" not in insp_txt.lower()
            assert "[IA PREDICTION]" not in insp_txt

            # Sin señal de pulso -> osciloscopio no inventa onda
            no_hr_state = dict(bidmc_state)
            no_hr_state["latest"] = dict(bidmc_state["latest"], hr=None)
            app.render_state(no_hr_state)
            await pilot.pause()
            no_hr_osc = str(app.query_one("#oscilloscope-box", Static).render())
            assert "SIN SEÑAL (—)" in no_hr_osc

    asyncio.run(_run())


def test_simulator_tui_headless():
    import asyncio
    from textual.widgets import Button, Static
    from astro.sim_tui import SimulatorTUIApp

    async def _run() -> None:
        app = SimulatorTUIApp(
            onboard_url="http://127.0.0.1:8999",
            gateway_url="http://127.0.0.1:8998",
        )
        async with app.run_test(size=(130, 42)) as pilot:
            await pilot.pause()

            for sc in ("rest", "exercise", "cabin", "co2_ramp", "solar_event", "signal_loss", "bidmc"):
                assert app.query_one(f"#scn-{sc}", Button) is not None

            for env in ("station", "transit", "rover", "base"):
                assert app.query_one(f"#env-{env}", Button) is not None

            for phase in ("watch", "arrival", "peak", "decay"):
                assert app.query_one(f"#phase-{phase}", Button) is not None

            for key in ("hr", "rr", "co2", "dose", "spo2", "bp", "temp", "hyd"):
                assert app.query_one(f"#toggle-null-{key}", Button) is not None

            assert app.query_one("#bar-co2", Static) is not None
            assert app.query_one("#sim-hover-inspector", Static) is not None
            await pilot.hover("#scn-solar_event")
            await pilot.pause()
            sim_insp = str(app.query_one("#sim-hover-inspector", Static).render())
            assert "DONKI" in sim_insp or "Solar" in sim_insp

            await pilot.click("#toggle-null-co2")
            await pilot.hover("#toggle-null-co2")
            await pilot.pause()
            assert app.suit_values["co2"] is None
            assert app._build_manual_payload()["co2"] is None
            assert "SIN SEÑAL (—)" in str(app.query_one("#val-co2", Static).render())
            assert "SIN SEÑAL" in str(app.query_one("#bar-co2", Static).render())
            toggle_insp = str(app.query_one("#sim-hover-inspector", Static).render())
            assert "ppCO₂" in toggle_insp or "CO₂" in toggle_insp
            assert "null" not in toggle_insp.lower()
            preview_txt = str(app.query_one("#manual-packet-preview", Static).render())
            assert "SIN SEÑAL (—)" in preview_txt
            assert "null" not in preview_txt.lower()

    asyncio.run(_run())
