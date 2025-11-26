# Data Input / Output
# Achieve a clean time-series dataframe
from __future__ import annotations
import pandas as pd

# Set required columns
REQ_COLS = ("open", "high", "low", "close", "volume")


def load_minute_df(path: str, tz: str = "America/New_York") -> pd.DataFrame:
    """
    Load a 1-minute OHLCV file (CSV or Parquet) and normalize schema.

    - Returns a tz-aware DatetimeIndex in `tz` (default ET).
    - Forces lowercase, stripped column names.
    - Requires: open, high, low, close, volume.
    """
    # --- read file ---
    if path.lower().endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    # --- normalize column names to lowercase + strip whitespace ---
    df.columns = [str(c).strip().lower() for c in df.columns]

    # --- pick datetime column ---
    dt_col = None
    for c in ("datetime", "timestamp", "time", "date"):
        if c in df.columns:
            dt_col = c
            break

    if dt_col is None:
        raise ValueError(
            f"load_minute_df: could not find datetime column in {path!r}; "
            f"got columns={list(df.columns)}"
        )

    # --- parse to DatetimeIndex and convert/localize to tz ---
    idx = pd.to_datetime(df[dt_col], errors="coerce")
    if idx.isna().any():
        raise ValueError(
            f"load_minute_df: datetime parse failed for column {dt_col!r} in {path!r}"
        )

    idx = pd.DatetimeIndex(idx)
    if idx.tz is None:
        # assume naive timestamps are already in tz (ET)
        idx = idx.tz_localize(tz)
    else:
        idx = idx.tz_convert(tz)

    df.index = idx

    # drop the original datetime column if still present
    if dt_col in df.columns:
        df = df.drop(columns=[dt_col])

    # --- enforce OHLCV contract ---
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"load_minute_df: missing required OHLCV columns {missing} in {path!r}; "
            f"got columns={list(df.columns)}"
        )

    # final clean-up
    df = df.sort_index()
    return df


# Regular Trading Hours
def slice_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Keep US RTH 09:30–16:00 ET (inclusive)."""
    return df.between_time("09:30", "16:00", inclusive="both")


# Resample the data
def resample(df1: pd.DataFrame, rule: str = "5min") -> pd.DataFrame:
    """Right-label/right-closed resample (no peeking)."""
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return df1.resample(rule, label="right", closed="right").agg(agg).dropna(how="all")
