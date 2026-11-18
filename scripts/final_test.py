"""Jalankan pengujian akhir hanya dengan cutoff dan persetujuan eksplisit."""

import argparse
import datetime as dt
import json
import statistics
from pathlib import Path

from thesis_core.data import DATA, ROOT, prepare, to_wib
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
    TEST_MAX_INJECTION_FRACTION,
    onsets,
    run_detector,
    write_csv,
)


def read_selection(path):
    """Terima hanya pilihan konfigurasi yang berasal dari validasi Bab 4."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        payload["source"] != "chronological validation only"
        or payload["historical_rows"] != 1995
        or payload["validation_rows"] != 855
        or payload["repetitions_per_scenario"] != REPETITIONS
        or payload["main_horizon_candles"] != MAIN_HORIZON
        or payload["feature_index"] != FEATURE_INDEX
        or set(payload["selected"]) != {"KSWIN", "PCA-CD"}
    ):
        raise ValueError("Konfigurasi validasi tidak cocok dengan rancangan Bab 4")
    configs = {}
    for method, item in payload["selected"].items():
        configs[method] = (method, *item["parameters"])
    return configs


def timestamp_rows(runs, test):
    """Pasangkan indeks injeksi dan alarm dengan waktu UTC serta WIB."""
    result = []
    for run in runs:
        shared = {key: run[key] for key in ("detector", "scenario", "trial")}
        indices = []
        if run["onset"] != "":
            indices.append(("injection_onset", int(run["onset"])))
        indices.extend(
            ("alarm", int(value)) for value in run["alarm_indices"].split(";") if value
        )
        for kind, index in indices:
            if index < 0 or index >= len(test):
                raise ValueError("Indeks alarm atau injeksi di luar data uji")
            utc_stamp = test[index][0]
            result.append(
                {
                    **shared,
                    "event": kind,
                    "index": index,
                    "time_utc": utc_stamp,
                    "time_wib": to_wib(utc_stamp),
                }
            )
    return result


def _test_rows(data_path, test_cutoff):
    """Baca data uji hanya sampai candle pada cutoff UTC yang diminta."""
    _, validation, test, _, _ = prepare(data_path)
    cutoff = dt.datetime.fromisoformat(test_cutoff)
    if cutoff.utcoffset() != dt.timedelta(0):
        raise ValueError("Batas data uji harus ditulis dalam UTC")
    test = [row for row in test if dt.datetime.fromisoformat(row[0]) <= cutoff]
    if not test or dt.datetime.fromisoformat(test[-1][0]) != cutoff:
        raise ValueError("Batas uji harus sama dengan waktu candle yang tersedia")
    return validation, test


def _cases(test, shared_onsets):
    """Buat empat jenis injeksi pada setiap titik awal yang sama."""
    return [
        (scenario, onset, make_stream(test, onset, scenario))
        for onset in shared_onsets
        for scenario in SCENARIOS
    ]


def _original_row(method, alarms, seconds):
    """Catat alarm pada aliran asli tanpa label kejadian."""
    return {
        "detector": method,
        "scenario": "original",
        "trial": 0,
        "onset": "",
        "alarm_count": len(alarms),
        "alarm_indices": ";".join(map(str, alarms)),
        "seconds": seconds,
        **{
            f"{key}_h{horizon}": ""
            for horizon in SENSITIVITY_HORIZONS
            for key in (
                "tp", "fp", "fp_before_onset", "fp_after_onset", "fn", "delay"
            )
        },
    }


def _injected_row(method, trial, scenario, onset, alarms, seconds, length):
    """Catat alarm dan kecocokan untuk satu salinan berinjeksi."""
    row = {
        "detector": method,
        "scenario": scenario,
        "trial": trial,
        "onset": onset,
        "alarm_count": len(alarms),
        "alarm_indices": ";".join(map(str, alarms)),
        "seconds": seconds,
    }
    for horizon in SENSITIVITY_HORIZONS:
        values = score_alarms(alarms, onset, length, horizon)
        row.update({f"{key}_h{horizon}": value for key, value in values.items()})
    return row


def _run_method(method, config, validation, test, cases):
    """Jalankan satu detektor pada data asli dan seluruh salinan uji."""
    original_alarms, original_seconds = run_detector(config, validation, test)
    rows = [_original_row(method, original_alarms, original_seconds)]
    for trial, (scenario, onset, stream) in enumerate(cases, start=1):
        alarms, seconds = run_detector(config, validation, stream)
        rows.append(
            _injected_row(method, trial, scenario, onset, alarms, seconds, len(stream))
        )
    return original_alarms, rows


def _method_summaries(method, rows, original_alarms):
    """Ringkas tiap skenario tanpa menghitung aliran asli sebagai FP."""
    summaries = []
    for scenario in SCENARIOS:
        group = [row for row in rows if row["scenario"] == scenario]
        metrics = summarize_group(group, missing_delay="")
        summaries.append(
            {
                "detector": method,
                "scenario": scenario,
                "repetitions": len(group),
                "tp": metrics["tp"],
                "fp": metrics["fp"],
                "fp_before_onset": metrics["fp_before_onset"],
                "fp_after_onset": metrics["fp_after_onset"],
                "fn": metrics["fn"],
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1": metrics["f1"],
                "mean_delay_candles": metrics["mean_delay"],
                "total_seconds": sum(row["seconds"] for row in group),
                "original_alarm_count": len(original_alarms),
            }
        )
    return summaries


def _save_results(
    output_root, runs, summaries, audits, test, selected, shared_onsets, test_cutoff
):
    """Simpan hasil per salinan, ringkasan, audit, waktu, dan metadata."""
    output = output_root / "reports"
    write_csv(output / "thesis_final_runs.csv", runs)
    write_csv(output / "thesis_final_summary.csv", summaries)
    write_csv(output / "thesis_final_injection_audit.csv", audits)
    write_csv(output / "thesis_final_timestamps.csv", timestamp_rows(runs, test))
    metadata = {
        "test_cutoff_utc": test_cutoff,
        "test_cutoff_wib": to_wib(test_cutoff),
        "test_rows": len(test),
        "onsets": shared_onsets,
        "feature_index": FEATURE_INDEX,
        "horizon_candles": MAIN_HORIZON,
        "macro_f1": {
            method: statistics.mean(
                row["f1"] for row in summaries if row["detector"] == method
            )
            for method in selected
        },
    }
    (output / "thesis_final_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(test_cutoff, selection_path, data_path=DATA, output_root=ROOT):
    """Laksanakan pengujian akhir setelah cutoff dan konfigurasi ditentukan."""
    validation, test = _test_rows(data_path, test_cutoff)
    selected = read_selection(selection_path)
    shared_onsets = onsets(len(test), TEST_MAX_INJECTION_FRACTION)
    cases = _cases(test, shared_onsets)
    audits = [
        item
        for scenario, onset, stream in cases
        for item in audit_injection(test, stream, onset, scenario)
    ]
    runs, summaries = [], []
    for method, config in selected.items():
        original_alarms, method_rows = _run_method(
            method, config, validation, test, cases
        )
        runs.extend(method_rows)
        summaries.extend(_method_summaries(method, method_rows, original_alarms))
        print(method, "complete", flush=True)
    _save_results(
        output_root, runs, summaries, audits, test, selected, shared_onsets, test_cutoff
    )
    print(
        "FINAL COMPLETE",
        "test_rows",
        len(test),
        "onsets",
        len(shared_onsets),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test-cutoff",
        required=True,
        help="Waktu candle terakhir yang dibekukan, dalam UTC",
    )
    parser.add_argument("--selection", default="reports/thesis_selected_config.json")
    parser.add_argument("--data", default=str(DATA))
    parser.add_argument("--confirm-final", action="store_true")
    args = parser.parse_args()
    if not args.confirm_final:
        parser.error("Uji akhir hanya berjalan dengan --confirm-final")
    main(args.test_cutoff, Path(args.selection), Path(args.data))
