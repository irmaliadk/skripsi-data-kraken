"""Jalankan uji akhir setelah batas waktu ditetapkan dan pelaksanaan dikonfirmasi."""

import argparse
import datetime as dt
import hashlib
import json
import statistics
from pathlib import Path

from scripts.versi_eksperimen import commit_eksperimen
from src.inti_skripsi.data import (
    DATA,
    HISTORICAL_ROWS,
    ROOT,
    TEST_CUTOFF_UTC,
    TEST_ROWS,
    VALIDATION_ROWS,
    siapkan_data,
    ke_wib,
)
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
    TEST_MAX_INJECTION_FRACTION,
    daftar_konfigurasi,
    pilih_titik_injeksi,
    rincian_jadwal,
    jalankan_detektor,
    tulis_csv,
)


def baca_konfigurasi_terpilih(path, data_path=DATA, *, code_commit):
    """Terima hanya pilihan konfigurasi yang berasal dari validasi Bab 4."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("code_commit") != code_commit:
        raise ValueError("Commit kode uji akhir berbeda dari commit validasi")
    data_hash = hashlib.sha256(Path(data_path).read_bytes()).hexdigest()
    if (
        payload["source"] != "chronological validation only"
        or payload.get("dataset_sha256") != data_hash
        or payload["historical_rows"] != HISTORICAL_ROWS
        or payload["validation_rows"] != VALIDATION_ROWS
        or payload["repetitions_per_scenario"] != REPETITIONS
        or payload["main_horizon_candles"] != MAIN_HORIZON
        or payload["feature_index"] != FEATURE_INDEX
        or set(payload["selected"]) != {"KSWIN", "PCA-CD"}
    ):
        raise ValueError("Konfigurasi validasi tidak cocok dengan rancangan Bab 4")
    configs = {
        method: (method, *item["parameters"])
        for method, item in payload["selected"].items()
    }
    kandidat = set(daftar_konfigurasi())
    for method, konfigurasi in configs.items():
        item = payload["selected"][method]
        if konfigurasi not in kandidat or any(
            item.get(kunci) != nilai
            for kunci, nilai in rincian_jadwal(konfigurasi).items()
        ):
            raise ValueError("Konfigurasi validasi atau jadwal pemeriksaan tidak cocok")
    return configs


def pasangkan_waktu(runs, test):
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
                    "time_wib": ke_wib(utc_stamp),
                }
            )
    return result


def _baris_uji(data_path, test_cutoff):
    """Baca data uji hingga waktu pembukaan candle terakhir dalam UTC."""
    _, validation, test, _, _ = siapkan_data(data_path)
    cutoff = dt.datetime.fromisoformat(test_cutoff)
    if cutoff.utcoffset() != dt.timedelta(0):
        raise ValueError("Batas data uji harus ditulis dalam UTC")
    test = [row for row in test if dt.datetime.fromisoformat(row[0]) <= cutoff]
    if not test or dt.datetime.fromisoformat(test[-1][0]) != cutoff:
        raise ValueError("Batas uji harus sama dengan waktu candle yang tersedia")
    return validation, test


def _siapkan_skenario(test, shared_onsets):
    """Buat empat jenis injeksi pada setiap titik awal yang sama."""
    return [
        (scenario, onset, buat_aliran(test, onset, scenario))
        for onset in shared_onsets
        for scenario in SCENARIOS
    ]


def _catatan_asli(method, daftar_alarm, seconds):
    """Catat alarm pada aliran asli tanpa label kejadian."""
    return {
        "detector": method,
        "scenario": "original",
        "trial": 0,
        "onset": "",
        "alarm_count": len(daftar_alarm),
        "alarm_indices": ";".join(map(str, daftar_alarm)),
        "seconds": seconds,
        **{
            f"{key}_h{horizon}": ""
            for horizon in SENSITIVITY_HORIZONS
            for key in ("tp", "fp", "fp_before_onset", "fp_after_onset", "fn", "delay")
        },
    }


def _catatan_injeksi(method, trial, scenario, onset, daftar_alarm, seconds, length):
    """Catat alarm dan kecocokan untuk satu salinan berinjeksi."""
    row = {
        "detector": method,
        "scenario": scenario,
        "trial": trial,
        "onset": onset,
        "alarm_count": len(daftar_alarm),
        "alarm_indices": ";".join(map(str, daftar_alarm)),
        "seconds": seconds,
    }
    for horizon in SENSITIVITY_HORIZONS:
        values = cocokkan_alarm(daftar_alarm, onset, length, horizon)
        row.update({f"{key}_h{horizon}": value for key, value in values.items()})
    return row


def _uji_metode(method, konfigurasi, validation, test, cases):
    """Jalankan satu detektor pada data asli dan seluruh salinan uji."""
    original_alarms, original_seconds = jalankan_detektor(konfigurasi, validation, test)
    rows = [_catatan_asli(method, original_alarms, original_seconds)]
    for trial, (scenario, onset, aliran) in enumerate(cases, start=1):
        daftar_alarm, seconds = jalankan_detektor(konfigurasi, validation, aliran)
        rows.append(
            _catatan_injeksi(
                method, trial, scenario, onset, daftar_alarm, seconds, len(aliran)
            )
        )
    return original_alarms, rows


def _ringkasan_metode(method, rows, original_alarms):
    """Ringkas tiap skenario tanpa menghitung aliran asli sebagai FP."""
    summaries = []
    for scenario in SCENARIOS:
        group = [row for row in rows if row["scenario"] == scenario]
        metrics = ringkas_skenario(group, missing_delay="")
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


def _simpan_hasil(
    output_root,
    runs,
    summaries,
    audits,
    test,
    selected,
    shared_onsets,
    test_cutoff,
    code_commit,
):
    """Simpan hasil per salinan, ringkasan, audit, waktu, dan metadata."""
    output = output_root / "reports"
    tulis_csv(output / "thesis_final_runs.csv", runs)
    tulis_csv(output / "thesis_final_summary.csv", summaries)
    tulis_csv(output / "thesis_final_injection_audit.csv", audits)
    tulis_csv(output / "thesis_final_timestamps.csv", pasangkan_waktu(runs, test))
    metadata = {
        "code_commit": code_commit,
        "test_cutoff_utc": test_cutoff,
        "test_cutoff_wib": ke_wib(test_cutoff),
        "test_rows": len(test),
        "onsets": shared_onsets,
        "feature_index": FEATURE_INDEX,
        "horizon_candles": MAIN_HORIZON,
        "jadwal_detektor": {
            metode: rincian_jadwal(konfigurasi)
            for metode, konfigurasi in selected.items()
        },
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
    """Laksanakan uji akhir dengan batas waktu dan konfigurasi terpilih."""
    if test_cutoff != TEST_CUTOFF_UTC:
        raise ValueError("Batas akhir data uji tidak sesuai keputusan penelitian")
    code_commit = commit_eksperimen()
    selected = baca_konfigurasi_terpilih(
        selection_path, data_path, code_commit=code_commit
    )
    validation, test = _baris_uji(data_path, test_cutoff)
    if len(test) != TEST_ROWS:
        raise ValueError("Jumlah data uji tidak sesuai data penelitian")
    shared_onsets = pilih_titik_injeksi(len(test), TEST_MAX_INJECTION_FRACTION)
    cases = _siapkan_skenario(test, shared_onsets)
    audits = [
        item
        for scenario, onset, aliran in cases
        for item in audit_injeksi(test, aliran, onset, scenario)
    ]
    runs, summaries = [], []
    for method, konfigurasi in selected.items():
        original_alarms, method_rows = _uji_metode(
            method, konfigurasi, validation, test, cases
        )
        runs.extend(method_rows)
        summaries.extend(_ringkasan_metode(method, method_rows, original_alarms))
        print(method, "selesai", flush=True)
    _simpan_hasil(
        output_root,
        runs,
        summaries,
        audits,
        test,
        selected,
        shared_onsets,
        test_cutoff,
        code_commit,
    )
    print(
        "Uji akhir selesai",
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
