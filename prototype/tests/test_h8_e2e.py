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


def test_e2e_control_sync_and_static_web_serving():
    client, _engine, _storage, _gateway = _make_e2e_client()

    for path in ("/", "/ui/", "/ui"):
        page = client.get(path)
        assert page.status_code == 200
        assert "ASTRA" in page.text
        assert "[IA PREDICTION]" not in page.text

    for asset in ("/css/styles.css", "/js/model.js", "/js/api.js", "/js/app.js", "/ui/js/modules.js"):
        resp = client.get(asset)
        assert resp.status_code == 200, f"Fallo sirviendo estático {asset}"
        assert "[IA PREDICTION]" not in resp.text

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
    parser = runner.build_parser()
    args_web = parser.parse_args(["--web", "--environment", "base", "--onboard-port", "8100", "--gateway-port", "8102"])
    assert args_web.web is True
    assert args_web.tui is False
    assert args_web.services_only is False
    assert args_web.environment == "base"
    assert args_web.onboard_port == 8100
    assert args_web.gateway_port == 8102

    args_replay = parser.parse_args(["--tui", "--replay", "muestra.csv"])
    assert args_replay.tui is True
    assert args_replay.replay == Path("muestra.csv")
