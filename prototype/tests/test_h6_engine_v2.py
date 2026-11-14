"""Pruebas unitarias e integración para contratos v2, motor analítico y pasarela H6."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from astro.contracts import (
    ActivityDeclaration,
    CheckInRequest,
    ContextEventRequest,
    EnvironmentUpdate,
    PrivacyUpdate,
    Telemetry,
)
from astro.engine import Engine, compute_co2_sensitivity
from astro.gateway import ControlUpdate, Gateway

T0 = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)


def make_sample(
    sample_id: str = "s-0",
    at: datetime = T0,
    **overrides,
) -> Telemetry:
    data = {
        "sample_id": sample_id,
        "measured_at": at,
        "hr": 72.0,
        "rr": 14.0,
        "co2": 2.0,
        "dose_rate": 0.5,
        "activity": "rest",
        "source": "simulated",
    }
    data.update(overrides)
    return Telemetry(**data)


def test_contracts_optional_fields_and_bidmc_null():
    valid = Telemetry(
        sample_id="ext-1",
        measured_at=T0,
        hr=76.0,
        rr=15.0,
        co2=2.2,
        dose_rate=0.8,
        activity="rest",
        source="replayed",
        crew_id="CREW-01",
        location_id="HAB-A",
        spo2=98.4,
        bp_sys=118.0,
        bp_dia=76.0,
        temp_c=36.7,
        hydration_pct=84.0,
        extras={"sensor_status": "ok", "motion_g": 0.12, "dropout_flag": None},
        source_ref="wearable_sim_01.jsonl",
    )
    assert valid.source == "replayed"
    assert valid.spo2 == 98.4
    assert valid.extras == {"sensor_status": "ok", "motion_g": 0.12, "dropout_flag": None}

    measured = make_sample("m-1", source="measured", crew_id="ASTRA-001")
    assert measured.source == "measured"

    # BIDMC válido mantiene co2 y dose_rate en None sin rellenar con 0.
    bidmc_ok = Telemetry(
        sample_id="bidmc-ok",
        measured_at=T0,
        hr=84.0,
        rr=18.0,
        co2=None,
        dose_rate=None,
        activity="unknown",
        source="bidmc",
        original_time_s=0.0,
    )
    assert bidmc_ok.co2 is None and bidmc_ok.dose_rate is None
    assert bidmc_ok.spo2 is None and bidmc_ok.temp_c is None

    # BIDMC rechaza co2 o dose_rate no nulos.
    with pytest.raises(ValidationError):
        Telemetry(
            sample_id="bidmc-bad-co2",
            measured_at=T0,
            hr=84.0,
            rr=18.0,
            co2=2.0,
            dose_rate=None,
            activity="unknown",
            source="bidmc",
        )
    with pytest.raises(ValidationError):
        Telemetry(
            sample_id="bidmc-bad-dose",
            measured_at=T0,
            hr=84.0,
            rr=18.0,
            co2=None,
            dose_rate=0.5,
            activity="unknown",
            source="bidmc",
        )

    # extras rechaza claves vacías y valores no finitos.
    with pytest.raises(ValidationError):
        make_sample("bad-key-1", extras={"": 1.0})
    with pytest.raises(ValidationError):
        make_sample("bad-key-2", extras={"   ": "ok"})
    with pytest.raises(ValidationError):
        make_sample("bad-nan", extras={"motion_g": float("nan")})
    with pytest.raises(ValidationError):
        make_sample("bad-inf", extras={"motion_g": float("inf")})

    # Nuevos modelos Pydantic de control y check-in.
    checkin = CheckInRequest(reaction_ms=[240.0, 255.0, 260.0], mood=4)
    assert checkin.source == "declared"
    with pytest.raises(ValidationError):
        CheckInRequest(reaction_ms=[])
    with pytest.raises(ValidationError):
        CheckInRequest(reaction_ms=[220.0, -5.0])
    with pytest.raises(ValidationError):
        CheckInRequest(reaction_ms=[220.0], mood=6)

    decl = ActivityDeclaration(activity="exercise", started_at=T0, note="Cinta")
    assert decl.activity == "exercise"
    ctx_req = ContextEventRequest(kind="solar", phase="arrival", shelter=True)
    assert ctx_req.shelter is True
    assert PrivacyUpdate(share_behavioral=True).share_behavioral is True
    assert EnvironmentUpdate(environment="rover").environment == "rover"


def test_personal_baseline_calibration_and_fixed():
    engine = Engine()
    assert engine.baseline["status"] == "calibrando"
    assert engine.baseline["hr"] is None

    # Ejercicio y BIDMC no deben calibrar la línea base.
    t = T0
    for i in range(130):
        t = T0 + timedelta(seconds=i)
        engine.ingest(
            make_sample(f"ex-{i}", t, hr=145.0, rr=28.0, activity="exercise"),
            t,
        )
    assert engine.baseline["status"] == "calibrando"

    t_bidmc = t + timedelta(seconds=1)
    engine.ingest(
        make_sample(
            "bidmc-ignore",
            t_bidmc,
            hr=68.0,
            rr=14.0,
            co2=None,
            dose_rate=None,
            activity="unknown",
            source="bidmc",
        ),
        t_bidmc,
    )
    assert engine.baseline["status"] == "calibrando"

    # Muestras de reposo con hr/rr faltantes no calibran.
    t_missing = t_bidmc + timedelta(seconds=1)
    engine.ingest(make_sample("miss-rest", t_missing, hr=None, rr=14.0, activity="rest"), t_missing)
    assert engine.baseline["status"] == "calibrando"

    # 120 muestras válidas de reposo calibran la línea base.
    base_start = t_missing + timedelta(seconds=1)
    for i in range(120):
        ts = base_start + timedelta(seconds=i)
        hr_val = 70.0 + (i % 3)  # valores 70, 71, 72 -> mediana 71.0
        rr_val = 14.0 + (i % 2)  # valores 14, 15 -> mediana 14.5
        engine.ingest(make_sample(f"rest-{i}", ts, hr=hr_val, rr=rr_val, activity="rest"), ts)

    fixed_baseline = dict(engine.baseline)
    assert fixed_baseline["status"] == "ready"
    assert fixed_baseline["source"] == "rest_window"
    assert fixed_baseline["hr"] == pytest.approx(71.0)
    assert fixed_baseline["rr"] == pytest.approx(14.5)
    assert fixed_baseline["hr_mad"] is not None and fixed_baseline["hr_mad"] >= 0.0
    assert fixed_baseline["rr_mad"] is not None and fixed_baseline["rr_mad"] >= 0.0

    # Nuevas muestras (aunque tengan pulso elevado en reposo) NO modifican la línea base fijada.
    # 71 + 25 = 96 -> sostenido a 99 bpm (< hr_watch=105) por >= 30 s eleva de normal a watch.
    elev_start = base_start + timedelta(seconds=120)
    for i in range(35):
        ts = elev_start + timedelta(seconds=i)
        engine.ingest(make_sample(f"elev-{i}", ts, hr=99.0, rr=16.0, activity="rest"), ts)

    final_now = elev_start + timedelta(seconds=34)
    state = engine.state(final_now)
    assert state["baseline"] == fixed_baseline
    assert state["assessment"]["level"] == "watch"
    assert state["assessment"]["hypothesis"].startswith("Hipótesis orientativa (escenario simulado):")

    # También acepta fijación explícita desde calibration_file y activa ML tras >= 120 s.
    manual_engine = Engine()
    manual_base = manual_engine.set_baseline(70.0, 14.0, source="calibration_file")
    assert manual_base["status"] == "ready"
    assert manual_base["source"] == "calibration_file"
    assert manual_base["hr"] == 70.0
    assert manual_base["rr"] == 14.0

    for i in range(120):
        ts = T0 + timedelta(seconds=i)
        manual_engine.ingest(
            make_sample(
                f"ml-{i}",
                ts,
                hr=70.0 + 0.5 * math.sin(i / 8.0),
                rr=14.0 + 0.2 * math.cos(i / 6.0),
                co2=2.0,
                activity="rest",
            ),
            ts,
        )
    ml_state = manual_engine.state(T0 + timedelta(seconds=119))
    assert ml_state["ml"]["forecast"]["available"] is True
    assert ml_state["assessment"]["forecast_hr"] == ml_state["ml"]["forecast"]["forecast_hr"]
    assert "RandomForest" in ml_state["assessment"]["forecast_method"]
    assert ml_state["ml"]["pattern"]["available"] is True
    assert ml_state["ml"]["pattern"]["pattern"] == "baseline_expected"
    assert ml_state["baseline"] == manual_base


def test_co2_sensitivity_ols_and_abstention():
    # Serie sintética conocida: rr = 14.0 + 4.0 * (co2 - 2.0) => pendiente s=4.0, r2=1.0
    series = [
        make_sample(
            f"co2-{i}",
            T0 + timedelta(seconds=i * 5),
            hr=74.0 + 0.1 * i,
            co2=round(2.0 + 0.05 * i, 4),
            rr=round(14.0 + 4.0 * (0.05 * i), 4),
            activity="rest",
        )
        for i in range(30)
    ]
    res = compute_co2_sensitivity(series)
    assert res["status"] == "ready"
    assert res["slope"] == pytest.approx(4.0, abs=1e-3)
    assert res["r2"] >= 0.6
    assert res["r2"] == pytest.approx(1.0, abs=1e-4)
    # Última muestra: co2=3.45, rr=19.8 -> 3.45 + (23.0 - 19.8)/4.0 = 4.25
    assert res["co2_personal"] == pytest.approx(4.25, abs=0.02)

    # También integrado en Engine (incluso > 120 muestras mediante long_history + history).
    engine = Engine()
    for i in range(150):
        ts = T0 + timedelta(seconds=i * 2)  # 300 s totales
        co2_val = 2.0 + 0.01 * i
        rr_val = 14.0 + 3.5 * (co2_val - 2.0)
        engine.ingest(
            make_sample(f"eng-{i}", ts, hr=74.0, co2=co2_val, rr=rr_val, activity="rest"),
            ts,
        )
    eng_sens = engine.state(T0 + timedelta(seconds=298))["co2_sensitivity"]
    assert eng_sens["status"] == "ready"
    assert eng_sens["slope"] == pytest.approx(3.5, abs=1e-3)
    assert eng_sens["r2"] >= 0.6

    # Abstención por muestras insuficientes (< 24) o ejercicio excluido.
    too_few = compute_co2_sensitivity(series[:20])
    assert too_few["status"] == "insufficient_data"
    assert too_few["slope"] is None
    assert too_few["co2_personal"] is None

    # Abstención por rango de CO₂ < 0.4 mmHg.
    flat_co2 = [
        make_sample(
            f"flat-{i}",
            T0 + timedelta(seconds=i * 5),
            co2=2.0 + 0.01 * i,  # rango 0.29 < 0.4
            rr=14.0 + 0.05 * i,
            activity="rest",
        )
        for i in range(30)
    ]
    low_range = compute_co2_sensitivity(flat_co2)
    assert low_range["status"] == "insufficient_data"
    assert low_range["slope"] is None
    assert low_range["co2_personal"] is None

    # Abstención por r² < 0.6 (señal respiratoria sin correlación lineal).
    noisy = [
        make_sample(
            f"noisy-{i}",
            T0 + timedelta(seconds=i * 5),
            co2=2.0 + 0.05 * i,
            rr=16.0 + (4.0 if i % 2 == 0 else -4.0),
            activity="rest",
        )
        for i in range(30)
    ]
    low_r2 = compute_co2_sensitivity(noisy)
    assert low_r2["status"] == "low_r2"
    assert low_r2["r2"] is not None and low_r2["r2"] < 0.6
    assert low_r2["slope"] is None
    assert low_r2["co2_personal"] is None


def test_projections_co2_eta_and_shelter_comparison():
    engine = Engine()
    # Rampa lineal de CO₂: +0.02 mmHg/s durante 60 s -> 2.00 a 3.18 mmHg
    # y radiación a 80.0 μSv/h.
    for i in range(60):
        ts = T0 + timedelta(seconds=i)
        engine.ingest(
            make_sample(
                f"ramp-{i}",
                ts,
                hr=76.0,
                rr=16.0,
                co2=round(2.0 + 0.02 * i, 4),
                dose_rate=80.0,
                activity="rest",
            ),
            ts,
        )

    now = T0 + timedelta(seconds=59)
    state = engine.state(now)
    co2_proj = state["projections"]["co2"]
    rad_proj = state["projections"]["radiation"]

    # Último CO₂ = 3.18, umbral station = 4.0, pendiente = 0.02 -> ETA = 41.0 s
    assert co2_proj["eta_s"] == pytest.approx(41.0, abs=0.5)
    assert co2_proj["eta_minutes"] == pytest.approx(41.0 / 60.0, abs=0.05)
    assert co2_proj["assumption"] == "Tendencia lineal constante en los últimos 120 s (no es predicción médica)"
    assert co2_proj["moving_avg_1h_mmhg"] is not None
    assert co2_proj["coverage_pct"] > 0.0

    # Dosis acumulada nunca disminuye y refugio reduce la tasa proyectada a 1 h.
    dose_before = state["dose_total"]
    assert dose_before > 0.0
    assert rad_proj["horizon_hours"] == 1.0
    assert rad_proj["projected_without_shelter"] == pytest.approx(dose_before + 80.0, abs=1e-3)
    assert rad_proj["projected_with_shelter"] == pytest.approx(dose_before + 80.0 * 0.15, abs=1e-3)
    assert rad_proj["projected_with_shelter"] < rad_proj["projected_without_shelter"]

    # Al activar refugio en nuevas muestras (baja dose_rate), dose_total sigue siendo monótona.
    for i in range(5):
        ts = now + timedelta(seconds=i + 1)
        engine.ingest(
            make_sample(f"sh-{i}", ts, hr=76.0, rr=16.0, co2=3.18, dose_rate=12.0),
            ts,
        )
    after = engine.state(now + timedelta(seconds=5))
    assert after["dose_total"] >= dose_before

    # Pendiente <= 0 en los últimos 120 s => eta_s = None, eta_minutes = None.
    flat_engine = Engine()
    for i in range(20):
        ts = T0 + timedelta(seconds=i)
        flat_engine.ingest(
            make_sample(f"dec-{i}", ts, co2=round(3.0 - 0.02 * i, 4), dose_rate=1.0),
            ts,
        )
    dec_proj = flat_engine.state(T0 + timedelta(seconds=19))["projections"]["co2"]
    assert dec_proj["eta_s"] is None
    assert dec_proj["eta_minutes"] is None


def test_gateway_co2_ramp_and_solar_event_profiles(tmp_path):
    gw_station = Gateway()
    gw_rover = Gateway()

    ctrl_s = gw_station.update(ControlUpdate(scenario="co2_ramp", environment="station"))
    ctrl_r = gw_rover.update(ControlUpdate(scenario="co2_ramp", environment="rover"))
    assert ctrl_s["environment"] == "station" and ctrl_s["solar_phase"] is None
    assert ctrl_r["environment"] == "rover" and ctrl_r["solar_phase"] is None

    for _ in range(40):
        p_station = gw_station.make_packet()
        p_rover = gw_rover.make_packet()

    # Todos los paquetes simulados validan contra Telemetry e incluyen señales auxiliares.
    t_station = Telemetry(**p_station)
    t_rover = Telemetry(**p_rover)
    assert t_station.spo2 is not None and t_station.bp_sys is not None and t_station.temp_c is not None
    assert t_rover.hydration_pct is not None
    # Rover tiene co2_ramp_rate_mmhg_min=1.2 vs station=0.6.
    assert t_rover.co2 > t_station.co2

    # Verificar solar_event con fases DONKI y refugio.
    gw_solar = Gateway()
    ctrl_watch = gw_solar.update(
        ControlUpdate(scenario="solar_event", environment="station", solar_phase="watch")
    )
    assert ctrl_watch["solar_phase"] == "watch"
    pkt_watch = gw_solar.make_packet()

    gw_solar.update(ControlUpdate(solar_phase="peak"))
    pkt_peak = gw_solar.make_packet()
    assert pkt_peak["dose_rate"] > pkt_watch["dose_rate"]

    gw_solar.update(ControlUpdate(shelter=True))
    pkt_peak_shelter = gw_solar.make_packet()
    assert pkt_peak_shelter["dose_rate"] < pkt_peak["dose_rate"]
    assert pkt_peak_shelter["dose_rate"] == pytest.approx(pkt_peak["dose_rate"] * 0.15, rel=1e-2)

    # Cambiar a rest resetea shelter y solar_phase.
    ctrl_rest = gw_solar.update(ControlUpdate(scenario="rest"))
    assert ctrl_rest["shelter"] is False
    assert ctrl_rest["solar_phase"] is None

    # Verificar signal_loss preserva None en señales perdidas.
    gw_solar.update(ControlUpdate(scenario="signal_loss"))
    pkt_loss = gw_solar.make_packet()
    assert pkt_loss["hr"] is None and pkt_loss["rr"] is None and pkt_loss["spo2"] is None
    assert pkt_loss["co2"] is not None and pkt_loss["dose_rate"] is not None

    # Verificar BIDMC mantiene None en co2, dose_rate y señales auxiliares.
    csv_path = tmp_path / "bidmc_mini.csv"
    csv_path.write_text("Time [s], HR, RESP\n0, 80, 16\n1, 81, 17\n", encoding="utf-8")
    gw_bidmc = Gateway(bidmc_path=csv_path)
    gw_bidmc.update(ControlUpdate(scenario="bidmc"))
    pkt_bidmc = gw_bidmc.make_packet()
    Telemetry(**pkt_bidmc)
    for null_field in ("co2", "dose_rate", "spo2", "bp_sys", "bp_dia", "temp_c", "hydration_pct"):
        assert pkt_bidmc[null_field] is None
    assert pkt_bidmc["activity"] == "unknown"
    assert pkt_bidmc["source"] == "bidmc"


def test_engine_environment_donki_questions_coach_and_report():
    on_ingest_calls: list[str] = []
    engine = Engine(environment="rover", on_ingest=lambda s: on_ingest_calls.append(s.sample_id))

    # Umbrales de rover: co2_alert=3.5, rr_alert=22.0 (más estrictos que station 4.0 / 23.0).
    engine.ingest(make_sample("r1", T0, hr=78.0, rr=22.5, co2=3.6, activity="rest"), T0)
    assert on_ingest_calls == ["r1"]
    assert engine.state(T0)["assessment"]["level"] == "alert"

    # Pregunta inteligente cuando activity="unknown" y señales válidas.
    t1 = T0 + timedelta(seconds=1)
    engine.ingest(make_sample("r2", t1, hr=110.0, rr=18.0, co2=2.0, activity="unknown"), t1)
    st_q = engine.state(t1)
    assert len(st_q["questions"]) == 1
    assert st_q["questions"][0]["id"] == "activity_context"
    opts = {opt["value"]: opt for opt in st_q["questions"][0]["options"]}
    assert opts["rest"]["hypothetical_level"] == "watch"
    assert opts["exercise"]["hypothetical_level"] == "normal"

    # Responder declaración de actividad resuelve la pregunta y actualiza evaluación.
    engine.set_activity_declaration(ActivityDeclaration(activity="rest", note="Descanso en módulo"), t1)
    st_decl = engine.state(t1)
    assert st_decl["questions"] == []
    assert st_decl["assessment"]["level"] == "watch"

    # Evento externo DONKI en fase watch eleva nivel fisiológico normal a watch y activa checklist.
    t2 = T0 + timedelta(seconds=2)
    engine.ingest(make_sample("r3", t2, hr=72.0, rr=14.0, co2=2.0, dose_rate=1.2, activity="rest"), t2)
    assert engine.state(t2)["assessment"]["level"] == "normal"
    engine.set_external_event(ContextEventRequest(kind="solar", phase="watch", shelter=False), t2)
    st_watch = engine.state(t2)
    assert st_watch["assessment"]["level"] == "watch"
    assert st_watch["assessment"]["title"] == "Evento solar en observación"
    assert any("DONKI" in ev for ev in st_watch["assessment"]["evidence"])
    shelter_routine = next(r for r in st_watch["coach"]["routines"] if r["id"] == "shelter_checklist")
    assert shelter_routine["active"] is True

    # Check-in, rutina, ack, privacidad e informe SBAR sin lenguaje clínico.
    checkin_res = engine.submit_checkin(
        CheckInRequest(reaction_ms=[240.0, 250.0, 260.0], sleep_hours=6.5, mood=3),
        now=t2,
    )
    assert checkin_res["co2_mmhg"] == 2.0
    engine.complete_routine("shelter_checklist", now=t2)
    engine.acknowledge(now=t2)

    private_rep = engine.report(now=t2)
    assert private_rep["share_behavioral"] is False
    assert private_rep["antecedentes"]["behavioral_summary"] is None

    engine.set_privacy(True)
    shared_rep = engine.report(now=t2)
    assert shared_rep["share_behavioral"] is True
    assert shared_rep["antecedentes"]["behavioral_summary"] is not None
    serialized = json.dumps(shared_rep, ensure_ascii=False)
    assert "[IA PREDICTION]" not in serialized
    assert "Hipótesis orientativa (escenario simulado)" in serialized

    # Tendencias de 1 h preservan campos y conteos reales.
    trends = engine.trends(window_s=3600, now=t2)
    assert trends["sample_count"] == 3
    assert trends["signals"]["hr"]["count"] == 3
    assert trends["signals"]["spo2"]["count"] == 0
    assert trends["signals"]["spo2"]["mean"] is None
