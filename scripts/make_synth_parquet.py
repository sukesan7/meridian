"""
Script: Synthetic Data Generator
Purpose: Creates deterministic OHLCV Parquet files for unit testing.

Description:
    Generates a Brownian Motion random walk with drift to simulate price action.
    Strictly conforms to the Meridian Data Contract (RTH 09:30-16:00 ET).
    Used by 'quickstart.sh' to allow running the engine without API keys.

Usage:
    python scripts/make_synth_parquet.py --out data/sample/synth.parquet --days 3
"""

from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def make_synth_rth_1m(start_date: str, n_days: int, tz: str, seed: int) -> pd.DataFrame:
    start = pd.Timestamp(start_date, tz=tz)
    rng = np.random.default_rng(seed)

    frames = []
    price = 100.0

    for d in range(n_days):
        day = (start + pd.Timedelta(days=d)).normalize()
        idx = pd.date_range(
            day + pd.Timedelta(hours=9, minutes=30),
            day + pd.Timedelta(hours=15, minutes=59),
            freq="1min",
            tz=tz,
        )

        drift = np.linspace(0, 1.5, len(idx))
        noise = rng.normal(0, 0.05, size=len(idx))
        close = price + drift + noise
        open_ = np.r_[close[0], close[:-1]]
        high = np.maximum(open_, close) + 0.02
        low = np.minimum(open_, close) - 0.02
        vol = rng.integers(50, 200, size=len(idx))

        df = pd.DataFrame(
            {
                "timestamp": idx.tz_convert("UTC"),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": vol,
            }
        )
        frames.append(df)
        price = float(close[-1] + 0.25)

    return pd.concat(frames, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="Output parquet path")
    ap.add_argument("--start-date", default="2025-01-06")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--tz", default="America/New_York")
    ap.add_argument("--seed", type=int, default=123)
    args = ap.parse_args()

    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    df = make_synth_rth_1m(args.start_date, args.days, args.tz, args.seed)
    df.to_parquet(out, index=False)
    print(str(out))


if __name__ == "__main__":
    main()
