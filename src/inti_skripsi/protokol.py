"""Konfigurasi kandidat, titik injeksi, deteksi, dan keluaran penelitian."""

import csv
import math
import random
import time
from pathlib import Path

from .data import FEATURE_COUNT
from .kswin import deteksi_kswin
from .deteksi_pca_cd import JADWAL_PCA_CD, jarak_pemeriksaan, deteksi_pca_cd


SCENARIOS = ("mean", "scale", "correlation", "combined")
INJECTION_SEED = 2015
REPETITIONS = 50
MIN_INJECTION_FRACTION = 0.5
VALIDATION_MAX_INJECTION_FRACTION = 0.75
TEST_MAX_INJECTION_FRACTION = 0.8
MIN_POST_INJECTION_ROWS = 200
KSWIN_WINDOWS = (200, 300, 400, 500)
KSWIN_SAMPLE_SIZES = (30, 60, 90)
KSWIN_FAMILY_ALPHA = 0.01
KSWIN_ALPHAS = (0.0001, 0.001, KSWIN_FAMILY_ALPHA / FEATURE_COUNT)
PCA_WINDOWS = (100, 150, 200, 250, 300)
PCA_THRESHOLDS = (0.5, 1, 2, 5, 10)
PCA_DELTA = 0.005


def daftar_konfigurasi():
    """Hasilkan seluruh kandidat sesuai urutan rancangan Bab 4."""
    for n in KSWIN_WINDOWS:
        for r in KSWIN_SAMPLE_SIZES:
            if n >= 2 * r:
                for alpha in KSWIN_ALPHAS:
                    yield ("KSWIN", n, r, alpha)
    for w in PCA_WINDOWS:
        for xi in PCA_THRESHOLDS:
            for jadwal in JADWAL_PCA_CD:
                yield ("PCA-CD", w, xi, PCA_DELTA, jadwal)


def nama_konfigurasi(konfigurasi):
    """Bentuk nama kandidat dari metode dan pengaturannya."""
    nama = f"{konfigurasi[0]}:{konfigurasi[1]}:{konfigurasi[2]}:{konfigurasi[3]:.9g}"
    return f"{nama}:{konfigurasi[4]}" if len(konfigurasi) == 5 else nama


def rincian_jadwal(konfigurasi):
    """Catat jadwal dan jarak aktual pemeriksaan setiap detektor."""
    if konfigurasi[0] == "KSWIN":
        return {"jadwal_pemeriksaan": "setiap_catatan", "jarak_pemeriksaan": 1}
    jadwal = konfigurasi[4] if len(konfigurasi) == 5 else "lima_persen"
    return {
        "jadwal_pemeriksaan": jadwal,
        "jarak_pemeriksaan": jarak_pemeriksaan(konfigurasi[1], jadwal),
    }


def pilih_titik_injeksi(
    length, upper_fraction, seed=INJECTION_SEED, repetitions=REPETITIONS
):
    """Pilih titik awal acak tanpa pengulangan pada bagian data."""
    lower = math.ceil(MIN_INJECTION_FRACTION * length)
    upper = math.floor(upper_fraction * length)
    choices = range(lower, upper + 1)
    if len(choices) < repetitions or length - upper - 1 < MIN_POST_INJECTION_ROWS:
        raise ValueError("Titik injeksi atau sisa 200 catatan setelah injeksi tidak mencukupi")
    return sorted(random.Random(seed).sample(choices, repetitions))


def jalankan_detektor(konfigurasi, data_sebelumnya, aliran):
    """Isi jendela awal dari data sebelumnya, lalu jalankan detektor."""
    method, a, b, c = konfigurasi[:4]
    pengisian_awal = a - 1 if method == "KSWIN" else 2 * a - 1
    prior = data_sebelumnya[-pengisian_awal:]
    if len(prior) != pengisian_awal:
        raise ValueError("Data sebelum aliran tidak cukup untuk jendela awal")
    start = time.perf_counter()
    if method == "KSWIN":
        raw = deteksi_kswin(prior + aliran, n=a, r=b, alpha=c)
    elif method == "PCA-CD":
        jadwal = konfigurasi[4] if len(konfigurasi) == 5 else "lima_persen"
        raw = deteksi_pca_cd(prior + aliran, w=a, xi=b, delta=c, jadwal=jadwal)[
            "alarms"
        ]
    else:
        raise ValueError(f"Metode detektor tidak dikenal: {method}")
    seconds = time.perf_counter() - start
    daftar_alarm = [i - pengisian_awal for i, _ in raw if i >= pengisian_awal]
    return daftar_alarm, seconds


def tulis_csv(path, records):
    """Simpan daftar hasil dengan urutan kolom dari catatan pertama."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        raise ValueError("Tidak ada hasil untuk ditulis")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
