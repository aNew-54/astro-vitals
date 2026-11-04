"""Prepare one row per recorded MMASH sleep episode, retaining original relative days."""
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import time
from zipfile import ZipFile

from bidmc_source import ROOT, atomic_write

FOLDER = ROOT / "data" / "mmash"
FIELDS = {
    "bed_day": "In Bed Date", "bed_time": "In Bed Time",
    "onset_day": "Onset Date", "onset_time": "Onset Time",
    "out_day": "Out Bed Date", "out_time": "Out Bed Time",
    "bed_min": "Total Minutes in Bed", "sleep_min": "Total Sleep Time (TST)",
    "latency_min": "Latency", "waso_min": "Wake After Sleep Onset (WASO)",
    "efficiency_pct": "Efficiency", "awakenings": "Number of Awakenings",
}
MEMBER = re.compile(r"DataPaper/user_(\d+)/sleep\.csv\Z")


def read_sleep(folder):
    published = {name: checksum for checksum, name in
                 (line.split() for line in (folder / "SHA256SUMS.txt").read_text().splitlines() if line.strip())}
    for name in ("MMASH.zip", "LICENSE.txt"):
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != published[name]:
            raise ValueError(f"No coincide el SHA-256 publicado de {name}.")
    episodes, by_user = [], {}
    with ZipFile(folder / "MMASH.zip") as archive:
        files = [(int(match[1]), member) for member in archive.namelist() if (match := MEMBER.fullmatch(member))]
        for user, member in sorted(files):
            if user in by_user:
                raise ValueError(f"Archivo de sueño duplicado para user_{user}.")
            with archive.open(member) as stream, io.TextIOWrapper(stream, encoding="utf-8-sig", newline="") as handle:
                source = csv.DictReader(handle)
                if not set(FIELDS.values()).issubset(source.fieldnames or []):
                    raise ValueError(f"Faltan columnas de sueño en {member}.")
                by_user[user] = 0
                for position, row in enumerate(source, 1):
                    entry = {"subject_id": f"user_{user}", "episode": position}
                    entry.update({k: row[v] for k, v in FIELDS.items()})
                    entry["same_day_midnight_wrap"] = int(
                        entry["bed_day"] == entry["out_day"]
                        and time.fromisoformat(entry["out_time"]) < time.fromisoformat(entry["bed_time"]))
                    entry["source_member"] = member
                    episodes.append(entry)
                    by_user[user] += 1
    if not episodes:
        raise ValueError("No se encontró ningún episodio en MMASH.")
    return episodes, by_user, published["MMASH.zip"]


def main():
    episodes, by_user, checksum = read_sleep(FOLDER)
    content = io.StringIO(newline="")
    writer = csv.DictWriter(content, episodes[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(episodes)
    summary = dict(dataset="MMASH 1.0.0", source_sha256=checksum, episode_count=len(episodes),
                   participants_reviewed=len(by_user), participants_with_episodes=sum(bool(n) for n in by_user.values()),
                   participants_without_episodes=[f"user_{u}" for u, n in by_user.items() if not n],
                   episode_count_distribution=dict(sorted(Counter(by_user.values()).items())),
                   same_day_midnight_wraps=sum(r["same_day_midnight_wrap"] for r in episodes))
    atomic_write(FOLDER / "episodios_sueno.csv", content.getvalue().encode())
    atomic_write(FOLDER / "resumen.json", (json.dumps(summary, indent=2) + "\n").encode())
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
