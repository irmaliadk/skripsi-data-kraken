"""Audit cepat kecukupan data; tidak menghitung hasil detektor."""
import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path


def read_data(path):
    rows = []
    invalid = 0
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"time", "close", "volume", "count"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Kolom wajib tidak lengkap: time, close, volume, count")
        for row in reader:
            try:
                stamp = datetime.fromisoformat(row["time"])
                close = float(row["close"])
                volume = float(row["volume"])
                count = float(row["count"])
                if close <= 0 or volume < 0 or count < 0:
                    raise ValueError("Nilai harga/aktivitas tidak valid")
                rows.append((stamp, close, volume, count))
            except (TypeError, ValueError):
                invalid += 1
    return rows, invalid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/btc_15m.csv")
    parser.add_argument("--output", default="reports/audit_data.md")
    args = parser.parse_args()
    rows, invalid = read_data(Path(args.input))
    if not rows:
        raise SystemExit("Tidak ada candle valid untuk diaudit.")
    stamps = [item[0] for item in rows]
    duplicate = len(stamps) - len(set(stamps))
    gaps = sum(b - a != timedelta(minutes=15) for a, b in zip(stamps, stamps[1:]))
    ordered = stamps == sorted(stamps)
    n = len(rows)
    lines = [
        "# Audit awal data Kraken BTC/USD",
        "",
        f"- Candle valid: **{n}**",
        f"- Periode UTC: **{min(stamps).isoformat()}** sampai **{max(stamps).isoformat()}**",
        f"- Urutan waktu kronologis: **{'ya' if ordered else 'tidak'}**",
        f"- Waktu ganda: **{duplicate}**",
        f"- Jarak antarcatatan selain 15 menit: **{gaps}**",
        f"- Baris dengan waktu/nilai tidak valid: **{invalid}**",
        "",
        "## Kecukupan konfigurasi paper",
        "",
        f"- KSWIN dengan jendela 300 observasi dapat mulai mengisi jendelanya: **{'ya' if n >= 300 else 'tidak'}**.",
        f"- PCA-CD dengan jendela 10.000 observasi dapat mengisi satu jendela: **{'ya' if n >= 10000 else 'tidak'}**.",
        "",
        "Audit ini hanya memeriksa data dan kelayakan ukuran jendela. "
        "Audit ini belum mengukur alarm, performa detektor, atau performa Random Forest.",
        "",
    ]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    if duplicate or gaps or invalid or not ordered:
        raise SystemExit("Audit menemukan masalah data; lihat laporan.")


if __name__ == "__main__":
    main()

