"""Small feasibility check for 1m/5m streams, not interval selection."""
import math
import statistics
from pathlib import Path
from pilot_detectors import read_features, pca_cd
from pilot_models import THRESHOLD, anomaly_score, train_if, train_rf, rf_predict
from validation_detectors import inject, reset_kswin

ROOT = Path(__file__).resolve().parents[1]

def run(interval):
    rows = read_features(ROOT / "data" / f"btc_{interval}m.csv")
    assert len(rows) >= 719
    rows = rows[-719:]
    train_raw, validation_raw = rows[:300], rows[300:]
    means = [statistics.mean(v[j] for _, v in train_raw) for j in range(3)]
    sds = [statistics.stdev(v[j] for _, v in train_raw) for j in range(3)]
    assert all(math.isfinite(sd) and sd > 0 for sd in sds)
    def standardize(section):
        return [(t, tuple((v[j] - means[j]) / sds[j] for j in range(3))) for t, v in section]
    train = standardize(train_raw)
    validation = standardize(validation_raw)
    forest = train_if([v for _, v in train])
    labels = [int(anomaly_score(forest, v) >= THRESHOLD) for _, v in train]
    rf_status = "not trained: one pseudo-label class"
    if len(set(labels)) == 2:
        rf = train_rf([(v, y) for (_, v), y in zip(train, labels)])
        rf_status = f"trained; first validation prediction={rf_predict(rf, validation[0][1])}"
    onset = len(validation) // 2
    injected = inject(validation, onset, "mean", 2, 1.0)
    pca_original = [i for i, _ in pca_cd(validation, w=100, xi=2, mode="text_ph")["alarms"]]
    pca_injected = [i for i, _ in pca_cd(injected, w=100, xi=2, mode="text_ph")["alarms"]]
    ks_original = [i for i, _ in reset_kswin(validation, n=200, r=20, alpha=0.0001)]
    ks_injected = [i for i, _ in reset_kswin(injected, n=200, r=20, alpha=0.0001)]
    return [
        f"## Interval {interval} menit",
        f"Data: {rows[0][0]} sampai {rows[-1][0]}; {len(rows)} baris fitur.",
        f"Uji teknis: 300 latih, {len(validation)} validasi; awal injeksi pada indeks validasi {onset}.",
        f"IF: {sum(labels)} label semu anomali dari 300 data latih.",
        f"RF: {rf_status}.",
        f"PCA-CD (w=100, xi=2) alarm asli {pca_original}, injeksi rerata {pca_injected}.",
        f"KSWIN (n=200, r=20, alpha=0.0001) alarm asli {ks_original}, injeksi rerata {ks_injected}.",
        "Angka metode di sini hanya untuk memastikan kode dapat berjalan; bukan hasil pemilihan interval atau parameter.",
        "",
    ]

def main():
    lines = ["# Pemeriksaan awal interval 1 dan 5 menit", "",
             "**Bukan hasil penelitian akhir. Hanya uji kelayakan kode pada 720 candle pertama.**", ""]
    for interval in (1, 5):
        lines += run(interval)
    out = ROOT / "reports" / "interval_feasibility.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf8")
    print("\n".join(lines))

if __name__ == "__main__":
    main()


