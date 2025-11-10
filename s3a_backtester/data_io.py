from __future__ import annotations
import pandas as pd


def load_minute_df(path: str, tz: str = "America/New_York") -> pd.DataFrame:
    """
    Load 1-minute OHLCV from CSV or Parquet.
    - Accepts a 'timestamp' column or first column as datetime.
    - Returns tz-aware DatetimeIndex localized to ET.
    """
    if path.lower().endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    if "timestamp" in df.columns:
        idx = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.drop(columns=["timestamp"])
    else:
        # assume first column is timestamp-like if not explicitly named
        idx = pd.to_datetime(df.iloc[:, 0], utc=True, errors="coerce")
        df = df.iloc[:, 1:]

    df.index = idx.tz_convert(tz)
    return df.sort_index()


def slice_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Keep US RTH 09:30–16:00 ET (inclusive on close)."""
    return df.between_time("09:30", "16:00", include_end=True)


def resample(df1: pd.DataFrame, rule: str = "5T") -> pd.DataFrame:
    """
    Resample to higher TF using label='right', closed='right' to avoid peeking.
    Returns completed bars only.
    """
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return df1.resample(rule, label="right", closed="right").agg(agg).dropna(how="all")
