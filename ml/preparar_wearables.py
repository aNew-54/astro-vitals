"""Prepare separate, participant-split activity and stress tables from original archives."""
import argparse
import csv
import hashlib
import io
import json
import pickle
import re
from collections import Counter
from zipfile import ZipFile

import numpy as np

from bidmc_source import ROOT, atomic_write

ACTIVITIES = {1: "reposo_sentado", 2: "escaleras", 3: "futbol_de_mesa", 4: "bicicleta",
              5: "conduccion", 6: "almuerzo", 7: "caminar", 8: "trabajo"}
CONDITIONS = {1: "basal", 2: "estres_inducido", 3: "diversion"}
SOURCES = {"ppg_dalia": ("data.zip", 8, 4, ACTIVITIES, "actividad"),
           "wesad": ("WESAD.zip", 30, 700, CONDITIONS, "condicion")}
FEATURES = ["acc_mag_mean", "acc_mag_sd", "bvp_sd", "eda_mean", "eda_sd", "temp_mean"]
RATES = {b"ACC": 32, b"BVP": 64, b"EDA": 4, b"TEMP": 4}


class ArrayReader(pickle.Unpickler):
    """Python 2 NumPy array reconstruction for the pinned, verified source archives."""
    permitted = {("numpy.core.multiarray", "_reconstruct"): np._core.multiarray._reconstruct,
                 ("numpy", "dtype"): np.dtype, ("numpy", "ndarray"): np.ndarray}

    def find_class(self, module, name):
        try:
            return self.permitted[module, name]
        except KeyError as exc:
            raise pickle.UnpicklingError(f"Objeto no admitido: {module}.{name}") from exc


def write_csv(path, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, buffer.getvalue().encode())


def wrist_features(wrist, start, width):
    channels = {}
    for key, rate in RATES.items():
        part = wrist[key][start * rate:(start + width) * rate]
        if len(part) != width * rate or not np.isfinite(part).all():
            return None
        channels[key] = part
    acc = np.linalg.norm(channels[b"ACC"], axis=1)
    values = (acc.mean(), acc.std(), channels[b"BVP"].std(), channels[b"EDA"].mean(),
              channels[b"EDA"].std(), channels[b"TEMP"].mean())
    return {key: round(float(val), 7) for key, val in zip(FEATURES, values)}


def subject_windows(source, raw, subject, split, width, label_hz, codebook, target):
    data = ArrayReader(raw, encoding="bytes").load()
    if data[b"subject"].decode() != subject:
        raise ValueError(f"Identidad inesperada en {subject}")
    wrist = data[b"signal"][b"wrist"]
    labels = np.ravel(data[b"activity"] if source == "ppg_dalia" else data[b"label"])
    hr_reference = np.ravel(data[b"label"]) if source == "ppg_dalia" else None
    del data
    rows, skipped = [], Counter()
    counts = Counter()
    whole_windows = len(labels) // (label_hz * width)
    for i in range(whole_windows):
        start = i * width
        segment = labels[start * label_hz:(start + width) * label_hz]
        if segment[0] not in codebook or not np.all(segment == segment[0]):
            skipped["label"] += 1
            continue
        x = wrist_features(wrist, start, width)
        if x is None:
            skipped["signal"] += 1
            continue
        row = dict(participante=subject, particion=split, inicio_s=start, fin_s=start + width, **x)
        if hr_reference is not None:
            idx = start // 2  # Source ECG labels cover [2*k, 2*k + 8).
            value = hr_reference[idx] if idx < len(hr_reference) else float("nan")
            row["fc_ecg_referencia_bpm"] = round(float(value), 5) if np.isfinite(value) else ""
        row[target] = codebook[int(segment[0])]
        rows.append(row)
        counts[row[target]] += 1
    if not rows:
        raise ValueError(f"{subject}: sin ventanas utilizables")
    inventory = dict(participante=subject, particion=split, ventanas_completas=whole_windows,
                     excluidas_etiqueta=skipped["label"], excluidas_senal=skipped["signal"],
                     ventanas_utiles=len(rows), **{c: counts[c] for c in codebook.values()})
    return rows, inventory


def prepare(source):
    filename, width, hz, codebook, target = SOURCES[source]
    folder = ROOT / "data" / source
    receipt = json.loads((folder / "fuente.json").read_text(encoding="utf-8"))
    with (folder / filename).open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != receipt["sha256"]:
            raise ValueError(f"{source}: el archivo no coincide con el recibo de adquisición.")
    collected, inventories = [], []
    with ZipFile(folder / filename) as archive:
        members = {m.group(1): name for name in archive.namelist()
                   if (m := re.fullmatch(r"(?:PPG_FieldStudy|WESAD)/(S\d+)/\1\.pkl", name))}
        if len(members) != 15:
            raise ValueError(f"{source}: se esperaban 15 participantes, figuran {len(members)}")
        ordered = sorted(members, key=lambda p: hashlib.sha256(f"wearables-v1/{source}/{p}".encode()).digest())
        for i, subject in enumerate(ordered):
            split = "train" if i < 9 else "validation" if i < 12 else "test"
            with archive.open(members[subject]) as stream:
                rows, info = subject_windows(source, stream, subject, split, width, hz, codebook, target)
            collected.extend(rows)
            inventories.append(info)
            print(f"{source} {subject} {split} {len(rows)}", flush=True)
        readme = next(p for p in archive.namelist() if p.lower().endswith("readme.pdf"))
        atomic_write(folder / "README_original.pdf", archive.read(readme))
    splits = {}
    for split in ("train", "validation", "test"):
        rows = [row for row in collected if row["particion"] == split]
        write_csv(folder / f"ventanas_{split}.csv", rows)
        splits[split] = dict(participants=len({r["participante"] for r in rows}), windows=len(rows),
                             classes=dict(sorted(Counter(r[target] for r in rows).items())))
    write_csv(folder / "inventario.csv", inventories)
    manifest = dict(source=source, version=1, original_sha256=receipt["sha256"],
                    context="terrestrial", features=FEATURES, target=target,
                    window_s=width, stride_s=width, splits=splits, windows=len(collected))
    atomic_write(folder / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("fuentes", nargs="*")
    selected = parser.parse_args().fuentes or list(SOURCES)
    if any(s not in SOURCES for s in selected):
        parser.error("Fuentes: ppg_dalia, wesad")
    for dataset in selected:
        prepare(dataset)
