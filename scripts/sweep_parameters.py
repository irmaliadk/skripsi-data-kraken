"""Sensitivity check on validation data; never reads observations after CUTOFF."""
import csv
import itertools
import statistics
from pathlib import Path
from pilot_detectors import pca_cd, read_features
from validation_detectors import CUTOFF, inject, reset_kswin

ROOT = Path(__file__).resolve().parents[1]
ONSETS = (400, 427, 454)
KINDS = ("mean", "scale", "correlation", "combined")
HORIZON = 400

def validation_rows():
    rows = [row for row in read_features(ROOT / "data" / "btc_15m.csv") if row[0] <= CUTOFF]
    assert len(rows) == 2850
    train, validation = rows[:1995], rows[1995:]
    means = [statistics.mean(row[1][j] for row in train) for j in range(3)]
    sds = [statistics.stdev(row[1][j] for row in train) for j in range(3)]
    return [(t, tuple((v[j] - means[j]) / sds[j] for j in range(3))) for t, v in validation]

def positions(method, stream, params):
    if method == "PCA-CD":
        return [i for i, _ in pca_cd(stream, w=params[0], xi=params[1], mode="text_ph")["alarms"]]
    return [i for i, _ in reset_kswin(stream, n=params[0], r=params[1], alpha=params[2])]

def main():
    validation = validation_rows()
    cases = {(onset, feature, kind): inject(validation, onset, kind, feature, 1.0)
             for onset, feature, kind in itertools.product(ONSETS, range(3), KINDS)}
    configs = [("PCA-CD", (w, xi)) for w, xi in itertools.product(
        (100, 150, 200), (1, 2, 3, 4, 5, 7.5, 10, 25, 100, 500))]
    configs += [("KSWIN", (n, r, alpha)) for n, r, alpha in itertools.product(
        (200, 300, 400), (20, 30), (0.00001, 0.0001, 0.001))]
    summary, events = [], []
    for method, params in configs:
        baseline = positions(method, validation, params)
        detection = control_count = same_count = 0
        by_kind = {kind: 0 for kind in KINDS}
        for (onset, feature, kind), stream in cases.items():
            end = min(len(validation) - 1, onset + HORIZON)
            control = [i for i in baseline if onset <= i <= end]
            hits = [i for i in positions(method, stream, params) if onset <= i <= end]
            detection += bool(hits)
            control_count += bool(control)
            same_count += bool(set(hits) & set(control))
            by_kind[kind] += bool(hits)
            events.append(dict(method=method, parameters=str(params), onset=onset,
                               feature=feature, injection=kind, control_alarms=str(control),
                               injected_alarms=str(hits), identical_alarm=bool(set(hits) & set(control))))
        summary.append(dict(method=method, parameters=str(params), scenarios=len(cases),
                            detected_within_400=detection, scenarios_with_control_alarm=control_count,
                            scenarios_with_identical_alarm=same_count,
                            **{f"detected_{k}": by_kind[k] for k in KINDS}))
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    for name, rows in (("sweep_parameters.csv", summary), ("sweep_events.csv", events)):
        with (out / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    print(f"Validation only: {len(configs)} configurations, {len(cases)} cases each")
    for method in ("PCA-CD", "KSWIN"):
        selected = [row for row in summary if row["method"] == method and
                    row["scenarios_with_control_alarm"] == 0]
        print(method, "zero control-alarm candidates:")
        for row in sorted(selected, key=lambda x: x["detected_within_400"], reverse=True)[:8]:
            print(row)
    print("Reports:", out / "sweep_parameters.csv", out / "sweep_events.csv")

if __name__ == "__main__":
    main()


