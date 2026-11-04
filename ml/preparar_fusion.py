"""Build the synchronized synthetic cohort and its separate pattern annotations."""
import csv
import gzip
import hashlib
import io
import json
import math
import random
from collections import Counter
from itertools import groupby
from statistics import fmean

from bidmc_source import ROOT, atomic_write
from preparar_bidmc import features_at
from preparar_etiquetas import Frame, SIGNALS, annotate, pattern_at, read_scripts

OUT = ROOT / "data" / "fusion_simulada"
GROUPS = {"train": 20, "validation": 5, "test": 5}


def seed(*parts):
    key = "/".join(("fusion-v1", *parts)).encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def schedule(template, rng, cabin_start=None):
    """Retain interventions, vary boundaries before labeling each generated session."""
    intervals = [(key, len(list(rows))) for key, rows in groupby(
        template, key=lambda f: (f.activity, f.intervention, f.dropout))]
    if cabin_start is not None:
        expected = [("rest", "none", "none"), ("rest", "cabin", "none"),
                    ("rest", "cabin", "rr"), ("rest", "none", "none")]
        if [key for key, _ in intervals] != expected:
            raise ValueError("Revisar la secuencia del guion de cabina antes de variar sus tiempos.")
        # Early sessions also supply long, unperturbed rest after washout. Later
        # sessions supply longer unperturbed rest before onset and more positives.
        max_clear = min(340, len(template) - cabin_start - 60)
        normal_sensor = (rng.randint(186, 213) if cabin_start <= 180
                         else rng.randint(min(278, max_clear - 10), max_clear))
        dropout = rng.randint(43, 56)
        durations = (cabin_start, normal_sensor, dropout, len(template) - cabin_start - normal_sensor - dropout)
        intervals = list(zip(expected, durations))
    states = []
    end = onset = 0
    for i, ((activity, cause, lost), duration) in enumerate(intervals):
        end += duration
        stop = end if i == len(intervals) - 1 or cabin_start is not None else end + rng.randint(-18, 18)
        if not states or (activity, cause) != (states[-1].activity, states[-1].intervention):
            onset = len(states)
        for t in range(len(states), stop):
            states.append(Frame(activity, cause, pattern_at(activity, cause, t - onset), lost, onset))
    return states


def approach(value, target, tau):
    return target + (value - target) * math.exp(-1 / tau)


def simulate(states, profile, rng):
    base_hr, base_rr, base_co2 = profile
    effort = rng.uniform(28, 64)
    breath = rng.uniform(6, 13)
    tau = rng.uniform(24, 46)
    slow_tau = tau * rng.uniform(3, 5)
    cabin_co2, cabin_rr = rng.uniform(1.4, 3.4), rng.uniform(4.0, 8.0)
    cabin_hr = rng.uniform(1.0, 8.0)
    drift = rng.uniform(0, 2 * math.pi)
    hr = control_hr = base_hr
    rr = control_rr = base_rr
    co2 = base_co2
    samples, contrast = {}, {}
    outage_start = rng.randrange(180, len(states) - 18)
    outage_end = outage_start + rng.randint(3, 15)
    outage_signal = rng.choice(SIGNALS)
    for t, frame in enumerate(states):
        effort_on = frame.activity == "exercise"
        slow = frame.intervention in {"slow", "slow_and_cabin"}
        cabin = frame.intervention in {"cabin", "slow_and_cabin"}
        target_hr = base_hr + effort * effort_on
        target_rr = base_rr + breath * effort_on
        control_hr = approach(control_hr, target_hr, tau)
        control_rr = approach(control_rr, target_rr, tau)
        hr = approach(hr, target_hr + cabin_hr * cabin, slow_tau if slow else tau)
        rr = approach(rr, target_rr + cabin_rr * cabin, slow_tau if slow else tau)
        co2 = approach(co2, base_co2 + cabin_co2 * cabin, 22)
        contrast[t] = (hr - control_hr, rr - control_rr, co2 - base_co2)
        row = {"hr": round(hr + 1.6 * math.sin(t / 20 + drift) + rng.gauss(0, 1.4), 2),
               "rr": round(rr + 0.4 * math.sin(t / 14 + drift) + rng.gauss(0, 0.45), 2),
               "co2": round(co2 + rng.gauss(0, 0.09), 3)}
        if frame.dropout != "none":
            row[frame.dropout] = None
        if outage_start <= t < outage_end:
            row[outage_signal] = None
        samples[t] = row
    return samples, contrast


