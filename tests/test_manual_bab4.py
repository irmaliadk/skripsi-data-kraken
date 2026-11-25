"""Periksa implementasi terhadap angka contoh hitung pada Bab 4."""

import math
import statistics
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from src.inti_skripsi.injeksi import injeksi  # noqa: E402
from src.inti_skripsi.data import DATA, baca_fitur  # noqa: E402
from src.inti_skripsi.kswin import statistik_ks, deteksi_kswin  # noqa: E402
from src.inti_skripsi.deteksi_pca_cd import (  # noqa: E402
    hitung_cd_area,
    kovarians,
    eigen_simetris,
    perbarui_page_hinkley,
    persentil,
    _proyeksi_acuan,
    _skor_perubahan,
    proyeksikan,
)


OLD = [6.499787, 6.881411, 6.748760, 6.552508]
NEW = [6.695799, 5.894403, 6.480045, 6.120297]
VOLUME_OLD = [1.777549, 2.670506, 2.450671, 2.481311]


class ManualBab4Tests(unittest.TestCase):
    """Cocokkan empat langkah metode dengan tabel manualisasi."""

    def test_kswin_threshold_and_distance(self):
        """Contoh ID 1–8 menghasilkan D=1 dan ambang 0,7587."""
        ambang = math.sqrt(-math.log(0.1) / 4)
        latest = [value + 1 for value in NEW]
        aliran = [
            (str(index), (0.0, 0.0, value)) for index, value in enumerate(OLD + latest)
        ]
        self.assertAlmostEqual(ambang, 0.7587, places=4)
        self.assertEqual(statistik_ks(OLD, latest), 1.0)
        self.assertEqual(deteksi_kswin(aliran, n=8, r=4, alpha=0.1)[0][0], 7)

    def test_pca_eigenvalues(self):
        """Kovarians ID 1–4 memberi dua nilai eigen pada Tabel 4.11."""
        rows = list(zip(VOLUME_OLD, OLD))
        _, matrix = kovarians(rows)
        eigen = eigen_simetris(matrix)
        self.assertAlmostEqual(matrix[0][0], 0.152567, places=5)
        self.assertAlmostEqual(eigen[0][0], 0.172174, places=5)
        self.assertAlmostEqual(eigen[1][0], 0.011617, places=5)

    def test_page_hinkley(self):
        """Tiga skor 0,30 diikuti 1,00 memberi 0,520 > 0,475."""
        score_sum = m = peak = 0.0
        count = 0
        for score in (0.30, 0.30, 0.30, 1.0):
            score_sum, count, m, peak, average, alarm = perbarui_page_hinkley(
                score, score_sum, count, m, peak, 0.005, 1, "text_ph"
            )
        self.assertAlmostEqual(peak - m, 0.520, places=6)
        self.assertAlmostEqual(average, 0.475, places=6)
        self.assertTrue(alarm)

    def test_pca_original_and_injected_at_id8(self):
        """Kedua aliran memberi alarm jika tiga skor 0,30 diasumsikan."""
        source = baca_fitur(DATA.with_name("btc_15m_study_20261111.csv"))[:8]
        acuan = [values[1:] for _, values in source[:4]]
        original = [values[1:] for _, values in source[4:]]
        injected = [
            values[1:] for _, values in injeksi(source[4:], 0, "mean", 2, 1 / 3)
        ]
        means, directions, reference_pc = _proyeksi_acuan(acuan)
        self.assertEqual(len(directions), 2)
        original_pc = proyeksikan(original, means, directions)
        injected_pc = proyeksikan(injected, means, directions)
        self.assertEqual(
            [
                hitung_cd_area(
                    [row[k] for row in reference_pc], [row[k] for row in original_pc]
                )
                for k in range(2)
            ],
            [0.75, 1.0],
        )
        self.assertEqual(
            [
                hitung_cd_area(
                    [row[k] for row in reference_pc], [row[k] for row in injected_pc]
                )
                for k in range(2)
            ],
            [0.25, 1.0],
        )
        for sample in (original, injected):
            score = _skor_perubahan(
                reference_pc, proyeksikan(sample, means, directions), directions
            )
            self.assertEqual(score, 1.0)
            total = cumulative = peak = 0.0
            count = 0
            for value in (0.30, 0.30, 0.30, score):
                total, count, cumulative, peak, average, alarm = perbarui_page_hinkley(
                    value, total, count, cumulative, peak, 0.005, 1, "text_ph"
                )
            self.assertAlmostEqual(peak - cumulative, 0.520)
            self.assertAlmostEqual(average, 0.475)
            self.assertTrue(alarm)

    def test_fd_histogram_and_cd_area(self):
        """Proyeksi Tabel 4.12 memberi skor CD-Area 0,25 dan 1,00."""
        acuan = [
            [-0.591381, -0.038243],
            [0.378639, -0.083758],
            [0.126308, -0.036292],
            [0.086435, 0.158294],
        ]
        changed = [
            [2.185020, -0.279220],
            [-0.549145, -0.443659],
            [0.138210, -0.812346],
            [0.338628, -0.353642],
        ]
        for dimension, width, score in (
            (0, 0.343215, 0.25),
            (1, 0.078085, 1.0),
        ):
            old = [row[dimension] for row in acuan]
            new = [row[dimension] for row in changed]
            ordered = sorted(old)
            iqr = persentil(ordered, 0.75) - persentil(ordered, 0.25)
            self.assertAlmostEqual(2 * iqr / len(old) ** (1 / 3), width, places=6)
            self.assertAlmostEqual(hitung_cd_area(old, new), score, places=6)

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
                changed = injeksi(rows, 0, scenario, 2, 1 / 3)
                for (_, values), target in zip(changed, targets):
                    self.assertAlmostEqual(values[2], target, places=5)
        scaled = [values[2] for _, values in injeksi(rows, 0, "scale", 2, 1 / 3)]
        self.assertAlmostEqual(
            statistics.pvariance(scaled), 4 * statistics.pvariance(NEW), places=9
        )


if __name__ == "__main__":
    unittest.main()
