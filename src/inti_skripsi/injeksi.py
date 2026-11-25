"""Empat injeksi terkendali dan pemeriksaan perubahan yang terbentuk."""

import math
import statistics

from .kswin import statistik_ks


MEAN_SHIFT_SD = 3
SPREAD_MULTIPLIER = 2
CYCLIC_SHIFT_DIVISOR = 2
AUDIT_WINDOW_ROWS = (30, 60, 90, 100, 150, 200, 250, 300, 400, 500)
FEATURE_INDEX = 2


def pearson(a, b):
    """Hitung korelasi Pearson dua deret dengan urutan sama."""
    ma, mb = statistics.mean(a), statistics.mean(b)
    numerator = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    denom = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return numerator / denom if denom else float("nan")


def injeksi(validation, onset, kind, chosen, scale):
    """Ubah fitur terpilih sejak titik injeksi sesuai skenario."""
    out = [(t, list(v)) for t, v in validation]
    after = out[onset:]
    if len(after) < 2:
        raise ValueError("Injeksi memerlukan sedikitnya dua catatan sesudah titik awal")
    if kind in ("mean", "combined"):
        for _, v in after:
            v[chosen] += MEAN_SHIFT_SD * scale
    if kind in ("scale", "combined"):
        center = statistics.mean(v[chosen] for _, v in after)
        for _, v in after:
            v[chosen] = center + SPREAD_MULTIPLIER * (v[chosen] - center)
    if kind in ("correlation", "combined"):
        column = [v[chosen] for _, v in after]
        offset = len(column) // CYCLIC_SHIFT_DIVISOR
        shifted = column[offset:] + column[:offset]
        for (_, v), value in zip(after, shifted):
            v[chosen] = value
    return [(t, tuple(v)) for t, v in out]


def buat_aliran(original, onset, scenario):
    """Sisipkan skenario pada fitur jumlah perdagangan yang dibakukan."""
    return injeksi(original, onset, scenario, FEATURE_INDEX, 1.0)


def _statistik(values):
    """Hitung rerata dan simpangan baku populasi untuk audit."""
    return statistics.mean(values), statistics.pstdev(values)


def _audit_potongan(before, after, size, onset, scenario):
    """Catat perubahan statistik pada satu cakupan sesudah injeksi."""
    base, altered = before[:size], after[:size]
    x = [v[FEATURE_INDEX] for _, v in base]
    y = [v[FEATURE_INDEX] for _, v in altered]
    other = 1 if FEATURE_INDEX != 1 else 0
    paired = [v[other] for _, v in base]
    mean0, sd0 = _statistik(x)
    mean1, sd1 = _statistik(y)
    return {
        "scenario": scenario,
        "onset": onset,
        "scope": "entire_post_onset" if size == len(before) else "first_window",
        "window_rows": size,
        "mean_before": mean0,
        "mean_after": mean1,
        "sd_before": sd0,
        "sd_after": sd1,
        "corr_before": pearson(paired, x),
        "corr_after": pearson(paired, y),
        "ks_before_after": statistik_ks(x, y),
    }


def _verifikasi_injeksi(full, before, after, scenario):
    """Periksa sifat utama skenario pada seluruh bagian injeksi."""
    if scenario == "mean":
        if not math.isclose(
            full["mean_after"] - full["mean_before"], float(MEAN_SHIFT_SD), abs_tol=1e-9
        ):
            raise ValueError("Injeksi rerata tidak sesuai")
    if scenario in ("scale", "combined"):
        if not math.isclose(
            full["sd_after"], SPREAD_MULTIPLIER * full["sd_before"], rel_tol=1e-9
        ):
            raise ValueError("Injeksi varians tidak sesuai")
    if scenario == "correlation":
        if sorted(v[FEATURE_INDEX] for _, v in before) != sorted(
            v[FEATURE_INDEX] for _, v in after
        ):
            raise ValueError("Pergeseran siklik tidak mempertahankan nilai fitur")


def audit_injeksi(original, changed, onset, scenario):
    """Audit segmen penuh dan sejumlah jendela pendek tiap salinan."""
    before, after = original[onset:], changed[onset:]
    if any(x[0] != y[0] for x, y in zip(original, changed)):
        raise ValueError("Injeksi mengubah urutan atau waktu catatan")
    if original[:onset] != changed[:onset]:
        raise ValueError("Injeksi mengubah catatan sebelum titik awal")
    widths = (len(before), *AUDIT_WINDOW_ROWS)
    result = [
        _audit_potongan(before, after, size, onset, scenario)
        for size in dict.fromkeys(widths)
        if size <= len(before)
    ]
    _verifikasi_injeksi(result[0], before, after, scenario)
    return result
