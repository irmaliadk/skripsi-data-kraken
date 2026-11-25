"""Periksa cakupan FP dan waktu pada ringkasan validasi."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.inti_skripsi.evaluasi import cocokkan_alarm, ringkas_skenario  # noqa: E402
from src.inti_skripsi.protokol import SCENARIOS  # noqa: E402
from tune_detectors import _ringkasan_skenario  # noqa: E402


class EvaluationBreakdownTests(unittest.TestCase):
    """Jaga definisi metrik saat FP diperinci."""

    def test_alarm_before_onset_is_reported_separately(self):
        """Alarm sebelum injeksi tetap FP tetapi memiliki kolom tersendiri."""
        result = cocokkan_alarm([2, 12, 15, 110], onset=10, length=130, horizon=96)
        self.assertEqual(result["tp"], 1)
        self.assertEqual(result["fp"], 3)
        self.assertEqual(result["fp_before_onset"], 1)
        self.assertEqual(result["fp_after_onset"], 2)
        self.assertEqual(result["delay"], 2)

    def test_scenario_time_excludes_control_and_other_scenarios(self):
        """Waktu tiap skenario hanya menjumlahkan salinannya sendiri."""
        rows = {}
        for index, scenario in enumerate(SCENARIOS, start=1):
            rows[scenario] = [
                {
                    "seconds": float(index),
                    "tp_h96": 1,
                    "fp_h96": 1,
                    "fp_before_onset_h96": 1,
                    "fp_after_onset_h96": 0,
                    "fn_h96": 0,
                    "delay_h96": 2,
                }
            ]
        summaries, _, _ = _ringkasan_skenario(("KSWIN", 200, 30, 0.001), [4], 9.0, rows)
        for index, summary in enumerate(summaries, start=1):
            self.assertEqual(summary["total_seconds"], float(index))
            self.assertEqual(summary["control_seconds"], 9.0)
            self.assertEqual(summary["fp_before_onset"], 1)
            self.assertEqual(summary["fp_after_onset"], 0)
        self.assertEqual(ringkas_skenario(rows[SCENARIOS[0]])["fp"], 1)


if __name__ == "__main__":
    unittest.main()
