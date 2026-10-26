"""Exploratory from-scratch KSWIN and PCA-CD smoke test; not thesis results.

Raab et al. 2020, Section 4.1: doi:10.1016/j.neucom.2019.11.111
Qahtan et al. 2015, Section 4: doi:10.1145/2783258.2783359
Freedman and Diaconis 1981: doi:10.1007/BF01025868
"""
import argparse
import csv
import math
import random
import time
from pathlib import Path


def read_features(path):
    output, prior = [], None
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for candle in csv.DictReader(handle):
            close = float(candle["close"])
            volume = float(candle["volume"])
            count = float(candle["count"])
            if close <= 0 or volume < 0 or count < 0:
                raise ValueError("Invalid candle")
            if prior is not None:
                output.append((candle["time"], (
                    math.log(close / prior), math.log1p(volume),
                    math.log1p(count))))
            prior = close
    return output


def ks_statistic(a, b):
    a, b = sorted(a), sorted(b)
    ia = ib = 0
    largest = 0.0
    for value in sorted(set(a + b)):
        while ia < len(a) and a[ia] <= value:
            ia += 1
        while ib < len(b) and b[ib] <= value:
            ib += 1
        largest = max(largest, abs(ia / len(a) - ib / len(b)))
    return largest


def kswin(stream, n=300, r=30, family_alpha=0.05, seed=2020):
    if n < 2 * r:
        raise ValueError("KSWIN needs n >= 2r")
    dimensions = len(stream[0][1])
    threshold = math.sqrt(-math.log(family_alpha / dimensions) / r)
    rng = random.Random(seed)
    alarms, counts = [], [0] * dimensions
    for end in range(n, len(stream) + 1):
        window = [row[1] for row in stream[end - n:end]]
        old_indices = rng.sample(range(n - r), r)
        distances = [
            ks_statistic([window[i][dim] for i in old_indices],
                         [row[dim] for row in window[-r:]])
            for dim in range(dimensions)
        ]
        active = [dim for dim, value in enumerate(distances)
                  if value > threshold]
        if active:
            alarms.append((end - 1, active))
            for dim in active:
                counts[dim] += 1
    return {"alarms": alarms, "counts": counts, "threshold": threshold}


def covariance(rows):
    n, d = len(rows), len(rows[0])
    means = [sum(row[j] for row in rows) / n for j in range(d)]
    matrix = [[sum((row[i] - means[i]) * (row[j] - means[j])
                   for row in rows) / (n - 1)
               for j in range(d)] for i in range(d)]
    return means, matrix


def eigen_symmetric(matrix):
    """Jacobi rotations on a symmetric 3-by-3 covariance matrix."""
    d = len(matrix)
    a = [row[:] for row in matrix]
    basis = [[float(i == j) for j in range(d)] for i in range(d)]
    for _ in range(100 * d * d):
        p, q = max(((i, j) for i in range(d) for j in range(i + 1, d)),
                   key=lambda pair: abs(a[pair[0]][pair[1]]))
        if abs(a[p][q]) < 1e-12:
            break
        angle = 0.5 * math.atan2(2 * a[p][q], a[q][q] - a[p][p])
        cosine, sine = math.cos(angle), math.sin(angle)
        rotate = [[float(i == j) for j in range(d)] for i in range(d)]
        rotate[p][p] = rotate[q][q] = cosine
        rotate[p][q], rotate[q][p] = sine, -sine
        temp = [[sum(a[i][k] * rotate[k][j] for k in range(d))
                 for j in range(d)] for i in range(d)]
        a = [[sum(rotate[k][i] * temp[k][j] for k in range(d))
              for j in range(d)] for i in range(d)]
        basis = [[sum(basis[i][k] * rotate[k][j] for k in range(d))
                  for j in range(d)] for i in range(d)]
    else:
        raise ArithmeticError("Jacobi eigen iteration did not converge")
    return sorted(((max(0.0, a[i][i]), [basis[j][i] for j in range(d)])
                   for i in range(d)), reverse=True)


def percentile(sorted_values, part):
    position = (len(sorted_values) - 1) * part
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    return sorted_values[lower] + (position - lower) * (
        sorted_values[upper] - sorted_values[lower])


def area_divergence(reference, test):
    """Qahtan CD-Area with equal-width histogram and FD bin-width rule."""
    ordered = sorted(reference)
    iqr = percentile(ordered, .75) - percentile(ordered, .25)
    if iqr <= 0:
        raise ValueError("Zero IQR: histogram needs another cited width rule")
    width = 2 * iqr / len(reference) ** (1 / 3)
    origin = ordered[0]
    old, new = {}, {}
    for value in reference:
        key = math.floor((value - origin) / width)
        old[key] = old.get(key, 0) + 1
    for value in test:
        key = math.floor((value - origin) / width)
        new[key] = new.get(key, 0) + 1
    overlap = sum(min(value, new.get(key, 0))
                  for key, value in old.items()) / len(reference)
    return 1 - overlap


def project(rows, means, directions):
    return [[sum((row[j] - means[j]) * direction[j]
                 for j in range(len(means))) for direction in directions]
            for row in rows]


