"""Integrity checks for the published synthetic classifier dataset."""
import csv
import gzip
import json
import math
import unittest
from collections import Counter, defaultdict
from itertools import groupby
from statistics import fmean

from preparar_fusion import GROUPS, OUT, SIGNALS


class FusionDataTests(unittest.TestCase):
    def test_partitions_predictors_and_classes(self):
        manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
        features = [f"{channel}_{suffix}" for channel in SIGNALS
                    for suffix in ("last", "mean_30s", "sd_30s", "slope_30s",
                                   "mean_120s", "sd_120s", "slope_120s")]
        features += ["activity", "phase_duration_s", "hr_delta", "rr_delta"]
        self.assertEqual(manifest["features"], features)
        with (OUT / "sesiones.csv").open() as fh:
            sessions = list(csv.DictReader(fh))
        self.assertEqual(len(sessions), len({s["seed"] for s in sessions}))
        self.assertEqual(len(sessions), len({s["session"] for s in sessions}))
        seen = set()
        for split, expected in GROUPS.items():
            part = {s["session"]: s["profile"] for s in sessions if s["split"] == split}
            profiles = set(part.values())
            self.assertEqual(len(profiles), expected)
            self.assertTrue(profiles.isdisjoint(seen))
            seen.update(profiles)
            self.assertEqual(set(Counter(part.values()).values()), {4})
            with (OUT / f"ventanas_{split}.csv").open() as fh:
                rows = list(csv.DictReader(fh))
            self.assertTrue(all(part[r["session"]] == r["profile"] for r in rows))
            self.assertEqual(len(rows), len({(r["session"], r["t_s"]) for r in rows}))
            classes = Counter(r["pattern"] for r in rows)
            self.assertEqual(set(classes), {"baseline_expected", "activity_expected",
                                            "persistent_recovery_deviation", "combined_cabin_physiology_pattern"})
            self.assertEqual(classes, manifest["splits"][split]["classes"])
            self.assertEqual(len(rows), manifest["splits"][split]["windows"])
            # The duration of rest alone must not reveal whether CO2 is elevated.
            ordinary = {int(r["phase_duration_s"]) for r in rows if r["pattern"] == "baseline_expected"}
            cabin = [int(r["phase_duration_s"]) for r in rows if r["pattern"] == "combined_cabin_physiology_pattern"]
            self.assertGreater(sum(d in ordinary for d in cabin) / len(cabin), 0.8)

    def test_windows_match_causal_telemetry_and_independent_annotation(self):
        with (OUT / "sesiones.csv").open() as fh:
            sessions = {r["session"]: r for r in csv.DictReader(fh)}
        windows = defaultdict(dict)
        for split in GROUPS:
            with (OUT / f"ventanas_{split}.csv").open() as fh:
                for row in csv.DictReader(fh):
                    windows[row["session"]][int(row["t_s"])] = row
        with gzip.open(OUT / "telemetria.csv.gz", "rt") as tf, gzip.open(OUT / "anotaciones.csv.gz", "rt") as af:
            tele = groupby(csv.DictReader(tf), key=lambda r: r["session"])
            annotations = groupby(csv.DictReader(af), key=lambda r: r["session"])
            checked = set()
            for (session, samples), (audit_session, labels) in zip(tele, annotations, strict=True):
                self.assertEqual(session, audit_session)
                self.assertNotIn(session, checked)
                checked.add(session)
                samples, labels = list(samples), list(labels)
                meta = sessions[session]
                self.assertEqual([int(r["t_s"]) for r in samples], list(range(900)))
                self.assertEqual([int(r["t_s"]) for r in labels], list(range(0, 900, 5)))
                self.assertTrue(all(r["profile"] == meta["profile"] and r["source"] == "simulated" for r in samples))
                for signal in ("hr", "rr"):
                    self.assertEqual(float(meta[f"calibration_{signal}"]),
                                     round(fmean(float(r[signal]) for r in samples[:120]), 5))
                phase_start = 0
                for idx, sample in enumerate(samples):
                    if idx and sample["activity"] != samples[idx - 1]["activity"]:
                        phase_start = idx
                    self.assertEqual(int(sample["phase_start_s"]), phase_start)
                for audit in labels:
                    t = int(audit["t_s"])
                    record = windows[session].get(t)
                    self.assertEqual(audit["status"] == "candidata", record is not None)
                    if audit["status"] in {"calibracion", "patrones_coincidentes"}:
                        continue
                    history = samples[t-119:t+1]
                    recent = history[-6:]
                    valid = all(sum(r[channel] != "" for r in history[-w:]) >= 0.8 * w
                                and any(r[channel] for r in recent) for w in (30, 120) for channel in SIGNALS)
                    self.assertEqual(audit["status"] == "senal_insuficiente", not valid)
                    if record is None:
                        continue
                    self.assertEqual(record["pattern"], audit["pattern_at_t"])
                    self.assertEqual(record["activity"], samples[t]["activity"])
                    self.assertEqual(int(record["phase_duration_s"]), t - int(samples[t]["phase_start_s"]))
                    for channel in SIGNALS:
                        for w in (30, 120):
                            points = [(int(r["t_s"]), float(r[channel])) for r in history[-w:] if r[channel]]
                            times, values = zip(*points)
                            mean_t, mean_v = fmean(times), fmean(values)
                            sd = math.sqrt(fmean((v-mean_v)**2 for v in values))
                            slope = sum((s-mean_t)*(v-mean_v) for s,v in points) / sum((s-mean_t)**2 for s in times)
                            for stat, value in (("mean", mean_v), ("sd", sd), ("slope", slope)):
                                self.assertAlmostEqual(float(record[f"{channel}_{stat}_{w}s"]), value, places=7)
                        self.assertEqual(float(record[f"{channel}_last"]), values[-1])
                        if channel in {"hr", "rr"}:
                            self.assertEqual(float(record[f"{channel}_delta"]),
                                             round(values[-1] - float(meta[f"calibration_{channel}"]), 5))
            self.assertEqual(checked, set(sessions))
