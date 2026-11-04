"""Archive NASA's published RR-1 payload and export environmental series offline."""
import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime, timezone
from urllib.request import urlopen

from bidmc_source import ROOT, atomic_write

OUT = ROOT / "data" / "iss_rr1"
URL = "https://visualization.osdr.nasa.gov/eda/dashboard_RR-1"
RAW = OUT / "rr1_original.json"


def source():
    if not RAW.exists() or not (OUT / "fuente.json").exists():
        with urlopen(URL, timeout=45) as response:
            html = response.read(10_000_001)
        if len(html) > 10_000_000:
            raise ValueError("Tamaño inesperado del dashboard RR-1.")
        match = re.search(rb'<script\s+id="data"\s+type="application/json">(.*?)</script>', html, re.S)
        if not match:
            raise ValueError("El visor NASA cambió el formato de su registro.")
        payload = match.group(1)
        if not isinstance(json.loads(payload).get("telemetry_data"), str):
            raise ValueError("Telemetría ausente en el visor NASA.")
        atomic_write(RAW, payload)
        receipt = dict(mission="RR-1", url=URL, archive=RAW.name,
                       sha256=hashlib.sha256(payload).hexdigest(),
                       acquired_utc=datetime.now(timezone.utc).isoformat())
        atomic_write(OUT / "fuente.json", (json.dumps(receipt, indent=2) + "\n").encode())
    content = RAW.read_bytes()
    receipt = json.loads((OUT / "fuente.json").read_text())
    if hashlib.sha256(content).hexdigest() != receipt["sha256"]:
        raise ValueError("RR-1 no coincide con la copia de origen.")
    return json.loads(content)


def value_or_blank(value, nonnegative):
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except ValueError:
        if str(value).strip().lower() in {"na", "nan", "null", "n/a"}:
            return ""
        raise
    return number if math.isfinite(number) and (not nonnegative or number >= 0) else ""


def table(name, data, time_field, columns):
    times = data["time"]
    if not times or any(len(data[k]) != len(times) for k in columns):
        raise ValueError(f"Series de distinta longitud en {name}.")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([time_field, *columns.values()])
    counts = {field: 0 for field in columns.values()}
    for index, timestamp in enumerate(times):
        row = []
        for key, field in columns.items():
            value = value_or_blank(data[key][index], nonnegative=(not key.startswith("temperature")))
            counts[field] += int(value != "")
            row.append(value)
        writer.writerow([timestamp, *row])
    atomic_write(OUT / name, output.getvalue().encode())
    return dict(rows=len(times), first=times[0], last=times[-1], valid=counts)


def main():
    payload = source()
    tel = json.loads(payload["telemetry_data"])
    rad = json.loads(payload["radiation_data"])
    cabin = table("cabina.csv", tel, "controller_time_gmt", {
        "co2_iss": "co2_iss_ppm", "co2_ground": "co2_ground_ppm",
        "temperature_iss": "temp_iss_degC", "temperature_ground": "temp_ground_degC",
        "rh_iss": "rh_iss_percent", "rh_ground": "rh_ground_percent"})
    radiation = table("radiacion_ambiental.csv", rad, "time_source", {
        "gcr": "gcr_mGy_day", "saa": "saa_mGy_day", "total": "total_mGy_day"})
    summary = dict(mission=payload["mission"], telemetry=cabin, radiation=radiation)
    atomic_write(OUT / "resumen.json", (json.dumps(summary, indent=2) + "\n").encode())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
