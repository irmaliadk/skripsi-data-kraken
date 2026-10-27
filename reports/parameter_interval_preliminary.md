# Audit awal interval dan parameter (27 Oktober 2026)

**Status: eksplorasi validasi, bukan hasil uji akhir atau keputusan parameter final.**

## Data dan prosedur

- Data 15 menit yang dipakai berhenti pada 26 Oktober 2026 pukul 15.15 UTC: 1.995 baris fitur untuk pelatihan dan 855 untuk validasi kronologis.
- Injeksi dicoba pada indeks validasi 400, 427, dan 454; pada masing-masing dari tiga fitur; untuk perubahan rerata, skala, korelasi, dan gabungan. Jadi ada 36 aliran injeksi per konfigurasi. Aliran-aliran ini berasal dari data yang sama dan **bukan 36 sampel independen**.
- Setiap aliran injeksi dibandingkan dengan aliran asli tanpa injeksi. Alarm dicatat dalam 400 candle setelah awal injeksi. Untuk PCA-CD, hasil juga diperiksa dengan batas 2w sesuai kriteria Qahtan et al. (2015).
- Diuji 30 konfigurasi PCA-CD: w = 100, 150, 200 dan xi = 1, 2, 3, 4, 5, 7.5, 10, 25, 100, 500. Diuji 18 konfigurasi KSWIN: n = 200, 300, 400; r = 20, 30; alpha per fitur = 0.00001, 0.0001, 0.001. Kisi ini adalah rancangan sensitivitas penelitian ini; nilainya tidak diklaim diwajibkan oleh paper.
- Hasil terperinci ada di artefak workflow *Audit parameter pada validasi historis*: sweep_parameters.csv dan sweep_events.csv.

## Temuan sementara

| Metode dan parameter | Aliran injeksi dengan alarm dalam batas | Aliran pembanding asli dengan alarm pada rentang sama | Median keterlambatan alarm yang terdeteksi |
|---|---:|---:|---:|
| PCA-CD w=200, xi=1 | 36/36 | 24/36 | 97 candle |
| PCA-CD w=200, xi=2 | 33/36 | 0/36 | 102 candle |
| PCA-CD w=200, xi=3 | 33/36 | 0/36 | 129 candle |
| PCA-CD w=200, xi=5 | 26/36 | 0/36 | 169 candle |
| KSWIN n=300, r=30, alpha=0.0001 | 36/36 | 36/36 | Belum digunakan untuk pemilihan |

Pada konfigurasi KSWIN yang sebelumnya dipakai, alarm muncul juga pada aliran asli di semua rentang yang diuji. Pada perubahan skala di uji pertama, waktu alarm sama persis pada aliran asli dan aliran injeksi. Karena itu jumlah alarm tersebut **tidak boleh langsung dinyatakan sebagai keberhasilan mendeteksi injeksi**.

Di antara konfigurasi PCA-CD yang dicoba, w=200 dan xi=2 lebih kuat daripada xi=5 pada validasi ini: lebih banyak aliran injeksi memberi alarm, tanpa alarm pada aliran pembanding dalam rentang tersebut. Ini belum membuktikan nilai tersebut optimal pada data lain. Prosedur Page–Hinkley pada naskah Qahtan perlu dicocokkan sekali lagi dengan implementasi karena uraian Bagian 4.5 dan kondisi pada Algoritme 1 tidak identik.

## Data interval lain

Workflow terpisah telah mengambil masing-masing 720 candle lengkap pada interval 1 menit dan 5 menit, dengan 0 jeda waktu pada rentang awalnya. Data utama 15 menit tidak diubah. Pengumpulan interval pembanding dijadwalkan setiap jam agar riwayatnya bertambah. Sebanyak 720 baris belum cukup untuk mengulang pembagian latih/validasi dan pengujian seperti pada aliran 15 menit; perbandingan hasil metode menunggu riwayat yang memadai.

## Rujukan

- Raab et al. (2020), *Reactive Soft Prototype Computing for Concept Drift Streams*. https://doi.org/10.1016/j.neucom.2019.11.111
- Qahtan et al. (2015), *A PCA-Based Change Detection Framework for Multidimensional Data Streams*. https://doi.org/10.1145/2783258.2783359
- Kraken, *Get OHLC Data*. https://docs.kraken.com/api-reference/market-data/get-ohlc-data


