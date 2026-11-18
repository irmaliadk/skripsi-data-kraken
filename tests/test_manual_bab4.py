"""Periksa implementasi terhadap angka contoh hitung pada Bab 4."""

import math
import statistics
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from thesis_core.injection import inject  # noqa: E402
from thesis_core.kswin import ks_statistic, reset_kswin  # noqa: E402
from thesis_core.pca_cd import (  # noqa: E402
    covariance,
    eigen_symmetric,
    page_hinkley_step,
)


OLD = [6.499787, 6.881411, 6.748760, 6.552508]
NEW = [6.695799, 5.894403, 6.480045, 6.120297]
VOLUME_OLD = [1.777549, 2.670506, 2.450671, 2.481311]


class ManualBab4Tests(unittest.TestCase):
    """Cocokkan empat langkah metode dengan tabel manualisasi."""

    def test_kswin_threshold_and_distance(self):
        """Contoh ID 1–8 menghasilkan D=1 dan ambang 0,7587."""
        threshold = math.sqrt(-math.log(0.1) / 4)
        latest = [value + 1 for value in NEW]
        stream = [
            (str(index), (0.0, 0.0, value)) for index, value in enumerate(OLD + latest)
        ]
        self.assertAlmostEqual(threshold, 0.7587, places=4)
        self.assertEqual(ks_statistic(OLD, latest), 1.0)
        self.assertEqual(reset_kswin(stream, n=8, r=4, alpha=0.1)[0][0], 7)

    def test_pca_eigenvalues(self):
        """Kovarians ID 1–4 memberi dua nilai eigen pada Tabel 4.11."""
        rows = list(zip(VOLUME_OLD, OLD))
        _, matrix = covariance(rows)
        eigen = eigen_symmetric(matrix)
        self.assertAlmostEqual(matrix[0][0], 0.152567, places=5)
        self.assertAlmostEqual(eigen[0][0], 0.172174, places=5)
        self.assertAlmostEqual(eigen[1][0], 0.011617, places=5)

    def test_page_hinkley(self):
        """Tiga skor 0,30 diikuti 1,00 memberi 0,520 > 0,475."""
        score_sum = m = peak = 0.0
        count = 0
        for score in (0.30, 0.30, 0.30, 1.0):
            score_sum, count, m, peak, average, alarm = page_hinkley_step(
                score, score_sum, count, m, peak, 0.005, 1, "text_ph"
            )
        self.assertAlmostEqual(peak - m, 0.520, places=6)
        self.assertAlmostEqual(average, 0.475, places=6)
        self.assertTrue(alarm)

    def test_four_injection_scenarios(self):
        """Empat baris ID 5–8 mengikuti Tabel 4.5–4.8."""
        rows = [
            (str(index), (0.0, 0.0, value)) for index, value in enumerate(NEW, start=5)
        ]
        expected = {
            "mean": [7.695799, 6.894403, 7.480045, 7.120297],
            "scale": [7.093962, 5.491170, 6.662453, 5.942959],
            "correlation": [6.480045, 6.120297, 6.695799, 5.894403],
            "combined": [7.662453, 6.942959, 8.093962, 6.491170],
        }
        for scenario, targets in expected.items():
            with self.subTest(scenario=scenario):
                changed = inject(rows, 0, scenario, 2, 1 / 3)
                for (_, values), target in zip(changed, targets):
                    self.assertAlmostEqual(values[2], target, places=5)
        scaled = [values[2] for _, values in inject(rows, 0, "scale", 2, 1 / 3)]
        self.assertAlmostEqual(
            statistics.pvariance(scaled), 4 * statistics.pvariance(NEW), places=9
        )


if __name__ == "__main__":
    unittest.main()
