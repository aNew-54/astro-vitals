"""Inspección y conversión explícita de registros CSV, TSV, JSON y JSONL a telemetría canónica."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from .units import (
    CANONICAL_SIGNALS,
    CANONICAL_UNITS,
    NUMERIC_SIGNALS,
    UnitConversionError,
    convert_unit,
    infer_unit_from_column,
    is_missing_marker,
    parse_nullable_float,
    suggest_canonical_column,
)

SUPPORTED_FORMATS = {".csv", ".tsv", ".json", ".jsonl"}

_ACTIVITY_MAP: dict[str, str] = {
    "rest": "rest",
    "reposo": "rest",
    "baseline": "rest",
    "basal": "rest",
    "idle": "rest",
    "sleep": "rest",
    "sueno": "rest",
    "exercise": "exercise",
    "ejercicio": "exercise",
    "activity": "exercise",
    "actividad": "exercise",
    "active": "exercise",
    "activo": "exercise",
    "work": "exercise",
    "trabajo": "exercise",
    "eva": "exercise",
    "recovery": "recovery",
    "recuperacion": "recovery",
    "cooldown": "recovery",
    "post_exercise": "recovery",
    "unknown": "unknown",
    "desconocido": "unknown",
    "desconocida": "unknown",
}


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


def _load_raw_rows(path: Path) -> tuple[str, list[str], list[dict[str, Any]], str]:
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Formato no soportado '{path.suffix}'. Formatos válidos: .csv, .tsv, .json, .jsonl."
        )

    raw_bytes = path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    fmt = suffix.lstrip(".")

    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter, skipinitialspace=True)
            if reader.fieldnames is None:
                raise ValueError(f"El archivo '{path}' está vacío o no tiene cabecera.")
            columns = [col.strip() for col in reader.fieldnames if col is not None]
            if not columns or any(col == "" for col in columns):
                raise ValueError(f"Cabecera inválida en '{path}'.")
            reader.fieldnames = columns
            rows: list[dict[str, Any]] = []
            for row in reader:
                cleaned_row = {k: v for k, v in row.items() if k is not None}
                rows.append(cleaned_row)
        return fmt, columns, rows, sha256

    text = raw_bytes.decode("utf-8-sig")
    if suffix == ".json":
        payload = json.loads(text)
        if isinstance(payload, dict):
            records = payload.get("records")
            if not isinstance(records, list):
                raise ValueError(
                    "El archivo JSON debe contener una lista de objetos o la clave 'records'."
                )
            rows = records
        elif isinstance(payload, list):
            rows = payload
        else:
            raise ValueError("El archivo JSON debe ser una lista de registros o {'records': [...]}.")
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]

    normalized_rows: list[dict[str, Any]] = []
    seen_columns: dict[str, None] = {}
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise ValueError(f"El registro #{index} en '{path}' no es un objeto JSON.")
        clean_item: dict[str, Any] = {}
        for key, value in item.items():
            col_name = str(key).strip()
            seen_columns[col_name] = None
            clean_item[col_name] = value
        normalized_rows.append(clean_item)

    return fmt, list(seen_columns.keys()), normalized_rows, sha256


def _compute_missing_counts(columns: list[str], rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {col: 0 for col in columns}
    for row in rows:
        for col in columns:
            if col not in row or is_missing_marker(row.get(col)):
                counts[col] += 1
    return counts


def inspect_file(path: str | Path) -> dict[str, Any]:
    """Inspecciona columnas, valores faltantes, rangos y unidades inferidas sin modificar datos."""
    source_path = Path(path)
    fmt, columns, rows, sha256 = _load_raw_rows(source_path)
    rows_count = len(rows)
    missing_counts = _compute_missing_counts(columns, rows)

    column_summaries: list[dict[str, Any]] = []
    for col in columns:
        suggested = suggest_canonical_column(col)
        numeric_values: list[float] = []
        for row in rows:
            raw = row.get(col)
            try:
                parsed = parse_nullable_float(raw)
            except ValueError:
                parsed = None
            if parsed is not None:
                numeric_values.append(parsed)

        missing_count = missing_counts[col]
        missing_pct = round((missing_count / rows_count) * 100.0, 2) if rows_count > 0 else 0.0
        column_summaries.append(
            {
                "name": col,
                "suggested_signal": suggested,
                "missing_count": missing_count,
                "missing_pct": missing_pct,
                "min": min(numeric_values) if numeric_values else None,
                "max": max(numeric_values) if numeric_values else None,
                "inferred_unit": infer_unit_from_column(col, suggested),
            }
        )

    return {
        "file": str(source_path),
        "format": fmt,
        "rows_count": rows_count,
        "sha256": sha256,
        "columns": column_summaries,
    }


def _resolve_column_mapping(
    columns: list[str],
    mapping: dict[str, str] | None,
) -> tuple[dict[str, str], list[str]]:
    col_mapping: dict[str, str] = {}
    assigned_signals: dict[str, str] = {}

    if mapping:
        for col in columns:
            if col in mapping:
                target = mapping[col]
                if target is None or str(target).strip().lower() in {"", "extra", "extras", "ignore"}:
                    continue
                normalized_target = str(target).strip().lower()
                if normalized_target not in CANONICAL_SIGNALS:
                    raise ValueError(
                        f"Señal canónica desconocida en mapping para '{col}': {target!r}."
                    )
                if normalized_target in assigned_signals:
                    raise ValueError(
                        f"Múltiples columnas mapeadas a la misma señal '{normalized_target}': "
                        f"{assigned_signals[normalized_target]!r} y {col!r}."
                    )
                col_mapping[col] = normalized_target
                assigned_signals[normalized_target] = col

    explicit_cols = set(mapping.keys()) if mapping else set()
    auto_claimed_by: dict[str, str] = {}
    for col in columns:
        if col in explicit_cols:
            continue
        suggested = suggest_canonical_column(col)
        if suggested is None:
            continue
        if suggested in assigned_signals:
            # Si el usuario ya asignó explícitamente otra columna a esa señal, esta pasa a extras.
            if suggested not in auto_claimed_by:
                continue
        if suggested in auto_claimed_by:
            raise ValueError(
                f"Múltiples columnas sugieren la misma señal '{suggested}': "
                f"{auto_claimed_by[suggested]!r} y {col!r}. Desambigua con 'mapping'."
            )
        col_mapping[col] = suggested
        assigned_signals[suggested] = col
        auto_claimed_by[suggested] = col

    extra_columns = [col for col in columns if col not in col_mapping]
    return col_mapping, extra_columns


def _resolve_unit(
    col: str,
    signal: str,
    units: dict[str, str] | None,
) -> str | None:
    if units:
        if col in units:
            return units[col]
        if signal in units:
            return units[signal]
        col_lower = col.strip().lower()
        for key, value in units.items():
            if key.strip().lower() == col_lower:
                return value
        for key, value in units.items():
            if key.strip().lower() == signal:
                return value
    return infer_unit_from_column(col, signal)


def _normalize_activity(raw: Any) -> str:
    if raw is None or isinstance(raw, bool) or is_missing_marker(raw):
        return "unknown"
    cleaned = _strip_accents(str(raw).strip().lower()).replace("-", "_").replace(" ", "_")
    return _ACTIVITY_MAP.get(cleaned, "unknown")


def _parse_extra_value(raw: Any) -> float | str | None:
    if is_missing_marker(raw):
        return None
    if isinstance(raw, bool):
        return str(raw).lower()
    if isinstance(raw, (int, float)):
        return parse_nullable_float(raw)
    if isinstance(raw, str):
        stripped = raw.strip()
        try:
            return parse_nullable_float(stripped)
        except ValueError:
            return stripped
    return json.dumps(raw, ensure_ascii=False)


def _parse_time_value(
    raw: Any,
    time_unit: str | None,
    base_utc: datetime,
) -> tuple[str, float | None]:
    if raw is None or isinstance(raw, bool) or is_missing_marker(raw):
        raise ValueError("Marca de tiempo ausente en una fila con columna temporal.")

    norm_unit = time_unit.strip().lower() if time_unit is not None else None
    if norm_unit in {"", "unknown", "none", "null", "na", "n/a"}:
        raise UnitConversionError(f"Unidad de tiempo inválida o desconocida: {time_unit!r}.")

    numeric_value: float | None = None
    if isinstance(raw, (int, float)):
        numeric_value = parse_nullable_float(raw)
    elif isinstance(raw, str):
        try:
            numeric_value = parse_nullable_float(raw)
        except ValueError:
            numeric_value = None

    if numeric_value is not None:
        if norm_unit in {None, "s", "sec", "secs", "second", "seconds", "seg"}:
            rel_s = numeric_value
        elif norm_unit in {"ms", "msec", "millisecond", "milliseconds"}:
            rel_s = numeric_value / 1000.0
        elif norm_unit in {"min", "mins", "minute", "minutes"}:
            rel_s = numeric_value * 60.0
        elif norm_unit in {"h", "hr", "hrs", "hour", "hours"}:
            rel_s = numeric_value * 3600.0
        else:
            raise UnitConversionError(f"Unidad de tiempo relativo no soportada: {time_unit!r}.")
        if rel_s < 0:
            raise ValueError(f"El tiempo relativo no puede ser negativo: {rel_s}.")
        measured_at = (base_utc + timedelta(seconds=rel_s)).astimezone(UTC).isoformat()
        return measured_at, rel_s

    text = str(raw).strip()
    try:
        parsed_dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Formato temporal no reconocido: {raw!r}.") from exc

    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=UTC)
    else:
        parsed_dt = parsed_dt.astimezone(UTC)
    return parsed_dt.isoformat(), None


def convert_file(
    path: str | Path,
    output_dir: str | Path | None = None,
    *,
    units: dict[str, str] | None = None,
    mapping: dict[str, str] | None = None,
    total_pressure_mmhg: float | None = None,
    base_time: datetime | None = None,
    source_name: str | None = None,
) -> dict[str, Any]:
    """Convierte un archivo de registro a registros compatibles con Telemetry y su manifiesto."""
    source_path = Path(path)
    _, columns, rows, sha256 = _load_raw_rows(source_path)
    missing_counts = _compute_missing_counts(columns, rows)

    col_mapping, extra_columns = _resolve_column_mapping(columns, mapping)

    resolved_units: dict[str, str] = {}
    observed_max_by_col: dict[str, float | None] = {}

    for col, signal in col_mapping.items():
        if signal not in NUMERIC_SIGNALS:
            continue
        unit = _resolve_unit(col, signal, units)
        if unit is None:
            raise UnitConversionError(
                f"Falta unidad declarada para la columna '{col}' (señal '{signal}'). "
                "Declárala con --unit o en el encabezado."
            )
        parsed_col_vals: list[float] = []
        for row in rows:
            parsed = parse_nullable_float(row.get(col))
            if parsed is not None:
                parsed_col_vals.append(parsed)
        observed_max = max(parsed_col_vals) if parsed_col_vals else None
        # Validar unidad y precondiciones (p. ej. Gy prohibido o ppm sin presión total).
        convert_unit(
            signal,
            1.0,
            unit,
            total_pressure_mmhg=total_pressure_mmhg,
            observed_max=observed_max,
        )
        resolved_units[col] = unit
        observed_max_by_col[col] = observed_max

    time_cols = [col for col, sig in col_mapping.items() if sig == "time"]
    time_col = time_cols[0] if time_cols else None
    time_unit: str | None = None
    if time_col is not None:
        time_unit = _resolve_unit(time_col, "time", units)
        if time_unit is not None and time_unit.strip().lower() in {"unknown", "none", "null", ""}:
            raise UnitConversionError(f"Unidad de tiempo inválida para '{time_col}': {time_unit!r}.")

    activity_cols = [col for col, sig in col_mapping.items() if sig == "activity"]
    activity_col = activity_cols[0] if activity_cols else None

    if base_time is None:
        base_utc = datetime.now(UTC)
    elif base_time.tzinfo is None:
        base_utc = base_time.replace(tzinfo=UTC)
    else:
        base_utc = base_time.astimezone(UTC)

    effective_source_ref = source_name or source_path.name
    records: list[dict[str, Any]] = []

    for idx, row in enumerate(rows):
        if time_col is not None:
            measured_at_iso, original_time_s = _parse_time_value(
                row.get(time_col), time_unit, base_utc
            )
        else:
            measured_at_iso = (base_utc + timedelta(seconds=idx)).astimezone(UTC).isoformat()
            original_time_s = None

        converted_signals: dict[str, float | None] = {sig: None for sig in NUMERIC_SIGNALS}
        for col, signal in col_mapping.items():
            if signal not in NUMERIC_SIGNALS:
                continue
            parsed_val = parse_nullable_float(row.get(col))
            converted_signals[signal] = convert_unit(
                signal,
                parsed_val,
                resolved_units[col],
                total_pressure_mmhg=total_pressure_mmhg,
                observed_max=observed_max_by_col[col],
            )

        activity_val = _normalize_activity(row.get(activity_col)) if activity_col else "unknown"
        extras = {col: _parse_extra_value(row.get(col)) for col in extra_columns}

        records.append(
            {
                "sample_id": str(uuid4()),
                "measured_at": measured_at_iso,
                "hr": converted_signals["hr"],
                "rr": converted_signals["rr"],
                "co2": converted_signals["co2"],
                "dose_rate": converted_signals["dose_rate"],
                "spo2": converted_signals["spo2"],
                "bp_sys": converted_signals["bp_sys"],
                "bp_dia": converted_signals["bp_dia"],
                "temp_c": converted_signals["temp_c"],
                "hydration_pct": converted_signals["hydration_pct"],
                "activity": activity_val,
                "source": "replayed",
                "original_time_s": original_time_s,
                "extras": extras,
                "source_ref": effective_source_ref,
            }
        )

    canonical_units = {
        sig: CANONICAL_UNITS[sig]
        for sig in col_mapping.values()
        if sig in NUMERIC_SIGNALS
    }

    meta: dict[str, Any] = {
        "sha256": sha256,
        "source_file": str(source_path),
        "source_ref": effective_source_ref,
        "rows_converted": len(records),
        "mapping": col_mapping,
        "units": resolved_units,
        "canonical_units": canonical_units,
        "ignored_or_extra_columns": extra_columns,
        "missing_counts": missing_counts,
        "total_pressure_mmhg": total_pressure_mmhg,
    }

    result: dict[str, Any] = {
        **meta,
        "records": records,
        "meta": meta,
    }

    if output_dir is not None:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        jsonl_path = out_path / f"{source_path.stem}.jsonl"
        meta_path = out_path / f"{source_path.stem}.meta.json"

        jsonl_body = "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in records)
        jsonl_path.write_text(jsonl_body, encoding="utf-8")
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        result["jsonl_path"] = str(jsonl_path)
        result["meta_path"] = str(meta_path)

    return result


def _parse_kv_pairs(items: list[str] | None, flag_name: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    if not items:
        return parsed
    for item in items:
        if "=" not in item:
            raise ValueError(f"Formato inválido para {flag_name}: {item!r}. Usa clave=valor.")
        key, value = item.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m astro.adapters.loader",
        description="Inspecciona y convierte archivos de telemetría externa para ASTRO-VITALS.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspecciona columnas y unidades.")
    inspect_parser.add_argument("path", help="Ruta al archivo (.csv, .tsv, .json, .jsonl).")

    convert_parser = subparsers.add_parser("convert", help="Convierte un archivo a .jsonl.")
    convert_parser.add_argument("path", help="Ruta al archivo (.csv, .tsv, .json, .jsonl).")
    convert_parser.add_argument("--output-dir", default=None, help="Directorio de salida.")
    convert_parser.add_argument(
        "--unit",
        action="append",
        default=[],
        help="Unidad explícita con formato col=unit (repetible).",
    )
    convert_parser.add_argument(
        "--map",
        action="append",
        default=[],
        help="Mapeo explícito con formato col=signal (repetible).",
    )
    convert_parser.add_argument(
        "--total-pressure-mmhg",
        type=float,
        default=None,
        help="Presión total en mmHg requerida para convertir CO₂ en ppm.",
    )
    convert_parser.add_argument(
        "--base-time",
        default=None,
        help="Fecha/hora base ISO-8601 UTC para archivos con tiempo relativo numérico.",
    )
    convert_parser.add_argument(
        "--source-name",
        default=None,
        help="Etiqueta de referencia de origen (source_ref).",
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "inspect":
            report = inspect_file(args.path)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0

        units = _parse_kv_pairs(args.unit, "--unit")
        mapping = _parse_kv_pairs(args.map, "--map") or None
        base_dt = datetime.fromisoformat(args.base_time) if args.base_time else None

        output = convert_file(
            args.path,
            output_dir=args.output_dir,
            units=units or None,
            mapping=mapping,
            total_pressure_mmhg=args.total_pressure_mmhg,
            base_time=base_dt,
            source_name=args.source_name,
        )
        summary = {
            "meta": output["meta"],
            "jsonl_path": output.get("jsonl_path"),
            "meta_path": output.get("meta_path"),
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    except (UnitConversionError, ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
