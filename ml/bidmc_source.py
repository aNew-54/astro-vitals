"""Download and verify the small BIDMC files needed for the heart-rate task."""
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "bidmc" / "raw"
BASE = "https://physionet.org/files/bidmc/1.0.0/"
RECORDS = tuple(f"{i:02d}" for i in range(1, 54))


def filenames(record):
    prefix = f"bidmc_csv/bidmc_{record}"
    return prefix + "_Numerics.csv", prefix + "_Fix.txt"


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        name = Path(tmp.name)
        try:
            tmp.write(data)
        except BaseException:
            tmp.close()
            name.unlink(missing_ok=True)
            raise
    try:
        os.replace(name, path)
    finally:
        name.unlink(missing_ok=True)


def hashes():
    return {name: digest for digest, name in (
        line.split() for line in (RAW / "SHA256SUMS.txt").read_text().splitlines() if line.strip()
    )}


def verified(relative, checks):
    data = (RAW / relative).read_bytes()
    if hashlib.sha256(data).hexdigest() != checks[relative]:
        raise ValueError(f"SHA-256 incorrecto: {relative}")
    return data


def fetch(relative):
    for attempt in range(3):
        try:
            with urlopen(BASE + relative, timeout=20) as response:
                data = response.read(200_001)
            if len(data) > 200_000:
                raise ValueError(f"Tamaño inesperado: {relative}")
            return data
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            sleep(attempt + 1)


def main():
    atomic_write(RAW / "SHA256SUMS.txt", fetch("SHA256SUMS.txt"))
    checks = hashes()
    paths = ["LICENSE", *(name for record in RECORDS for name in filenames(record))]

    def ensure(relative):
        if (RAW / relative).is_file():
            verified(relative, checks)
            return
        local = ROOT / "prototype" / "data" / Path(relative).name
        data = local.read_bytes() if local.is_file() else fetch(relative)
        if hashlib.sha256(data).hexdigest() != checks[relative]:
            raise ValueError(f"SHA-256 incorrecto: {relative}")
        atomic_write(RAW / relative, data)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for _ in pool.map(ensure, paths):
            pass
    print(f"BIDMC 1.0.0: {len(paths)} archivos verificados contra PhysioNet.")


if __name__ == "__main__":
    main()
