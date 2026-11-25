"""PCA-CD, CD-Area, dan Page–Hinkley yang dihitung dari awal."""

import math


JACOBI_ROTATIONS_PER_DIMENSION = 100
JACOBI_TOLERANCE = 1e-12
HISTOGRAM_IQR_MULTIPLIER = 2
PCA_VARIANCE_FRACTION = 0.999
PCA_CHECK_FRACTION = 0.05
PCA_MAX_CHECK_STEP = 100
JADWAL_PCA_CD = ("setiap_catatan", "lima_persen")


def jarak_pemeriksaan(w, jadwal):
    """Tentukan jarak pemeriksaan dalam jumlah catatan."""
    if jadwal == "setiap_catatan":
        return 1
    if jadwal == "lima_persen":
        # Ikuti interval Qahtan dkk. §4.4 dengan pembulatan ke catatan utuh.
        return max(1, min(round(PCA_CHECK_FRACTION * w), PCA_MAX_CHECK_STEP))
    raise ValueError(f"Jadwal pemeriksaan PCA-CD tidak dikenal: {jadwal}")


def kovarians(rows):
    """Hitung rerata dan matriks kovarians sampel."""
    n, d = len(rows), len(rows[0])
    means = [sum(row[j] for row in rows) / n for j in range(d)]
    matrix = [
        [
            sum((row[i] - means[i]) * (row[j] - means[j]) for row in rows) / (n - 1)
            for j in range(d)
        ]
        for i in range(d)
    ]
    return means, matrix


def _elemen_luar_diagonal_terbesar(matrix, dimensions):
    """Temukan elemen di luar diagonal dengan nilai mutlak terbesar."""
    return max(
        ((i, j) for i in range(dimensions) for j in range(i + 1, dimensions)),
        key=lambda pair: abs(matrix[pair[0]][pair[1]]),
    )


def _rotasi_jacobi(matrix, basis, p, q, dimensions):
    """Lakukan satu rotasi Jacobi pada matriks dan vektor dasar."""
    angle = 0.5 * math.atan2(2 * matrix[p][q], matrix[q][q] - matrix[p][p])
    cosine, sine = math.cos(angle), math.sin(angle)
    rotate = [[float(i == j) for j in range(dimensions)] for i in range(dimensions)]
    rotate[p][p] = rotate[q][q] = cosine
    rotate[p][q], rotate[q][p] = sine, -sine
    temp = [
        [
            sum(matrix[i][k] * rotate[k][j] for k in range(dimensions))
            for j in range(dimensions)
        ]
        for i in range(dimensions)
    ]
    matrix = [
        [
            sum(rotate[k][i] * temp[k][j] for k in range(dimensions))
            for j in range(dimensions)
        ]
        for i in range(dimensions)
    ]
    basis = [
        [
            sum(basis[i][k] * rotate[k][j] for k in range(dimensions))
            for j in range(dimensions)
        ]
        for i in range(dimensions)
    ]
    return matrix, basis


def eigen_simetris(matrix):
    """Hitung nilai dan vektor eigen matriks simetris dengan Jacobi."""
    d = len(matrix)
    a = [row[:] for row in matrix]
    basis = [[float(i == j) for j in range(d)] for i in range(d)]
    for _ in range(JACOBI_ROTATIONS_PER_DIMENSION * d * d):
        p, q = _elemen_luar_diagonal_terbesar(a, d)
        if abs(a[p][q]) < JACOBI_TOLERANCE:
            break
        a, basis = _rotasi_jacobi(a, basis, p, q, d)
    else:
        raise ArithmeticError("Perhitungan nilai eigen Jacobi tidak konvergen")
    return sorted(
        ((max(0.0, a[i][i]), [basis[j][i] for j in range(d)]) for i in range(d)),
        reverse=True,
    )


def persentil(sorted_values, part):
    """Interpolasikan persentil dari nilai yang telah diurutkan."""
    position = (len(sorted_values) - 1) * part
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    return sorted_values[lower] + (position - lower) * (
        sorted_values[upper] - sorted_values[lower]
    )


