"""Tests for window feature extraction and colab-v1 ML model inference (H2)."""

from __future__ import annotations

import json
import math
import sys
import warnings
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from astro.contracts import Telemetry
from astro.ml_models import ModelRunner, extract_window_features

ML_DIR = Path(__file__).resolve().parents[2] / "ml"
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

from preparar_bidmc import features_at  # noqa: E402

T0 = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)


def _make_telemetry_series(
    seconds: int,
    *,
    hr_fn=lambda s: 70.0 + 0.15 * math.sin(s / 5.0) + 0.02 * s,
    rr_fn=lambda s: 14.0 + 0.05 * math.cos(s / 4.0) + 0.005 * s,
    co2_fn=lambda s: 2.0 + 0.001 * math.sin(s / 6.0),
    source: str = "simulated",
    activity: str = "rest",
    start_at: datetime = T0,
    drop_secs: set[int] | None = None,
) -> list[Telemetry]:
    drop_secs = drop_secs or set()
    items: list[Telemetry] = []
    for s in range(seconds):
        is_drop = s in drop_secs
        hr = None if is_drop else round(float(hr_fn(s)), 4)
        rr = None if is_drop else round(float(rr_fn(s)), 4)
        co2 = None if (source == "bidmc" or is_drop) else round(float(co2_fn(s)), 4)
        items.append(
            Telemetry(
                sample_id=f"{source}-{s}",
                measured_at=start_at + timedelta(seconds=s),
                hr=hr,
                rr=rr,
                co2=co2,
                dose_rate=None if source == "bidmc" else 0.5,
                activity="unknown" if source == "bidmc" else activity,
                source=source,
            )
        )
    return items


def _assert_no_banned_clinical_strings(payload: dict) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "[IA PREDICTION]" not in serialized
    for key in ("hypothesis", "method"):
        value = payload.get(key)
        if value is not None:
            assert "[IA PREDICTION]" not in value


def test_extract_window_features_matches_preparar_bidmc_parity():
    samples_by_sec = {
        s: {
            "hr": round(68.0 + 0.25 * s + 1.5 * math.sin(s / 7.0), 4),
            "rr": round(14.0 + 0.03 * s + 0.4 * math.cos(s / 5.0), 4),
        }
        for s in range(150)
    }
    # Inject valid gaps (< 20% missing and last 5s valid) plus future points > 120.
    for gap_s in (10, 11, 50, 95, 117):
        samples_by_sec[gap_s]["hr"] = None
    samples_by_sec[100]["rr"] = None

    ref = features_at(samples_by_sec, 120, channels=("hr", "rr"))
    got, reason = extract_window_features(samples_by_sec, now=120, channels=("hr", "rr"))

    assert reason is None
    assert ref is not None
    assert got == ref

    # Verify deque/Telemetry sequence mode produces identical values over the same 120s window (1..120).
    seq = deque(
        Telemetry(
            sample_id=f"sim-{s}",
            measured_at=T0 + timedelta(seconds=s),
            hr=samples_by_sec[s]["hr"],
            rr=samples_by_sec[s]["rr"],
            co2=2.0,
            dose_rate=0.5,
            activity="rest",
            source="simulated",
        )
        for s in range(1, 121)
    )
    seq_features, seq_reason = extract_window_features(
        seq,
        now=T0 + timedelta(seconds=120),
        channels=("hr", "rr"),
    )
    assert seq_reason is None
    assert seq_features == ref


def test_extract_window_features_edge_cases_and_same_second_dedup():
    assert extract_window_features([]) == (None, "sin_datos")
    assert extract_window_features({}) == (None, "sin_datos")

    # Duplicate timestamps rounding to the same second pick the most recent sample.
    series = [
        {
            "measured_at": (T0 + timedelta(seconds=s)).isoformat(),
            "hr": 70.0,
            "rr": 14.0,
            "source": "simulated",
        }
        for s in range(120)
    ]
    series.append(
        {
            "measured_at": (T0 + timedelta(seconds=119, milliseconds=300)).isoformat(),
            "hr": 77.5,
            "rr": 15.5,
            "source": "simulated",
        }
    )
    feats, reason = extract_window_features(series, now=T0 + timedelta(seconds=120))
    assert reason is None
    assert feats is not None
    assert feats["hr_last"] == 77.5
    assert feats["rr_last"] == 15.5

    # Mixed source keeps only the trailing contiguous block matching the last sample.
    mixed = _make_telemetry_series(100, source="simulated") + _make_telemetry_series(
        40,
        source="bidmc",
        start_at=T0 + timedelta(seconds=100),
    )
    feats_mixed, reason_mixed = extract_window_features(
        mixed,
        now=T0 + timedelta(seconds=139),
        channels=("hr", "rr"),
    )
    assert feats_mixed is None
    assert reason_mixed == "calibrando"


