from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from astro.api import create_app
from astro.contracts import Telemetry
from astro.engine import ConflictError, Engine


NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def sample(id="first", at=NOW, **overrides):
    values = dict(sample_id=id, measured_at=at, hr=74, rr=15, co2=1.0,
                  dose_rate=3.6, activity="rest", source="simulated")
    values.update(overrides)
    return Telemetry(**values)


def test_empty_and_stale_are_not_current_health_assessments():
    engine = Engine()
    assert engine.state(NOW)["assessment"]["level"] == "unknown"
    engine.ingest(sample(), NOW)
    assert engine.state(NOW)["assessment"]["level"] == "normal"
    stale = engine.state(NOW + timedelta(seconds=6))
    assert stale["assessment"]["level"] == "unknown"
    assert stale["assessment"]["forecast_hr"] is None
    assert not stale["dose_complete"]


def test_duplicate_is_idempotent_and_conflict_rejected():
    engine = Engine()
    engine.ingest(sample(), NOW)
    second = sample("second", NOW + timedelta(seconds=1))
    engine.ingest(second, NOW + timedelta(seconds=1))
    before = engine.state(NOW + timedelta(seconds=1))
    assert engine.ingest(second, NOW + timedelta(seconds=1))["duplicate"]
    after = engine.state(NOW + timedelta(seconds=1))
    assert before["dose_total"] == after["dose_total"]
    assert after["received_count"] == 2
    with pytest.raises(ConflictError):
        engine.ingest(sample("second", NOW + timedelta(seconds=1), hr=99), NOW)


def test_trapezoid_units_and_gap_are_not_integrated_as_zero():
    engine = Engine()
    engine.ingest(sample(dose_rate=3600), NOW)
    second_at = NOW + timedelta(seconds=2)
    engine.ingest(sample("second", second_at, dose_rate=7200), second_at)
    assert engine.state(second_at)["dose_total"] == pytest.approx(3.0)
    later = NOW + timedelta(seconds=20)
    engine.ingest(sample("gap", later, dose_rate=7200), later)
    state = engine.state(later)
    assert state["dose_total"] == pytest.approx(3.0)
    assert not state["dose_complete"]
    end = later + timedelta(seconds=1)
    engine.ingest(sample("refuge", end, dose_rate=0.1), end)
    assert engine.state(end)["dose_total"] >= state["dose_total"]


def test_missing_signal_not_filled_and_no_false_zero_exposure():
    engine = Engine()
    engine.ingest(sample(hr=None, dose_rate=None), NOW)
    state = engine.state(NOW)
    assert state["latest"]["hr"] is None
    assert state["assessment"]["level"] == "unknown"
    assert state["assessment"]["forecast_hr"] is None
    assert not state["dose_complete"]


def test_context_changes_interpretation_and_solar_is_independent():
    engine = Engine()
    engine.ingest(sample(hr=130, activity="exercise"), NOW)
    assert engine.state(NOW)["assessment"]["level"] == "normal"
    later = NOW + timedelta(seconds=1)
    engine.ingest(sample("recovery", later, hr=130, activity="recovery"), later)
    assert engine.state(later)["assessment"]["level"] == "watch"
    later += timedelta(seconds=1)
    engine.ingest(sample("solar", later, hr=None, dose_rate=45), later)
    assert engine.state(later)["assessment"]["level"] == "alert"
    assert "Radiación" in engine.state(later)["assessment"]["title"]


def test_acknowledgement_does_not_resolve_condition_or_duplicate():
    engine = Engine()
    engine.ingest(sample(co2=5, rr=26), NOW)
    assert engine.acknowledge(NOW)["accepted"]
    assert engine.acknowledge(NOW)["duplicate"]
    state = engine.state(NOW)
    assert state["assessment"]["level"] == "alert"
    assert len(state["events"]) == 2
    with pytest.raises(ConflictError):
        engine.acknowledge(NOW + timedelta(seconds=8))


def test_bidmc_does_not_fabricate_environment_or_space_hypothesis():
    engine = Engine()
    engine.ingest(sample(source="bidmc", co2=None, dose_rate=None, activity="unknown", original_time_s=0), NOW)
    state = engine.state(NOW)
    assert state["assessment"]["level"] == "unknown"
    assert "Registro real" in state["assessment"]["title"]
    assert state["latest"]["co2"] is None
    assert state["latest"]["original_time_s"] == 0


def test_api_validation_and_ordering():
    client = TestClient(create_app())
    now = datetime.now(timezone.utc)
    payload = sample(at=now).model_dump(mode="json")
    assert client.get("/health").status_code == 200
    assert client.post("/api/v1/telemetry", json=payload).status_code == 200
    assert client.post("/api/v1/telemetry", json=payload).json()["duplicate"]
    future = sample("future", now + timedelta(minutes=1)).model_dump(mode="json")
    assert client.post("/api/v1/telemetry", json=future).status_code == 422
    old = sample("old", now - timedelta(seconds=1)).model_dump(mode="json")
    assert client.post("/api/v1/telemetry", json=old).status_code == 409
    invalid = dict(payload, sample_id="invalid", source="bidmc", co2=5)
    assert client.post("/api/v1/telemetry", json=invalid).status_code == 422
    naive = dict(payload, sample_id="naive", measured_at="2026-10-28T12:00:00")
    assert client.post("/api/v1/telemetry", json=naive).status_code == 422
