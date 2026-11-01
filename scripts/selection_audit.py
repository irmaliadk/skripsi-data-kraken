"""Select working detector settings from chronological pilot validation.

Cerqueira et al. (2026) motivate timing-aware F1 and separate validation.
Erol et al. (2023) compare alarms on original and modified real streams.
The paired-control diagnostic below is our conservative adaptation, not a
published replacement for the standard injected-event F1 score.
"""
import csv
import pathlib
import random
import statistics
import tempfile

import tune_detectors
from pilot_detectors import pca_cd, read_features
from validation_detectors import CUTOFF, reset_kswin


ROOT = pathlib.Path(__file__).resolve().parents[1]
HORIZON = 85  # Fixed in the preceding sweep before its results were inspected.


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def alarm_indices(row):
    return [int(value) for value in row["alarm_indices"].split(";") if value]


def evaluate(summary, runs):
    by_config = {}
    for row in runs:
        by_config.setdefault(row["config"], []).append(row)
    evaluated = []
    for item in summary:
        cases = by_config[item["config"]]
        original = next(row for row in cases if row["scenario"] == "original")
        original_alarms = alarm_indices(original)
        clear = ambiguous = missed = 0
        for case in cases:
            if case is original:
                continue
            onset = int(case["onset"])
            end = min(onset + HORIZON, 854)
            has_injected_alarm = any(onset <= alarm <= end for alarm in alarm_indices(case))
            has_original_alarm = any(onset <= alarm <= end for alarm in original_alarms)
            if has_injected_alarm and not has_original_alarm:
                clear += 1
            elif has_injected_alarm and has_original_alarm:
                ambiguous += 1
            else:
                missed += 1
        assert clear + ambiguous + missed == 8
        evaluated.append({
            "config": item["config"], "method": item["method"],
            "clear": clear, "ambiguous": ambiguous, "missed": missed,
            "original_alarms": int(item["control_alarms"]),
            "same_pattern": int(item["same_alarm_pattern_as_control"]),
            "fp85": int(item["fp_h85"]),
            "f1_50": float(item["f1_h50"]),
            "f1_85": float(item["f1_h85"]),
            "f1_100": float(item["f1_h100"]),
            "delay85": item["mean_delay_h85"],
            "retrain_count": int(item["retrains"]),
        })
    return evaluated


def rank(row):
    # Separate injection-window evidence from events also alarmed by the
    # unchanged stream; then prefer fewer original-stream alarms. Remaining
    # ties use the published timing-aware F1 and fewer unmatched alarms.
    return (-row["clear"], row["ambiguous"], row["original_alarms"],
            -row["f1_85"], row["fp85"], row["config"])


