"""Membaca candle, membentuk fitur, dan membagi data secara kronologis."""

import csv
import datetime as dt
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "btc_15m.csv"
HISTORICAL_END = dt.datetime.fromisoformat("2026-10-17 17:30:00+00:00")
VALIDATION_END = dt.datetime.fromisoformat("2026-10-26 15:15:00+00:00")
HISTORICAL_ROWS = 1995
VALIDATION_ROWS = 855
FEATURE_COUNT = 3
CANDLE_INTERVAL_MINUTES = 15
WIB = dt.timezone(dt.timedelta(hours=7), name="WIB")


def read_features(path):
    """Bentuk tiga fitur dari CSV OHLC Kraken dalam urutan aslinya."""
    output, prior = [], None
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for candle in csv.DictReader(handle):
            close = float(candle["close"])
            volume = float(candle["volume"])
            count = float(candle["count"])
            if close <= 0 or volume < 0 or count < 0:
                raise ValueError("Nilai candle tidak valid")
            if prior is not None:
                output.append(
                    (
                        candle["time"],
                        (
                            math.log(close / prior),
                            math.log1p(volume),
                            math.log1p(count),
                        ),
                    )
                )
            prior = close
    return output


def to_wib(utc_stamp):
    """Ubah tampilan waktu UTC ke WIB tanpa mengubah indeks candle."""
    moment = dt.datetime.fromisoformat(utc_stamp)
    if moment.tzinfo is None or moment.utcoffset() != dt.timedelta(0):
        raise ValueError("Waktu sumber harus memiliki zona UTC")
    return moment.astimezone(WIB).strftime("%Y-%m-%d %H:%M:%S WIB")


def check_data(rows):
    """Pastikan setiap fitur berjarak 15 menit dan waktunya unik."""
    times = [dt.datetime.fromisoformat(stamp) for stamp, _ in rows]
    interval = dt.timedelta(minutes=CANDLE_INTERVAL_MINUTES)
    if any(b - a != interval for a, b in zip(times, times[1:])):
        raise ValueError(
            "Data berfitur memiliki urutan waktu atau interval yang tidak lengkap"
        )
    if len(set(times)) != len(times):
        raise ValueError("Data berfitur memiliki waktu ganda")


def _split_rows(rows):
    """Pisahkan fitur menurut dua batas waktu penelitian."""
    stamped = [
        (dt.datetime.fromisoformat(stamp), (stamp, values)) for stamp, values in rows
    ]
    historical = [row for moment, row in stamped if moment <= HISTORICAL_END]
    validation = [
        row for moment, row in stamped if HISTORICAL_END < moment <= VALIDATION_END
    ]
    test = [row for moment, row in stamped if moment > VALIDATION_END]
    if (
        len(historical) != HISTORICAL_ROWS
        or dt.datetime.fromisoformat(historical[-1][0]) != HISTORICAL_END
    ):
        raise ValueError("Batas bagian historis tidak sesuai Bab 4")
    if (
        len(validation) != VALIDATION_ROWS
        or dt.datetime.fromisoformat(validation[-1][0]) != VALIDATION_END
    ):
        raise ValueError("Batas bagian validasi tidak sesuai Bab 4")
    return historical, validation, test


def _standardize(part, means, spreads):
    """Gunakan statistik historis yang sama pada setiap bagian."""
    return [
        (
            stamp,
            tuple((values[j] - means[j]) / spreads[j] for j in range(FEATURE_COUNT)),
        )
        for stamp, values in part
    ]


def prepare(path=DATA):
    """Siapkan data historis, validasi, dan uji beserta statistik historis."""
    rows = read_features(path)
    check_data(rows)
    historical, validation, test = _split_rows(rows)
    means = [statistics.mean(v[j] for _, v in historical) for j in range(FEATURE_COUNT)]
    spreads = [
        statistics.stdev(v[j] for _, v in historical) for j in range(FEATURE_COUNT)
    ]
    if any(value <= 0 for value in spreads):
        raise ValueError("Simpangan baku historis harus positif")
    return (
        _standardize(historical, means, spreads),
        _standardize(validation, means, spreads),
        _standardize(test, means, spreads),
        means,
        spreads,
    )
