# Perbandingan KSWIN dan PCA-CD pada data Kraken

Data BTC/USD interval 15 menit dikumpulkan oleh `collect.yml` setiap tiga jam.
Pengumpulan pembanding interval 1 dan 5 menit tetap berjalan melalui
`collect-alternative-intervals.yml`.

Eksperimen membaca `data/raw/btc_15m_study_20261125.csv`. Periode penelitian
memuat 5.737 candle yang dimulai dari 26 September 2026 pukul 22.45 UTC sampai
25 November 2026 pukul 16.45 UTC (23.45 WIB). Sesudah candle pertama dipakai
sebagai acuan harga, pembagiannya adalah 2.008 baris historis, 1.720 validasi,
dan 2.008 uji dari 5.736 baris fitur.

Setelah pengumpulan mencakup candle terakhir, jalankan
`python -m scripts.bekukan_data` dari akar repo. Perintah ini membaca
`data/collection/btc_15m.csv`, memeriksa periode dan pembagian, lalu menulis
salinan penelitian dan menampilkan SHA-256. CSV pengumpulan dapat terus
bertambah. Salinan 11 November dipertahankan sebagai data acuan tes regresi.

## Kode untuk rancangan Bab 4

- `src/inti_skripsi/data.py`: baca CSV, bentuk fitur, periksa interval,
  bagi data berdasarkan waktu, dan bakukan fitur memakai data historis.
- `src/inti_skripsi/kswin.py`: statistik Kolmogorov–Smirnov dan KSWIN.
- `src/inti_skripsi/deteksi_pca_cd.py`: PCA, CD-Area, dan Page–Hinkley.
- `src/inti_skripsi/injeksi.py`: empat jenis injeksi dan audit perubahan.
- `src/inti_skripsi/evaluasi.py`: pasangan alarm dan ringkasan metrik.
- `src/inti_skripsi/protokol.py`: kandidat, titik injeksi, jendela awal,
  pemanggilan detektor, dan penulisan keluaran.
- `scripts/tune_detectors.py`: validasi dengan 50 titik injeksi per jenis.
  Menguji 50 kandidat PCA-CD (5 ukuran jendela × 5 faktor ambang × 2 jadwal).
  Pemilihan satu konfigurasi per metode memakai rerata F1 empat jenis sebagai
  kriteria pertama. Keluaran berada di `reports/thesis_*.csv` dan
  `reports/thesis_selected_config.json`.
- `scripts/final_test.py`: memakai konfigurasi hasil validasi dan batas akhir
  data uji yang ditetapkan secara eksplisit. Perintah ini memerlukan
  `--confirm-final` agar tidak dijalankan tanpa sengaja. Berkas
  `reports/thesis_final_timestamps.csv` menampilkan waktu awal injeksi dan
  alarm dalam UTC serta WIB; urutan dan perhitungan tetap menggunakan UTC.

Untuk mengisi jendela awal, program mengambil catatan terakhir bagian
historis saat validasi dan catatan terakhir bagian validasi asli saat uji akhir.

Kolom `fp_before_onset` dan `fp_after_onset` memerinci FP pada salinan
berinjeksi; jumlah keduanya sama dengan `fp` yang dipakai dalam metrik utama.
Alarm pada aliran asli tetap dicatat tanpa TP, FP, atau FN. Dalam ringkasan
validasi, `total_seconds` memuat jumlah durasi semua salinan pada skenario itu, sedangkan `control_seconds` menyimpan waktu aliran asli. Waktu seluruh
aliran kandidat tetap dipakai sebagai kriteria tambahan pemilihan konfigurasi.

Susunan repositori: `data/collection/` berisi CSV hasil pengumpulan berjalan;
`data/raw/` berisi masukan penelitian yang dibekukan; `src/inti_skripsi/`
berisi fungsi penelitian; `scripts/` berisi perintah; `tests/` berisi pemeriksaan;
`reports/` berisi catatan dan keluaran. Jalankan perintah dari akar repositori.

PCA-CD memakai histogram dan memeriksa skor pada tiap catatan atau pada
jarak 5% dari ukuran jendela. Berkas pilihan validasi mencatat jadwal dan
jarak aktual. Uji akhir membaca konfigurasi yang terpilih pada validasi.

### Dasar metode

- [Raab dkk., §4.1](https://arxiv.org/pdf/2007.05432) menjelaskan sampel lama
  dan terbaru serta ambang statistik KS. Kode menerapkan statistik tersebut
  per fitur dan mencatat satu alarm aliran jika ada fitur yang melewati ambang.
- [Qahtan dkk., §4.2–4.5](https://doi.org/10.1145/2783258.2783359)
  menjelaskan proyeksi PCA berdasarkan jendela acuan, CD-Area, skor maksimum
  antarkomponen, interval pemeriksaan, dan aturan kumulatif Page–Hinkley.
  Penelitian ini memakai varian histogram dan membandingkan dua jadwal.
- [Freedman dan Diaconis](https://doi.org/10.1007/BF01025868) menjadi acuan
  lebar kelas histogram. Kode menetapkan lebar dan titik awal kelas dari
  jendela acuan dan memakai batas kelas yang sama untuk jendela uji.

Penataan direktori mengikuti prinsip pemisahan data, kode, dan hasil
dari [Wilson dkk.](https://doi.org/10.1371/journal.pcbi.1005510).

Alur kerja pengumpulan memakai Python 3.11 dengan `requests==2.34.2` dan
`pandas==3.1.1`, sesuai versi yang terpasang pada eksekusi pengumpulan
`44295702322`. Alur kerja validasi dan pengujian memakai Python 3.12.

Satu pemeriksaan kode yang cepat dapat dijalankan dengan
`python -m scripts.tune_detectors --smoke`. Mode ini menggunakan satu titik
injeksi dan satu kandidat per metode, serta tidak menghasilkan konfigurasi
terpilih. GitHub Actions `protocol-smoke.yml` menjalankan uji kecil itu
apabila CSV penelitian sudah tersedia. Contoh hitung Bab 4 dan kesetaraan alarm
dengan kode lama dapat diperiksa dengan `python -m unittest discover -s tests`.

Validasi lengkap dapat dijalankan melalui alur kerja `tuning-sweep.yml` secara
manual. Pilihan konfigurasi disimpan dalam artefak `thesis-detector-validation`
beserta SHA-256 CSV penelitian dan SHA commit kode. Setelah hasil validasi diperiksa, nomor eksekusi
validasi dimasukkan sebagai `validation_run_id` pada alur kerja
`final-detector-comparison.yml`. Alur kerja uji akhir membuka commit dari
eksekusi validasi dan mengambil konfigurasi terpilih dari artefaknya. Program
memeriksa SHA commit dan hash data sebelum memakai konfigurasi tersebut.
Batas akhir uji
ditetapkan pada 25 November 2026 pukul 16.45 UTC. Uji akhir hanya dimulai
secara manual.

Fitur yang diubah oleh injeksi adalah log(1 + jumlah perdagangan), sesuai
contoh manualisasi. Skrip dan workflow eksperimen lama berada di `archive/`;
bagian itu bukan pelaksanaan Bab 4 Plan B. Pengumpulan data utama dan pembanding
tetap berada di direktori aktif.