def severity_check(selected):
    """Sensitivity check at a smaller paper-scale perturbation.

    Qahtan et al. use baseline sigma=0.2 and steps up to epsilon=0.05 in
    their Gaussian examples. The ratio 0.05/0.2=0.25 motivates the *scale*
    here; applying it to Kraken is an adaptation, not a reproduction.
    """
    data = [row for row in read_features(ROOT / "data" / "btc_15m.csv")
            if row[0] <= CUTOFF]
    assert len(data) == 2850
    raw_train, raw_val = data[:1995], data[1995:]
    means = [statistics.mean(v[j] for _, v in raw_train) for j in range(3)]
    spreads = [statistics.stdev(v[j] for _, v in raw_train) for j in range(3)]
    def standardize(rows):
        return [(time, tuple((v[j] - means[j]) / spreads[j] for j in range(3)))
                for time, v in rows]
    train, val = standardize(raw_train), standardize(raw_val)
    feature = random.Random(2015).randrange(3)
    training_sd = statistics.pstdev(v[feature] for _, v in train)

    def make_case(onset, scenario, mean_multiplier, sd_multiplier):
        changed = [(time, list(v)) for time, v in val]
        after = changed[onset:]
        if scenario in ("mean", "combined"):
            for _, values in after:
                values[feature] += mean_multiplier * training_sd
        if scenario in ("scale", "combined"):
            center = statistics.mean(v[feature] for _, v in after)
            for _, values in after:
                values[feature] = center + sd_multiplier * (values[feature] - center)
        if scenario in ("correlation", "combined"):
            column = [v[feature] for _, v in after]
            offset = len(column) // 2
            for (_, values), shifted in zip(after, column[offset:] + column[:offset]):
                values[feature] = shifted
        return [(time, tuple(v)) for time, v in changed]

    def alarms(method, stream):
        _, first, second, third = selected[method]["config"].split(":")
        if method == "KSWIN":
            n, r, alpha = int(first), int(second), float(third)
            history = train[-(n - 1):]
            return [i - len(history) for i, _ in reset_kswin(
                history + stream, n=n, r=r, alpha=alpha)
                    if i >= len(history)]
        w, xi, delta = int(first), float(second), float(third)
        history = train[-(2 * w - 1):]
        return [i - len(history) for i, _ in pca_cd(
            history + stream, w=w, xi=xi, delta=delta,
            mode="text_ph")["alarms"] if i >= len(history)]

    output = []
    for method in ("KSWIN", "PCA-CD"):
        original = alarms(method, val)
        for level, mean_multiplier, sd_multiplier in (
                ("paper-scale", 0.25, 1.25), ("pilot-strong", 3.0, 2.0)):
            clear = ambiguous = tp = fp = fn = 0
            for onset in (285, 427):
                for scenario in ("mean", "scale", "correlation", "combined"):
                    detected = alarms(method, make_case(
                        onset, scenario, mean_multiplier, sd_multiplier))
                    hit = any(onset <= i <= onset + HORIZON for i in detected)
                    control = any(onset <= i <= onset + HORIZON for i in original)
                    clear += hit and not control
                    ambiguous += hit and control
                    tp += hit
                    fp += len(detected) - int(hit)
                    fn += not hit
            precision = tp / (tp + fp) if tp + fp else 0
            recall = tp / (tp + fn) if tp + fn else 0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
            output.append((method, level, clear, ambiguous, tp, fp, fn, f1))
    return output


