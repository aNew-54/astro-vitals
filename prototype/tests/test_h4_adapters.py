import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from astro.adapters import (
    UnitConversionError,
    convert_file,
    convert_unit,
    inspect_file,
    parse_nullable_float,
)
from astro.adapters.units import ALIASES, MISSING_MARKERS, suggest_canonical_column
from astro.contracts import Telemetry
from astro.donki import (
    DEFAULT_DONKI_PATH,
    SOLAR_PHASES,
    get_solar_context,
    load_donki_event,
    phase_at_elapsed,
)

PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]


def test_parse_nullable_float_and_missing_markers():
    assert {"", "na", "n/a", "null", "none", "nan", "-999", "-999.0", "-9999"} <= MISSING_MARKERS
    for marker in (None, "", "  ", "NA", "N/A", "na", "null", "None", "NaN", "-999", "-999.0", -999, -999.0, "-9999", -9999):
        assert parse_nullable_float(marker) is None

    assert parse_nullable_float(True) is None
    assert parse_nullable_float(False) is None
    assert parse_nullable_float(float("nan")) is None
    assert parse_nullable_float(float("inf")) is None
    assert parse_nullable_float(float("-inf")) is None
    assert parse_nullable_float("inf") is None
    assert parse_nullable_float("-inf") is None

    assert parse_nullable_float(0) == 0.0
    assert parse_nullable_float("0.0") == 0.0
    assert parse_nullable_float(" 72.5 ") == 72.5


def test_aliases_and_canonical_column_suggestions():
    assert "hr" in ALIASES and "pulso" in ALIASES["hr"]
    assert "co2" in ALIASES and "ppco2" in ALIASES["co2"]
    assert suggest_canonical_column(" HR ") == "hr"
    assert suggest_canonical_column("pulso") == "hr"
    assert suggest_canonical_column("respiración") == "rr"
    assert suggest_canonical_column("Time [s]") == "time"
    assert suggest_canonical_column("co2 [kPa]") == "co2"
    assert suggest_canonical_column("dose_rate (mSv/h)") == "dose_rate"
    assert suggest_canonical_column("presión_sistólica") == "bp_sys"
    assert suggest_canonical_column("temperatura") == "temp_c"
    assert suggest_canonical_column("hidratación") == "hydration_pct"
    assert suggest_canonical_column("PULSE") is None


def test_explicit_unit_conversions_and_rejections():
    assert convert_unit("co2", 2.0, "mmHg") == 2.0
    assert convert_unit("co2", 0.5, "kPa") == pytest.approx(0.5 * 7.50062)
    assert convert_unit("co2", 2000.0, "ppm", total_pressure_mmhg=760.0) == pytest.approx(1.52)

    assert convert_unit("dose_rate", 12.5, "µSv/h") == 12.5
    assert convert_unit("dose_rate", 12.5, "μSv/h") == 12.5
    assert convert_unit("dose_rate", 12.5, "microSv/h") == 12.5
    assert convert_unit("dose_rate", 0.085, "mSv/h") == pytest.approx(85.0)

    assert convert_unit("spo2", 97.0, "%") == 97.0
    assert convert_unit("spo2", 0.97, "fraction", observed_max=0.99) == pytest.approx(97.0)
    assert convert_unit("bp_sys", 16.0, "kPa") == pytest.approx(16.0 * 7.50062)
    assert convert_unit("bp_dia", 80.0, "mmHg") == 80.0
    assert convert_unit("temp_c", 310.15, "K") == pytest.approx(37.0)
    assert convert_unit("hydration_pct", 62.0, "percent") == 62.0
    assert convert_unit("hr", 72.0, "1/min") == 72.0
    assert convert_unit("rr", 16.0, "brpm") == 16.0
    assert convert_unit("co2", None, "mmHg") is None

    # Rechazo explícito: ppm sin presión total
    with pytest.raises(UnitConversionError):
        convert_unit("co2", 2000.0, "ppm")
    with pytest.raises(UnitConversionError):
        convert_unit("co2", 2000.0, "ppm", total_pressure_mmhg=0)

    # Rechazo explícito: Gy / mGy / rad a Sv
    for forbidden in ("Gy/h", "mGy/h", "mGy/d", "Gy", "mGy", "rad/h"):
        with pytest.raises(UnitConversionError):
            convert_unit("dose_rate", 0.2, forbidden)

    # Rechazo explícito: unidad ausente o desconocida
    with pytest.raises(UnitConversionError):
        convert_unit("hr", 75.0, None)
    with pytest.raises(UnitConversionError):
        convert_unit("hr", 75.0, "unknown")

    # Rechazo explícito: spo2 fracción con máximo observado > 1.0
    with pytest.raises(UnitConversionError):
        convert_unit("spo2", 0.98, "fraction", observed_max=98.0)


