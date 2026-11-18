"""Pilih satu konfigurasi tiap detektor hanya dari bagian validasi."""

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from thesis_core.data import ROOT, prepare
from thesis_core.evaluation import (
    MAIN_HORIZON,
    SENSITIVITY_HORIZONS,
    score_alarms,
    summarize_group,
)
from thesis_core.injection import FEATURE_INDEX, audit_injection, make_stream
from thesis_core.protocol import (
    REPETITIONS,
    SCENARIOS,
    VALIDATION_MAX_INJECTION_FRACTION,
    configuration_name,
    configurations,
    onsets,
    run_detector,
    write_csv,
)


def select_key(item):
    """Urutkan kandidat menurut F1 dan tiga kriteria tambahan Bab 4."""
    delay = item["mean_delay"] if item["mean_delay"] is not None else math.inf
    return (
        -item["macro_f1"],
        item["control_alarms"],
        delay,
        item["total_seconds"],
        item["config"],
    )


def _cases(validation, chosen_onsets):
    """Buat salinan validasi dengan titik bersama untuk empat skenario."""
    return [
        (scenario, onset, make_stream(validation, onset, scenario))
        for onset in chosen_onsets
        for scenario in SCENARIOS
    ]


def _run_candidate(config, historical, validation, cases):
    """Catat aliran asli dan seluruh salinan satu kandidat."""
    name = configuration_name(config)
    control_alarms, control_seconds = run_detector(config, historical, validation)
    rows, by_scenario = [], defaultdict(list)
    for scenario, onset, stream in cases:
        alarms, seconds = run_detector(config, historical, stream)
        row = {
            "config": name,
            "detector": config[0],
            "scenario": scenario,
            "onset": onset,
            "alarm_count": len(alarms),
            "alarm_indices": ";".join(map(str, alarms)),
            "seconds": seconds,
        }
        for horizon in SENSITIVITY_HORIZONS:
            values = score_alarms(alarms, onset, len(stream), horizon)
            row.update({f"{key}_h{horizon}": value for key, value in values.items()})
        rows.append(row)
        by_scenario[scenario].append(row)
    return control_alarms, control_seconds, rows, by_scenario


def _scenario_summaries(config, control_alarms, control_seconds, by_scenario):
    """Ringkas empat jenis injeksi dan kumpulkan keterlambatannya."""
    name = configuration_name(config)
    summaries, scenario_f1, delays = [], [], []
    for scenario in SCENARIOS:
        group = by_scenario[scenario]
        metrics = summarize_group(group)
        scenario_f1.append(metrics["f1"])
        delays.extend(
            row[f"delay_h{MAIN_HORIZON}"]
            for row in group
            if row[f"delay_h{MAIN_HORIZON}"] is not None
        )
        summaries.append(
            {
                "config": name,
                "detector": config[0],
                "scenario": scenario,
                "repetitions": len(group),
                **metrics,
                "control_alarms": len(control_alarms),
                "control_alarm_indices": ";".join(map(str, control_alarms)),
                "control_seconds": control_seconds,
                "total_seconds": sum(row["seconds"] for row in group),
            }
        )
    return summaries, scenario_f1, delays


def _summarize_candidate(config, control_alarms, control_seconds, rows, by_scenario):
    """Bentuk ringkasan skenario dan kriteria pemilihan satu kandidat."""
    total_seconds = control_seconds + sum(row["seconds"] for row in rows)
    summaries, scenario_f1, delays = _scenario_summaries(
        config, control_alarms, control_seconds, by_scenario
    )
    candidate = {
        "config": configuration_name(config),
        "method": config[0],
        "parameters": list(config[1:]),
        "macro_f1": statistics.mean(scenario_f1),
        "control_alarms": len(control_alarms),
        "mean_delay": statistics.mean(delays) if delays else None,
        "total_seconds": total_seconds,
    }
    return summaries, candidate


def _write_results(
    output_root,
    smoke,
    rows,
    summaries,
    audits,
    historical,
    validation,
    chosen_onsets,
    selected,
):
    """Simpan keluaran validasi dan pilihan konfigurasi bila lengkap."""
    output = output_root / "reports"
    prefix = "smoke" if smoke else "thesis"
    write_csv(output / f"{prefix}_validation_runs.csv", rows)
    write_csv(output / f"{prefix}_validation_summary.csv", summaries)
    write_csv(output / f"{prefix}_injection_audit.csv", audits)
    if smoke:
        return
    payload = {
        "source": "chronological validation only",
        "historical_rows": len(historical),
        "validation_rows": len(validation),
        "onsets": chosen_onsets,
        "feature_index": FEATURE_INDEX,
        "main_horizon_candles": MAIN_HORIZON,
        "repetitions_per_scenario": REPETITIONS,
        "selected": selected,
    }
    (output / "thesis_selected_config.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _validation_inputs(smoke, data_path):
    """Siapkan salinan dan kandidat yang sama untuk semua detektor."""
    historical, validation, _, _, _ = prepare(data_path) if data_path else prepare()
    chosen_onsets = onsets(len(validation), VALIDATION_MAX_INJECTION_FRACTION)
    if smoke:
        chosen_onsets = chosen_onsets[:1]
    candidates = list(configurations())
    if smoke:
        candidates = [
            next(c for c in candidates if c[0] == method)
            for method in ("KSWIN", "PCA-CD")
        ]
    cases = _cases(validation, chosen_onsets)
    audits = [
        item
        for scenario, onset, stream in cases
        for item in audit_injection(validation, stream, onset, scenario)
    ]
    return historical, validation, chosen_onsets, candidates, cases, audits


def _evaluate_candidates(candidates, historical, validation, cases):
    """Jalankan kandidat dan pilih satu konfigurasi per metode."""
    rows, summaries, selected = [], [], {}
    for config in candidates:
        control, seconds, candidate_rows, groups = _run_candidate(
            config, historical, validation, cases
        )
        rows.extend(candidate_rows)
        one_summary, candidate = _summarize_candidate(
            config, control, seconds, candidate_rows, groups
        )
        summaries.extend(one_summary)
        if config[0] not in selected or select_key(candidate) < select_key(
            selected[config[0]]
        ):
            selected[config[0]] = candidate
        print(
            f"{configuration_name(config)}: mean F1={candidate['macro_f1']:.4f}",
            flush=True,
        )
    return rows, summaries, selected


def main(smoke=False, data_path=None, output_root=ROOT):
    """Jalankan validasi tanpa menggunakan data uji untuk memilih kandidat."""
    historical, validation, chosen_onsets, candidates, cases, audits = (
        _validation_inputs(smoke, data_path)
    )
    rows, summaries, selected = _evaluate_candidates(
        candidates, historical, validation, cases
    )
    _write_results(
        output_root,
        smoke,
        rows,
        summaries,
        audits,
        historical,
        validation,
        chosen_onsets,
        selected,
    )
    print(
        "SMOKE ONLY" if smoke else "VALIDATION COMPLETE",
        "onsets",
        len(chosen_onsets),
        "configs",
        len(candidates),
        "runs",
        len(rows),
        flush=True,
    )
    return selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--data", help="CSV candle untuk pemeriksaan kode")
    args = parser.parse_args()
    main(smoke=args.smoke, data_path=Path(args.data) if args.data else None)
