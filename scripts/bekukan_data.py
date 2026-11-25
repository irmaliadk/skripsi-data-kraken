"""Siapkan salinan CSV penelitian setelah seluruh interval tersedia."""

import argparse
import csv
import hashlib
import io
import os
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from src.inti_skripsi.data import (
    DATA,
    DATA_START_UTC,
    RAW_ROWS,
    ROOT,
    TEST_CUTOFF_UTC,
    siapkan_data,
)


def salin_periode(sumber):
    """Ambil hanya catatan dalam periode penelitian dari CSV pengumpulan."""
    awal = datetime.fromisoformat(DATA_START_UTC)
    akhir = datetime.fromisoformat(TEST_CUTOFF_UTC)
    hasil = io.StringIO(newline="")
    with sumber.open(newline="", encoding="utf-8-sig") as berkas:
        pembaca = csv.DictReader(berkas)
        penulis = csv.DictWriter(hasil, pembaca.fieldnames, lineterminator="\n")
        penulis.writeheader()
        for baris in pembaca:
            waktu = datetime.fromisoformat(baris["time"])
            if waktu.utcoffset() != awal.utcoffset():
                raise ValueError("Waktu catatan pengumpulan harus memiliki zona UTC")
            if awal <= waktu <= akhir:
                penulis.writerow(baris)
    return hasil.getvalue().encode("utf-8")


def bekukan_data(sumber, tujuan):
    """Periksa isi CSV dan simpan versi tetap jika seluruh periode lengkap."""
    isi = salin_periode(sumber)
    if len(isi.splitlines()) - 1 != RAW_ROWS:
        raise ValueError(f"Periode penelitian harus memuat tepat {RAW_ROWS} candle")
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=tujuan.parent) as folder:
        sementara = Path(folder) / "periksa.csv"
        sementara.write_bytes(isi)
        siapkan_data(sementara)
        # Pasang berkas yang sudah diperiksa tanpa menimpa salinan yang ada.
        try:
            if os.name == "nt":
                sementara.rename(tujuan)
            else:
                tujuan.hardlink_to(sementara)
        except FileExistsError:
            if tujuan.read_bytes() != isi:
                raise FileExistsError(f"Berkas penelitian berbeda sudah ada: {tujuan}")
    return hashlib.sha256(isi).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sumber", type=Path, nargs="?", default=ROOT / "data/collection/btc_15m.csv"
    )
    args = parser.parse_args()
    print(f"SHA-256: {bekukan_data(args.sumber, DATA)}")