def test_csv_english_with_missing_markers_and_outputs(tmp_path):
    csv_path = tmp_path / "bidmc_sample.csv"
    csv_path.write_text(
        "Time [s], HR, PULSE, RESP, SpO2, activity\n"
        "0, 94, 93, 25, 97, rest\n"
        "1, NA, -999, N/A, NaN, exercise\n"
        "2, -999, 91, , null, \n",
        encoding="utf-8",
    )
    expected_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()

    info = inspect_file(csv_path)
    assert info["format"] == "csv"
    assert info["rows_count"] == 3
    assert info["sha256"] == expected_sha
    cols = {c["name"]: c for c in info["columns"]}
    assert cols["HR"]["suggested_signal"] == "hr"
    assert cols["HR"]["missing_count"] == 2
    assert cols["HR"]["missing_pct"] == pytest.approx(66.67, abs=0.01)
    assert cols["HR"]["min"] == 94.0 and cols["HR"]["max"] == 94.0
    assert cols["HR"]["inferred_unit"] is None
    assert cols["Time [s]"]["inferred_unit"] == "s"
    assert cols["PULSE"]["suggested_signal"] is None

    # Sin declarar unidades para HR/RESP/SpO2 debe rechazar explícitamente.
    with pytest.raises(UnitConversionError):
        convert_file(csv_path)

    base_dt = datetime(2026, 11, 14, 12, 0, 0, tzinfo=UTC)
    out_dir = tmp_path / "out_csv"
    result = convert_file(
        csv_path,
        output_dir=out_dir,
        units={"HR": "bpm", "RESP": "resp/min", "SpO2": "%"},
        base_time=base_dt,
        source_name="bidmc_sample_ref",
    )

    records = result["records"]
    assert len(records) == 3
    assert records[0]["hr"] == 94.0
    assert records[0]["rr"] == 25.0
    assert records[0]["spo2"] == 97.0
    assert records[0]["original_time_s"] == 0.0
    assert records[0]["measured_at"] == "2026-11-14T12:00:00+00:00"
    assert records[0]["activity"] == "rest"
    assert records[0]["source"] == "replayed"
    assert records[0]["source_ref"] == "bidmc_sample_ref"
    assert records[0]["extras"] == {"PULSE": 93.0}

    # Marcadores ausentes pasan a None, nunca a 0.
    assert records[1]["hr"] is None
    assert records[1]["rr"] is None
    assert records[1]["spo2"] is None
    assert records[1]["extras"] == {"PULSE": None}
    assert records[1]["activity"] == "exercise"
    assert records[2]["hr"] is None
    assert records[2]["rr"] is None
    assert records[2]["spo2"] is None
    assert records[2]["activity"] == "unknown"

    # Verificar archivos generados .jsonl y .meta.json con sha256.
    jsonl_path = Path(result["jsonl_path"])
    meta_path = Path(result["meta_path"])
    assert jsonl_path.name == "bidmc_sample.jsonl"
    assert meta_path.name == "bidmc_sample.meta.json"
    assert jsonl_path.exists() and meta_path.exists()

    jsonl_lines = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert len(jsonl_lines) == 3
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["sha256"] == expected_sha
    assert meta["rows_converted"] == 3
    assert meta["ignored_or_extra_columns"] == ["PULSE"]
    assert meta["missing_counts"]["HR"] == 2
    assert meta["units"]["HR"] == "bpm"

    # Validar campos núcleo con Telemetry actual (y completo si contracts.py se amplía).
    for rec in records:
        if "spo2" in Telemetry.model_fields and "extras" in Telemetry.model_fields:
            Telemetry(**rec)
        else:
            Telemetry(
                sample_id=rec["sample_id"],
                measured_at=rec["measured_at"],
                hr=rec["hr"],
                rr=rec["rr"],
                co2=rec["co2"],
                dose_rate=rec["dose_rate"],
                activity=rec["activity"],
                source="simulated",
                original_time_s=rec["original_time_s"],
            )


