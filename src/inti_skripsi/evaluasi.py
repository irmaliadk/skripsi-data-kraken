"""Pencocokan alarm dan ringkasan metrik kedua detektor."""

import statistics


MAIN_HORIZON = 96
SENSITIVITY_HORIZONS = (24, 25, 48, 50, 85, 96, 100, 192, 200)


def cocokkan_alarm(daftar_alarm, onset, length, horizon=MAIN_HORIZON):
    """Pasangkan alarm dan pisahkan alarm sebelum serta sesudah injeksi."""
    matches = [
        index
        for index in daftar_alarm
        if onset <= index <= min(onset + horizon, length - 1)
    ]
    tp = int(bool(matches))
    fp_before_onset = sum(index < onset for index in daftar_alarm)
    return {
        "tp": tp,
        "fp": len(daftar_alarm) - tp,
        "fp_before_onset": fp_before_onset,
        "fp_after_onset": len(daftar_alarm) - tp - fp_before_onset,
        "fn": 1 - tp,
        "delay": min(matches) - onset if matches else None,
    }


def hitung_metrik(tp, fp, fn):
    """Hitung precision, recall, dan F1 dari jumlah kejadian."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def ringkas_skenario(group, horizon=MAIN_HORIZON, missing_delay=None):
    """Gabungkan 50 salinan satu skenario dengan aturan yang sama."""
    tp = sum(row[f"tp_h{horizon}"] for row in group)
    fp = sum(row[f"fp_h{horizon}"] for row in group)
    fn = sum(row[f"fn_h{horizon}"] for row in group)
    fp_before_onset = sum(row[f"fp_before_onset_h{horizon}"] for row in group)
    fp_after_onset = sum(row[f"fp_after_onset_h{horizon}"] for row in group)
    precision, recall, f1 = hitung_metrik(tp, fp, fn)
    delay_key = f"delay_h{horizon}"
    mean_delay = (
        statistics.mean(row[delay_key] for row in group if row[delay_key] is not None)
        if any(row[delay_key] is not None for row in group)
        else missing_delay
    )
    return {
        "tp": tp,
        "fp": fp,
        "fp_before_onset": fp_before_onset,
        "fp_after_onset": fp_after_onset,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mean_delay": mean_delay,
    }
