# Perbandingan KSWIN dan PCA-CD pada data Kraken

Data BTC/USD interval 15 menit dikumpulkan oleh `collect.yml`. Pengumpulan
terjadwal tetap berjalan setiap tiga jam.

## Kode untuk rancangan Bab 4

- `scripts/thesis_protocol.py`: pembagian waktu, pembakuan fitur, empat
  injeksi, audit perubahan, konfigurasi kandidat, detektor, dan aturan alarm.
- `scripts/tune_detectors.py`: validasi dengan 50 titik injeksi per jenis.
  Memilih satu konfigurasi per metode dengan rerata F1 empat jenis sebagai
  kriteria pertama. Keluaran berada di `reports/thesis_*.csv` dan
  `reports/thesis_selected_config.json`.
- `scripts/final_test.py`: memakai konfigurasi hasil validasi dan batas akhir
  data uji yang ditetapkan secara eksplisit. Perintah ini memerlukan
  `--confirm-final` agar tidak dijalankan tanpa sengaja.

Satu pemeriksaan kode yang cepat dapat dijalankan dengan
`python scripts/tune_detectors.py --smoke`. Mode ini menggunakan satu titik
injeksi dan satu kandidat per metode, serta tidak menghasilkan konfigurasi
terpilih. GitHub Actions `protocol-smoke.yml` menjalankan pemeriksaan yang
sama saat kode protokol berubah.

Validasi lengkap dapat dijalankan melalui workflow `tuning-sweep.yml` secara
manual. Workflow `final-detector-comparison.yml` juga hanya berjalan secara
manual dan meminta waktu candle uji terakhir dalam UTC; workflow tersebut
menjalankan validasi terlebih dahulu sebelum pengujian akhir.

Fitur yang diubah oleh injeksi saat ini adalah log(1 + jumlah perdagangan),
sesuai contoh manualisasi. Pilihan fitur ini harus tercatat jelas dalam naskah
sebelum hasil akhir dilaporkan. Skrip pilot, RF/IF, dan laporan lama di repositori
merupakan jejak eksplorasi topik sebelumnya, bukan pelaksanaan Bab 4 Plan B.