def save_rows(name, rows, compress=False):
    buff = io.StringIO(newline="")
    writer = csv.DictWriter(buff, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    data = buff.getvalue().encode()
    atomic_write(OUT / name, gzip.compress(data, mtime=0) if compress else data)


def build():
    templates = read_scripts()
    telemetry, audit, sessions = [], [], []
    tables = {split: [] for split in GROUPS}
    profile_offset = 0
    for split, count in GROUPS.items():
        # Spread early and late cabin episodes across each partition. At a comparable
        # time in rest, different profiles can have either clean air or an intervention.
        slots = list(range(count))
        random.Random(seed(split, "cabin-timing")).shuffle(slots)
        for index in range(count):
            person = f"F{profile_offset + index + 1:02d}"
            profile_rng = random.Random(seed(split, person))
            profile = (profile_rng.uniform(60, 85), profile_rng.uniform(11, 18), profile_rng.uniform(1.5, 3.0))
            for name, template in templates.items():
                number = seed(split, person, name)
                session = f"S{number:016x}"
                rng = random.Random(number)
                cabin_start = None
                if name == "cabina":
                    cabin_start = 150 + round(430 * slots[index] / (count - 1)) + rng.randint(-9, 9)
                states = schedule(template, rng, cabin_start)
                samples, contrast = simulate(states, profile, rng)
                cal_hr = round(fmean(samples[t]["hr"] for t in range(120)), 5)
                cal_rr = round(fmean(samples[t]["rr"] for t in range(120)), 5)
                sessions.append(dict(profile=person, session=session, split=split, seed=number,
                                     script=name, calibration_hr=cal_hr, calibration_rr=cal_rr))
                phase_start = 0
                for t, frame in enumerate(states):
                    if t and frame.activity != states[t - 1].activity:
                        phase_start = t
                    ids = dict(profile=person, session=session, t_s=t)
                    telemetry.append(dict(**ids, **samples[t], activity=frame.activity,
                                          phase_start_s=phase_start, source="simulated"))
                    if t % 5:
                        continue
                    truth, status = annotate(states, t)
                    x = features_at(samples, t, SIGNALS) if t >= 120 else None
                    dh, dr, dc = contrast[t]
                    if status not in {"calibracion", "patrones_coincidentes"} and x is None:
                        status = "senal_insuficiente"
                    elif status == "candidata":
                        if ((frame.intervention == "slow" and (dh < 2 or dr < 0.5)) or
                              (frame.intervention == "cabin" and (dc < 0.5 or dr < 1))):
                            status = "contraste_debil"
                        elif frame.intervention == "none" and (dh > 2 or dr > 1 or dc > 0.5):
                            status = "transicion_residual"
                    audit.append(dict(**ids, pattern_at_t=truth, status=status,
                                      delta_hr_control=round(dh, 4), delta_rr_control=round(dr, 4),
                                      delta_co2_control=round(dc, 4)))
                    if status == "candidata":
                        x.update(activity=frame.activity, phase_duration_s=t - phase_start,
                                 hr_delta=round(x["hr_last"] - cal_hr, 5),
                                 rr_delta=round(x["rr_last"] - cal_rr, 5))
                        tables[split].append(dict(**ids, **x, pattern=truth))
        profile_offset += count
    save_rows("telemetria.csv.gz", telemetry, True)
    save_rows("anotaciones.csv.gz", audit, True)
    save_rows("sesiones.csv", sessions)
    counts = {}
    for split, rows in tables.items():
        save_rows(f"ventanas_{split}.csv", rows)
        counts[split] = dict(profiles=GROUPS[split], sessions=GROUPS[split] * len(templates),
                             windows=len(rows), classes=dict(Counter(r["pattern"] for r in rows)))
    features = [c for c in tables["train"][0] if c not in {"profile", "session", "t_s", "pattern"}]
    manifest = dict(version=2, source="synthetic", telemetry_hz=1, window_s=120, stride_s=5,
                    features=features, target="pattern", splits=counts, telemetry_rows=len(telemetry),
                    status_counts=dict(Counter(r["status"] for r in audit)))
    atomic_write(OUT / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    build()
