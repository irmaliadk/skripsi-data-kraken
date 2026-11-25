"""Periksa candle sumber sebelum harga acuan pertama dilepas."""

import csv
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from scripts.bekukan_data import bekukan_data  # noqa: E402
from src.inti_skripsi.data import TEST_CUTOFF_UTC, baca_fitur, siapkan_data  # noqa: E402


class RawCandleTests(unittest.TestCase):
    """Jaga pemeriksaan waktu dan angka pada CSV mentah."""

    def _write(self, rows):
        folder = tempfile.TemporaryDirectory()
        path = Path(folder.name) / "candles.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ("time", "open", "high", "low", "close", "vwap", "volume", "count")
            )
            writer.writerows(rows)
        self.addCleanup(folder.cleanup)
        return path

    def test_gap_between_first_two_candles(self):
        """Jeda pertama harus terlihat meskipun baris pertama hanya acuan."""
        path = self._write(
            [
                ("2026-11-11 00:00:00+00:00", 100, 101, 99, 100, 100, 1, 10),
                ("2026-11-11 00:30:00+00:00", 100, 101, 99, 101, 100, 2, 11),
                ("2026-11-11 00:45:00+00:00", 101, 102, 100, 102, 101, 3, 12),
            ]
        )
        with self.assertRaisesRegex(ValueError, "interval candle mentah"):
            baca_fitur(path)

    def _tulis_rangkaian(self, jumlah):
        """Buat catatan sintetis tiap 15 menit dengan nilai fitur yang bervariasi."""
        awal = datetime.fromisoformat("2026-09-26 22:45:00+00:00")
        return self._write(
            (
                (awal + timedelta(minutes=15 * i)).isoformat(sep=" "),
                100,
                110,
                90,
                100 + i % 7,
                100,
                1 + i % 11,
                10 + i % 13,
            )
            for i in range(jumlah)
        )

    def test_frozen_study_data(self):
        """Uji batas dan hitungan dengan catatan sintetis, termasuk ekstra satu candle."""
        sumber = self._tulis_rangkaian(5738)
        salinan = sumber.with_name("penelitian.csv")
        self.assertEqual(len(bekukan_data(sumber, salinan)), 64)
        historical, validation, test, _, _ = siapkan_data(salinan)
        self.assertEqual(
            (len(historical), len(validation), len(test)), (2008, 1720, 2008)
        )
        self.assertEqual(test[-1][0], TEST_CUTOFF_UTC)

    def test_incomplete_study_data(self):
        """Tolak rangkaian yang kurang satu candle dan jangan buat salinannya."""
        sumber = self._tulis_rangkaian(5736)
        salinan = sumber.with_name("penelitian.csv")
        with self.assertRaisesRegex(ValueError, "bagian uji|waktu terakhir uji"):
            siapkan_data(sumber)
        with self.assertRaisesRegex(ValueError, "tepat 5737 candle"):
            bekukan_data(sumber, salinan)
        self.assertFalse(salinan.exists())

    def test_nan_volume(self):
        """Volume NaN tidak boleh lolos perbandingan volume negatif."""
        path = self._write(
            [
                ("2026-11-11 00:00:00+00:00", 100, 101, 99, 100, 100, "NaN", 10),
                ("2026-11-11 00:15:00+00:00", 100, 101, 99, 101, 100, 2, 11),
            ]
        )
        with self.assertRaisesRegex(ValueError, "angka terhingga"):
            baca_fitur(path)


if __name__ == "__main__":
    unittest.main()
