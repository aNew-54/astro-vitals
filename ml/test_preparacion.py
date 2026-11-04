"""Regression checks for temporal leakage, subject leakage and the annotation script."""
import csv
import unittest

from preparar_bidmc import OUT, RECORDS, SPLITS, features_at, hashes, read_record, subject_ids
from preparar_etiquetas import annotate, read_scripts


class PreparationTests(unittest.TestCase):
    def test_features_use_only_history_and_reject_a_stale_channel(self):
        original = {s: {"hr": float(s), "rr": 15.0} for s in range(200)}
        historical = {s: row for s, row in original.items() if s <= 120}
        x = features_at(original, 120)
        self.assertEqual(x, features_at(historical, 120))
        self.assertEqual(x["hr_last"], 120)
        self.assertAlmostEqual(x["hr_slope_30s"], 1.0)
        for s in range(115, 121):
            historical[s]["rr"] = None
        self.assertIsNone(features_at(historical, 120))

    def test_delivered_windows_match_source_targets_and_keep_subjects_together(self):
        checks = hashes()
        ids = subject_ids(checks)
        samples = {r: read_record(r, checks) for r in RECORDS}
        seen_subjects = set()
        with (OUT / "inventario.csv").open(newline="") as handle:
            inventory = list(csv.DictReader(handle))
        self.assertEqual({r["record_id"] for r in inventory}, set(RECORDS))
        for split in SPLITS:
            records = {r["record_id"]: r for r in inventory if r["split"] == split}
            group = {ids[r] for r in records}
            self.assertTrue(seen_subjects.isdisjoint(group))
            seen_subjects.update(group)
            with (OUT / f"ventanas_{split}.csv").open(newline="") as handle:
                windows = list(csv.DictReader(handle))
            self.assertEqual(len(windows), sum(int(r["usable"]) for r in records.values()))
            for w in windows:
                record, t = w["record_id"], int(w["t_s"])
                self.assertIn(record, records)
                self.assertEqual(w["subject_id"], ids[record])
                self.assertEqual(int(w["target_t_s"]), t + 60)
                self.assertEqual(float(w["target_hr_bpm"]), samples[record][t + 60]["hr"])
        self.assertEqual(seen_subjects, set(ids.values()))

    def test_intervention_truth_survives_missing_sensor_and_excludes_mixed_windows(self):
        scenes = read_scripts()
        cabin = "combined_cabin_physiology_pattern"
        self.assertEqual(annotate(scenes["cabina"], 575), (cabin, "senal_insuficiente"))
        self.assertEqual(annotate(scenes["coincidencia"], 500), ("", "patrones_coincidentes"))
        slow = "persistent_recovery_deviation"
        self.assertEqual(annotate(scenes["recuperacion"], 450), (slow, "transicion"))
        self.assertEqual(annotate(scenes["recuperacion"], 570), (slow, "candidata"))
