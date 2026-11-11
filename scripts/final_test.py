"""Run the Bab 4 comparison only after validation and an explicit cutoff.

No final test runs on import or on a GitHub push. A complete validation file,
an observed test cutoff, and --confirm-final are all required.
"""

import argparse
import datetime as dt
import json
import statistics
from pathlib import Path

from thesis_protocol import (
    DATA, FEATURE_INDEX, MAIN_HORIZON, REPETITIONS, ROOT, SCENARIOS,
    SENSITIVITY_HORIZONS, audit_injection, make_stream, measures, onsets,
    prepare, run_detector, score_alarms, write_csv,
)


def read_selection(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if (payload["source"] != "chronological validation only"
            or payload["historical_rows"] != 1995
            or payload["validation_rows"] != 855
            or payload["repetitions_per_scenario"] != REPETITIONS
            or payload["main_horizon_candles"] != MAIN_HORIZON
            or payload["feature_index"] != FEATURE_INDEX
            or set(payload["selected"]) != {"KSWIN", "PCA-CD"}):
        raise ValueError("Konfigurasi validasi tidak cocok dengan rancangan Bab 4")
    configs = {}
    for method, item in payload["selected"].items():
        configs[method] = (method, *item["parameters"])
    return configs


def main(test_cutoff, selection_path, data_path=DATA, output_root=ROOT):
    historical, _, test, _, _ = prepare(data_path)
    cutoff = dt.datetime.fromisoformat(test_cutoff)
    if cutoff.utcoffset() != dt.timedelta(0):
        raise ValueError("Batas data uji harus ditulis dalam UTC")
    test = [row for row in test
            if dt.datetime.fromisoformat(row[0]) <= cutoff]
    if not test or dt.datetime.fromisoformat(test[-1][0]) != cutoff:
        raise ValueError("Batas uji harus sama dengan waktu candle yang tersedia")
    selected = read_selection(selection_path)
    shared_onsets = onsets(len(test), .8)
    cases = [(scenario, onset, make_stream(test, onset, scenario))
             for onset in shared_onsets for scenario in SCENARIOS]
    audits = []
    for scenario, onset, stream in cases:
        audits.extend(audit_injection(test, stream, onset, scenario))

    runs, summaries = [], []
    for method, config in selected.items():
        original_alarms, original_seconds = run_detector(
            config, historical, test)
        runs.append({
            "detector": method, "scenario": "original", "trial": 0,
            "onset": "", "alarm_count": len(original_alarms),
            "alarm_indices": ";".join(map(str, original_alarms)),
            "seconds": original_seconds,
            **{f"{key}_h{horizon}": "" for horizon in SENSITIVITY_HORIZONS
               for key in ("tp", "fp", "fn", "delay")},
        })
        for trial, (scenario, onset, stream) in enumerate(cases, start=1):
            alarms, seconds = run_detector(config, historical, stream)
            row = {
                "detector": method, "scenario": scenario, "trial": trial,
                "onset": onset, "alarm_count": len(alarms),
                "alarm_indices": ";".join(map(str, alarms)),
                "seconds": seconds,
            }
            for horizon in SENSITIVITY_HORIZONS:
                values = score_alarms(alarms, onset, len(stream), horizon)
                row.update({f"{key}_h{horizon}": value
                            for key, value in values.items()})
            runs.append(row)
        for scenario in SCENARIOS:
            group = [row for row in runs if row["detector"] == method
                     and row["scenario"] == scenario]
            tp = sum(row[f"tp_h{MAIN_HORIZON}"] for row in group)
            fp = sum(row[f"fp_h{MAIN_HORIZON}"] for row in group)
            fn = sum(row[f"fn_h{MAIN_HORIZON}"] for row in group)
            precision, recall, f1 = measures(tp, fp, fn)
            delays = [row[f"delay_h{MAIN_HORIZON}"] for row in group
                      if row[f"delay_h{MAIN_HORIZON}"] is not None]
            summaries.append({
                "detector": method, "scenario": scenario,
                "repetitions": len(group), "tp": tp, "fp": fp, "fn": fn,
                "precision": precision, "recall": recall, "f1": f1,
                "mean_delay_candles": statistics.mean(delays) if delays else "",
                "total_seconds": sum(row["seconds"] for row in group),
                "original_alarm_count": len(original_alarms),
            })
        print(method, "complete", flush=True)

    output = output_root / "reports"
    write_csv(output / "thesis_final_runs.csv", runs)
    write_csv(output / "thesis_final_summary.csv", summaries)
    write_csv(output / "thesis_final_injection_audit.csv", audits)
    metadata = {
        "test_cutoff_utc": test_cutoff,
        "test_rows": len(test),
        "onsets": shared_onsets,
        "feature_index": FEATURE_INDEX,
        "horizon_candles": MAIN_HORIZON,
        "macro_f1": {
            method: statistics.mean(row["f1"] for row in summaries
                                    if row["detector"] == method)
            for method in selected
        },
    }
    (output / "thesis_final_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print("FINAL COMPLETE", "test_rows", len(test),
          "onsets", len(shared_onsets), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-cutoff", required=True,
                        help="Waktu candle terakhir yang dibekukan, dalam UTC")
    parser.add_argument("--selection", default="reports/thesis_selected_config.json")
    parser.add_argument("--data", default=str(DATA))
    parser.add_argument("--confirm-final", action="store_true")
    args = parser.parse_args()
    if not args.confirm_final:
        parser.error("Uji akhir hanya berjalan dengan --confirm-final")
    main(args.test_cutoff, Path(args.selection), Path(args.data))

