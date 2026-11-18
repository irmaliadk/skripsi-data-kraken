"""Periksa candle sumber sebelum harga acuan pertama dilepas."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from thesis_core.data import DATA, TEST_CUTOFF_UTC, read_features, prepare  # noqa: E402


class RawCandleTests(unittest.TestCase):
    """Jaga pemeriksaan waktu dan angka pada CSV mentah."""

    def _write(self, rows):
        folder = tempfile.TemporaryDirectory()
        path = Path(folder.name) / "candles.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(("time", "open", "high", "low", "close", "vwap", "volume", "count"))
            writer.writerows(rows)
        self.addCleanup(folder.cleanup)
        return path

    def test_gap_between_first_two_candles(self):
        """Jeda pertama harus terlihat meskipun baris pertama hanya acuan."""
        path = self._write([
            ("2026-11-11 00:00:00+00:00", 100, 101, 99, 100, 100, 1, 10),
            ("2026-11-11 00:30:00+00:00", 100, 101, 99, 101, 100, 2, 11),
            ("2026-11-11 00:45:00+00:00", 101, 102, 100, 102, 101, 3, 12),
        ])
        with self.assertRaisesRegex(ValueError, "interval candle mentah"):
            read_features(path)

    def test_frozen_study_data(self):
        """Jumlah fitur dan tiga bagian mengikuti batas 11 November."""
        historical, validation, test, _, _ = prepare(DATA)
        self.assertEqual((len(historical), len(validation), len(test)), (1995, 855, 1542))
        self.assertEqual(test[-1][0], TEST_CUTOFF_UTC)

    def test_nan_volume(self):
        """Volume NaN tidak boleh lolos perbandingan volume negatif."""
        path = self._write([
            ("2026-11-11 00:00:00+00:00", 100, 101, 99, 100, 100, "NaN", 10),
            ("2026-11-11 00:15:00+00:00", 100, 101, 99, 101, 100, 2, 11),
        ])
        with self.assertRaisesRegex(ValueError, "angka terhingga"):
            read_features(path)


if __name__ == "__main__":
    unittest.main()
