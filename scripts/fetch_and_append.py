"""
Dipanggil otomatis oleh GitHub Actions (lihat .github/workflows/collect.yml).
Mengambil 720 candle TERBARU dari Kraken, menggabungkannya dengan data yang
sudah tersimpan di data/btc_15m.csv, membuang baris kembar (berdasarkan
waktu), lalu menyimpannya kembali -- supaya data terus bertambah tanpa
pernah ketimpa atau hilang.
"""
import os
import pandas as pd
import requests

PAIR = "XBTUSD"
INTERVAL_MENIT = 15
OUTPUT = "data/btc_15m.csv"


def ambil_dari_kraken() -> pd.DataFrame:
    url = "https://api.kraken.com/0/public/OHLC"
    resp = requests.get(url, params={"pair": PAIR, "interval": INTERVAL_MENIT}, timeout=30)
    data = resp.json()
    if data["error"]:
        raise RuntimeError(f"Kraken mengirim error: {data['error']}")

    candles = [v for k, v in data["result"].items() if k != "last"][0]
    kolom = ["time", "open", "high", "low", "close", "vwap", "volume", "count"]
    df = pd.DataFrame(candles, columns=kolom)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df[kolom[1:]] = df[kolom[1:]].astype(float)
    df = df.iloc[:-1]  # buang candle terakhir, belum selesai terbentuk
    return df


def main():
    baru = ambil_dari_kraken()
    print(f"Berhasil mengambil {len(baru)} candle dari Kraken.")

    os.makedirs("data", exist_ok=True)
    if os.path.exists(OUTPUT):
        lama = pd.read_csv(OUTPUT, parse_dates=["time"])
        gabungan = pd.concat([lama, baru], ignore_index=True)
    else:
        gabungan = baru

    gabungan = gabungan.drop_duplicates(subset="time").sort_values("time")
    gabungan.to_csv(OUTPUT, index=False)
    print(f"Total data tersimpan sekarang: {len(gabungan)} baris, "
          f"dari {gabungan['time'].min()} sampai {gabungan['time'].max()}.")


if __name__ == "__main__":
    main()