def pca_cd(stream, w=300, delta=.005, xi=500, mode="text_ph"):
    """Qahtan CD-Area; compare Sec. 4.5 PH and Algorithm-1 line-27."""
    if len(stream) < 2 * w:
        raise ValueError("PCA-CD needs at least 2w observations")
    values = [item[1] for item in stream]
    step = max(1, min(round(.05 * w), 100))
    cursor = 0
    alarms, component_counts = [], []
    checks = 0
    while cursor + 2 * w <= len(values):
        reference = values[cursor:cursor + w]
        means, cov = covariance(reference)
        eigen = eigen_symmetric(cov)
        total = sum(pair[0] for pair in eigen)
        if total <= 0:
            raise ValueError("Reference has zero covariance")
        directions, cumulative_variance = [], 0.0
        for eigenvalue, vector in eigen:
            directions.append(vector)
            cumulative_variance += eigenvalue
            if cumulative_variance / total >= .999:
                break
        component_counts.append(len(directions))
        reference_pc = project(reference, means, directions)
        score_sum = m = peak = 0.0
        score_count = 0
        restart = False
        for end in range(cursor + 2 * w, len(values) + 1):
            if (end - cursor - 2 * w) % step != 0:
                continue
            test_pc = project(values[end - w:end], means, directions)
            score = max(area_divergence(
                [row[dim] for row in reference_pc],
                [row[dim] for row in test_pc])
                for dim in range(len(directions)))
            checks += 1
            score_count += 1
            score_sum += score
            average = score_sum / score_count
            m += average - score + delta
            peak = max(peak, m)
            if mode == "text_ph":
                alarm = peak - m > xi * average
            elif mode == "algorithm_line_27":
                alarm = score > xi * average
            else:
                raise ValueError("Unknown PH mode")
            if alarm:
                alarms.append((end - 1, score))
                cursor = end
                restart = True
                break
        if not restart:
            break
    return {"alarms": alarms, "components": component_counts,
            "checks": checks, "step": step}


def sanity():
    assert ks_statistic([0, 1], [0, 1]) == 0
    assert ks_statistic([0, 0], [1, 1]) == 1
    equal = [float(i) for i in range(100)]
    assert area_divergence(equal, equal) == 0
    rng = random.Random(12)
    rows = [[rng.gauss(0, 1) for _ in range(3)] for _ in range(200)]
    _, matrix = covariance(rows)
    eigen = eigen_symmetric(matrix)
    assert abs(sum(x[0] for x in eigen) -
               sum(matrix[i][i] for i in range(3))) < 1e-6


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/btc_15m.csv")
    parser.add_argument("--output", default="reports/pilot_detectors.md")
    parser.add_argument("--pca-window", type=int, default=300)
    args = parser.parse_args()
    sanity()
    stream = read_features(args.input)
    tic = time.perf_counter()
    ks = kswin(stream)
    ks_seconds = time.perf_counter() - tic
    pca = {}
    for mode in ("text_ph", "algorithm_line_27"):
        tic = time.perf_counter()
        pca[mode] = pca_cd(stream, w=args.pca_window, mode=mode)
        pca[mode]["seconds"] = time.perf_counter() - tic
    lines = [
        "# Uji kecil KSWIN dan PCA-CD pada data Kraken asli",
        "",
        "**Ini pemeriksaan implementasi, bukan evaluasi kinerja skripsi.**",
        "Tanpa injeksi dan acuan kejadian pergeseran distribusi data,",
        "jumlah alarm tidak menunjukkan TP, FP, akurasi, atau F1-score.",
        "",
        f"- Jumlah baris fitur: {len(stream)}",
        f"- Periode: {stream[0][0]} sampai {stream[-1][0]}",
        "- Fitur: log(close_t/close_t-1), log(1+volume), log(1+count)",
        "",
        "## KSWIN",
        "",
        "- n=300 dan r=30 dari Raab et al.; alpha keluarga=0,05",
        "  dibagi tiga fitur seperti koreksi Bonferroni pada paper.",
        f"- Ambang KS: {ks['threshold']:.6f}",
        f"- Titik dengan alarm: {len(ks['alarms'])}",
        f"- Alarm per fitur: {ks['counts']}",
        f"- Waktu eksekusi: {ks_seconds:.3f} detik",
        "",
        "## PCA-CD (CD-Area)",
        "",
        f"- w={args.pca_window} hanya nilai percobaan untuk uji kode;",
        "  ini belum keputusan konfigurasi skripsi.",
        "- PCA mempertahankan setidaknya 99,9% varians.",
        "- Histogram dari Qahtan et al.; lebar bin memakai aturan",
        "  Freedman-Diaconis dari data jendela acuan.",
        "- delta=0,005 dan xi=500 dari eksperimen Qahtan et al.",
    ]
    for mode, result in pca.items():
        first = [stream[index][0] for index, _ in result["alarms"][:5]]
        lines += ["", f"### {mode}",
                  f"- Jumlah alarm: {len(result['alarms'])}",
                  f"- Jumlah pemeriksaan: {result['checks']}",
                  f"- Banyak komponen tiap acuan: {result['components']}",
                  f"- Pemeriksaan setiap {result['step']} candle",
                  f"- Waktu eksekusi: {result['seconds']:.3f} detik",
                  "- Lima alarm pertama: " + (", ".join(first) or "tidak ada")]
    lines += [
        "", "## Perbedaan yang perlu ditinjau",
        "",
        "Qahtan et al. Sec. 4.5 menjelaskan alarm Page-Hinkley melalui",
        "M_t - m_t, tetapi Algorithm 1 baris 27 membandingkan skor saat",
        "ini dengan xi kali reratanya. Kedua bacaan dicoba secara terpisah;",
        "hasil yang tampak lebih bagus tidak boleh menjadi alasan memilih",
        "salah satunya untuk skripsi.",
        "",
        "Sumber: https://doi.org/10.1016/j.neucom.2019.11.111 ;",
        "https://doi.org/10.1145/2783258.2783359 ;",
        "https://doi.org/10.1007/BF01025868", "",
    ]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

