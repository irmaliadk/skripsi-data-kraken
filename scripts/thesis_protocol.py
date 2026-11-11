"""Shared, chronological protocol for the KSWIN versus PCA-CD thesis.

This file implements the design in Bab 4. It contains no test-set results and
does not choose a detector configuration from the test period.
"""

import csv
import datetime as dt
import math
import random
import statistics
import time
from pathlib import Path

from pilot_detectors import ks_statistic, pca_cd, read_features
from validation_detectors import inject, pearson, reset_kswin


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "btc_15m.csv"
HISTORICAL_END = "2026-10-17 17:30:00+00:00"
VALIDATION_END = "2026-10-26 15:15:00+00:00"
HISTORICAL_ROWS = 1995
VALIDATION_ROWS = 855
SCENARIOS = ("mean", "scale", "correlation", "combined")
FEATURE_INDEX = 2  # log(1 + jumlah perdagangan), as in the manual example.
SEED = 2015
REPETITIONS = 50
MAIN_HORIZON = 96
SENSITIVITY_HORIZONS = (24, 25, 48, 50, 85, 96, 100, 192, 200)


def configurations():
    for n in (200, 300, 400, 500):
        for r in (30, 60, 90):
            if n >= 2 * r:
                for alpha in (.0001, .001, .01 / 3):
                    yield ("KSWIN", n, r, alpha)
    for w in (100, 150, 200, 250, 300):
        for xi in (.5, 1, 2, 5, 10):
            yield ("PCA-CD", w, xi, .005)


def configuration_name(config):
    return f"{config[0]}:{config[1]}:{config[2]}:{config[3]:.9g}"


def check_data(rows):
    times = [dt.datetime.fromisoformat(stamp) for stamp, _ in rows]
    if any(b - a != dt.timedelta(minutes=15) for a, b in zip(times, times[1:])):
        raise ValueError("Data berfitur memiliki urutan waktu atau interval yang tidak lengkap")
    if len(set(times)) != len(times):
        raise ValueError("Data berfitur memiliki waktu ganda")


def prepare(path=DATA):
    rows = read_features(path)
    check_data(rows)
    historical = [row for row in rows if row[0] <= HISTORICAL_END]
    validation = [row for row in rows
                  if HISTORICAL_END < row[0] <= VALIDATION_END]
    test = [row for row in rows if row[0] > VALIDATION_END]
    if len(historical) != HISTORICAL_ROWS or historical[-1][0] != HISTORICAL_END:
        raise ValueError("Batas bagian historis tidak sesuai Bab 4")
    if len(validation) != VALIDATION_ROWS or validation[-1][0] != VALIDATION_END:
        raise ValueError("Batas bagian validasi tidak sesuai Bab 4")
    means = [statistics.mean(v[j] for _, v in historical) for j in range(3)]
    spreads = [statistics.stdev(v[j] for _, v in historical) for j in range(3)]
    if any(value <= 0 for value in spreads):
        raise ValueError("Simpangan baku historis harus positif")

    def standardize(part):
        return [(stamp, tuple((values[j] - means[j]) / spreads[j]
                              for j in range(3))) for stamp, values in part]

    return (standardize(historical), standardize(validation),
            standardize(test), means, spreads)


def onsets(length, upper_fraction, seed=SEED, repetitions=REPETITIONS):
    lower = math.ceil(.5 * length)
    upper = math.floor(upper_fraction * length)
    choices = range(lower, upper + 1)
    if len(choices) < repetitions or length - upper - 1 < 200:
        raise ValueError("Data tidak cukup untuk titik injeksi dan batas 200 catatan")
    return sorted(random.Random(seed).sample(choices, repetitions))


def make_stream(original, onset, scenario):
    # Historical features are standardized to a sample SD of exactly one.
    return inject(original, onset, scenario, FEATURE_INDEX, 1.0)


def run_detector(config, historical, stream):
    method, a, b, c = config
    warmup = a - 1 if method == "KSWIN" else 2 * a - 1
    prior = historical[-warmup:]
    if len(prior) != warmup:
        raise ValueError("Bagian historis tidak cukup untuk jendela awal")
    start = time.perf_counter()
    if method == "KSWIN":
        raw = reset_kswin(prior + stream, n=a, r=b, alpha=c)
    elif method == "PCA-CD":
        raw = pca_cd(prior + stream, w=a, xi=b, delta=c,
                     mode="text_ph")["alarms"]
    else:
        raise ValueError(method)
    seconds = time.perf_counter() - start
    alarms = [i - warmup for i, _ in raw if i >= warmup]
    return alarms, seconds


def score_alarms(alarms, onset, length, horizon=MAIN_HORIZON):
    matches = [index for index in alarms
               if onset <= index <= min(onset + horizon, length - 1)]
    tp = int(bool(matches))
    return {
        "tp": tp, "fp": len(alarms) - tp, "fn": 1 - tp,
        "delay": min(matches) - onset if matches else None,
    }


def measures(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _stats(values):
    return (statistics.mean(values), statistics.pstdev(values))


def audit_injection(original, changed, onset, scenario):
    """Record actual full-segment and short-window changes before detection."""
    before = original[onset:]
    after = changed[onset:]
    if any(x[0] != y[0] for x, y in zip(original, changed)):
        raise ValueError("Injeksi mengubah urutan atau waktu catatan")
    if original[:onset] != changed[:onset]:
        raise ValueError("Injeksi mengubah catatan sebelum titik awal")
    widths = (len(before), 30, 60, 90, 100, 150, 200, 250, 300, 400, 500)
    result = []
    for size in dict.fromkeys(widths):
        if size > len(before):
            continue
        base = before[:size]
        altered = after[:size]
        x = [v[FEATURE_INDEX] for _, v in base]
        y = [v[FEATURE_INDEX] for _, v in altered]
        other = 1 if FEATURE_INDEX != 1 else 0
        paired = [v[other] for _, v in base]
        mean0, sd0 = _stats(x)
        mean1, sd1 = _stats(y)
        result.append({
            "scenario": scenario, "onset": onset,
            "scope": "entire_post_onset" if size == len(before) else "first_window",
            "window_rows": size,
            "mean_before": mean0, "mean_after": mean1,
            "sd_before": sd0, "sd_after": sd1,
            "corr_before": pearson(paired, x),
            "corr_after": pearson(paired, y),
            "ks_before_after": ks_statistic(x, y),
        })
    full = result[0]
    if scenario == "mean":
        if not math.isclose(full["mean_after"] - full["mean_before"], 3.0, abs_tol=1e-9):
            raise ValueError("Injeksi rerata tidak sesuai")
    if scenario in ("scale", "combined"):
        if not math.isclose(full["sd_after"], 2 * full["sd_before"], rel_tol=1e-9):
            raise ValueError("Injeksi varians tidak sesuai")
    if scenario == "correlation":
        if sorted(v[FEATURE_INDEX] for _, v in before) != sorted(
                v[FEATURE_INDEX] for _, v in after):
            raise ValueError("Pergeseran siklik tidak mempertahankan nilai fitur")
    return result


def write_csv(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        raise ValueError("Tidak ada hasil untuk ditulis")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

