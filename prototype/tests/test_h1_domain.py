import pytest

from astro.config import CONFIG_VERSION, PARAMETERS, get_param, get_parameter_spec
from astro.glossary import LEVEL_GLOSSARY, SIGNAL_GLOSSARY, get_glossary
from astro.profiles import PROFILES, get_profile, list_profiles
from astro.signals import SIGNALS, get_signal, list_signals


def test_config_provenance_and_helpers():
    assert CONFIG_VERSION == "v0.2-demo"
    expected_keys = {
        "co2_nasa_1h",
        "hr_watch",
        "co2_alert",
        "rr_alert",
        "dose_rate_alert",
        "shelter_factor",
        "stale_seconds",
        "reaction_drift_ms",
        "baseline_window_s",
    }
    assert set(PARAMETERS.keys()) == expected_keys

    nasa_params = [name for name, spec in PARAMETERS.items() if spec["origin"] == "nasa_ref"]
    assert nasa_params == ["co2_nasa_1h"]
    assert get_param("co2_nasa_1h") == 3.0

    nasa_spec = get_parameter_spec("co2_nasa_1h")
    assert nasa_spec["unit"] == "mmHg"
    assert "2.3" in nasa_spec["note"]
    assert "OCHMO-TB-004" in nasa_spec["note"]

    # El retorno de get_parameter_spec debe ser copia independiente.
    nasa_spec["value"] = 999.0
    assert get_param("co2_nasa_1h") == 3.0

    for name, spec in PARAMETERS.items():
        assert isinstance(spec["value"], float)
        assert isinstance(spec["unit"], str) and spec["unit"]
        assert isinstance(spec["note"], str) and spec["note"]
        if name != "co2_nasa_1h":
            assert spec["origin"] == "demo"

    with pytest.raises(KeyError):
        get_param("missing_param")


def test_signals_catalog_and_usage_flags():
    expected_signals = {
        "hr",
        "rr",
        "co2",
        "dose_rate",
        "spo2",
        "bp_sys",
        "bp_dia",
        "temp_c",
        "hydration_pct",
    }
    assert set(SIGNALS.keys()) == expected_signals
    assert len(list_signals()) == 9

    for key, spec in SIGNALS.items():
        assert spec["key"] == key
        assert isinstance(spec["label"], str) and spec["label"]
        assert isinstance(spec["unit"], str) and spec["unit"]
        assert isinstance(spec["min"], float)
        assert isinstance(spec["max"], float)
        assert spec["min"] < spec["max"]
        assert isinstance(spec["plausible_range"], tuple)
        assert len(spec["plausible_range"]) == 2
        lo, hi = spec["plausible_range"]
        assert isinstance(lo, float) and isinstance(hi, float)
        assert spec["min"] <= lo < hi <= spec["max"]
        assert isinstance(spec["used_in_forecast"], bool)
        assert isinstance(spec["used_in_classifier"], bool)
        assert isinstance(spec["used_in_rules"], bool)

    assert {k for k, v in SIGNALS.items() if v["used_in_forecast"]} == {"hr", "rr"}
    assert {k for k, v in SIGNALS.items() if v["used_in_classifier"]} == {"hr", "rr", "co2"}

    hr_spec = get_signal("hr")
    assert hr_spec is not None and hr_spec["unit"] == "bpm"
    hr_spec["unit"] = "mutated"
    assert SIGNALS["hr"]["unit"] == "bpm"
    assert get_signal("nonexistent") is None


def test_glossary_covers_all_signals_and_levels():
    assert set(SIGNAL_GLOSSARY.keys()) == set(SIGNALS.keys())
    required_signal_fields = {"what_is", "why_it_matters", "what_to_do", "limitations"}

    for key, entry in SIGNAL_GLOSSARY.items():
        assert set(entry.keys()) == required_signal_fields
        for field in required_signal_fields:
            assert isinstance(entry[field], str) and entry[field].strip(), f"{key}.{field} vacío"
            assert "[IA PREDICTION]" not in entry[field]

    co2_text = " ".join(SIGNAL_GLOSSARY["co2"].values())
    assert "3.0 mmHg" in co2_text
    assert "1 h" in co2_text
    assert "NASA OCHMO-TB-004" in co2_text
    assert "2.3 mmHg" in co2_text

    expected_levels = {"normal", "watch", "alert", "unknown"}
    required_level_fields = {"label", "color", "meaning", "what_to_do", "limitations"}
    assert set(LEVEL_GLOSSARY.keys()) == expected_levels

    for level, entry in LEVEL_GLOSSARY.items():
        assert set(entry.keys()) == required_level_fields
        for field in required_level_fields:
            assert isinstance(entry[field], str) and entry[field].strip(), f"{level}.{field} vacío"
            assert "[IA PREDICTION]" not in entry[field]
        assert entry["color"].startswith("#")

    glossary = get_glossary()
    assert glossary == {"signals": SIGNAL_GLOSSARY, "levels": LEVEL_GLOSSARY}


def test_profiles_change_thresholds():
    expected_profiles = {"transit", "station", "rover", "base"}
    assert set(PROFILES.keys()) == expected_profiles
    assert len(list_profiles()) == 4

    assert PROFILES["station"]["thresholds"] == {
        "hr_watch": 105.0,
        "co2_alert": 4.0,
        "rr_alert": 23.0,
        "dose_rate_alert": 40.0,
    }
    assert PROFILES["rover"]["thresholds"] == {
        "hr_watch": 102.0,
        "co2_alert": 3.5,
        "rr_alert": 22.0,
        "dose_rate_alert": 35.0,
    }
    assert PROFILES["transit"]["thresholds"] == {
        "hr_watch": 104.0,
        "co2_alert": 3.8,
        "rr_alert": 22.5,
        "dose_rate_alert": 30.0,
    }
    assert PROFILES["base"]["thresholds"] == {
        "hr_watch": 105.0,
        "co2_alert": 4.0,
        "rr_alert": 23.0,
        "dose_rate_alert": 25.0,
    }

    # Cada perfil debe tener umbrales y tasas diferenciados.
    threshold_signatures = {
        tuple(sorted(profile["thresholds"].items())) for profile in PROFILES.values()
    }
    assert len(threshold_signatures) == 4
    assert PROFILES["rover"]["co2_ramp_rate_mmhg_min"] > PROFILES["station"]["co2_ramp_rate_mmhg_min"]
    assert PROFILES["base"]["radiation_multiplier"] > PROFILES["station"]["radiation_multiplier"]
    assert PROFILES["transit"]["radiation_multiplier"] > PROFILES["station"]["radiation_multiplier"]

    for profile_id, profile in PROFILES.items():
        assert profile["id"] == profile_id
        assert profile["origin"] == "demo"
        assert set(profile["rest_targets"].keys()) == {"hr", "rr", "co2", "dose_rate"}
        assert isinstance(profile["name"], str) and profile["name"]
        assert isinstance(profile["description"], str) and profile["description"]
        assert isinstance(profile["help_text"], str) and profile["help_text"]
        assert "[IA PREDICTION]" not in profile["help_text"]

    default_profile = get_profile()
    assert default_profile["id"] == "station"
    default_profile["thresholds"]["hr_watch"] = 999.0
    assert PROFILES["station"]["thresholds"]["hr_watch"] == 105.0

    with pytest.raises(ValueError):
        get_profile("deep_void_invalid")
