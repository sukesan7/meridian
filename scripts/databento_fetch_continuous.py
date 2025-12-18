"""
Fetch Databento OHLCV-1m for continuous futures (e.g., NQ.v.0, ES.v.0)
and save a raw Parquet file.

Why: Web portal downloads are "parent product" requests and include many
child instruments + spreads. API lets you request a single continuous instrument.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import databento as db
import pandas as pd


def parse_date_utc(s: str) -> pd.Timestamp:
    """Parse YYYY-MM-DD into a UTC-normalized timestamp at 00:00."""
    ts = pd.Timestamp(s)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC")
    return ts.normalize().tz_localize("UTC")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="GLBX.MDP3")
    parser.add_argument("--schema", default="ohlcv-1m")
    parser.add_argument("--symbol", required=True, help="e.g. NQ.v.0 or ES.v.0")
    parser.add_argument(
        "--stype-in",
        default="continuous",
        help="continuous | parent | raw_symbol | ...",
    )
    parser.add_argument("--start", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument(
        "--out-dir", default="data/raw/databento_api", help="Base output dir"
    )
    args = parser.parse_args()

    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        raise SystemExit("Missing env var DATABENTO_API_KEY")

    # We treat user-provided end as INCLUSIVE and convert to EXCLUSIVE for Databento.
    start_utc = parse_date_utc(args.start)
    end_exclusive_utc = parse_date_utc(args.end) + pd.Timedelta(days=1)

    if end_exclusive_utc <= start_utc:
        raise SystemExit(
            f"Invalid range: start={start_utc} end_exclusive={end_exclusive_utc} (end must be after start)"
        )

    # Safety: prevent spending.
    days = (end_exclusive_utc - start_utc).days
    if days > 120:
        raise SystemExit(
            f"Refusing to request {days} days (>120). Reduce --start/--end."
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_symbol = args.symbol.replace("/", "_")
    out_path = (
        out_dir
        / f"{args.dataset}_{args.schema}_{safe_symbol}_{args.start}_{args.end}.parquet"
    )

    client = db.Historical(api_key)

    store = client.timeseries.get_range(
        dataset=args.dataset,
        schema=args.schema,
        symbols=[args.symbol],
        stype_in=args.stype_in,
        start=str(start_utc.date()),
        end=str(end_exclusive_utc.date()),  # EXCLUSIVE end date
    )

    store.to_parquet(str(out_path))
    print(f"[DONE] wrote raw parquet: {out_path}")


if __name__ == "__main__":
    main()
