"""Periksa kombinasi jadwal tanpa menjalankan eksperimen penelitian."""

import unittest
from unittest.mock import patch

from src.inti_skripsi.deteksi_pca_cd import deteksi_pca_cd, jarak_pemeriksaan
from src.inti_skripsi.protokol import daftar_konfigurasi, nama_konfigurasi


class JadwalPcaCdTests(unittest.TestCase):
    def test_grid_dan_jarak(self):
        kandidat = [k for k in daftar_konfigurasi() if k[0] == "PCA-CD"]
        self.assertEqual(len(kandidat), 50)
        self.assertEqual(len({nama_konfigurasi(k) for k in kandidat}), 50)
        for w, jarak in zip((100, 150, 200, 250, 300), (5, 8, 10, 12, 15)):
            self.assertEqual(jarak_pemeriksaan(w, "lima_persen"), jarak)
            self.assertEqual(jarak_pemeriksaan(w, "setiap_catatan"), 1)

    def test_posisi_pemeriksaan_aktual(self):
        aliran = [(None, (i,)) for i in range(209)]
        for jadwal, akhir in (
            ("setiap_catatan", list(range(199, 209))),
            ("lima_persen", [199, 204]),
        ):
            with self.subTest(jadwal=jadwal):
                with (
                    patch(
                        "src.inti_skripsi.deteksi_pca_cd._proyeksi_acuan",
                        return_value=([], [], []),
                    ),
                    patch(
                        "src.inti_skripsi.deteksi_pca_cd.proyeksikan",
                        side_effect=lambda jendela, *_: jendela,
                    ) as proyeksi,
                    patch(
                        "src.inti_skripsi.deteksi_pca_cd._skor_perubahan",
                        return_value=0.0,
                    ),
                ):
                    hasil = deteksi_pca_cd(aliran, w=100, jadwal=jadwal)
                self.assertEqual(
                    [p.args[0][-1][0] for p in proyeksi.call_args_list], akhir
                )
                self.assertEqual(hasil["checks"], len(akhir))
