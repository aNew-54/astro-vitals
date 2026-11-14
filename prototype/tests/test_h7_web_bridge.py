from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

from astro.engine import Engine
from astro.gateway import Gateway, create_app as create_gateway_app
from astro.storage import Storage
from astro.web_bridge import create_web_router


def test_sqlite_seed_and_null_preservation(tmp_path):
    db_path = tmp_path / "astro.db"
    storage = Storage(db_path)

    astronauts = storage.get_astronauts()
    assert len(astronauts) == 1
    assert astronauts[0] == {
        "id": 1,
        "code": "ASTRA-001",
        "name": "Cmdr. Elena Vance",
        "role": "Mission Commander",
        "mission": "ASTRA-01",
        "mission_day": 1,
        "age": 42,
        "blood_type": "O+",
        "height_cm": 170.0,
        "weight_kg": 65.0,
        "status": "nominal",
    }

    bidmc_sample = {
        "sample_id": "bidmc-001",
        "measured_at": "2026-11-14T12:00:00+00:00",
        "hr": 94.0,
        "rr": 25.0,
        "co2": None,
        "dose_rate": None,
        "spo2": None,
        "bp_sys": None,
        "bp_dia": None,
        "temp_c": None,
        "hydration_pct": None,
        "activity": "unknown",
        "source": "bidmc",
        "original_time_s": 0.0,
    }
    first = storage.record_telemetry(bidmc_sample, assessment={"level": "unknown"}, scenario="bidmc")
    duplicate = storage.record_telemetry(bidmc_sample, assessment={"level": "unknown"}, scenario="bidmc")
    assert duplicate["id"] == first["id"]

    signal_loss_sample = {
        "sample_id": "loss-001",
        "measured_at": "2026-11-14T12:00:02+00:00",
        "hr": None,
        "rr": None,
        "co2": 2.0,
        "dose_rate": 0.0,
        "eva_load": 0.0,
        "source": "simulated",
    }
    loss_row = storage.record_telemetry(signal_loss_sample, scenario="signal_loss")

    # Verificación directa sobre SQLite: ausentes son NULL (None), nunca 0.
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM measurements ORDER BY id ASC").fetchall()
        assert len(rows) == 2

        raw_bidmc = dict(rows[0])
        assert raw_bidmc["heart_rate_bpm"] == 94.0
        assert raw_bidmc["respiratory_rate_rpm"] == 25.0
        for null_col in (
            "systolic_bp",
            "diastolic_bp",
            "spo2_percent",
            "body_temp_c",
            "ambient_co2_mmhg",
            "hydration_percent",
            "radiation_usvh",
            "fatigue_index",
            "countermeasures_percent",
            "eva_load",
        ):
            assert raw_bidmc[null_col] is None, f"{null_col} debe ser NULL en SQLite"

        raw_loss = dict(rows[1])
        assert raw_loss["heart_rate_bpm"] is None
        assert raw_loss["respiratory_rate_rpm"] is None
        assert raw_loss["radiation_usvh"] == 0.0
        assert raw_loss["eva_load"] == 0.0

    # Verificación vía JSON REST y contrato WS
    app = FastAPI()
    app.include_router(create_web_router(storage=storage))
    client = TestClient(app)
    res_list = client.get("/api/measurements/")
    assert res_list.status_code == 200
    items = res_list.json()
    assert len(items) == 2
    bidmc_json = next(item for item in items if item["sample_id"] == "bidmc-001")
    assert bidmc_json["ambient_co2_mmhg"] is None
    assert bidmc_json["radiation_usvh"] is None
    assert bidmc_json["spo2_percent"] is None

    ws_payload = storage.to_ws_payload(first)
    assert ws_payload["type"] == "telemetry"
    assert ws_payload["hr"] == 94.0
    assert ws_payload["rr"] == 25.0
    assert ws_payload["co2"] is None
    assert ws_payload["dose"] is None
    assert ws_payload["spo2"] is None

    ws_loss = storage.to_ws_payload(loss_row)
    assert ws_loss["hr"] is None
    assert ws_loss["rr"] is None
    assert ws_loss["dose"] == 0.0
    assert ws_loss["eva_load"] == 0.0

    # Concurrencia básica entre hilos sobre el mismo archivo SQLite
    def write_worker(idx: int) -> int:
        created = storage.create_measurement({"hr": 70.0 + idx, "co2": None, "source": "simulated"})
        return created["id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(write_worker, range(8)))
    assert len(set(ids)) == 8


def test_no_ia_prediction_string():
    storage = Storage(":memory:")

    # 1. Insight critical que intenta inyectar [IA PREDICTION]
    ins1 = storage.create_insight(
        {
            "astronaut_id": 1,
            "risk_level": "critical",
            "category": "co2",
            "description": "[IA PREDICTION]: Posible hipercapnia por acumulación de CO2",
            "recommendation": "[IA PREDICTION] Revisar depuradores",
        }
    )
    assert "[IA PREDICTION]" not in ins1["description"]
    assert "[IA PREDICTION]" not in ins1["recommendation"]
    assert "Hipótesis orientativa (escenario simulado)" in ins1["description"]

    # 2. Insight critical sin etiqueta prohibida: su alerta sigue usando el prefijo obligatorio
    ins2 = storage.create_insight(
        {
            "astronaut_id": 1,
            "risk_level": "critical",
            "category": "radiation",
            "description": "Tasa simulada por encima del umbral de demostración",
            "recommendation": "Activar refugio simulado",
        }
    )
    assert "[IA PREDICTION]" not in ins2["description"]

    alerts = storage.list_alerts(astronaut_id=1)
    assert len(alerts) == 2
    for alert in alerts:
        assert "[IA PREDICTION]" not in alert["message"]
        assert "[IA PREDICTION]" not in (alert["suggested_action"] or "")
        assert alert["message"].startswith("Hipótesis orientativa (escenario simulado)")

    # 3. record_telemetry con watch y alert sanitiza y deduplica alertas activas
    storage.record_telemetry(
        {
            "sample_id": "t-alert-1",
            "measured_at": "2026-11-14T12:10:00+00:00",
            "hr": 115.0,
            "rr": 26.0,
            "co2": 5.2,
            "dose_rate": 0.5,
            "source": "simulated",
        },
        assessment={
            "level": "alert",
            "title": "[IA PREDICTION] Cambio respiratorio y ambiental",
            "evidence": ["[IA PREDICTION]: CO2 5.2 mmHg y respiración 26/min"],
            "next_step": "Verificar sensores y contexto de cabina.",
        },
        scenario="cabin",
    )
    # Segunda muestra con la misma evaluación activa: no debe duplicar la alerta
    storage.record_telemetry(
        {
            "sample_id": "t-alert-2",
            "measured_at": "2026-11-14T12:10:01+00:00",
            "hr": 116.0,
            "rr": 26.0,
            "co2": 5.3,
            "dose_rate": 0.5,
            "source": "simulated",
        },
        assessment={
            "level": "alert",
            "title": "[IA PREDICTION] Cambio respiratorio y ambiental",
            "evidence": ["CO2 5.3 mmHg"],
            "next_step": "Verificar sensores y contexto de cabina.",
        },
        scenario="cabin",
    )
    all_alerts = storage.list_alerts(astronaut_id=1)
    assert len(all_alerts) == 3  # 2 previas de insights + 1 nueva de telemetría
    latest_alert = all_alerts[0]
    assert latest_alert["severity"] == "critical"
    assert "[IA PREDICTION]" not in latest_alert["message"]
    assert latest_alert["message"].startswith("Hipótesis orientativa (escenario simulado)")

    # Al reconocerla y cambiar a watch, se genera nueva alerta warning
    storage.acknowledge_alert(latest_alert["id"])
    storage.record_telemetry(
        {
            "sample_id": "t-watch-1",
            "measured_at": "2026-11-14T12:10:02+00:00",
            "hr": 108.0,
            "rr": 18.0,
            "co2": 2.0,
            "dose_rate": 0.5,
            "source": "simulated",
        },
        assessment={
            "level": "watch",
            "title": "Hipótesis: pulso fuera del patrón de demo",
            "next_step": "Confirmar actividad.",
        },
        scenario="rest",
    )
    all_alerts = storage.list_alerts(astronaut_id=1)
    assert len(all_alerts) == 4
    assert all_alerts[0]["severity"] == "warning"
    assert all_alerts[0]["message"].startswith("Hipótesis orientativa (escenario simulado)")

    for insight in storage.get_insights():
        assert "[IA PREDICTION]" not in insight["description"]
        assert "[IA PREDICTION]" not in insight["recommendation"]
        assert "Hipótesis orientativa (escenario simulado)" in insight["description"]


def test_web_bridge_rest_and_websocket(tmp_path):
    storage = Storage(tmp_path / "bridge.db")
    app = FastAPI()
    app.include_router(create_web_router(storage=storage))

    with TestClient(app) as client:
        # Astronauts
        res_astros = client.get("/api/astronauts/")
        assert res_astros.status_code == 200
        assert res_astros.json()[0]["code"] == "ASTRA-001"

        assert client.get("/api/astronauts/1").status_code == 200
        assert client.get("/api/astronauts/999").status_code == 404

        res_new_astro = client.post(
            "/api/astronauts/",
            json={
                "code": "ASTRA-002",
                "name": "Dr. Mateo Cruz",
                "role": "Flight Engineer",
                "mission": "ASTRA-01",
                "mission_day": 2,
            },
        )
        assert res_new_astro.status_code == 201
        assert res_new_astro.json()["code"] == "ASTRA-002"

        res_dup_astro = client.post(
            "/api/astronauts/",
            json={
                "code": "ASTRA-002",
                "name": "Duplicate",
                "role": "Engineer",
                "mission": "ASTRA-01",
            },
        )
        assert res_dup_astro.status_code == 409

        # Latest vacío antes de medir
        assert client.get("/api/measurements/latest").json() == []

        # Control fallback limpio sin pasarela
        ctrl_get = client.get("/api/control")
        assert ctrl_get.status_code == 200
        assert ctrl_get.json()["scenario"] == "rest"
        assert ctrl_get.json()["environment"] == "station"

        # WebSocket: primero no_data, luego telemetría tras persistir medición con None
        with client.websocket_connect("/telemetry") as ws:
            first_msg = ws.receive_json()
            assert first_msg == {"type": "no_data"}

            res_meas = client.post(
                "/api/measurements/",
                json={
                    "astronaut_id": 1,
                    "hr": 82.0,
                    "rr": 17.0,
                    "co2": None,
                    "dose_rate": None,
                    "spo2": None,
                    "source": "bidmc",
                    "scenario": "bidmc",
                },
            )
            assert res_meas.status_code == 201
            created_meas = res_meas.json()
            assert created_meas["ambient_co2_mmhg"] is None
            assert created_meas["radiation_usvh"] is None

            second_msg = ws.receive_json()
            assert second_msg["type"] == "telemetry"
            assert second_msg["measurement_id"] == created_meas["id"]
            assert second_msg["hr"] == 82.0
            assert second_msg["rr"] == 17.0
            assert second_msg["co2"] is None
            assert second_msg["dose"] is None
            assert second_msg["spo2"] is None
            assert second_msg["sys"] is None

        # Reconexión WS con dato ya existente: responde de inmediato con telemetría
        with client.websocket_connect("/telemetry") as ws_reconnect:
            immediate = ws_reconnect.receive_json()
            assert immediate["type"] == "telemetry"
            assert immediate["measurement_id"] == created_meas["id"]

        # GET measurements & latest
        assert len(client.get("/api/measurements/?astronaut_id=1&limit=10").json()) == 1
        latest = client.get("/api/measurements/latest").json()
        assert len(latest) == 1
        assert latest[0]["ambient_co2_mmhg"] is None

        # Alerts + ACK
        res_alert = client.post(
            "/api/alerts/",
            json={
                "astronaut_id": 1,
                "severity": "warning",
                "metric": "hr",
                "zone": "cardiovascular",
                "message": "Pulso elevado en simulación",
                "suggested_action": "Observar tendencia",
            },
        )
        assert res_alert.status_code == 201
        alert_id = res_alert.json()["id"]
        assert len(client.get("/api/alerts/?acknowledged=false").json()) == 1
        res_ack = client.patch(f"/api/alerts/{alert_id}/ack")
        assert res_ack.status_code == 200
        assert res_ack.json()["acknowledged"] is True
        assert client.patch("/api/alerts/9999/ack").status_code == 404

        # Logs
        res_log = client.post(
            "/api/logs/",
            json={
                "astronaut_id": 1,
                "zone": "cabin",
                "action": "Revisión de depurador CO2",
                "metrics": {"hr": 82.0, "co2": None},
            },
        )
        assert res_log.status_code == 201
        logs = client.get("/api/logs/?astronaut_id=1&limit=10").json()
        assert len(logs) == 1
        assert logs[0]["zone"] == "cabin"

        # Insights
        res_insight = client.post(
            "/api/insights/",
            json={
                "astronaut_id": 1,
                "risk_level": "critical",
                "category": "cabin",
                "description": "[IA PREDICTION] Aumento simulado de CO2",
                "recommendation": "Revisar ventilación",
            },
        )
        assert res_insight.status_code == 201
        insights = client.get("/api/insights/?limit=10").json()
        assert len(insights) == 1
        assert "[IA PREDICTION]" not in insights[0]["description"]
        critical_alerts = client.get("/api/alerts/?severity=critical").json()
        assert len(critical_alerts) == 1
        assert critical_alerts[0]["message"].startswith("Hipótesis orientativa (escenario simulado)")


def test_control_syncs_gateway_and_engine(tmp_path):
    storage = Storage(tmp_path / "sync.db")
    engine = Engine()
    gateway = Gateway()

    app = FastAPI()
    app.include_router(create_web_router(engine=engine, storage=storage, gateway=gateway))

    with TestClient(app) as client:
        res_solar = client.post(
            "/api/control",
            json={
                "scenario": "solar_event",
                "environment": "transit",
                "solar_phase": "arrival",
            },
        )
        assert res_solar.status_code == 200
        body = res_solar.json()
        assert body["scenario"] == "solar_event"
        assert body["environment"] == "transit"
        assert body["solar_phase"] == "arrival"
        assert engine.environment == "transit"
        assert engine.external_event is not None
        assert engine.external_event["phase"] == "arrival"
        assert engine.received_count == 1
        assert len(storage.list_measurements()) == 1

        res_rest = client.post("/api/control", json={"scenario": "rest"})
        assert res_rest.status_code == 200
        assert res_rest.json()["scenario"] == "rest"
        assert res_rest.json()["environment"] == "transit"
        assert engine.external_event is None
        assert engine.received_count == 2


def test_control_gateway_url_and_stub_safety(monkeypatch):
    gw_app = create_gateway_app(Gateway(), start_worker=False)
    transport = httpx.ASGITransport(app=gw_app)
    orig_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return orig_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_async_client)

    engine = Engine()
    app = FastAPI()
    app.include_router(
        create_web_router(
            engine=engine,
            storage=Storage(":memory:"),
            gateway_url="http://gateway.local",
        )
    )
    with TestClient(app) as client:
        res_get = client.get("/api/control")
        assert res_get.status_code == 200
        assert res_get.json()["scenario"] == "rest"

        res_post = client.post(
            "/api/control",
            json={"scenario": "solar_event", "environment": "base", "solar_phase": "peak"},
        )
        assert res_post.status_code == 200
        assert res_post.json()["scenario"] == "solar_event"
        assert res_post.json()["environment"] == "base"
        assert engine.environment == "base"
        assert engine.external_event["phase"] == "peak"

    # Stub gateway sin _consume / sent_count no debe romperse
    class MinimalStubGateway:
        def __init__(self) -> None:
            self.scenario = "rest"
            self.paused = False
            self.shelter = False

        def control(self) -> dict:
            return {"scenario": self.scenario, "paused": self.paused, "shelter": self.shelter}

        def update(self, change) -> dict:
            if getattr(change, "scenario", None) is not None:
                self.scenario = change.scenario
            if getattr(change, "paused", None) is not None:
                self.paused = change.paused
            if getattr(change, "shelter", None) is not None:
                self.shelter = change.shelter
            return self.control()

        def make_packet(self) -> dict:
            return {
                "sample_id": "stub-1",
                "measured_at": "2026-11-14T12:00:00+00:00",
                "hr": 75.0,
                "rr": 15.0,
                "co2": 2.0,
                "dose_rate": 0.5,
                "activity": "rest",
                "source": "simulated",
            }

    stub = MinimalStubGateway()
    stub_engine = Engine()
    stub_storage = Storage(":memory:")
    stub_app = FastAPI()
    stub_app.include_router(create_web_router(engine=stub_engine, storage=stub_storage, gateway=stub))

    with TestClient(stub_app) as client:
        res = client.post("/api/control", json={"scenario": "exercise"})
        assert res.status_code == 200
        assert res.json()["scenario"] == "exercise"
        assert stub_engine.received_count == 1
        assert len(stub_storage.list_measurements()) == 1
