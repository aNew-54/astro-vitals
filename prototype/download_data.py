"""Download the small public BIDMC example. No download occurs during the demo."""
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

URL = "https://physionet.org/files/bidmc/1.0.0/bidmc_csv/bidmc_01_Numerics.csv"
LICENSE_URL = "https://physionet.org/files/bidmc/1.0.0/LICENSE"
DEST = Path(__file__).parent / "data" / "bidmc_01_Numerics.csv"


def main():
    with urlopen(URL, timeout=30) as response:
        payload = response.read(100_000)
    with urlopen(LICENSE_URL, timeout=30) as response:
        license_text = response.read(100_000)
    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig")), skipinitialspace=True))
    if not rows or not {"Time [s]", "HR", "RESP"}.issubset(rows[0]):
        raise ValueError("La descarga no tiene las columnas esperadas de BIDMC.")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_bytes(payload)
    (DEST.parent / "BIDMC-LICENSE.txt").write_bytes(license_text)
    DEST.with_suffix(".source.json").write_text(json.dumps({
        "dataset": "BIDMC PPG and Respiration Dataset", "version": "1.0.0", "record": "01",
        "source_url": URL, "dataset_url": "https://physionet.org/content/bidmc/1.0.0/",
        "license": "Open Data Commons Attribution License v1.0",
        "license_url": "https://physionet.org/content/bidmc/view-license/1.0.0/",
        "attribution": "Pimentel, M. A. F., Johnson, A. E. W., & Charlton, P. H. (2018). BIDMC PPG and Respiration Dataset (version 1.0.0). PhysioNet. https://doi.org/10.13026/C2208R",
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(payload).hexdigest(), "rows": len(rows),
        "modifications": "Original CSV unchanged; runtime maps HR/RESP, NaN to null, and retains relative time."
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"BIDMC 01: {len(rows)} muestras guardadas en {DEST}")


if __name__ == "__main__":
    main()
