"""
Generate a deterministic RTH minute-bar OHLCV fixture for CI determinism checks.

Design goals:
- Deterministic given (seed, params)
- America/New_York timezone
- RTH minutes only: 09:30 -> 15:59 (390 bars/day)
- Tick-size quantized prices (reduces float weirdness, more realistic)
- Includes an overnight gap between sessions (exercises gap-risk logic)
- Outputs Parquet (preferred) or CSV

Usage:
  python scripts/ci/make_ci_data.py --out ci_data.parquet
  python scripts/ci/make_ci_data.py --out ci_data.csv --format csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

RTH_START = (9, 30)
RTH_BARS_PER_DAY = 390  # 09:30 .. 15:59 inclusive (390 1-min bars)


def _rth_index_for_day(day: pd.Timestamp, tz: str) -> pd.DatetimeIndex:
    """
    Create a 1-minute RTH index for a single trading day.
    Bars are timestamped at bar-start: 09:30 .. 15:59.
    """
    day = pd.Timestamp(day).normalize()
    start = pd.Timestamp(
        year=day.year,
        month=day.month,
        day=day.day,
        hour=RTH_START[0],
        minute=RTH_START[1],
    ).tz_localize(tz)
    idx = pd.date_range(start=start, periods=RTH_BARS_PER_DAY, freq="1min")
    return idx


def _generate_day_ohlcv(
    idx: pd.DatetimeIndex,
    rng: np.random.Generator,
    tick_size: float,
    start_price: float,
    vol_ticks: int,
) -> tuple[pd.DataFrame, float]:
    """
    Generate a day's OHLCV as a tick-quantized random walk.
    Returns (df_day, last_close).
    """
    n = len(idx)

    moves = rng.integers(-vol_ticks, vol_ticks + 1, size=n, dtype=np.int32)
    close = start_price + np.cumsum(moves, dtype=np.int64) * tick_size

    open_ = np.empty_like(close)
    open_[0] = start_price
    open_[1:] = close[:-1]

    wick_hi = rng.integers(0, 4, size=n, dtype=np.int32) * tick_size
    wick_lo = rng.integers(0, 4, size=n, dtype=np.int32) * tick_size

    high = np.maximum(open_, close) + wick_hi
    low = np.minimum(open_, close) - wick_lo

    volume = rng.integers(100, 5000, size=n, dtype=np.int32)

    df = pd.DataFrame(
        {
            "open": open_.astype(np.float64),
            "high": high.astype(np.float64),
            "low": low.astype(np.float64),
            "close": close.astype(np.float64),
            "volume": volume.astype(np.int64),
        },
        index=idx,
    )
    df.index.name = "datetime"
    return df, float(df["close"].iloc[-1])


def build_fixture(
    tz: str,
    start_date: str,
    num_days: int,
    seed: int,
    tick_size: float,
    base_price: float,
    vol_ticks: int,
    overnight_gap_ticks: int,
) -> pd.DataFrame:
    """
    Build a multi-day RTH-only dataset with an overnight gap between sessions.
    """
    rng = np.random.default_rng(seed)

    days = pd.bdate_range(start=start_date, periods=num_days)

    frames: list[pd.DataFrame] = []
    last_close = base_price

    for i, d in enumerate(days):
        idx = _rth_index_for_day(d, tz=tz)

        if i > 0:
            last_close = last_close + overnight_gap_ticks * tick_size

        df_day, last_close = _generate_day_ohlcv(
            idx=idx,
            rng=rng,
            tick_size=tick_size,
            start_price=last_close,
            vol_ticks=vol_ticks,
        )
        frames.append(df_day)

    df_all = pd.concat(frames, axis=0)

    # Safety checks (fail fast if something is off)
    if not isinstance(df_all.index, pd.DatetimeIndex) or df_all.index.tz is None:
        raise RuntimeError("Index must be tz-aware DatetimeIndex.")
    if not df_all.index.is_monotonic_increasing:
        raise RuntimeError("Index must be strictly monotonic increasing.")
    req_cols = ("open", "high", "low", "close", "volume")
    missing = [c for c in req_cols if c not in df_all.columns]
    if missing:
        raise RuntimeError(f"Missing required columns: {missing}")

    return df_all


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--out", required=True, help="Output file path (e.g., ci_data.parquet)"
    )
    p.add_argument("--format", choices=["parquet", "csv"], default="parquet")
    p.add_argument("--tz", default="America/New_York")
    p.add_argument("--start-date", default="2024-01-02")  # weekday
    p.add_argument("--num-days", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--tick-size", type=float, default=0.25)
    p.add_argument("--base-price", type=float, default=15000.0)
    p.add_argument(
        "--vol-ticks", type=int, default=2, help="per-minute move range in ticks"
    )
    p.add_argument(
        "--overnight-gap-ticks",
        type=int,
        default=40,
        help="fixed gap applied at next day open (in ticks)",
    )
    args = p.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = build_fixture(
        tz=args.tz,
        start_date=args.start_date,
        num_days=args.num_days,
        seed=args.seed,
        tick_size=args.tick_size,
        base_price=args.base_price,
        vol_ticks=args.vol_ticks,
        overnight_gap_ticks=args.overnight_gap_ticks,
    )

    if args.format == "parquet":
        # Pyarrow
        df.to_parquet(out_path, engine="pyarrow", compression="zstd")
    else:
        # CSV
        df.to_csv(out_path)

    print(f"Wrote {len(df):,} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
