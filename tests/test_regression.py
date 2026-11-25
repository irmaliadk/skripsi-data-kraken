"""Bandingkan keluaran deterministik refaktor dengan implementasi lama."""

import importlib.util
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "archive" / "scripts"))
import thesis_protocol as old  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from src.inti_skripsi.data import siapkan_data  # noqa: E402
from src.inti_skripsi.evaluasi import cocokkan_alarm  # noqa: E402
from src.inti_skripsi.injeksi import audit_injeksi, buat_aliran  # noqa: E402
from src.inti_skripsi.protokol import (  # noqa: E402
    daftar_konfigurasi,
    pilih_titik_injeksi,
    jalankan_detektor,
)
from scripts.final_test import _baris_uji, baca_konfigurasi_terpilih, pasangkan_waktu  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "archived_final_test", ROOT / "archive" / "scripts" / "final_test.py"
)
old_final = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old_final)

BATAS_LAMA = {
    "HISTORICAL_ROWS": 1995,
    "VALIDATION_ROWS": 855,
    "TEST_ROWS": 1542,
    "HISTORICAL_END": datetime.fromisoformat("2026-10-17 17:30:00+00:00"),
    "VALIDATION_END": datetime.fromisoformat("2026-10-26 15:15:00+00:00"),
    "TEST_CUTOFF_UTC": "2026-11-11 16:45:00+00:00",
}


class RegressionTests(unittest.TestCase):
    """Jaga keluaran alarm dan metrik ketika susunan kode berubah."""

    @classmethod
    def setUpClass(cls):
        """Bekukan salinan CSV agar dua versi membaca data yang sama."""
        cls.folder = tempfile.TemporaryDirectory()
        cls.data = Path(cls.folder.name) / "btc_15m.csv"
        shutil.copyfile(ROOT / "data" / "raw" / "btc_15m_study_20261111.csv", cls.data)
        cls.old_parts = old.prepare(cls.data)
        with patch.multiple("src.inti_skripsi.data", **BATAS_LAMA):
            cls.new_parts = siapkan_data(cls.data)

    @classmethod
    def tearDownClass(cls):
        """Hapus salinan data sementara sesudah pemeriksaan."""
        cls.folder.cleanup()

    def test_features_splits_and_onsets(self):
        """Fitur, pembagian, kandidat, dan titik injeksi harus identik."""
        self.assertEqual(self.old_parts, self.new_parts)
        sebelumnya = [
            c[:4] for c in daftar_konfigurasi() if len(c) == 4 or c[4] == "lima_persen"
        ]
        self.assertEqual(list(old.configurations()), sebelumnya)
        self.assertEqual(old.onsets(855, 0.75), pilih_titik_injeksi(855, 0.75))

    def test_alarm_metrics_and_injection_audit(self):
        """Bandingkan kedua detektor pada empat salinan validasi yang sama."""
        historical, validation = self.old_parts[:2]
        onset = old.onsets(len(validation), 0.75)[0]
        configs = (("KSWIN", 500, 90, 0.001), ("PCA-CD", 100, 1, 0.005))
        for scenario in old.SCENARIOS:
            old_stream = old.make_stream(validation, onset, scenario)
            new_stream = buat_aliran(validation, onset, scenario)
            self.assertEqual(old_stream, new_stream)
            self.assertEqual(
                old.audit_injection(validation, old_stream, onset, scenario),
                audit_injeksi(validation, new_stream, onset, scenario),
            )
            for konfigurasi in configs:
                with self.subTest(scenario=scenario, method=konfigurasi[0]):
                    old_alarms, _ = old.run_detector(
                        konfigurasi, historical, old_stream
                    )
                    new_alarms, _ = jalankan_detektor(
                        konfigurasi, historical, new_stream
                    )
                    self.assertEqual(old_alarms, new_alarms)
                    for horizon in old.SENSITIVITY_HORIZONS:
                        previous = old.score_alarms(
                            old_alarms, onset, len(old_stream), horizon
                        )
                        current = cocokkan_alarm(
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
        cutoff = "2026-11-11 16:45:00+00:00"
        with patch.multiple("src.inti_skripsi.data", **BATAS_LAMA):
            validation, test = _baris_uji(self.data, cutoff)
        old_test = [row for row in self.old_parts[2] if row[0] <= cutoff]
        self.assertEqual(validation, self.old_parts[1])
        self.assertEqual(test, old_test)
        self.assertEqual(len(test), 1542)
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
            pasangkan_waktu(runs, test), old_final.timestamp_rows(runs, test)
        )

    def test_selected_configuration_reader(self):
        """Pembaca konfigurasi tetap menerima payload valid yang sama."""
        commit = "a" * 40
        payload = {
            "code_commit": commit,
            "source": "chronological validation only",
            "dataset_sha256": hashlib.sha256(
                (ROOT / "data" / "raw" / "btc_15m_study_20261111.csv").read_bytes()
            ).hexdigest(),
            "historical_rows": 2008,
            "validation_rows": 1720,
            "repetitions_per_scenario": 50,
            "main_horizon_candles": 96,
            "feature_index": 2,
            "selected": {
                "KSWIN": {
                    "parameters": [400, 90, 0.0001],
                    "jadwal_pemeriksaan": "setiap_catatan",
                    "jarak_pemeriksaan": 1,
                },
                "PCA-CD": {
                    "parameters": [100, 2, 0.005, "lima_persen"],
                    "jadwal_pemeriksaan": "lima_persen",
                    "jarak_pemeriksaan": 5,
                },
            },
        }
        selection = Path(self.folder.name) / "selection.json"
        selection.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(
            baca_konfigurasi_terpilih(selection, self.data, code_commit=commit),
            {
                "KSWIN": ("KSWIN", 400, 90, 0.0001),
                "PCA-CD": ("PCA-CD", 100, 2, 0.005, "lima_persen"),
            },
        )
        with self.assertRaisesRegex(ValueError, "Commit kode uji akhir"):
            baca_konfigurasi_terpilih(selection, self.data, code_commit="b" * 40)
        payload["selected"]["PCA-CD"]["jarak_pemeriksaan"] = 1
        selection.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "jadwal pemeriksaan"):
            baca_konfigurasi_terpilih(selection, self.data, code_commit=commit)
        payload["selected"]["PCA-CD"]["jarak_pemeriksaan"] = 5
        payload["dataset_sha256"] = "0" * 64
        selection.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Konfigurasi validasi"):
            baca_konfigurasi_terpilih(selection, self.data, code_commit=commit)


if __name__ == "__main__":
    unittest.main()
