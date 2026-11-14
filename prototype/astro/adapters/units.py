"""Conversión explícita de unidades, marcadores de ausencia y mapeo de columnas."""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any


class UnitConversionError(ValueError):
    """Error explícito por unidad faltante, incompatible o conversión prohibida."""


MISSING_MARKERS: set[str] = {
    "",
    "na",
    "n/a",
    "null",
    "none",
    "nan",
    "-999",
    "-999.0",
    "-9999",
}

ALIASES: dict[str, set[str]] = {
    "hr": {"hr", "heart_rate", "heart_rate_bpm", "pulso", "fc", "bpm"},
    "rr": {"rr", "resp", "respiratory_rate", "respiratory_rate_rpm", "respiracion", "fr"},
    "co2": {"co2", "ppco2", "ambient_co2", "ambient_co2_mmhg", "co2_mmhg", "co2_ppm"},
    "dose_rate": {"dose_rate", "dose", "radiation", "radiation_usvh", "tasa_dosis", "dosimetro"},
    "spo2": {"spo2", "spo2_percent", "sat_o2", "saturacion"},
    "bp_sys": {"bp_sys", "sys", "systolic", "systolic_bp", "presion_sistolica"},
    "bp_dia": {"bp_dia", "dia", "diastolic", "diastolic_bp", "presion_diastolica"},
    "temp_c": {"temp_c", "temp", "body_temp_c", "temperatura"},
    "hydration_pct": {"hydration_pct", "hyd", "hydration_percent", "hidratacion"},
    "activity": {"activity", "actividad", "phase", "fase"},
    "time": {"time", "time [s]", "time_s", "timestamp", "measured_at", "fecha", "tiempo"},
}

CANONICAL_UNITS: dict[str, str] = {
    "hr": "bpm",
    "rr": "resp/min",
    "co2": "mmHg",
    "dose_rate": "μSv/h",
    "spo2": "%",
    "bp_sys": "mmHg",
    "bp_dia": "mmHg",
    "temp_c": "°C",
    "hydration_pct": "%",
}

NUMERIC_SIGNALS: frozenset[str] = frozenset(CANONICAL_UNITS)
CANONICAL_SIGNALS: frozenset[str] = NUMERIC_SIGNALS | {"activity", "time"}

_KPA_TO_MMHG = 7.50062
_KELVIN_OFFSET = 273.15

_UNIT_SUFFIX_RULES: tuple[tuple[str, str], ...] = (
    ("_microsv_h", "usv/h"),
    ("_microsvh", "usv/h"),
    ("_usv_h", "usv/h"),
    ("_usvh", "usv/h"),
    ("_msv_h", "msv/h"),
    ("_msvh", "msv/h"),
    ("_mgy_day", "mgy/d"),
    ("_mgy_d", "mgy/d"),
    ("_mgy_h", "mgy/h"),
    ("_mgyh", "mgy/h"),
    ("_gy_day", "gy/d"),
    ("_gy_d", "gy/d"),
    ("_gy_h", "gy/h"),
    ("_gyh", "gy/h"),
    ("_rad_h", "rad/h"),
    ("_radh", "rad/h"),
    ("_mgy", "mgy"),
    ("_gy", "gy"),
    ("_resp_min", "resp/min"),
    ("_brpm", "brpm"),
    ("_rpm", "rpm"),
    ("_bpm", "bpm"),
    ("_mmhg", "mmhg"),
    ("_kpa", "kpa"),
    ("_ppm", "ppm"),
    ("_percent", "percent"),
    ("_pct", "%"),
    ("_fraction", "fraction"),
    ("_ratio", "ratio"),
    ("_celsius", "c"),
    ("_degc", "c"),
    ("_kelvin", "k"),
    ("_c", "c"),
    ("_k", "k"),
)

_TIME_SUFFIX_RULES: tuple[tuple[str, str], ...] = (
    ("_ms", "ms"),
    ("_s", "s"),
)

