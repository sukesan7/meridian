from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd


def _extract_time_range(
    df: pd.DataFrame,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None, str]:
    """
    Return (t_min, t_max, source) where source is:
      - "index" if DatetimeIndex
      - "timestamp_col" if 'timestamp' column
      - "none" if no usable datetime axis
    Always returns tz-aware UTC timestamps when possible.
    """
    # 1) Prefer explicit timestamp column if present
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        ts = ts.dropna()
        if not ts.empty:
            return ts.min(), ts.max(), "timestamp_col"

    # 2) Otherwise use DatetimeIndex if available
    if isinstance(df.index, pd.DatetimeIndex):
        idx = pd.to_datetime(df.index, utc=True, errors="coerce")
        idx = idx.dropna()
        if not idx.empty:
            return idx.min(), idx.max(), "index"

    # 3) No usable datetime axis
    return None, None, "none"


def scan_parquet_dir(
    parquet_dir: Path, pattern: str | None, require_datetime: bool
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    paths = sorted(parquet_dir.rglob(pattern or "*.parquet"))
    for p in paths:
        try:
            # Read minimal set of columns; include timestamp if it exists
            # If a file doesn't have these columns, we'll fall back to reading without columns.
            wanted_cols = ["open", "high", "low", "close", "timestamp"]
            try:
                df = pd.read_parquet(p, columns=wanted_cols)
                cols_present = df.columns.tolist()
            except Exception:
                df = pd.read_parquet(p)
                cols_present = df.columns.tolist()

            t_min, t_max, t_src = _extract_time_range(df)

            if require_datetime and (t_min is None or t_max is None):
                # skip files that don't have usable timestamps
                continue

            rows.append(
                {
                    "path": str(p),
                    "rows": int(len(df)),
                    "t_min": t_min,
                    "t_max": t_max,
                    "t_src": t_src,
                    "cols": ",".join(cols_present),
                    "bytes": int(p.stat().st_size),
                }
            )
        except Exception as e:
            rows.append({"path": str(p), "error": repr(e)})

    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Inventory parquet files (rows, time coverage, schema)."
    )
    ap.add_argument(
        "--parquet-dir",
        required=True,
        help="Directory to scan recursively for parquet files.",
    )
    ap.add_argument(
        "--out", default="outputs/data_inventory.csv", help="Output CSV path."
    )
    ap.add_argument(
        "--pattern",
        default=None,
        help="Optional glob pattern to restrict files, e.g. '*_RTH.parquet' or 'by_day/**/*.parquet'.",
    )
    ap.add_argument(
        "--require-datetime",
        action="store_true",
        help="If set, skip files that do not have a usable datetime axis (DatetimeIndex or timestamp column).",
    )
    args = ap.parse_args()

    parquet_dir = Path(args.parquet_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    inv = scan_parquet_dir(
        parquet_dir, pattern=args.pattern, require_datetime=args.require_datetime
    )

    # Derive covered dates if timestamps exist (tz-safe: already UTC)
    if not inv.empty and "t_min" in inv.columns and "t_max" in inv.columns:
        ok = inv.dropna(subset=["t_min", "t_max"]).copy()
        if not ok.empty:
            ok["date_min"] = pd.to_datetime(ok["t_min"], utc=True).dt.date
            ok["date_max"] = pd.to_datetime(ok["t_max"], utc=True).dt.date
            # merge back
            inv = inv.merge(ok[["path", "date_min", "date_max"]], on="path", how="left")

    inv.to_csv(out, index=False)
    print(f"Wrote inventory: {out}")
    print(inv.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
