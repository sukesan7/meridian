# Data Input / Output
# Achieve a clean time-series dataframe
from __future__ import annotations
import pandas as pd

# Set required columns
REQ_COLS = ("open", "high", "low", "close", "volume")


def load_minute_df(path: str, tz: str = "America/New_York") -> pd.DataFrame:
    # Load 1-minute OHLCV data, parse UTC timestamp, return the timezone aware ET index with strict schema
    df = (
        pd.read_parquet(path)
        if path.lower().endswith(".parquet")
        else pd.read_csv(path)
    )

    # Detect the timestamp column
    ts = None
    for cand in ("timestamp", "datetime", "time", "date"):
        if cand in df.columns:
            ts = pd.to_datetime(df[cand], utc=True, errors="coerce")
            df = df.drop(columns=[cand])
            break
    if ts is None:
        ts = pd.to_datetime(df.iloc[:, 0], utc=True, errors="coerce")
        df = df.iloc[:, 1:]
    if ts.isna().any():
        raise ValueError(f"Invalid timestamps: {int(ts.isna().sum())} rows")

    # Timezone-convert on a DateTimeIndex
    idx = pd.DatetimeIndex(ts).tz_convert(tz)
    df.index = idx

    # Strict Schema
    missing = [c for c in REQ_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    # Sanity Check
    df = df.sort_index()
    if not df.index.is_monotonic_increasing:
        raise ValueError("Index not sorted ascending")

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
