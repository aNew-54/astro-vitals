import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from astro.gateway import ControlUpdate, Gateway, create_app, load_bidmc


def test_bidmc_mapping_preserves_missing_values(tmp_path):
    path = tmp_path / "record.csv"
    path.write_text("Time [s], HR, PULSE, RESP, SpO2\n0,94,93,25,97\n1,NaN,90,NaN,NaN\n", encoding="utf-8")
    rows = load_bidmc(path)
    assert rows == [
        {"original_time_s": 0.0, "hr": 94.0, "rr": 25.0},
        {"original_time_s": 1.0, "hr": None, "rr": None},
    ]
    node = Gateway(bidmc_path=path)
    node.update(ControlUpdate(scenario="bidmc"))
    packet = node.make_packet()
    assert packet["source"] == "bidmc"
    assert packet["co2"] is None and packet["dose_rate"] is None
    assert packet["activity"] == "unknown"
    assert packet["original_time_s"] == 0


def test_shelter_changes_dose_only_and_resets_on_new_scenario():
    exposed, sheltered = Gateway(), Gateway()
    for node in (exposed, sheltered):
        node.update(ControlUpdate(scenario="solar"))
        for _ in range(8):
            node.make_packet()
    sheltered.update(ControlUpdate(shelter=True))
    first, second = exposed.make_packet(), sheltered.make_packet()
    assert second["dose_rate"] < first["dose_rate"]
    assert (second["hr"], second["rr"], second["co2"]) == (first["hr"], first["rr"], first["co2"])
    sheltered.update(ControlUpdate(scenario="rest"))
    assert sheltered.shelter is False


def test_retry_preserves_packet_and_replay_stops_at_eof(tmp_path):
    path = tmp_path / "record.csv"
    path.write_text("Time [s], HR, RESP\n0,94,25\n", encoding="utf-8")
    node = Gateway(bidmc_path=path)
    node.update(ControlUpdate(scenario="bidmc"))
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(503 if len(sent) == 1 else 200, json={})

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await node.tick(client)
            assert node.sent_count == 0 and node.control()["remaining_samples"] == 1
            await node.tick(client)
            await node.tick(client)

    asyncio.run(exercise())
    assert len(sent) == 2 and sent[0] == sent[1]
    assert node.sent_count == 1 and node.paused
    assert node.control()["remaining_samples"] == 0
    assert "finalizado" in node.error
    previous_epoch = node._epoch
    with TestClient(create_app(node, start_worker=False)) as client:
        status = client.post("/control", json={"scenario": "bidmc"}).json()
    assert not status["paused"] and status["error"] is None
    assert status["remaining_samples"] == 1
    assert node._epoch == previous_epoch + 1
    restarted = node.make_packet()
    assert restarted["original_time_s"] == 0
    assert restarted["sample_id"] != sent[-1]["sample_id"]


def test_invalid_control_is_rejected_and_missing_record_is_visible(tmp_path):
    node = Gateway(bidmc_path=tmp_path / "absent.csv")
    with TestClient(create_app(node, start_worker=False)) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/control", json={"scenario": "unknown"}).status_code == 422
        status = client.post("/control", json={"scenario": "bidmc"}).json()
        assert status["paused"] and "No se pudo abrir" in status["error"]
