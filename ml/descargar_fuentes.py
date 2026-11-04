"""Fetch independent source archives for activity, stress, sleep and solar context."""
import argparse
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from bidmc_source import ROOT, atomic_write

DATA = ROOT / "data"
MMASH = "https://physionet.org/files/mmash/1.0.0/"
EVENT = "2024-05-11T04:07:00-SEP-001"
SOURCES = {
    "actividad": ("ppg_dalia", "data.zip", "https://archive.ics.uci.edu/ml/machine-learning-databases/00495/data.zip"),
    "estres": ("wesad", "WESAD.zip", "https://uni-siegen.sciebo.de/s/HGdUkoNlW1Ub0Gx/download"),
    "sueno": ("mmash", "MMASH.zip", MMASH + "MMASH.zip"),
    "solar": ("donki", "sep_2024-05-10_15.json", "https://ccmc.gsfc.nasa.gov/DONKI/WS/get/SEP?startDate=2024-05-10&endDate=2024-05-15"),
}


def download(url, path):
    subprocess.run(["curl.exe", "-fLsS", "--connect-timeout", "25", "--retry", "2",
                    "--retry-delay", "2", "--speed-limit", "1024", "--speed-time", "90",
                    "--max-time", "1800", "-o", str(path), url], check=True)


def digest(path):
    with path.open("rb") as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def select_event(path, folder):
    events = json.loads(path.read_bytes())
    matches = [event for event in events if event.get("sepID") == EVENT]
    if len(matches) != 1:
        raise ValueError(f"La consulta DONKI no contiene exactamente un evento {EVENT}.")
    atomic_write(folder / "evento.json", (json.dumps(matches[0], indent=2) + "\n").encode())


def verify_mmash(folder, checksum):
    sums = {name: sha for sha, name in (line.split() for line in
            (folder / "SHA256SUMS.txt").read_text().splitlines() if line.strip())}
    return sums.get("MMASH.zip") == checksum and sums.get("LICENSE.txt") == digest(folder / "LICENSE.txt")


def acquire(key):
    directory, filename, url = SOURCES[key]
    folder = DATA / directory
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / filename
    receipt = folder / "fuente.json"
    if receipt.exists() and dest.exists():
        previous = json.loads(receipt.read_text(encoding="utf-8"))
        if previous["url"] == url and digest(dest) == previous["sha256"]:
            if key == "solar":
                select_event(dest, folder)
            if key != "sueno" or (all((folder / n).exists() for n in ("SHA256SUMS.txt", "LICENSE.txt"))
                                   and verify_mmash(folder, previous["sha256"])):
                return f"{key}: copia verificada"
    with TemporaryDirectory(dir=folder) as tmp:
        staged = Path(tmp) / filename
        download(url, staged)
        checksum = digest(staged)
        if key == "sueno":
            for name in ("SHA256SUMS.txt", "LICENSE.txt"):
                download(MMASH + name, Path(tmp) / name)
            if not verify_mmash(Path(tmp), checksum):
                raise ValueError("La copia de MMASH no coincide con las sumas publicadas.")
            for name in ("SHA256SUMS.txt", "LICENSE.txt"):
                (Path(tmp) / name).replace(folder / name)
        if key == "solar":
            select_event(staged, folder)
        else:
            with ZipFile(staged) as archive:
                corrupt = archive.testzip()
                if corrupt or not archive.namelist():
                    raise ValueError(f"ZIP incompleto o dañado ({key}): {corrupt}")
        staged.replace(dest)
        info = dict(url=url, file=filename, sha256=checksum, bytes=dest.stat().st_size,
                    acquired_utc=datetime.now(timezone.utc).isoformat())
        atomic_write(receipt, (json.dumps(info, indent=2) + "\n").encode())
    return f"{key}: {info['bytes']:,} bytes verificados"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fuentes", nargs="*")
    names = parser.parse_args().fuentes or list(SOURCES)
    if any(name not in SOURCES for name in names):
        parser.error(f"Fuentes válidas: {', '.join(SOURCES)}")
    errors = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = {pool.submit(acquire, name): name for name in dict.fromkeys(names)}
        for task in as_completed(tasks):
            name = tasks[task]
            try:
                print(task.result(), flush=True)
            except Exception as exc:
                errors.append(name)
                print(f"{name}: {exc}", flush=True)
    if errors:
        raise SystemExit(f"Fallaron: {', '.join(errors)}")


if __name__ == "__main__":
    main()