def hitung_cd_area(acuan, test):
    """Hitung CD-Area memakai histogram dengan lebar Freedman–Diaconis."""
    ordered = sorted(acuan)
    iqr = persentil(ordered, 0.75) - persentil(ordered, 0.25)
    if iqr <= 0:
        raise ValueError("IQR nol: histogram memerlukan aturan lebar kelas lain")
    width = HISTOGRAM_IQR_MULTIPLIER * iqr / len(acuan) ** (1 / 3)
    # Gunakan batas kelas acuan yang sama bagi kedua jendela.
    origin = ordered[0]
    old, new = {}, {}
    for value in acuan:
        key = math.floor((value - origin) / width)
        old[key] = old.get(key, 0) + 1
    for value in test:
        key = math.floor((value - origin) / width)
        new[key] = new.get(key, 0) + 1
    overlap = sum(min(value, new.get(key, 0)) for key, value in old.items()) / len(
        acuan
    )
    return 1 - overlap


def proyeksikan(rows, means, directions):
    """Proyeksikan setiap catatan pada komponen utama acuan."""
    return [
        [
            sum((row[j] - means[j]) * direction[j] for j in range(len(means)))
            for direction in directions
        ]
        for row in rows
    ]


def _proyeksi_acuan(acuan):
    """Bangun PCA acuan dan tentukan komponen yang dipertahankan."""
    means, cov = kovarians(acuan)
    eigen = eigen_simetris(cov)
    total = sum(pair[0] for pair in eigen)
    if total <= 0:
        raise ValueError("Jendela acuan memiliki kovarians nol")
    directions, cumulative_variance = [], 0.0
    for eigenvalue, vector in eigen:
        directions.append(vector)
        cumulative_variance += eigenvalue
        if cumulative_variance / total >= PCA_VARIANCE_FRACTION:
            break
    return means, directions, proyeksikan(acuan, means, directions)


def _skor_perubahan(reference_pc, test_pc, directions):
    """Ambil skor CD-Area terbesar dari komponen yang digunakan."""
    return max(
        hitung_cd_area(
            [row[dim] for row in reference_pc], [row[dim] for row in test_pc]
        )
        for dim in range(len(directions))
    )


def _alarm_page_hinkley(score, average, peak, m, xi, mode):
    """Terapkan salah satu aturan keputusan Page–Hinkley yang tersedia."""
    if mode == "text_ph":
        return peak - m > xi * average
    if mode == "algorithm_line_27":
        return score > xi * average
    raise ValueError("Mode Page–Hinkley tidak dikenal")


def perbarui_page_hinkley(score, score_sum, score_count, m, peak, delta, xi, mode):
    """Perbarui statistik Page–Hinkley untuk satu skor CD-Area."""
    score_count += 1
    score_sum += score
    average = score_sum / score_count
    m += average - score + delta
    peak = max(peak, m)
    alarm = _alarm_page_hinkley(score, average, peak, m, xi, mode)
    return score_sum, score_count, m, peak, average, alarm


def _periksa_jendela(values, cursor, w, step, projection, delta, xi, mode):
    """Periksa jendela uji dan kembalikan alarm pertama setelah acuan."""
    means, directions, reference_pc = projection
    score_sum = m = peak = 0.0
    score_count = checks = 0
    # Mulai memeriksa saat kedua jendela sudah terisi.
    for end in range(cursor + 2 * w, len(values) + 1, step):
        test_pc = proyeksikan(values[end - w : end], means, directions)
        score = _skor_perubahan(reference_pc, test_pc, directions)
        checks += 1
        score_sum, score_count, m, peak, _, alarm = perbarui_page_hinkley(
            score, score_sum, score_count, m, peak, delta, xi, mode
        )
        if alarm:
            return (end - 1, score), checks
    return None, checks


def deteksi_pca_cd(
    aliran, w=300, delta=0.005, xi=500, mode="text_ph", jadwal="lima_persen"
):
    """Jalankan PCA-CD pada aliran multidimensi tanpa label."""
    if len(aliran) < 2 * w:
        raise ValueError("PCA-CD memerlukan sedikitnya 2w catatan")
    values = [item[1] for item in aliran]
    step = jarak_pemeriksaan(w, jadwal)
    cursor = checks = 0
    daftar_alarm, component_counts = [], []
    while cursor + 2 * w <= len(values):
        acuan = values[cursor : cursor + w]
        projection = _proyeksi_acuan(acuan)
        component_counts.append(len(projection[1]))
        alarm, inspected = _periksa_jendela(
            values, cursor, w, step, projection, delta, xi, mode
        )
        checks += inspected
        if alarm is None:
            break
        daftar_alarm.append(alarm)
        cursor = alarm[0] + 1
    return {
        "alarms": daftar_alarm,
        "components": component_counts,
        "checks": checks,
        "step": step,
    }
