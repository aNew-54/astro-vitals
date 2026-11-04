"""Build the BIDMC inventory, participant split and 60 s forecast tables offline."""
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from statistics import fmean, pstdev

from bidmc_source import RAW, RECORDS, atomic_write, filenames, hashes, verified

OUT = RAW.parent / "preparado"
SIGNALS = (("hr", "HR", 300), ("rr", "RESP", 100))
SPLITS = ("train", "validation", "test")
FEATURES = [name for signal, _, _ in SIGNALS for name in (
    f"{signal}_last", *(f"{signal}_{stat}_{width}s" for width in (30, 120)
                         for stat in ("mean", "sd", "slope"))
)]


def subject_ids(checks):
    subjects = {}
    for record in RECORDS:
        _, fixed = filenames(record)
        metadata = verified(fixed, checks).decode()
        match = re.search(r"^MIMIC II matched wdb ID:[ \t]*(s\d+)\s*$", metadata, re.M)
        if not match or "Numerics sampling frequency: 1 Hz" not in metadata:
            raise ValueError(f"Revisar identidad/frecuencia del registro {record}.")
        subjects[record] = match[1]
    return subjects


def split_subjects(subjects):
    # BIDMC 01 is a worked example in the project and belongs in training.
    known = subjects["01"]
    def sort_key(subject):
        return hashlib.sha256(f"astro-vitals-bidmc-v1/{subject}".encode()).hexdigest()
    ordered = [known, *sorted(set(subjects.values()) - {known}, key=sort_key)]
    held = round(len(ordered) * 0.15)
    return {s: ("train" if i < len(ordered) - 2 * held else
                "validation" if i < len(ordered) - held else "test")
            for i, s in enumerate(ordered)}


def read_record(record, checks):
    numeric, _ = filenames(record)
    rows = csv.DictReader(io.StringIO(verified(numeric, checks).decode("utf-8-sig")),
                          skipinitialspace=True)
    samples = {}
    for row in rows:
        second = int(row["Time [s]"])
        if samples and second <= next(reversed(samples)):
            raise ValueError(f"Tiempo inválido en {numeric}, segundo {second}")
        sample = {}
        for signal, column, maximum in SIGNALS:
            value = float(row[column]) if row[column].strip() else float("nan")
            sample[signal] = value if math.isfinite(value) and 0 < value <= maximum else None
        samples[second] = sample
    if not samples:
        raise ValueError(f"Registro vacío: {numeric}")
    return samples


def longest_gap(samples, signal):
    longest = current = 0
    for sec in range(min(samples), max(samples) + 1):
        current = current + 1 if samples.get(sec, {}).get(signal) is None else 0
        longest = max(longest, current)
    return longest


def features_at(samples, t, channels=("hr", "rr")):
    features = {}
    for signal in channels:
        for width in (30, 120):
            points = [(s, samples[s][signal]) for s in range(t - width + 1, t + 1)
                      if s in samples and samples[s][signal] is not None]
            if len(points) < math.ceil(0.8 * width) or t - points[-1][0] > 5:
                return None
            times, values = zip(*points)
            center_t, mean = fmean(times), fmean(values)
            slope = (sum((s - center_t) * (v - mean) for s, v in points)
                     / sum((s - center_t) ** 2 for s in times))
            features[f"{signal}_last"] = values[-1]
            for stat, value in (("mean", mean), ("sd", pstdev(values)), ("slope", slope)):
                features[f"{signal}_{stat}_{width}s"] = round(value, 8)
    return features


def prepare_record(record, subject, split, samples, checks):
    numeric, fixed = filenames(record)
    first, last = min(samples), max(samples)
    info = dict(record_id=record, subject_id=subject, split=split, rows=len(samples),
                first_s=first, last_s=last, missing_seconds=last - first + 1 - len(samples))
    for signal, _, _ in SIGNALS:
        valid = sum(row[signal] is not None for row in samples.values())
        info[f"{signal}_valid"] = valid
        info[f"{signal}_coverage_pct"] = round(100 * valid / (last - first + 1), 2)
        info[f"{signal}_max_gap_s"] = longest_gap(samples, signal)
    start = 5 * math.ceil((first + 119) / 5)
    examples = []
    counts = Counter()
    for t in range(start, last - 60 + 1, 5):
        counts["candidate"] += 1
        x = features_at(samples, t)
        if x is None:
            counts["input_rejected"] += 1
            continue
        target = samples.get(t + 60, {}).get("hr")
        if target is None:
            counts["target_missing"] += 1
            continue
        examples.append(dict(record_id=record, subject_id=subject, t_s=t, target_t_s=t + 60,
                             **x, target_hr_bpm=target))
    info.update(candidate=counts["candidate"], input_rejected=counts["input_rejected"],
                target_missing=counts["target_missing"], usable=len(examples),
                numeric_file=numeric, numeric_sha256=checks[numeric],
                metadata_file=fixed, metadata_sha256=checks[fixed])
    return info, examples


def validation_baselines(examples, signals_by_record):
    persistence_errors, trend_errors = [], []
    for row in examples:
        t = row["t_s"]
        samples = signals_by_record[row["record_id"]]
        last_s = next(s for s in range(t, t - 6, -1) if samples.get(s, {}).get("hr") is not None)
        last = row["hr_last"]
        trend = last + row["hr_slope_30s"] * (row["target_t_s"] - last_s)
        persistence_errors.append(abs(row["target_hr_bpm"] - last))
        trend_errors.append(abs(row["target_hr_bpm"] - trend))
    return dict(windows=len(examples), mae_persistence_bpm=round(fmean(persistence_errors), 4),
                mae_trend_30s_bpm=round(fmean(trend_errors), 4))


def write_csv(name, rows, columns):
    content = io.StringIO(newline="")
    writer = csv.DictWriter(content, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(OUT / name, content.getvalue().encode())


def main():
    checks = hashes()
    verified("LICENSE", checks)
    subjects = subject_ids(checks)
    splits = split_subjects(subjects)
    inventory = []
    tables = {split: [] for split in SPLITS}
    validation_signals = {}
    for record, subject in subjects.items():
        split = splits[subject]
        samples = read_record(record, checks)
        info, examples = prepare_record(record, subject, split, samples, checks)
        if split == "validation":
            validation_signals[record] = samples
        inventory.append(info)
        tables[split].extend(examples)

    write_csv("inventario.csv", inventory, inventory[0].keys())
    columns = ["record_id", "subject_id", "t_s", "target_t_s", *FEATURES, "target_hr_bpm"]
    summary = {}
    for split, examples in tables.items():
        write_csv(f"ventanas_{split}.csv", examples, columns)
        part = [r for r in inventory if r["split"] == split]
        summary[split] = dict(participants=len({r["subject_id"] for r in part}), records=len(part),
                              records_with_windows=sum(r["usable"] > 0 for r in part),
                              participants_with_windows=len({r["subject_id"] for r in part if r["usable"]}),
                              windows=len(examples))
    manifest = dict(source_version="BIDMC 1.0.0", preparation_version=1,
                    features=FEATURES, target="target_hr_bpm", horizon_s=60,
                    split_by="MIMIC II matched wdb ID", splits=summary,
                    validation_baselines=validation_baselines(tables["validation"], validation_signals))
    atomic_write(OUT / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
