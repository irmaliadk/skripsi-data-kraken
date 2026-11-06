"""Frozen final comparison of KSWIN and PCA-CD on later Kraken candles.

Fifty onset trials in 50-80% of a real stream adapt Cerqueira et al. (2026).
The chronological order is preserved, unlike that paper's shuffled streams.
The 50 trials share one Kraken period and are not independent datasets.
"""

import argparse
import csv
import math
import pathlib
import random
import statistics
import time

from final_config import (
    KSWIN_ALPHA_PER_FEATURE, KSWIN_REFERENCE_SAMPLE, KSWIN_WINDOW,
    MAX_DETECTION_DELAY_CANDLES, PCA_CD_DELTA, PCA_CD_PAGE_HINKLEY_MODE,
    PCA_CD_WINDOW, PCA_CD_XI, VALIDATION_CUTOFF_UTC,
)
from pilot_detectors import ks_statistic, pca_cd, read_features
from validation_detectors import inject, pearson, reset_kswin


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_CUTOFF_UTC = "2026-11-06 10:30:00+00:00"
TRIALS = 50
ONSET_SEED = 2015
SCENARIOS = ("mean", "scale", "correlation", "combined")


def save_csv(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def measures(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def score_alarms(alarms, onset, length):
    accepted = [i for i in alarms if onset <= i <= min(onset + MAX_DETECTION_DELAY_CANDLES, length - 1)]
    tp = int(bool(accepted))
    fp = len(alarms) - tp
    fn = 1 - tp
    delay = min(accepted) - onset if accepted else ""
    return tp, fp, fn, delay


def main(limit_trials=None):
    rows = read_features(ROOT / "data" / "btc_15m.csv")
    earlier = [row for row in rows if row[0] <= VALIDATION_CUTOFF_UTC]
    later = [row for row in rows if VALIDATION_CUTOFF_UTC < row[0] <= TEST_CUTOFF_UTC]
    if len(earlier) != 2850 or len(later) != 1037:
        raise ValueError(f"Frozen split mismatch: earlier={len(earlier)}, later={len(later)}")
    train = earlier[:1995]
    centers = [statistics.mean(v[j] for _, v in train) for j in range(3)]
    spreads = [statistics.stdev(v[j] for _, v in train) for j in range(3)]

    def normalized(stream):
        return [(t, tuple((v[j] - centers[j]) / spreads[j] for j in range(3)))
                for t, v in stream]

    earlier, later, train = normalized(earlier), normalized(later), normalized(train)
    feature = random.Random(2015).randrange(3)
    scale = statistics.pstdev(v[feature] for _, v in train)
    lower, upper = math.ceil(len(later) * .5), math.floor(len(later) * .8)
    onsets = random.Random(ONSET_SEED).sample(range(lower, upper + 1), TRIALS)
    assert len(set(onsets)) == TRIALS
    assert max(onsets) + MAX_DETECTION_DELAY_CANDLES < len(later)

    settings = {
        "KSWIN": (KSWIN_WINDOW - 1, lambda stream: reset_kswin(
            stream, n=KSWIN_WINDOW, r=KSWIN_REFERENCE_SAMPLE,
            alpha=KSWIN_ALPHA_PER_FEATURE)),
        "PCA-CD": (2 * PCA_CD_WINDOW - 1, lambda stream: pca_cd(
            stream, w=PCA_CD_WINDOW, xi=PCA_CD_XI,
            delta=PCA_CD_DELTA, mode=PCA_CD_PAGE_HINKLEY_MODE)["alarms"]),
    }
    runs = []
    for detector, (warmup, detect) in settings.items():
        prior = earlier[-warmup:]
        start = time.perf_counter()
        control = [(i - warmup, detail) for i, detail in detect(prior + later)
                   if i >= warmup]
        control_indices = [i for i, _ in control]
        runs.append(dict(detector=detector, scenario="original", trial=0,
                         onset="", alarm_count=len(control), tp="", fp="", fn="",
                         delay="", seconds=round(time.perf_counter()-start, 6),
                         correlation_before="", correlation_after="", local_ks="",
                         control_alarm_in_window="", distinct_from_control="",
                         same_pattern_as_control="",
                         alarm_indices=";".join(str(i) for i, _ in control)))
        for trial, onset in enumerate(onsets[:limit_trials], start=1):
            for scenario in SCENARIOS:
                stream = inject(later, onset, scenario, feature, scale)
                original = [v[feature] for _, v in later[onset:]]
                altered = [v[feature] for _, v in stream[onset:]]
                other = 1 if feature != 1 else 0
                comparator = [v[other] for _, v in later[onset:]]
                corr0, corr1 = pearson(comparator, original), pearson(comparator, altered)
                local_ks = ks_statistic(original[:100], altered[:100])
                if scenario == "correlation":
                    assert sorted(original) == sorted(altered)
                    assert not math.isclose(corr0, corr1)
                start = time.perf_counter()
                alarms = [(i - warmup, detail) for i, detail in detect(prior + stream)
                          if i >= warmup]
                elapsed = time.perf_counter() - start
                alarm_indices = [i for i, _ in alarms]
                tp, fp, fn, delay = score_alarms(alarm_indices, onset, len(stream))
                control_hit = any(onset <= i <= onset + MAX_DETECTION_DELAY_CANDLES
                                  for i in control_indices)
                runs.append(dict(detector=detector, scenario=scenario, trial=trial,
                                 onset=onset, alarm_count=len(alarms), tp=tp, fp=fp,
                                 fn=fn, delay=delay, seconds=round(elapsed, 6),
                                 correlation_before=round(corr0, 6),
                                 correlation_after=round(corr1, 6),
                                 local_ks=round(local_ks, 6),
                                 control_alarm_in_window=int(control_hit),
                                 distinct_from_control=int(bool(tp) and not control_hit),
                                 same_pattern_as_control=int(alarm_indices == control_indices),
                                 alarm_indices=";".join(str(i) for i in alarm_indices)))
        print(detector, "complete", flush=True)

    summary = []
    for detector in settings:
        for scenario in SCENARIOS:
            selected = [row for row in runs if row["detector"] == detector and row["scenario"] == scenario]
            tp, fp, fn = (sum(row[key] for row in selected) for key in ("tp", "fp", "fn"))
            precision, recall, f1 = measures(tp, fp, fn)
            delays = [row["delay"] for row in selected if row["delay"] != ""]
            summary.append(dict(detector=detector, scenario=scenario,
                                trials=len(selected), tp=tp, fp=fp, fn=fn,
                                distinct_from_control=sum(row["distinct_from_control"] for row in selected),
                                coincident_with_control=sum(row["tp"] and row["control_alarm_in_window"] for row in selected),
                                same_pattern_as_control=sum(row["same_pattern_as_control"] for row in selected),
                                precision=round(precision, 6), recall=round(recall, 6),
                                f1=round(f1, 6),
                                mean_delay=round(statistics.mean(delays), 3) if delays else "",
                                total_seconds=round(sum(row["seconds"] for row in selected), 3)))
    out = ROOT / "reports"
    save_csv(out / "final_test_runs.csv", runs)
    save_csv(out / "final_test_summary.csv", summary)
    for detector in settings:
        group = [row for row in summary if row["detector"] == detector]
        print(detector, "macro_f1", round(statistics.mean(row["f1"] for row in group), 6), flush=True)
    print("trials", len(onsets[:limit_trials]), "test_rows", len(later),
          "onset_range", (min(onsets), max(onsets)), "feature", feature,
          "cutoff", TEST_CUTOFF_UTC, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-trials", type=int)
    args = parser.parse_args()
    main(args.limit_trials)