def test_tsv_spanish_ppm_and_cli_convert(tmp_path):
    tsv_path = tmp_path / "cabina_es.tsv"
    tsv_path.write_text(
        "tiempo_s\tpulso\trespiracion\tco2\tfase\n"
        "0\t76\t15\t2641\treposo\n"
        "5\t118\t24\t5000\tejercicio\n",
        encoding="utf-8",
    )

    # Sin presión total debe lanzar UnitConversionError al convertir co2 en ppm.
    with pytest.raises(UnitConversionError):
        convert_file(
            tsv_path,
            units={"pulso": "bpm", "respiracion": "resp/min", "co2": "ppm"},
        )

    out_dir = tmp_path / "cli_out"
    cmd = [
        sys.executable,
        "-m",
        "astro.adapters.loader",
        "convert",
        str(tsv_path),
        "--output-dir",
        str(out_dir),
        "--unit",
        "pulso=bpm",
        "--unit",
        "respiracion=resp/min",
        "--unit",
        "co2=ppm",
        "--total-pressure-mmhg",
        "760",
    ]
    proc = subprocess.run(
        cmd,
        cwd=PROTOTYPE_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    cli_summary = json.loads(proc.stdout)
    assert cli_summary["meta"]["rows_converted"] == 2

    jsonl_path = out_dir / "cabina_es.jsonl"
    meta_path = out_dir / "cabina_es.meta.json"
    assert jsonl_path.exists() and meta_path.exists()

    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["hr"] == 76.0
    assert rows[0]["rr"] == 15.0
    assert rows[0]["co2"] == pytest.approx(2641.0 * 760.0 / 1_000_000.0)
    assert rows[0]["activity"] == "rest"
    assert rows[0]["original_time_s"] == 0.0
    assert rows[1]["co2"] == pytest.approx(5000.0 * 760.0 / 1_000_000.0)
    assert rows[1]["activity"] == "exercise"

    # También probar CLI inspect.
    inspect_proc = subprocess.run(
        [sys.executable, "-m", "astro.adapters.loader", "inspect", str(tsv_path)],
        cwd=PROTOTYPE_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    inspect_report = json.loads(inspect_proc.stdout)
    assert inspect_report["format"] == "tsv"
    assert inspect_report["rows_count"] == 2


def test_json_kpa_and_msvh_conversions_and_gy_rejection(tmp_path):
    json_path = tmp_path / "env_units.json"
    json_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "timestamp": "2026-11-14T08:00:00Z",
                        "co2_kpa": 0.4,
                        "dose_rate_msvh": 0.042,
                        "bp_sys_kpa": 16.0,
                        "temp_k": 310.15,
                    },
                    {
                        "timestamp": "2026-11-14T08:00:05+02:00",
                        "co2_kpa": None,
                        "dose_rate_msvh": "NA",
                        "bp_sys_kpa": -999,
                        "temp_k": 309.65,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = convert_file(json_path)
    records = result["records"]
    assert len(records) == 2
    assert records[0]["co2"] == pytest.approx(0.4 * 7.50062)
    assert records[0]["dose_rate"] == pytest.approx(42.0)
    assert records[0]["bp_sys"] == pytest.approx(16.0 * 7.50062)
    assert records[0]["temp_c"] == pytest.approx(37.0)
    assert records[0]["original_time_s"] is None
    assert records[0]["measured_at"] == "2026-11-14T08:00:00+00:00"

    assert records[1]["co2"] is None
    assert records[1]["dose_rate"] is None
    assert records[1]["bp_sys"] is None
    assert records[1]["temp_c"] == pytest.approx(36.5)
    assert records[1]["measured_at"] == "2026-11-14T06:00:05+00:00"

    # Archivo con Gy/h o mGy/d debe ser rechazado con UnitConversionError.
    gy_path = tmp_path / "absorbed.json"
    gy_path.write_text(
        json.dumps([{"timestamp": "2026-11-14T08:00:00Z", "dose_mgy_day": 0.21}]),
        encoding="utf-8",
    )
    with pytest.raises(UnitConversionError):
        convert_file(gy_path)


def test_jsonl_extras_and_iso_timestamp(tmp_path):
    jsonl_path = tmp_path / "wearable.jsonl"
    lines = [
        {
            "measured_at": "2026-11-14T15:30:00Z",
            "heart_rate_bpm": 82,
            "spo2_percent": 98,
            "hydration_pct": 64.5,
            "sensor_status": "ok",
            "motion_g": 0.12,
            "dropout_flag": False,
        },
        {
            "measured_at": "2026-11-14T15:30:01Z",
            "heart_rate_bpm": "NaN",
            "spo2_percent": "-999",
            "hydration_pct": "N/A",
            "sensor_status": "NA",
            "motion_g": "null",
            "dropout_flag": True,
        },
    ]
    jsonl_path.write_text(
        "\n".join(json.dumps(row) for row in lines) + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out_jsonl"
    result = convert_file(jsonl_path, output_dir=out_dir)
    records = result["records"]
    assert len(records) == 2

    assert records[0]["hr"] == 82.0
    assert records[0]["spo2"] == 98.0
    assert records[0]["hydration_pct"] == 64.5
    assert records[0]["original_time_s"] is None
    assert records[0]["measured_at"] == "2026-11-14T15:30:00+00:00"
    assert records[0]["extras"] == {
        "sensor_status": "ok",
        "motion_g": 0.12,
        "dropout_flag": "false",
    }

    assert records[1]["hr"] is None
    assert records[1]["spo2"] is None
    assert records[1]["hydration_pct"] is None
    assert records[1]["extras"] == {
        "sensor_status": None,
        "motion_g": None,
        "dropout_flag": "true",
    }
    assert set(result["meta"]["ignored_or_extra_columns"]) == {
        "sensor_status",
        "motion_g",
        "dropout_flag",
    }


def test_donki_loads_local_event_and_phases():
    assert DEFAULT_DONKI_PATH.exists()
    event = load_donki_event()
    assert event["sep_id"] == "2024-05-11T04:07:00-SEP-001"
    assert event["event_time"] == "2024-05-11T04:07Z"
    assert event["instruments"] == ["STEREO A: IMPACT 13-100 MeV"]
    assert event["link"] == "https://ccmc.gsfc.nasa.gov/DONKI/view/SEP/30717/-1"
    assert event["linked_events"] == [
        "2024-05-11T01:10:00-FLR-001",
        "2024-05-11T01:36:00-CME-001",
    ]
    assert len(event["notifications"]) == 2
    assert event["source"] == "NASA CCMC DONKI (respaldo local)"
    assert "11 de mayo de 2024" in event["historical_note"]

    assert SOLAR_PHASES == ("watch", "arrival", "peak", "decay")
    assert phase_at_elapsed(0.0) == "watch"
    assert phase_at_elapsed(14.9) == "watch"
    assert phase_at_elapsed(15.0) == "arrival"
    assert phase_at_elapsed(29.9) == "arrival"
    assert phase_at_elapsed(30.0) == "peak"
    assert phase_at_elapsed(49.9) == "peak"
    assert phase_at_elapsed(50.0) == "decay"

    watch_ctx = get_solar_context("watch")
    assert watch_ctx["level"] == "watch"
    assert watch_ctx["title"] == "Evento solar en observación (contexto NASA DONKI)"
    assert watch_ctx["activates_shelter_checklist"] is True
    assert watch_ctx["next_step"] == "Revisar lista de refugio antes de la llegada estimada (escenario simulado)."
    assert watch_ctx["timeline_label"] == "Línea de tiempo comprimida de demostración"
    assert watch_ctx["simulated_dose_rate_usvh"] < 5.0

    arrival_ctx = get_solar_context("arrival")
    peak_ctx = get_solar_context("peak")
    peak_shelter_ctx = get_solar_context("peak", shelter=True, shelter_factor=0.15)
    decay_ctx = get_solar_context("decay")

    assert arrival_ctx["simulated_dose_rate_usvh"] > watch_ctx["simulated_dose_rate_usvh"]
    assert peak_ctx["simulated_dose_rate_usvh"] > arrival_ctx["simulated_dose_rate_usvh"]
    assert peak_shelter_ctx["simulated_dose_rate_usvh"] == pytest.approx(
        peak_ctx["base_dose_rate_usvh"] * 0.15
    )
    assert decay_ctx["simulated_dose_rate_usvh"] < peak_ctx["simulated_dose_rate_usvh"]
    assert decay_ctx["activates_shelter_checklist"] is False

    with pytest.raises(ValueError):
        get_solar_context("invalid-phase")
