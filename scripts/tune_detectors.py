"""Bab 4 validation: 50 shared onsets per scenario, then choose one setting.

Use --smoke for a small code check. A smoke check never writes a selected
configuration and must not be reported as a validation result.
"""

import argparse
import json
import math
import statistics
from collections import defaultdict

from thesis_protocol import (
    FEATURE_INDEX, MAIN_HORIZON, REPETITIONS, ROOT, SCENARIOS,
    SENSITIVITY_HORIZONS, audit_injection, configuration_name,
    configurations, make_stream, measures, onsets, prepare,
    run_detector, score_alarms, write_csv,
)


def select_key(item):
    delay = item["mean_delay"] if item["mean_delay"] is not None else math.inf
    return (-item["macro_f1"], item["control_alarms"],
            delay, item["total_seconds"], item["config"])


def main(smoke=False, data_path=None, output_root=ROOT):
    historical, validation, _, _, _ = prepare(data_path) if data_path else prepare()
    all_onsets = onsets(len(validation), .75)
    if smoke:
        all_onsets = all_onsets[:1]
    config_list = list(configurations())
    if smoke:
        config_list = [next(c for c in config_list if c[0] == method)
                       for method in ("KSWIN", "PCA-CD")]
    cases = [(scenario, onset, make_stream(validation, onset, scenario))
             for onset in all_onsets for scenario in SCENARIOS]
    injection_audits = []
    for scenario, onset, stream in cases:
        injection_audits.extend(audit_injection(validation, stream, onset, scenario))

    runs, summaries, selected = [], [], {}
    for config in config_list:
        name = configuration_name(config)
        control_alarms, control_seconds = run_detector(
            config, historical, validation)
        by_scenario = defaultdict(list)
        for scenario, onset, stream in cases:
            alarms, seconds = run_detector(config, historical, stream)
            row = {
                "config": name, "detector": config[0], "scenario": scenario,
                "onset": onset, "alarm_count": len(alarms),
                "alarm_indices": ";".join(map(str, alarms)),
                "seconds": seconds,
            }
            for horizon in SENSITIVITY_HORIZONS:
                values = score_alarms(alarms, onset, len(stream), horizon)
                row.update({f"{key}_h{horizon}": value
                            for key, value in values.items()})
            runs.append(row)
            by_scenario[scenario].append(row)
        scenario_f1, delays = [], []
        total_seconds = control_seconds + sum(row["seconds"] for row in runs
                                               if row["config"] == name)
        for scenario in SCENARIOS:
            group = by_scenario[scenario]
            tp = sum(row[f"tp_h{MAIN_HORIZON}"] for row in group)
            fp = sum(row[f"fp_h{MAIN_HORIZON}"] for row in group)
            fn = sum(row[f"fn_h{MAIN_HORIZON}"] for row in group)
            precision, recall, f1 = measures(tp, fp, fn)
            scenario_f1.append(f1)
            delays.extend(row[f"delay_h{MAIN_HORIZON}"] for row in group
                          if row[f"delay_h{MAIN_HORIZON}"] is not None)
            summaries.append({
                "config": name, "detector": config[0],
                "scenario": scenario, "repetitions": len(group),
                "tp": tp, "fp": fp, "fn": fn,
                "precision": precision, "recall": recall, "f1": f1,
                "mean_delay": statistics.mean(
                    row[f"delay_h{MAIN_HORIZON}"] for row in group
                    if row[f"delay_h{MAIN_HORIZON}"] is not None)
                if any(row[f"delay_h{MAIN_HORIZON}"] is not None for row in group)
                else None,
                "control_alarms": len(control_alarms),
                "control_alarm_indices": ";".join(map(str, control_alarms)),
                "total_seconds": total_seconds,
            })
        candidate = {
            "config": name, "method": config[0], "parameters": list(config[1:]),
            "macro_f1": statistics.mean(scenario_f1),
            "control_alarms": len(control_alarms),
            "mean_delay": statistics.mean(delays) if delays else None,
            "total_seconds": total_seconds,
        }
        previous = selected.get(config[0])
        if previous is None or select_key(candidate) < select_key(previous):
            selected[config[0]] = candidate
        print(f"{name}: mean F1={candidate['macro_f1']:.4f}", flush=True)

    output = output_root / "reports"
    write_csv(output / ("smoke_validation_runs.csv" if smoke else
                        "thesis_validation_runs.csv"), runs)
    write_csv(output / ("smoke_validation_summary.csv" if smoke else
                        "thesis_validation_summary.csv"), summaries)
    write_csv(output / ("smoke_injection_audit.csv" if smoke else
                        "thesis_injection_audit.csv"), injection_audits)
    if not smoke:
        payload = {
            "source": "chronological validation only",
            "historical_rows": len(historical),
            "validation_rows": len(validation),
            "onsets": all_onsets,
            "feature_index": FEATURE_INDEX,
            "main_horizon_candles": MAIN_HORIZON,
            "repetitions_per_scenario": REPETITIONS,
            "selected": selected,
        }
        (output / "thesis_selected_config.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
    print("SMOKE ONLY" if smoke else "VALIDATION COMPLETE",
          "onsets", len(all_onsets), "configs", len(config_list),
          "runs", len(runs), flush=True)
    return selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--data", help="CSV candle untuk pemeriksaan kode")
    args = parser.parse_args()
    from pathlib import Path
    main(smoke=args.smoke, data_path=Path(args.data) if args.data else None)

