# Databento OHLCV-1m CSV -> normalized Parquet (per-day, ET-indexed)
"""
Converts Databento OHLCV 1-minute CSV files into engine-friendly Parquet:

Input:
  data/raw/NQ/*.csv
  data/raw/ES/*.csv

Output (partitioned by day, ET timezone, timestamp as DatetimeIndex):
  data/vendor_parquet/NQ/by_day/<SYMBOL>/YYYY/MM/YYYY-MM-DD.parquet
  data/vendor_parquet/ES/by_day/<SYMBOL>/YYYY/MM/YYYY-MM-DD.parquet

Normalized schema (columns):
  open, high, low, close, volume
Index:
  timestamp (DatetimeIndex, tz-aware America/New_York)

Notes:
- We intentionally write to a new subfolder `by_day/` so it doesn't collide with
  existing legacy files like data/vendor_parquet/NQ/NQH2.parquet.
- This is designed for "last 3 months" style gating and easy missing-day audits.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd


RAW_BASE_DEFAULT = Path("data/raw")
OUT_BASE_DEFAULT = Path("data/vendor_parquet")
TZ_OUT = "America/New_York"


def find_timestamp_column(cols: Iterable[str]) -> str:
    candidates = ["ts_event", "ts_recv", "ts", "timestamp", "time", "datetime"]
    for c in candidates:
        if c in cols:
            return c
    raise ValueError(
        f"Could not find timestamp column in {list(cols)} (tried {candidates})"
    )


def find_symbol_column(cols: Iterable[str]) -> str | None:
    candidates = ["symbol", "instrument_id"]
    for c in candidates:
        if c in cols:
            return c
    return None


def normalize_one_csv(
    csv_path: Path,
    symbols: set[str] | None,
    date_from: pd.Timestamp | None,
    date_to: pd.Timestamp | None,
) -> pd.DataFrame:
    # Peek header only
    header = pd.read_csv(csv_path, nrows=0)
    cols = list(header.columns)

    ts_col = find_timestamp_column(cols)
    sym_col = find_symbol_column(cols)

    # OHLCV columns (assume Databento OHLCV naming)
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise ValueError(
            f"{csv_path.name}: missing OHLCV columns {missing}. Found {cols}"
        )

    usecols = [ts_col, *required]
    if sym_col is not None:
        usecols.append(sym_col)

    df = pd.read_csv(csv_path, usecols=usecols)

    # Timestamp -> UTC -> ET
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce").dropna()
    df = df.loc[ts.index].copy()
    df["timestamp"] = ts.dt.tz_convert(TZ_OUT)

    # Symbol normalize
    if sym_col is None:
        df["symbol"] = "UNKNOWN"
    elif sym_col == "instrument_id":
        df = df.rename(columns={"instrument_id": "symbol"})
    else:
        # sym_col == "symbol"
        pass

    # Filter symbols if requested
    if symbols is not None:
        df = df[df["symbol"].isin(symbols)]

    # Filter date range (ET dates)
    if date_from is not None:
        df = df[df["timestamp"] >= date_from]
    if date_to is not None:
        # inclusive end date if user passes a date; we implement [from, to_end_of_day]
        df = df[df["timestamp"] <= date_to]

    # Keep only normalized cols + index
    df = df[["timestamp", "symbol", *required]].dropna(subset=["timestamp"])
    df = df.sort_values("timestamp").set_index("timestamp").sort_index()

    return df


def write_partitioned_by_day(
    df: pd.DataFrame,
    out_root: Path,
) -> int:
    """
    Write df (ET indexed) into per-day parquet under:
      out_root/by_day/<SYMBOL>/YYYY/MM/YYYY-MM-DD.parquet

    Returns number of files written.
    """
    if df.empty:
        return 0

    written = 0

    # Group by symbol first
    for symbol, df_sym in df.groupby("symbol"):
        df_sym = df_sym.drop(columns=["symbol"])

        # Group by ET calendar day
        for day, day_df in df_sym.groupby(df_sym.index.date):
            day = pd.Timestamp(day).date()
            yyyy = f"{day:%Y}"
            mm = f"{day:%m}"

            out_dir = out_root / "by_day" / symbol / yyyy / mm
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{day:%Y-%m-%d}.parquet"

            if out_path.exists():
                existing = pd.read_parquet(out_path)

                # Ensure index is datetime; if not, try to coerce
                if not isinstance(existing.index, pd.DatetimeIndex):
                    if "timestamp" in existing.columns:
                        existing["timestamp"] = pd.to_datetime(
                            existing["timestamp"], utc=True
                        ).dt.tz_convert(TZ_OUT)
                        existing = existing.set_index("timestamp").sort_index()
                    else:
                        raise ValueError(
                            f"{out_path} exists but has no DatetimeIndex and no timestamp col."
                        )

                combined = pd.concat([existing, day_df], axis=0)

                # Deduplicate by timestamp index (keep last)
                combined = combined[
                    ~combined.index.duplicated(keep="last")
                ].sort_index()
                combined.to_parquet(out_path, index=True)
            else:
                day_df.to_parquet(out_path, index=True)

            written += 1

    return written


def process_product(
    product: str,
    raw_base: Path,
    out_base: Path,
    symbols: set[str] | None,
    date_from: str | None,
    date_to: str | None,
) -> None:
    raw_dir = raw_base / product
    if not raw_dir.exists():
        print(f"[WARN] Raw dir missing: {raw_dir}")
        return

    out_root = out_base / product
    out_root.mkdir(parents=True, exist_ok=True)

    # Interpret date filters as ET day bounds
    dt_from = pd.Timestamp(date_from, tz=TZ_OUT) if date_from else None
    dt_to = None
    if date_to:
        # end of day inclusive
        dt_to = pd.Timestamp(date_to, tz=TZ_OUT) + pd.Timedelta(
            hours=23, minutes=59, seconds=59
        )

    csv_files = sorted(raw_dir.glob("*.csv"))
    if not csv_files:
        print(f"[WARN] No CSV files found in {raw_dir}")
        return

    print(f"[INFO] {product}: {len(csv_files)} CSV files found in {raw_dir}")
    total_written = 0
    total_rows = 0

    for path in csv_files:
        print(f"  -> {path.name}")
        df = normalize_one_csv(path, symbols=symbols, date_from=dt_from, date_to=dt_to)
        total_rows += len(df)

        n_written = write_partitioned_by_day(df, out_root=out_root)
        total_written += n_written

    print(
        f"[DONE] {product}: rows={total_rows:,} day-files-written/updated={total_written:,}"
    )
    print(f"       Output root: {out_root / 'by_day'}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert Databento OHLCV-1m CSVs to per-day ET-indexed Parquet."
    )
    ap.add_argument(
        "--products",
        nargs="+",
        default=["NQ", "ES"],
        help="Products to process (default: NQ ES).",
    )
    ap.add_argument(
        "--raw-base",
        default=str(RAW_BASE_DEFAULT),
        help="Raw base directory (default: data/raw).",
    )
    ap.add_argument(
        "--out-base",
        default=str(OUT_BASE_DEFAULT),
        help="Output base directory (default: data/vendor_parquet).",
    )
    ap.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Optional: limit to specific symbols (e.g., NQU5 NQZ5).",
    )
    ap.add_argument(
        "--from",
        dest="date_from",
        default=None,
        help="Start date (ET) YYYY-MM-DD (inclusive).",
    )
    ap.add_argument(
        "--to",
        dest="date_to",
        default=None,
        help="End date (ET) YYYY-MM-DD (inclusive).",
    )
    args = ap.parse_args()

    raw_base = Path(args.raw_base)
    out_base = Path(args.out_base)
    symbols = set(args.symbols) if args.symbols else None

    for prod in args.products:
        process_product(
            product=prod,
            raw_base=raw_base,
            out_base=out_base,
            symbols=symbols,
            date_from=args.date_from,
            date_to=args.date_to,
        )


if __name__ == "__main__":
    main()
