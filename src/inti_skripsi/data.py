"""Membaca candle, membentuk fitur, dan membagi data secara kronologis."""

import csv
import datetime as dt
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "raw" / "btc_15m_study_20261125.csv"
DATA_START_UTC = "2026-09-26 22:45:00+00:00"
HISTORICAL_END = dt.datetime.fromisoformat("2026-10-17 20:45:00+00:00")
VALIDATION_END = dt.datetime.fromisoformat("2026-11-04 18:45:00+00:00")
HISTORICAL_ROWS = 2008
VALIDATION_ROWS = 1720
TEST_ROWS = 2008
TEST_CUTOFF_UTC = "2026-11-25 16:45:00+00:00"
RAW_ROWS = 1 + HISTORICAL_ROWS + VALIDATION_ROWS + TEST_ROWS
FEATURE_COUNT = 3
CANDLE_INTERVAL_MINUTES = 15
WIB = dt.timezone(dt.timedelta(hours=7), name="WIB")


def _baca_candle(path):
    """Periksa seluruh candle mentah sebelum pembentukan fitur."""
    candles = []
    previous_time = None
    interval = dt.timedelta(minutes=CANDLE_INTERVAL_MINUTES)
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for candle in csv.DictReader(handle):
            moment = dt.datetime.fromisoformat(candle["time"])
            if moment.utcoffset() != dt.timedelta(0):
                raise ValueError("Waktu candle harus memiliki zona UTC")
            if previous_time is not None and moment - previous_time != interval:
                raise ValueError("Urutan atau interval candle mentah tidak lengkap")
            values = {
                key: float(candle[key])
                for key in ("open", "high", "low", "close", "vwap", "volume", "count")
            }
            if not all(math.isfinite(value) for value in values.values()):
                raise ValueError("Nilai candle mentah harus berupa angka terhingga")
            close, volume, count = (values[key] for key in ("close", "volume", "count"))
            if close <= 0 or volume < 0 or count < 0:
                raise ValueError("Nilai candle tidak valid")
            candles.append((candle["time"], close, volume, count))
            previous_time = moment
    return candles


def baca_fitur(path):
    """Bentuk tiga fitur setelah seluruh candle mentah diperiksa."""
    candles = _baca_candle(path)
    output = []
    for previous, current in zip(candles, candles[1:]):
        stamp, close, volume, count = current
        output.append(
            (
                stamp,
                (
                    math.log(close / previous[1]),
                    math.log1p(volume),
                    math.log1p(count),
                ),
            )
        )
    return output


def ke_wib(utc_stamp):
    """Ubah tampilan waktu UTC ke WIB tanpa mengubah indeks candle."""
    moment = dt.datetime.fromisoformat(utc_stamp)
    if moment.tzinfo is None or moment.utcoffset() != dt.timedelta(0):
        raise ValueError("Waktu sumber harus memiliki zona UTC")
    return moment.astimezone(WIB).strftime("%Y-%m-%d %H:%M:%S WIB")


def periksa_data(rows):
    """Periksa waktu setiap catatan dan selang 15 menit antarcatatan."""
    times = [dt.datetime.fromisoformat(stamp) for stamp, _ in rows]
    interval = dt.timedelta(minutes=CANDLE_INTERVAL_MINUTES)
    if any(b - a != interval for a, b in zip(times, times[1:])):
        raise ValueError(
            "Data berfitur memiliki urutan waktu atau interval yang tidak lengkap"
        )
    if len(set(times)) != len(times):
        raise ValueError("Data berfitur memiliki waktu ganda")


def _bagi_data(rows):
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
    if (
        len(test) != TEST_ROWS
        or dt.datetime.fromisoformat(test[-1][0])
        != dt.datetime.fromisoformat(TEST_CUTOFF_UTC)
    ):
        raise ValueError("Batas bagian uji tidak sesuai Bab 4")
    return historical, validation, test


def _bakukan_fitur(part, means, spreads):
    """Gunakan statistik historis yang sama pada setiap bagian."""
    return [
        (
            stamp,
            tuple((values[j] - means[j]) / spreads[j] for j in range(FEATURE_COUNT)),
        )
        for stamp, values in part
    ]


def siapkan_data(path=DATA):
    """Siapkan data historis, validasi, dan uji beserta statistik historis."""
    rows = baca_fitur(path)
    periksa_data(rows)
    historical, validation, test = _bagi_data(rows)
    means = [statistics.mean(v[j] for _, v in historical) for j in range(FEATURE_COUNT)]
    spreads = [
        statistics.stdev(v[j] for _, v in historical) for j in range(FEATURE_COUNT)
    ]
    if any(value <= 0 for value in spreads):
        raise ValueError("Simpangan baku historis harus positif")
    return (
        _bakukan_fitur(historical, means, spreads),
        _bakukan_fitur(validation, means, spreads),
        _bakukan_fitur(test, means, spreads),
        means,
        spreads,
    )