def test_model_runner_loads_real_colab_v1_models_and_handles_missing_dir(tmp_path):
    runner = ModelRunner()
    assert runner.forecast_error is None
    assert runner.pattern_error is None
    assert runner._forecast_model is not None
    assert runner._pattern_model is not None
    assert len(runner._forecast_features) == 14
    assert len(runner._pattern_features) == 25
    assert runner._pattern_threshold == pytest.approx(0.6)

    missing_runner = ModelRunner(models_root=tmp_path)
    assert missing_runner.forecast_error is not None
    assert missing_runner.pattern_error is not None

    series = _make_telemetry_series(120)
    now = T0 + timedelta(seconds=119)
    fc_res = missing_runner.predict_forecast(series, now=now)
    assert fc_res["available"] is False
    assert fc_res["status"] == "no_evaluable"
    assert fc_res["reason"] == "modelo_no_disponible"
    assert fc_res["persistence_hr"] == pytest.approx(series[-1].hr)
    assert fc_res["forecast_hr"] == fc_res["persistence_hr"]
    _assert_no_banned_clinical_strings(fc_res)

    pat_res = missing_runner.predict_pattern(
        series,
        now=now,
        baseline={"hr": 70.0, "rr": 14.0},
        activity="rest",
        phase_duration_s=120.0,
    )
    assert pat_res["available"] is False
    assert pat_res["status"] == "no_evaluable"
    assert pat_res["reason"] == "modelo_no_disponible"
    _assert_no_banned_clinical_strings(pat_res)


def test_predict_forecast_calibrating_valid_stale_and_insufficient():
    runner = ModelRunner()

    # < 120 s -> calibrando with persistence fallback
    short_series = _make_telemetry_series(80)
    short_now = T0 + timedelta(seconds=79)
    short_res = runner.predict_forecast(short_series, now=short_now)
    assert short_res["available"] is False
    assert short_res["status"] == "calibrando"
    assert short_res["reason"] == "calibrando"
    assert short_res["ml_forecast_hr"] is None
    assert short_res["persistence_hr"] == pytest.approx(short_series[-1].hr)
    assert short_res["forecast_hr"] == short_res["persistence_hr"]
    assert short_res["interval_radius_bpm"] == pytest.approx(4.62)
    assert short_res["horizon_s"] == 60
    assert short_res["model_version"] == "heart_rate_forecast/colab-v1"
    _assert_no_banned_clinical_strings(short_res)

    # >= 120 s valid -> available=True and finite numerical prediction without feature-name warnings
    full_series = _make_telemetry_series(125)
    full_now = T0 + timedelta(seconds=124)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ok_res = runner.predict_forecast(full_series, now=full_now)
    assert not [w for w in caught if "feature names" in str(w.message).lower()]
    assert ok_res["available"] is True
    assert ok_res["status"] == "ok"
    assert ok_res["reason"] is None
    assert isinstance(ok_res["forecast_hr"], float)
    assert math.isfinite(ok_res["forecast_hr"])
    assert ok_res["ml_forecast_hr"] == ok_res["forecast_hr"]
    assert ok_res["persistence_hr"] == pytest.approx(full_series[-1].hr)
    assert ok_res["horizon_s"] == 60
    assert ok_res["method"].startswith("Hipótesis orientativa (escenario simulado):")
    _assert_no_banned_clinical_strings(ok_res)

    # Stale data (> 5 s) -> datos_antiguos and no persistence HR
    stale_res = runner.predict_forecast(full_series, now=full_now + timedelta(seconds=6))
    assert stale_res["available"] is False
    assert stale_res["status"] == "datos_antiguos"
    assert stale_res["reason"] == "datos_antiguos"
    assert stale_res["persistence_hr"] is None
    assert stale_res["forecast_hr"] is None
    _assert_no_banned_clinical_strings(stale_res)

    # Insufficient coverage (>= 120 s history, > 20% missing in recent window)
    gapped = _make_telemetry_series(120, drop_secs=set(range(95, 115)))
    gapped_res = runner.predict_forecast(gapped, now=T0 + timedelta(seconds=119))
    assert gapped_res["available"] is False
    assert gapped_res["status"] == "no_evaluable"
    assert gapped_res["reason"] == "cobertura_insuficiente"
    _assert_no_banned_clinical_strings(gapped_res)


