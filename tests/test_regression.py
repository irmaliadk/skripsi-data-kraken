"""Bandingkan keluaran deterministik refaktor dengan implementasi lama."""

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "archive" / "scripts"))
import thesis_protocol as old  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from thesis_core.data import prepare  # noqa: E402
from thesis_core.evaluation import score_alarms  # noqa: E402
from thesis_core.injection import audit_injection, make_stream  # noqa: E402
from thesis_core.protocol import (  # noqa: E402
    configurations,
    onsets,
    run_detector,
)
from final_test import _test_rows, read_selection, timestamp_rows  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "archived_final_test", ROOT / "archive" / "scripts" / "final_test.py"
)
old_final = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old_final)


class RegressionTests(unittest.TestCase):
    """Jaga keluaran alarm dan metrik ketika susunan kode berubah."""

    @classmethod
    def setUpClass(cls):
        """Bekukan salinan CSV agar dua versi membaca data yang sama."""
        cls.folder = tempfile.TemporaryDirectory()
        cls.data = Path(cls.folder.name) / "btc_15m.csv"
        shutil.copyfile(ROOT / "data" / "btc_15m.csv", cls.data)
        cls.old_parts = old.prepare(cls.data)
        cls.new_parts = prepare(cls.data)

    @classmethod
    def tearDownClass(cls):
        """Hapus salinan data sementara sesudah pemeriksaan."""
        cls.folder.cleanup()

    def test_features_splits_and_onsets(self):
        """Fitur, pembagian, kandidat, dan titik injeksi harus identik."""
        self.assertEqual(self.old_parts, self.new_parts)
        self.assertEqual(list(old.configurations()), list(configurations()))
        self.assertEqual(old.onsets(855, 0.75), onsets(855, 0.75))

    def test_alarm_metrics_and_injection_audit(self):
        """Bandingkan kedua detektor pada empat salinan validasi yang sama."""
        historical, validation = self.old_parts[:2]
        onset = old.onsets(len(validation), 0.75)[0]
        configs = (("KSWIN", 500, 90, 0.001), ("PCA-CD", 100, 1, 0.005))
        for scenario in old.SCENARIOS:
            old_stream = old.make_stream(validation, onset, scenario)
            new_stream = make_stream(validation, onset, scenario)
            self.assertEqual(old_stream, new_stream)
            self.assertEqual(
                old.audit_injection(validation, old_stream, onset, scenario),
                audit_injection(validation, new_stream, onset, scenario),
            )
            for config in configs:
                with self.subTest(scenario=scenario, method=config[0]):
                    old_alarms, _ = old.run_detector(config, historical, old_stream)
                    new_alarms, _ = run_detector(config, historical, new_stream)
                    self.assertEqual(old_alarms, new_alarms)
                    for horizon in old.SENSITIVITY_HORIZONS:
                        previous = old.score_alarms(
                            old_alarms, onset, len(old_stream), horizon
                        )
                        current = score_alarms(
                            new_alarms, onset, len(new_stream), horizon
                        )
                        self.assertEqual(
                            previous, {key: current[key] for key in previous}
                        )
                        self.assertEqual(
                            current["fp"],
                            current["fp_before_onset"] + current["fp_after_onset"],
                        )

    def test_final_input_and_output_helpers(self):
        """Periksa cutoff dan keluaran waktu tanpa menjalankan uji akhir."""
        cutoff = "2026-11-08 05:30:00+00:00"
        validation, test = _test_rows(self.data, cutoff)
        old_test = [row for row in self.old_parts[2] if row[0] <= cutoff]
        self.assertEqual(validation, self.old_parts[1])
        self.assertEqual(test, old_test)
        self.assertEqual(len(test), 1209)
        runs = [
            {
                "detector": "KSWIN",
                "scenario": "mean",
                "trial": 1,
                "onset": 4,
                "alarm_indices": "0;7",
            }
        ]
        self.assertEqual(
            timestamp_rows(runs, test), old_final.timestamp_rows(runs, test)
        )

    def test_selected_configuration_reader(self):
        """Pembaca konfigurasi tetap menerima payload valid yang sama."""
        payload = {
            "source": "chronological validation only",
            "historical_rows": 1995,
            "validation_rows": 855,
            "repetitions_per_scenario": 50,
            "main_horizon_candles": 96,
            "feature_index": 2,
            "selected": {
                "KSWIN": {"parameters": [400, 90, 0.0001]},
                "PCA-CD": {"parameters": [100, 2, 0.005]},
            },
        }
        selection = Path(self.folder.name) / "selection.json"
        selection.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(read_selection(selection), old_final.read_selection(selection))


if __name__ == "__main__":
    unittest.main()