_BRACKET_UNIT_RE = re.compile(r"[\[\(]([^\]\)]+)[\]\)]\s*$")
_TIME_PREFIX_RE = re.compile(r"^(time|tiempo|elapsed|t)(?:_|$)")


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


def _normalize_micro(text: str) -> str:
    return text.replace("\u00b5", "u").replace("\u03bc", "u")


def _normalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    normalized = _normalize_micro(unit.strip().lower())
    return re.sub(r"\s+", "", normalized)


def _normalize_column_token(column_name: str) -> str:
    text = _strip_accents(_normalize_micro(column_name.strip().lower()))
    text = re.sub(r"[\s\-]+", "_", text)
    return text.strip("_")


def suggest_canonical_column(column_name: str) -> str | None:
    """Sugiere la señal canónica (o 'time'/'activity') correspondiente a una columna."""
    if not column_name or not isinstance(column_name, str):
        return None

    direct = column_name.strip().lower()
    for signal, aliases in ALIASES.items():
        if direct in aliases:
            return signal

    accent_free = _strip_accents(direct)
    for signal, aliases in ALIASES.items():
        if accent_free in aliases:
            return signal

    # Quitar unidad explícita entre corchetes o paréntesis al final, p. ej. "CO2 [kPa]".
    without_brackets = _BRACKET_UNIT_RE.sub("", accent_free).strip()
    if without_brackets:
        for signal, aliases in ALIASES.items():
            if without_brackets in aliases:
                return signal

    token = _normalize_column_token(without_brackets or accent_free)
    for signal, aliases in ALIASES.items():
        if token in aliases:
            return signal

    for suffix, _ in (*_UNIT_SUFFIX_RULES, *_TIME_SUFFIX_RULES):
        if token.endswith(suffix) and len(token) > len(suffix):
            stem = token[: -len(suffix)]
            for signal, aliases in ALIASES.items():
                if stem in aliases:
                    return signal

    return None


def infer_unit_from_column(column_name: str, signal: str | None = None) -> str | None:
    """Infiere la unidad declarada explícitamente en el encabezado de una columna."""
    if not column_name or not isinstance(column_name, str):
        return None

    stripped = column_name.strip().lower()
    match = _BRACKET_UNIT_RE.search(stripped)
    if match:
        bracket_unit = _normalize_unit(match.group(1))
        if bracket_unit:
            return bracket_unit

    token = _normalize_column_token(stripped)
    if token == "bpm":
        return "bpm"

    for suffix, unit in _UNIT_SUFFIX_RULES:
        if token.endswith(suffix) and len(token) > len(suffix):
            return unit

    resolved_signal = signal or suggest_canonical_column(column_name)
    if resolved_signal == "time" or _TIME_PREFIX_RE.match(token):
        for suffix, unit in _TIME_SUFFIX_RULES:
            if token.endswith(suffix) and len(token) > len(suffix):
                return unit

    return None


