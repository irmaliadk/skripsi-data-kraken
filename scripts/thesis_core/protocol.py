"""Konfigurasi kandidat, titik injeksi, deteksi, dan keluaran penelitian."""

import csv
import math
import random
import time
from pathlib import Path

from .data import FEATURE_COUNT
from .kswin import reset_kswin
from .pca_cd import pca_cd


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


def configurations():
    """Hasilkan seluruh kandidat sesuai urutan rancangan Bab 4."""
    for n in KSWIN_WINDOWS:
        for r in KSWIN_SAMPLE_SIZES:
            if n >= 2 * r:
                for alpha in KSWIN_ALPHAS:
                    yield ("KSWIN", n, r, alpha)
    for w in PCA_WINDOWS:
        for xi in PCA_THRESHOLDS:
            yield ("PCA-CD", w, xi, PCA_DELTA)


def configuration_name(config):
    """Bentuk nama stabil untuk konfigurasi detektor."""
    return f"{config[0]}:{config[1]}:{config[2]}:{config[3]:.9g}"


def onsets(length, upper_fraction, seed=INJECTION_SEED, repetitions=REPETITIONS):
    """Pilih titik awal acak tanpa pengulangan pada bagian data."""
    lower = math.ceil(MIN_INJECTION_FRACTION * length)
    upper = math.floor(upper_fraction * length)
    choices = range(lower, upper + 1)
    if len(choices) < repetitions or length - upper - 1 < MIN_POST_INJECTION_ROWS:
        raise ValueError("Data tidak cukup untuk titik injeksi dan batas 200 catatan")
    return sorted(random.Random(seed).sample(choices, repetitions))


def run_detector(config, preceding, stream):
    """Isi jendela awal dari data sebelumnya, lalu jalankan detektor."""
    method, a, b, c = config
    warmup = a - 1 if method == "KSWIN" else 2 * a - 1
    prior = preceding[-warmup:]
    if len(prior) != warmup:
        raise ValueError("Data sebelum aliran tidak cukup untuk jendela awal")
    start = time.perf_counter()
    if method == "KSWIN":
        raw = reset_kswin(prior + stream, n=a, r=b, alpha=c)
    elif method == "PCA-CD":
        raw = pca_cd(prior + stream, w=a, xi=b, delta=c, mode="text_ph")["alarms"]
    else:
        raise ValueError(f"Metode detektor tidak dikenal: {method}")
    seconds = time.perf_counter() - start
    alarms = [i - warmup for i, _ in raw if i >= warmup]
    return alarms, seconds


def write_csv(path, records):
    """Simpan daftar hasil dengan urutan kolom dari catatan pertama."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        raise ValueError("Tidak ada hasil untuk ditulis")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
