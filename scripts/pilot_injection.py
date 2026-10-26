"""Paper-based exploratory injection smoke test on Kraken features.

Qahtan et al. (2015), Section 5.3: Gauss-1D and Scale-1D.
Raab et al. (2020), Section 5.3: one drift in the middle of the stream.
Not the thesis's final drift evaluation.
"""
import argparse
import random
from pathlib import Path
from pilot_detectors import read_features, kswin, pca_cd


def inject(stream, first, column, kind, seed=2015):
    rng = random.Random(seed)
    result = []
    for position, (stamp, values) in enumerate(stream):
        values = list(values)
        if position >= first:
            if kind == "Gauss-1D":
                values[column] += rng.gauss(0, 1)
            elif kind == "Scale-1D":
                values[column] *= 2
            else:
                raise ValueError(kind)
        result.append((stamp, tuple(values)))
    return result


def examine(stream, w):
    ks = kswin(stream)
    pca_text = pca_cd(stream, w=w, mode="text_ph")
    pca_algorithm = pca_cd(stream, w=w, mode="algorithm_line_27")
    return ks, pca_text, pca_algorithm


def count_in(alarms, first, last):
    return sum(first <= item[0] <= last for item in alarms)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/btc_15m.csv")
    parser.add_argument("--output", default="reports/pilot_injection.md")
    parser.add_argument("--pca-window", type=int, default=300)
    args = parser.parse_args()
    original = read_features(args.input)
    onset = len(original) // 2
    chosen = random.Random(2015).randrange(3)
    endpoint = min(len(original) - 1, onset + 2 * args.pca_window)
    lines = [
        "# Uji kecil injeksi pada data Kraken",
        "",
        "**Diagnostik implementasi, bukan hasil akhir skripsi.**",
        "Skenario Gauss-1D dan Scale-1D mengikuti eksperimen data",
        "nyata Qahtan et al. (2015), Sec. 5.3. Titik awal di tengah",
        "aliran mengikuti pengujian satu pergeseran Raab et al. (2020),",
        "Sec. 5.3. Satu fitur dipilih acak dengan seed tetap.",
        "",
        f"- Baris fitur: {len(original)}",
        f"- Awal injeksi: baris {onset} ({original[onset][0]})",
        f"- Fitur terpilih (0=harga, 1=volume, 2=jumlah perdagangan): {chosen}",
        f"- Rentang pemeriksaan alarm: {original[onset][0]} hingga "
        f"{original[endpoint][0]} (2w={2 * args.pca_window} candle)",
        "- KSWIN: n=300, r=30, alpha keluarga=0,05 dibagi 3 fitur.",
        f"- PCA-CD: w={args.pca_window} untuk uji kode saja; "
        "delta=0,005, xi=500, 99,9% varians, CD-Area.",
        "",
        "| Aliran | Titik alarm KSWIN seluruhnya | KSWIN dalam 2w | "
        "PCA-CD PH teks dalam 2w | PCA-CD baris 27 dalam 2w |",
        "|---|---:|---:|---:|---:|",
    ]
    scenarios = [("Asli", original)]
    scenarios += [(name, inject(original, onset, chosen, name))
                  for name in ("Gauss-1D", "Scale-1D")]
    for name, data in scenarios:
        ks, text, algorithm = examine(data, args.pca_window)
        lines.append(
            f"| {name} | {len(ks['alarms'])} | "
            f"{count_in(ks['alarms'], onset, endpoint)} | "
            f"{count_in(text['alarms'], onset, endpoint)} | "
            f"{count_in(algorithm['alarms'], onset, endpoint)} |")
    lines += [
        "",
        "Hitungan di atas adalah titik alarm, bukan jumlah kejadian",
        "pergeseran yang berhasil dideteksi. Alarm berulang belum dipasangkan",
        "dengan satu kejadian. Data asli dapat berubah secara alami.",
        "Tidak ada accuracy, precision, recall, atau F1-score yang",
        "dapat disimpulkan dari tabel ini.",
        "",
        "Jika konfigurasi PCA-CD tidak memberi alarm, itu menunjukkan",
        "bahwa konfigurasi dari eksperimen paper belum tentu cocok",
        "untuk aliran 2.850 baris fitur dan w=300. Jangan mengubah ambang",
        "berdasarkan hasil uji ini lalu melaporkannya sebagai hasil final.",
        "",
        "Sumber: https://doi.org/10.1145/2783258.2783359 ;",
        "https://doi.org/10.1016/j.neucom.2019.11.111", "",
    ]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()


