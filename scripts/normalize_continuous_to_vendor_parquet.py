"""
Script: ETL Normalizer
Purpose: Transforms raw Databento API dumps into the strict Meridian Data Contract.

Description:
    Performs the Critical Path ETL steps:
    1. Timezone Standardization: UTC -> America/New_York.
    2. RTH Slicing: Filters for 09:30 - 16:00 ET.
    3. Grid Alignment: Reindexes to a dense 1-minute grid (gap handling via ffill/zero-vol).
    4. Schema Enforcement: Drops vendor metadata, keeps only OHLCV + Symbol.

Usage:
    python scripts/normalize_continuous_to_vendor_parquet.py \
        --raw-parquet data/raw/databento_api/raw_nq.parquet \
        --symbol NQ.v.0 --product NQ

Arguments:
    --raw-parquet : Path to the source file from Databento.
    --product     : Product code (NQ/ES) for folder organization.
    --write-by-day: (Flag) Also output partitioned files for unit testing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SessionSpec:
    start_hm: tuple[int, int] = (9, 30)
    end_hm: tuple[int, int] = (16, 0)  # end is exclusive; grid ends at 15:59


def _ensure_timestamp_utc(df: pd.DataFrame) -> pd.Series:
    # Common cases from Databento parquet:
    # - 'ts_event' as ISO8601 string or int nanoseconds
    # - 'timestamp' already present
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True)
        return ts

    if "ts_event" in df.columns:
        col = df["ts_event"]
        # int nanoseconds since epoch or ISO8601 strings
        if np.issubdtype(col.dtype, np.number):
            ts = pd.to_datetime(col.astype("int64"), utc=True, unit="ns")
        else:
            ts = pd.to_datetime(col, utc=True)
        return ts

    # fallback: index
    if isinstance(df.index, pd.DatetimeIndex):
        if df.index.tz is None:
            return df.index.tz_localize("UTC")
        return df.index.tz_convert("UTC")

    raise ValueError(
        "Could not infer timestamp column (expected 'timestamp' or 'ts_event' or DatetimeIndex)"
    )


def _rth_minute_grid(session_date: pd.Timestamp, spec: SessionSpec) -> pd.DatetimeIndex:
    start = pd.Timestamp(
        year=session_date.year,
        month=session_date.month,
        day=session_date.day,
        hour=spec.start_hm[0],
        minute=spec.start_hm[1],
        tz=ET,
    )
    end = pd.Timestamp(
        year=session_date.year,
        month=session_date.month,
        day=session_date.day,
        hour=spec.end_hm[0],
        minute=spec.end_hm[1],
        tz=ET,
    )
    # end exclusive -> last bar at 15:59
    return pd.date_range(start, end - pd.Timedelta(minutes=1), freq="1min")


def _normalize_one_day(
    day_df: pd.DataFrame, symbol: str, spec: SessionSpec
) -> pd.DataFrame | None:
    if day_df.empty:
        return None

    ts_utc = _ensure_timestamp_utc(day_df)
    ts_et = ts_utc.dt.tz_convert(ET)

    day_df = day_df.copy()
    day_df["timestamp_utc"] = ts_utc
    day_df["timestamp_et"] = ts_et

    # RTH slice
    d0 = ts_et.dt.normalize().iloc[0]
    grid = _rth_minute_grid(d0, spec)

    # Filter to RTH window for that day
    mask = (day_df["timestamp_et"] >= grid.min()) & (
        day_df["timestamp_et"] <= grid.max()
    )
    rth = day_df.loc[
        mask, ["timestamp_et", "open", "high", "low", "close", "volume"]
    ].copy()
    if rth.empty:
        return None

    rth = rth.sort_values("timestamp_et").drop_duplicates(subset=["timestamp_et"])
    rth = rth.set_index("timestamp_et")

    # Reindex to full 1-min grid
    rth = rth.reindex(grid)

    # Fill: close ffill; if first is missing, backfill once.
    rth["close"] = rth["close"].ffill().bfill(limit=1)

    # For filled bars, set OHLC to close; volume=0
    for c in ["open", "high", "low"]:
        rth[c] = rth[c].fillna(rth["close"])
    rth["volume"] = rth["volume"].fillna(0).astype("int64")

    out = rth.reset_index().rename(columns={"index": "timestamp_et"})
    out["timestamp"] = out["timestamp_et"].dt.tz_convert("UTC")
    out["symbol"] = symbol

    out = out[["timestamp", "symbol", "open", "high", "low", "close", "volume"]]
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-parquet",
        required=True,
        help="Raw parquet from databento_fetch_continuous.py",
    )
    parser.add_argument("--symbol", required=True, help="e.g. NQ.v.0")
    parser.add_argument(
        "--product", required=True, help="NQ or ES (just used for folder naming)"
    )
    parser.add_argument("--start", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument(
        "--out-root", default="data/vendor_parquet", help="Base vendor_parquet dir"
    )
    parser.add_argument("--write-by-day", action="store_true", default=True)
    parser.add_argument("--write-combined", action="store_true", default=True)
    args = parser.parse_args()

    raw_path = Path(args.raw_parquet)
    if not raw_path.exists():
        raise SystemExit(f"Raw parquet not found: {raw_path}")

    df = pd.read_parquet(raw_path)

    # Keep only the symbol we asked for (defensive if file includes anything else).
    if "symbol" in df.columns:
        df = df[df["symbol"] == args.symbol].copy()

    ts_utc = _ensure_timestamp_utc(df)
    df = df.copy()
    df["timestamp"] = ts_utc

    start = pd.Timestamp(args.start).normalize()
    end = pd.Timestamp(args.end).normalize()
    all_dates = pd.date_range(start, end, freq="D")

    out_base = Path(args.out_root) / args.product
    by_day_root = out_base / "by_day" / args.symbol

    spec = SessionSpec()
    day_frames: list[pd.DataFrame] = []
    written_days = 0
    skipped_days = 0

    for d in all_dates:
        # filter by ET date for session grouping
        ts_et = df["timestamp"].dt.tz_convert(ET)
        mask = ts_et.dt.date == d.date()
        day_df = df.loc[mask, :]
        out_day = _normalize_one_day(day_df, args.symbol, spec)
        if out_day is None:
            skipped_days += 1
            continue

        day_frames.append(out_day)

        if args.write_by_day:
            y = f"{d.year:04d}"
            m = f"{d.month:02d}"
            by_day_dir = by_day_root / y / m
            by_day_dir.mkdir(parents=True, exist_ok=True)
            out_path = by_day_dir / f"{d.date()}.parquet"
            out_day.to_parquet(out_path, index=False)
            written_days += 1

    if not day_frames:
        raise SystemExit("No RTH sessions produced. Wrong date range or wrong symbol.")

    combined = pd.concat(day_frames, ignore_index=True).sort_values("timestamp")

    if args.write_combined:
        out_base.mkdir(parents=True, exist_ok=True)
        combined_path = out_base / f"{args.symbol}_{args.start}_{args.end}_RTH.parquet"
        combined.to_parquet(combined_path, index=False)
        print(f"[DONE] combined parquet: {combined_path}")

    print(f"[DONE] by-day written: {written_days}, skipped: {skipped_days}")
    print(f"[INFO] combined rows: {len(combined)} (expect ~390 * trading_days)")


if __name__ == "__main__":
    main()
