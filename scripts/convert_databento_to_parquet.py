#!/usr/bin/env python
"""
Convert Databento OHLCV-1m CSVs (already .zst-decompressed) into
normalized Parquet files for the 3A backtester.

Input  (per product):
    data/raw/databento/NQ/*.csv
    data/raw/databento/ES/*.csv

Output (per symbol):
    data/vendor_parquet/NQ/<symbol>.parquet
    data/vendor_parquet/ES/<symbol>.parquet

Schema written to Parquet:
    timestamp (UTC, ISO8601)
    symbol
    open
    high
    low
    close
    volume
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


RAW_BASE = Path("data/raw/databento")
OUT_BASE = Path("data/vendor_parquet")


def find_timestamp_column(df: pd.DataFrame) -> str:
    """Guess the timestamp column name from typical Databento schemas."""
    candidates = [
        "ts_event",  # Databento OHLCV-1m
        "ts_recv",
        "ts",
        "timestamp",
        "time",
    ]
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(
        f"Could not find a timestamp column in {list(df.columns)} "
        f"(looked for {candidates})."
    )


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize Databento OHLCV-1m frame to our standard columns.

    Output columns:
        timestamp (UTC), symbol, open, high, low, close, volume
    """
    df = df.copy()

    ts_col = find_timestamp_column(df)
    ts = pd.to_datetime(df[ts_col], utc=True)
    df["timestamp"] = ts

    # Symbol/instrument column
    if "symbol" in df.columns:
        sym_col = "symbol"
    elif "instrument_id" in df.columns:
        sym_col = "instrument_id"
        df = df.rename(columns={"instrument_id": "symbol"})
    else:
        # Some Databento exports may not include symbol if only 1 instrument.
        sym_col = None

    # Ensure OHLCV columns exist
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns {missing} in {list(df.columns)}")

    cols = ["timestamp"]
    if sym_col is not None:
        cols.append("symbol")
    cols.extend(required)

    # Drop any duplicate/extra rows and sort
    df = df[cols].dropna(subset=["timestamp"])
    df = df.sort_values("timestamp")

    return df


def append_to_parquet(out_path: Path, df: pd.DataFrame) -> None:
    """Append df to Parquet file (by re-reading, concatenating, and rewriting)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        existing = pd.read_parquet(out_path)
        combined = pd.concat([existing, df], ignore_index=True)
        # Remove duplicate timestamps if they exist
        combined = combined.drop_duplicates(subset=["timestamp"])
        combined = combined.sort_values("timestamp")
    else:
        combined = df

    combined.to_parquet(out_path, index=False)


def process_product(product: str) -> None:
    raw_dir = RAW_BASE / product
    if not raw_dir.exists():
        print(f"[WARN] Raw directory does not exist: {raw_dir}")
        return

    out_root = OUT_BASE / product
    out_root.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(raw_dir.glob("*.csv"))
    if not csv_files:
        print(f"[WARN] No CSV files found in {raw_dir}")
        return

    print(f"[INFO] Processing {len(csv_files)} CSV files for {product}...")

    for path in csv_files:
        print(f"  -> {path.name}")
        df_raw = pd.read_csv(path)
        df_norm = normalize_ohlcv(df_raw)

        if "symbol" in df_norm.columns:
            # Split into one Parquet per symbol
            for symbol, df_sym in df_norm.groupby("symbol"):
                out_path = out_root / f"{symbol}.parquet"
                append_to_parquet(out_path, df_sym)
        else:
            # No symbol column – treat entire file as one stream
            out_path = out_root / f"{path.stem}.parquet"
            append_to_parquet(out_path, df_norm)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Databento OHLCV-1m CSVs to normalized Parquet files."
    )
    parser.add_argument(
        "--products",
        nargs="+",
        default=["NQ", "ES"],
        help="Which products to process (default: NQ ES).",
    )
    args = parser.parse_args()

    for prod in args.products:
        process_product(prod)


if __name__ == "__main__":
    main()
