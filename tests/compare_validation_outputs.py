"""Bandingkan keluaran validasi lama dan baru selain waktu dinding."""

import argparse
import csv
import json
from pathlib import Path


CSV_NAMES = (
    "thesis_validation_runs.csv",
    "thesis_validation_summary.csv",
    "thesis_injection_audit.csv",
)
TIMING_FIELDS = {"seconds", "total_seconds"}


def _csv_rows(path):
    """Baca CSV sebagai daftar baris dengan nama kolom."""
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def compare_csv(before, after, name):
    """Pastikan urutan baris dan seluruh nilai selain durasi sama."""
    old_rows = _csv_rows(before / name)
    new_rows = _csv_rows(after / name)
    if len(old_rows) != len(new_rows):
        raise AssertionError(f"Jumlah baris berbeda pada {name}")
    for number, (old, new) in enumerate(zip(old_rows, new_rows), start=1):
        old = {key: value for key, value in old.items() if key not in TIMING_FIELDS}
        new = {key: value for key, value in new.items() if key not in TIMING_FIELDS}
        if old != new:
            raise AssertionError(f"Baris {number} berbeda pada {name}")
    return len(old_rows)


def compare_selection(before, after):
    """Pastikan konfigurasi terpilih dan nilainya sama selain durasi."""
    name = "thesis_selected_config.json"
    old = json.loads((before / name).read_text(encoding="utf-8"))
    new = json.loads((after / name).read_text(encoding="utf-8"))
    for payload in (old, new):
        for item in payload["selected"].values():
            item.pop("total_seconds", None)
    if old != new:
        raise AssertionError("Konfigurasi terpilih atau metriknya berbeda")
    return {method: item["parameters"] for method, item in old["selected"].items()}


def main():
    """Terima dua direktori laporan dan tampilkan hasil perbandingan."""
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    for name in CSV_NAMES:
        print(name, compare_csv(args.before, args.after, name), "baris sama")
    print("Konfigurasi terpilih sama:", compare_selection(args.before, args.after))


if __name__ == "__main__":
    main()