def test_predict_pattern_bidmc_abstention_and_guardrails():
    runner = ModelRunner()
    bidmc_series = _make_telemetry_series(125, source="bidmc")
    now = T0 + timedelta(seconds=124)

    # BIDMC has co2=None -> clean abstention with reason="falta_co2" (never imputed as 0)
    res_bidmc = runner.predict_pattern(
        bidmc_series,
        now=now,
        baseline={"hr": 70.0, "rr": 14.0},
        activity="rest",
        phase_duration_s=124.0,
    )
    assert res_bidmc["available"] is False
    assert res_bidmc["status"] == "no_evaluable"
    assert res_bidmc["reason"] == "falta_co2"
    assert res_bidmc["pattern"] is None
    assert res_bidmc["score"] is None
    assert res_bidmc["threshold"] == pytest.approx(0.6)
    assert res_bidmc["hypothesis"].startswith("Hipótesis orientativa (escenario simulado):")
    _assert_no_banned_clinical_strings(res_bidmc)

    # Unknown activity -> actividad_desconocida
    sim_series = _make_telemetry_series(125)
    res_unknown_act = runner.predict_pattern(
        sim_series,
        now=now,
        baseline={"hr": 70.0, "rr": 14.0},
        activity="unknown",
    )
    assert res_unknown_act["available"] is False
    assert res_unknown_act["status"] == "no_evaluable"
    assert res_unknown_act["reason"] == "actividad_desconocida"
    _assert_no_banned_clinical_strings(res_unknown_act)

    # Missing baseline -> calibrando / sin_linea_base
    res_no_base = runner.predict_pattern(sim_series, now=now, baseline=None, activity="rest")
    assert res_no_base["available"] is False
    assert res_no_base["status"] == "calibrando"
    assert res_no_base["reason"] == "sin_linea_base"
    _assert_no_banned_clinical_strings(res_no_base)

    # Short history (< 120 s) -> calibrando
    res_short = runner.predict_pattern(
        _make_telemetry_series(60),
        now=T0 + timedelta(seconds=59),
        baseline={"hr": 70.0, "rr": 14.0},
        activity="rest",
    )
    assert res_short["available"] is False
    assert res_short["status"] == "calibrando"
    assert res_short["reason"] == "calibrando"
    _assert_no_banned_clinical_strings(res_short)


def test_predict_pattern_rest_cabin_and_low_confidence():
    runner = ModelRunner()
    now = T0 + timedelta(seconds=119)
    baseline = {"hr": 70.0, "rr": 14.0}

    # Stable rest: hr ~ 70, rr ~ 14, co2 ~ 2.0
    rest_series = _make_telemetry_series(
        120,
        hr_fn=lambda s: 70.0 + 0.8 * math.sin(s / 10.0),
        rr_fn=lambda s: 14.0 + 0.3 * math.cos(s / 8.0),
        co2_fn=lambda s: 2.0 + 0.05 * math.sin(s / 12.0),
    )
    rest_res = runner.predict_pattern(
        rest_series,
        now=now,
        baseline=baseline,
        activity="rest",
        phase_duration_s=120.0,
    )
    assert rest_res["available"] is True
    assert rest_res["status"] == "ok"
    assert rest_res["reason"] is None
    assert rest_res["pattern"] == "baseline_expected"
    assert rest_res["score"] >= 0.6
    assert rest_res["threshold"] == pytest.approx(0.6)
    assert sum(rest_res["probabilities"].values()) == pytest.approx(1.0, abs=1e-2)
    assert rest_res["hypothesis"].startswith("Hipótesis orientativa (escenario simulado):")
    assert rest_res["model_version"] == "physiological_patterns/colab-v1"
    _assert_no_banned_clinical_strings(rest_res)

    # Combined cabin pattern: co2 ~ 5.0, rr ~ 24, hr ~ 95
    cabin_series = _make_telemetry_series(
        120,
        hr_fn=lambda s: 95.0 + 0.9 * math.sin(s / 10.0),
        rr_fn=lambda s: 24.0 + 0.4 * math.cos(s / 8.0),
        co2_fn=lambda s: 5.0 + 0.06 * math.sin(s / 12.0),
    )
    cabin_res = runner.predict_pattern(
        cabin_series,
        now=now,
        baseline=baseline,
        activity="rest",
        phase_duration_s=120.0,
    )
    assert cabin_res["available"] is True
    assert cabin_res["status"] == "ok"
    assert cabin_res["reason"] is None
    assert cabin_res["pattern"] == "combined_cabin_physiology_pattern"
    assert cabin_res["score"] >= 0.6
    assert cabin_res["hypothesis"].startswith("Hipótesis orientativa (escenario simulado):")
    _assert_no_banned_clinical_strings(cabin_res)

    # Low confidence (< 0.6) triggers abstention with reason="confianza_insuficiente"
    low_conf_runner = ModelRunner()
    low_conf_runner._pattern_model = SimpleNamespace(
        classes_=np.array(
            [
                "activity_expected",
                "baseline_expected",
                "combined_cabin_physiology_pattern",
                "persistent_recovery_deviation",
            ]
        ),
        predict_proba=lambda _: np.array([[0.35, 0.30, 0.25, 0.10]]),
    )
    low_res = low_conf_runner.predict_pattern(
        rest_series,
        now=now,
        baseline=baseline,
        activity="rest",
        phase_duration_s=120.0,
    )
    assert low_res["available"] is False
    assert low_res["status"] == "no_evaluable"
    assert low_res["reason"] == "confianza_insuficiente"
    assert low_res["pattern"] is None
    assert low_res["score"] == pytest.approx(0.35)
    assert low_res["hypothesis"].startswith("Hipótesis orientativa (escenario simulado):")
    _assert_no_banned_clinical_strings(low_res)
