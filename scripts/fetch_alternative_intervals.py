"""Collect separate 1-minute and 5-minute Kraken candles for feasibility checks.

The established 15-minute dataset is untouched.
"""
from pathlib import Path
import pandas as pd
import requests

PAIR = "XBTUSD"
COLUMNS = ["time", "open", "high", "low", "close", "vwap", "volume", "count"]
ROOT = Path(__file__).resolve().parents[1]

def fetch(interval):
    response = requests.get(
        "https://api.kraken.com/0/public/OHLC",
        params={"pair": PAIR, "interval": interval},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload["error"]:
        raise RuntimeError(f"Kraken error for {interval}m: {payload['error']}")
    rows = next(value for key, value in payload["result"].items() if key != "last")
    frame = pd.DataFrame(rows[:-1], columns=COLUMNS)
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    frame[COLUMNS[1:]] = frame[COLUMNS[1:]].astype(float)
    return frame

def save(interval):
    path = ROOT / "data" / f"btc_{interval}m.csv"
    path.parent.mkdir(exist_ok=True)
    new = fetch(interval)
    if path.exists():
        previous = pd.read_csv(path, parse_dates=["time"])
        previous["time"] = pd.to_datetime(previous["time"], utc=True)
        combined = pd.concat((previous, new), ignore_index=True)
    else:
        combined = new
    combined = combined.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    gaps = combined["time"].diff().dropna()
    unusual = int((gaps != pd.Timedelta(minutes=interval)).sum())
    combined.to_csv(path, index=False)
    print(f"{interval}m: {len(combined)} completed candles, "
          f"{combined['time'].iloc[0]} to {combined['time'].iloc[-1]}, "
          f"nonstandard gaps={unusual}")

if __name__ == "__main__":
    for interval in (1, 5):
        save(interval)


