"""Uji Kolmogorov–Smirnov dan detektor KSWIN dari awal."""

import math
import random

from .data import FEATURE_COUNT


KSWIN_SEED = 2020


def statistik_ks(a, b):
    """Hitung jarak terbesar dua distribusi kumulatif empiris."""
    a, b = sorted(a), sorted(b)
    ia = ib = 0
    largest = 0.0
    for value in sorted(set(a + b)):
        while ia < len(a) and a[ia] <= value:
            ia += 1
        while ib < len(b) and b[ib] <= value:
            ib += 1
        largest = max(largest, abs(ia / len(a) - ib / len(b)))
    return largest


def deteksi_kswin(aliran, n=300, r=30, alpha=0.0001):
    """Periksa setiap jendela penuh dan sisakan r catatan setelah alarm."""
    rng = random.Random(KSWIN_SEED)
    buffer, daftar_alarm = [], []
    ambang = math.sqrt(-math.log(alpha) / r)
    for i, (_, values) in enumerate(aliran):
        buffer.append(values)
        if len(buffer) > n:
            buffer.pop(0)
        if len(buffer) < n:
            continue
        old = rng.sample(range(n - r), r)
        active = [
            j
            for j in range(FEATURE_COUNT)
            if statistik_ks(
                [buffer[k][j] for k in old], [buffer[k][j] for k in range(n - r, n)]
            )
            > ambang
        ]
        if active:
            daftar_alarm.append((i, active))
            buffer = buffer[-r:]
    return daftar_alarm