def is_missing_marker(raw: Any) -> bool:
    """Indica si un valor crudo representa ausencia explícita (sin rellenar con cero)."""
    if raw is None:
        return True
    if isinstance(raw, bool):
        return False
    if isinstance(raw, (int, float)):
        value = float(raw)
        return not math.isfinite(value) or value in (-999.0, -9999.0)
    if isinstance(raw, str):
        cleaned = raw.strip().lower()
        if cleaned in MISSING_MARKERS or cleaned in {"inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
            return True
        return False
    return False


def parse_nullable_float(raw: Any) -> float | None:
    """Convierte un valor a float o None si es marcador de ausencia, bool o NaN/Inf."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        cleaned = raw.strip()
        if cleaned.lower() in MISSING_MARKERS:
            return None
        value = float(cleaned)
    else:
        raise ValueError(f"Valor no convertible a float: {raw!r}")

    if not math.isfinite(value) or value in (-999.0, -9999.0):
        return None
    return value


def convert_unit(
    signal: str,
    value: float | None,
    unit: str | None,
    *,
    total_pressure_mmhg: float | None = None,
    observed_max: float | None = None,
) -> float | None:
    """Convierte explícitamente una medición a la unidad canónica de ASTRO-VITALS."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise UnitConversionError(f"Valor booleano inválido para señal '{signal}'.")

    numeric = float(value)
    if not math.isfinite(numeric):
        return None

    sig = signal.strip().lower()
    norm_unit = _normalize_unit(unit)
    if norm_unit is None or norm_unit in {"", "unknown", "none", "null", "na", "n/a"}:
        raise UnitConversionError(
            f"Unidad no declarada o desconocida ({unit!r}) para la señal '{signal}'."
        )

    if sig == "co2":
        if norm_unit in {"mmhg", "mm_hg"}:
            return numeric
        if norm_unit == "kpa":
            return numeric * _KPA_TO_MMHG
        if norm_unit == "ppm":
            if (
                total_pressure_mmhg is None
                or isinstance(total_pressure_mmhg, bool)
                or not math.isfinite(float(total_pressure_mmhg))
                or float(total_pressure_mmhg) <= 0
            ):
                raise UnitConversionError(
                    "No se puede convertir CO₂ de ppm a mmHg sin total_pressure_mmhg > 0."
                )
            return numeric * float(total_pressure_mmhg) / 1_000_000.0
        raise UnitConversionError(f"Unidad no soportada para 'co2': {unit!r}.")

    if sig == "dose_rate":
        if "gy" in norm_unit or "rad" in norm_unit:
            raise UnitConversionError(
                "Conversión prohibida de dosis absorbida (Gy) a dosis equivalente (Sv)."
            )
        if norm_unit in {"usv/h", "usvh", "microsv/h", "microsvh"}:
            return numeric
        if norm_unit in {"msv/h", "msvh"}:
            return numeric * 1000.0
        raise UnitConversionError(f"Unidad no soportada para 'dose_rate': {unit!r}.")

    if sig == "spo2":
        if norm_unit in {"%", "percent", "pct"}:
            return numeric
        if norm_unit in {"fraction", "ratio", "0-1"}:
            if (observed_max is not None and observed_max > 1.0) or numeric > 1.0:
                raise UnitConversionError(
                    "La señal 'spo2' declarada como fracción contiene valores > 1.0."
                )
            return numeric * 100.0
        raise UnitConversionError(f"Unidad no soportada para 'spo2': {unit!r}.")

    if sig == "hr":
        if norm_unit in {"bpm", "1/min"}:
            return numeric
        raise UnitConversionError(f"Unidad no soportada para 'hr': {unit!r}.")

    if sig == "rr":
        if norm_unit in {"resp/min", "rpm", "brpm", "1/min"}:
            return numeric
        raise UnitConversionError(f"Unidad no soportada para 'rr': {unit!r}.")

    if sig in {"bp_sys", "bp_dia"}:
        if norm_unit in {"mmhg", "mm_hg"}:
            return numeric
        if norm_unit == "kpa":
            return numeric * _KPA_TO_MMHG
        raise UnitConversionError(f"Unidad no soportada para '{sig}': {unit!r}.")

    if sig == "temp_c":
        if norm_unit in {"c", "°c", "celsius", "degc"}:
            return numeric
        if norm_unit in {"k", "kelvin"}:
            return numeric - _KELVIN_OFFSET
        raise UnitConversionError(f"Unidad no soportada para 'temp_c': {unit!r}.")

    if sig == "hydration_pct":
        if norm_unit in {"%", "percent", "pct"}:
            return numeric
        raise UnitConversionError(f"Unidad no soportada para 'hydration_pct': {unit!r}.")

    raise UnitConversionError(f"Señal desconocida para conversión: {signal!r}.")
