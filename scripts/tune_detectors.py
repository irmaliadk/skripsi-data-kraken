"""Pilih satu konfigurasi tiap detektor hanya dari bagian validasi."""

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from scripts.versi_eksperimen import commit_eksperimen
from src.inti_skripsi.data import DATA, ROOT, siapkan_data
from src.inti_skripsi.evaluasi import (
    MAIN_HORIZON,
    SENSITIVITY_HORIZONS,
    cocokkan_alarm,
    ringkas_skenario,
)
from src.inti_skripsi.injeksi import FEATURE_INDEX, audit_injeksi, buat_aliran
from src.inti_skripsi.protokol import (
    REPETITIONS,
    SCENARIOS,
    VALIDATION_MAX_INJECTION_FRACTION,
    nama_konfigurasi,
    daftar_konfigurasi,
    pilih_titik_injeksi,
    jalankan_detektor,
    rincian_jadwal,
    tulis_csv,
)


def kunci_pemilihan(item):
    """Urutkan kandidat menurut F1 dan tiga kriteria tambahan Bab 4."""
    delay = item["mean_delay"] if item["mean_delay"] is not None else math.inf
    return (
        -item["macro_f1"],
        item["control_alarms"],
        delay,
        item["total_seconds"],
        item["config"],
    )


def _siapkan_skenario(validation, chosen_onsets):
    """Buat salinan validasi dengan titik awal yang sama untuk empat skenario."""
    return [
        (scenario, onset, buat_aliran(validation, onset, scenario))
        for onset in chosen_onsets
        for scenario in SCENARIOS
    ]


def _jalankan_kandidat(konfigurasi, historical, validation, cases):
    """Catat aliran asli dan seluruh salinan satu kandidat."""
    name = nama_konfigurasi(konfigurasi)
    control_alarms, control_seconds = jalankan_detektor(
        konfigurasi, historical, validation
    )
    rows, by_scenario = [], defaultdict(list)
    for scenario, onset, aliran in cases:
        daftar_alarm, seconds = jalankan_detektor(konfigurasi, historical, aliran)
        row = {
            "config": name,
            "detector": konfigurasi[0],
            **rincian_jadwal(konfigurasi),
            "scenario": scenario,
            "onset": onset,
            "alarm_count": len(daftar_alarm),
            "alarm_indices": ";".join(map(str, daftar_alarm)),
            "seconds": seconds,
        }
        for horizon in SENSITIVITY_HORIZONS:
            values = cocokkan_alarm(daftar_alarm, onset, len(aliran), horizon)
            row.update({f"{key}_h{horizon}": value for key, value in values.items()})
        rows.append(row)
        by_scenario[scenario].append(row)
    return control_alarms, control_seconds, rows, by_scenario


def _ringkasan_skenario(konfigurasi, control_alarms, control_seconds, by_scenario):
    """Ringkas empat jenis injeksi dan kumpulkan keterlambatannya."""
    name = nama_konfigurasi(konfigurasi)
    summaries, scenario_f1, delays = [], [], []
    for scenario in SCENARIOS:
        group = by_scenario[scenario]
        metrics = ringkas_skenario(group)
        scenario_f1.append(metrics["f1"])
        delays.extend(
            row[f"delay_h{MAIN_HORIZON}"]
            for row in group
            if row[f"delay_h{MAIN_HORIZON}"] is not None
        )
        summaries.append(
            {
                "config": name,
                "detector": konfigurasi[0],
                **rincian_jadwal(konfigurasi),
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


def _ringkas_kandidat(konfigurasi, control_alarms, control_seconds, rows, by_scenario):
    """Bentuk ringkasan skenario dan kriteria pemilihan satu kandidat."""
    total_seconds = control_seconds + sum(row["seconds"] for row in rows)
    summaries, scenario_f1, delays = _ringkasan_skenario(
        konfigurasi, control_alarms, control_seconds, by_scenario
    )
    candidate = {
        "config": nama_konfigurasi(konfigurasi),
        "method": konfigurasi[0],
        "parameters": list(konfigurasi[1:]),
        **rincian_jadwal(konfigurasi),
        "macro_f1": statistics.mean(scenario_f1),
        "control_alarms": len(control_alarms),
        "mean_delay": statistics.mean(delays) if delays else None,
        "total_seconds": total_seconds,
    }
    return summaries, candidate


def _tulis_hasil(
    output_root,
    smoke,
    rows,
    summaries,
    audits,
    historical,
    validation,
    chosen_onsets,
    selected,
    data_path,
    code_commit,
):
    """Simpan keluaran validasi dan pilihan konfigurasi bila lengkap."""
    output = output_root / "reports"
    prefix = "smoke" if smoke else "thesis"
    tulis_csv(output / f"{prefix}_validation_runs.csv", rows)
    tulis_csv(output / f"{prefix}_validation_summary.csv", summaries)
    tulis_csv(output / f"{prefix}_injection_audit.csv", audits)
    if smoke:
        return
    payload = {
        "source": "chronological validation only",
        "dataset_sha256": hashlib.sha256(Path(data_path).read_bytes()).hexdigest(),
        "code_commit": code_commit,
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


def _siapkan_validasi(smoke, data_path):
    """Siapkan kandidat tiap metode dan salinan validasi yang dipakai bersama."""
    historical, validation, _, _, _ = (
        siapkan_data(data_path) if data_path else siapkan_data()
    )
    chosen_onsets = pilih_titik_injeksi(
        len(validation), VALIDATION_MAX_INJECTION_FRACTION
    )
    if smoke:
        chosen_onsets = chosen_onsets[:1]
    candidates = list(daftar_konfigurasi())
    if smoke:
        candidates = [
            next(c for c in candidates if c[0] == method)
            for method in ("KSWIN", "PCA-CD")
        ]
    cases = _siapkan_skenario(validation, chosen_onsets)
    audits = [
        item
        for scenario, onset, aliran in cases
        for item in audit_injeksi(validation, aliran, onset, scenario)
    ]
    return historical, validation, chosen_onsets, candidates, cases, audits


def _nilai_kandidat(candidates, historical, validation, cases):
    """Jalankan kandidat dan pilih satu konfigurasi per metode."""
    rows, summaries, selected = [], [], {}
    for konfigurasi in candidates:
        control, seconds, candidate_rows, groups = _jalankan_kandidat(
            konfigurasi, historical, validation, cases
        )
        rows.extend(candidate_rows)
        one_summary, candidate = _ringkas_kandidat(
            konfigurasi, control, seconds, candidate_rows, groups
        )
        summaries.extend(one_summary)
        if konfigurasi[0] not in selected or kunci_pemilihan(
            candidate
        ) < kunci_pemilihan(selected[konfigurasi[0]]):
            selected[konfigurasi[0]] = candidate
        print(
            f"{nama_konfigurasi(konfigurasi)}: mean F1={candidate['macro_f1']:.4f}",
            flush=True,
        )
    return rows, summaries, selected


def main(smoke=False, data_path=None, output_root=ROOT):
    """Jalankan validasi tanpa menggunakan data uji untuk memilih kandidat."""
    code_commit = None if smoke else commit_eksperimen()
    historical, validation, chosen_onsets, candidates, cases, audits = (
        _siapkan_validasi(smoke, data_path)
    )
    rows, summaries, selected = _nilai_kandidat(
        candidates, historical, validation, cases
    )
    _tulis_hasil(
        output_root,
        smoke,
        rows,
        summaries,
        audits,
        historical,
        validation,
        chosen_onsets,
        selected,
        data_path if data_path else DATA,
        code_commit,
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