def main():
    with tempfile.TemporaryDirectory(prefix="kraken-selection-") as tmp:
        tune_detectors.OUTPUT_ROOT = pathlib.Path(tmp)
        tune_detectors.main(limit=None, skip_rf=True, method_filter=None)
        summary = read_csv(pathlib.Path(tmp) / "reports" / "tuning_sweep_summary.csv")
        runs = read_csv(pathlib.Path(tmp) / "reports" / "tuning_sweep_runs.csv")
    evaluated = evaluate(summary, runs)
    assert len(evaluated) == 237
    selected = {}
    for method in ("KSWIN", "PCA-CD"):
        candidates = sorted((row for row in evaluated if row["method"] == method), key=rank)
        selected[method] = candidates[0]
        print("SELECTED", method, candidates[0], flush=True)

    lines = [
        "# Audit pemilihan konfigurasi pada data validasi",
        "",
        "Data latih 1.995 candle, validasi 855 candle, dua titik injeksi, empat skenario.",
        "Sebanyak 147 konfigurasi KSWIN dan 90 konfigurasi PCA-CD diuji ulang.",
        "Batas utama 85 candle sudah tertulis dalam kode uji sebelum hasil sweep dibaca.",
        "Batas 50 dan 100 candle ditampilkan untuk memeriksa kepekaan hasil.",
        "",
        "Alarm pada aliran asli diperiksa pada jendela 85 candle yang sama.",
        "'Terpisah' berarti aliran injeksi memberi alarm dan aliran asli tidak",
        "memberi alarm pada jendela kejadian tersebut. 'Ambigu' berarti keduanya",
        "memberi alarm pada jendela yang sama. Ini hanya pemeriksaan tambahan",
        "untuk menghindari mengaitkan alarm alami dengan injeksi secara otomatis;",
        "bukan bukti bahwa injeksi menyebabkan alarm dan bukan pengganti F1 standar.",
        "Perbandingan aliran asli dan hasil injeksi mengadaptasi Erol et al. (2023).",
        "Aturan pengelompokan Terpisah/Ambigu di sini adalah keputusan penelitian ini.",
        "F1, batas keterlambatan, dan alarm tanpa pasangan mengikuti kerangka",
        "evaluasi Cerqueira et al. (2026).",
        "",
        "Urutan pilihan pada validasi: jumlah kejadian Terpisah terbanyak, lalu",
        "Ambigu paling sedikit, alarm aliran asli paling sedikit, F1 pada batas",
        "85 candle paling tinggi, kemudian alarm tanpa pasangan paling sedikit.",
        "Urutan ini ditulis terbuka agar keputusan dapat diulang; paper tidak",
        "mewajibkan urutan prioritas tersebut. Tidak ada hasil uji akhir yang dipakai.",
        "",
        "| Metode | Konfigurasi | Terpisah / 8 | Ambigu / 8 | Alarm asli | F1 @50 | F1 @85 | F1 @100 | FP @85 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method in ("KSWIN", "PCA-CD"):
        ranked = sorted((row for row in evaluated if row["method"] == method), key=rank)
        for row in ranked[:5]:
            lines.append(f"| {method} | {row['config']} | {row['clear']} | {row['ambiguous']} | "
                         f"{row['original_alarms']} | {row['f1_50']:.3f} | "
                         f"{row['f1_85']:.3f} | {row['f1_100']:.3f} | {row['fp85']} |")
    lines += [
        "",
        "## Pemeriksaan pada dua besaran injeksi",
        "",
        "Qahtan et al. memakai SD awal 0,2 dan langkah perubahan hingga 0,05",
        "pada contoh Gaussian. Rasio 0,05/0,2 = 0,25 dipakai sebagai dasar",
        "uji sensitivitas +0,25 SD dan x1,25 SD pada Kraken. Ini adaptasi",
        "skala, bukan replikasi generator atau kekuatan injeksi yang setara.",
        "Skenario korelasi memakai pergeseran siklik yang sama pada kedua tingkat.",
        "",
        "| Metode | Tingkat | Terpisah / 8 | Ambigu / 8 | TP/FP/FN @85 | F1 @85 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for method, level, clear, ambiguous, tp, fp, fn, f1 in severity_check(selected):
        lines.append(f"| {method} | {level} | {clear} | {ambiguous} | "
                     f"{tp}/{fp}/{fn} | {f1:.3f} |")
    lines += [
        "",
        "## Batas interpretasi",
        "",
        "Kedelapan kejadian dibuat dari satu aliran validasi yang sama dan tidak",
        "setara dengan delapan dataset independen. Pergeseran korelasi memakai",
        "pergeseran waktu siklik; distribusi dalam jendela pendek ikut berubah.",
        "Besaran +3 SD untuk rerata dan x2 untuk simpangan baku adalah kandidat",
        "uji awal, bukan besaran baku dari paper Qahtan. Konfigurasi terpilih",
        "adalah pengaturan kerja untuk pengujian berikutnya, bukan bukti optimal",
        "pada semua data Bitcoin. Bekukan sebelum menilai data uji yang lebih baru.",
        "",
        "Sumber: https://arxiv.org/html/2606.07789 ;",
        "https://ioannismavromatis.com/assets/pdf/publications/dataDriftDetectors.pdf ;",
        "https://doi.org/10.1145/2783258.2783359",
        "",
    ]
    output = ROOT / "reports" / "selection_audit.md"
    output.parent.mkdir(exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print("REPORT", output, flush=True)


if __name__ == "__main__":
    main()

