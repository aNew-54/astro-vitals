"""Generate reference annotations for the simulation scripts, without sensor data."""
import csv
import io
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from bidmc_source import atomic_write

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios"
PERSISTENCE_S = 30
SIGNALS = ("hr", "rr", "co2")


@dataclass(frozen=True)
class Frame:
    activity: str
    intervention: str
    pattern: str
    dropout: str
    onset_s: int


def pattern_at(activity, intervention, elapsed):
    if intervention == "none":
        return "baseline_expected" if activity == "rest" else "activity_expected"
    if elapsed < PERSISTENCE_S or intervention == "slow_and_cabin":
        return ""
    return {"slow": "persistent_recovery_deviation",
            "cabin": "combined_cabin_physiology_pattern"}[intervention]


def read_scripts():
    sessions = defaultdict(list)
    with (SCENARIOS / "guion_v1.csv").open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            name = row["session"]
            start, end = int(row["start_s"]), int(row["end_s"])
            activity, cause, lost = row["activity"], row["intervention"], row["dropout"]
            if start != len(sessions[name]) or end <= start:
                raise ValueError(f"Intervalos no consecutivos: {name} en {start}.")
            if activity not in {"rest", "exercise", "recovery"} or lost not in (*SIGNALS, "none"):
                raise ValueError(f"Actividad o canal desconocido en {name}.")
            if cause not in {"none", "slow", "cabin", "slow_and_cabin"}:
                raise ValueError(f"Intervención desconocida en {name}.")
            if cause in {"slow", "slow_and_cabin"} and activity != "recovery":
                raise ValueError("La desviación requiere una fase de recuperación.")
            series = sessions[name]
            # A sensor dropout does not restart an ongoing injected intervention.
            onset = start
            if series and series[-1].activity == activity and series[-1].intervention == cause:
                onset = series[-1].onset_s
            for t in range(start, end):
                truth = pattern_at(activity, cause, t - onset)
                series.append(Frame(activity, cause, truth, lost, onset))
    return sessions


def annotate(series, t):
    current = series[t]
    truth = current.pattern
    if t < 120:
        return truth, "calibracion"
    if current.intervention == "slow_and_cabin":
        return truth, "patrones_coincidentes"
    win = series[t - 119:t + 1]
    for width in (30, 120):
        for channel in SIGNALS:
            valid = [row.dropout != channel for row in win[-width:]]
            if sum(valid) < 0.8 * width or not any(valid[-6:]):
                return truth, "senal_insuficiente"
    if not truth or any(row.activity != current.activity or row.pattern != truth for row in win):
        return truth, "transicion"
    return truth, "candidata"


def main():
    content = io.StringIO(newline="")
    writer = csv.writer(content, lineterminator="\n")
    writer.writerow(["session", "t_s", "pattern_at_t", "window_status"])
    counts = Counter()
    for name, series in read_scripts().items():
        if any(row.activity != "rest" or row.intervention != "none" or row.dropout != "none"
               for row in series[:120]) or len(series) < 120:
            raise ValueError(f"{name} requiere 120 s de reposo inicial válido.")
        for t in range(0, len(series), 5):
            truth, status = annotate(series, t)
            writer.writerow([name, t, truth, status])
            counts[status] += 1
    atomic_write(SCENARIOS / "anotaciones_v1.csv", content.getvalue().encode())
    print(dict(counts))


if __name__ == "__main__":
    main()
