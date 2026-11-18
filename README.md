# Perbandingan KSWIN dan PCA-CD pada data Kraken

Data BTC/USD interval 15 menit dikumpulkan oleh `collect.yml` setiap tiga jam.
Pengumpulan pembanding interval 1 dan 5 menit tetap berjalan melalui
`collect-alternative-intervals.yml`.

Masukan penelitian dibekukan dalam `data/btc_15m_study_20261111.csv`:
4.393 candle dari 26 September 2026 pukul 22.45 UTC sampai 11 November 2026
pukul 16.45 UTC (11 November pukul 23.45 WIB). SHA-256 berkas tersebut adalah
`984e7015f14fe0eb203c9b2c6d95ed5990d0c9071cc18e6b5a295322203b2bbd`.
CSV pengumpulan `data/btc_15m.csv` tetap bertambah tanpa mengubah masukan
penelitian. Fitur berjumlah 4.392 baris: 1.995 historis, 855 validasi, dan
1.542 uji.

## Kode untuk rancangan Bab 4

- `scripts/thesis_core/data.py`: baca CSV, bentuk fitur, periksa interval,
  bagi data berdasarkan waktu, dan bakukan fitur memakai data historis.
- `scripts/thesis_core/kswin.py`: statistik Kolmogorov–Smirnov dan KSWIN.
- `scripts/thesis_core/pca_cd.py`: PCA, CD-Area, dan Page–Hinkley.
- `scripts/thesis_core/injection.py`: empat jenis injeksi dan audit perubahan.
- `scripts/thesis_core/evaluation.py`: pasangan alarm dan ringkasan metrik.
- `scripts/thesis_core/protocol.py`: kandidat, titik injeksi, jendela awal,
  pemanggilan detektor, dan penulisan keluaran.
- `scripts/tune_detectors.py`: validasi dengan 50 titik injeksi per jenis.
  Memilih satu konfigurasi per metode dengan rerata F1 empat jenis sebagai
  kriteria pertama. Keluaran berada di `reports/thesis_*.csv` dan
  `reports/thesis_selected_config.json`.
- `scripts/final_test.py`: memakai konfigurasi hasil validasi dan batas akhir
  data uji yang ditetapkan secara eksplisit. Perintah ini memerlukan
  `--confirm-final` agar tidak dijalankan tanpa sengaja. Berkas
  `reports/thesis_final_timestamps.csv` menampilkan waktu awal injeksi dan
  alarm dalam UTC serta WIB; urutan dan perhitungan tetap menggunakan UTC.

Jendela awal validasi diisi dengan akhir bagian historis. Pada pengujian akhir,
jendela awal diisi dengan akhir data validasi asli, tepat sebelum bagian uji.

Kolom `fp_before_onset` dan `fp_after_onset` memerinci FP pada salinan
berinjeksi; jumlah keduanya sama dengan `fp` yang dipakai dalam metrik utama.
Alarm pada aliran asli tetap dicatat tanpa TP, FP, atau FN. Dalam ringkasan
validasi, `total_seconds` setiap skenario menjumlahkan salinan skenario itu
sendiri, sedangkan `control_seconds` menyimpan waktu aliran asli. Waktu seluruh
aliran kandidat tetap dipakai sebagai kriteria tambahan pemilihan konfigurasi.

Workflow pengumpulan memakai Python 3.11 dengan `requests==2.34.2` dan
`pandas==3.1.1`, sesuai versi yang terpasang pada run pengumpulan
`44295702322`. Workflow validasi dan pengujian memakai Python 3.12.

Satu pemeriksaan kode yang cepat dapat dijalankan dengan
`python scripts/tune_detectors.py --smoke`. Mode ini menggunakan satu titik
injeksi dan satu kandidat per metode, serta tidak menghasilkan konfigurasi
terpilih. GitHub Actions `protocol-smoke.yml` menjalankan pemeriksaan yang
sama saat kode protokol berubah. Contoh hitung Bab 4 dan kesetaraan alarm
dengan kode lama dapat diperiksa dengan `python -m unittest discover -s tests`.

Validasi lengkap dapat dijalankan melalui workflow `tuning-sweep.yml` secara
manual. Pilihan konfigurasi disimpan dalam artefak `thesis-detector-validation`
beserta SHA-256 CSV penelitian. Setelah hasil validasi diperiksa, nomor run
validasi dimasukkan sebagai `validation_run_id` pada workflow
`final-detector-comparison.yml`. Workflow uji akhir mengambil konfigurasi dari
artefak tersebut dan memeriksa hash data sebelum memakainya. Batas akhir uji
ditetapkan pada 11 November 2026 pukul 16.45 UTC. Uji akhir hanya dimulai
secara manual; perubahan ini tidak menjalankannya.

Fitur yang diubah oleh injeksi adalah log(1 + jumlah perdagangan), sesuai
contoh manualisasi. Skrip dan workflow eksperimen lama berada di `archive/`;
bagian itu bukan pelaksanaan Bab 4 Plan B. Pengumpulan data utama dan pembanding
tetap berada di direktori aktif.

