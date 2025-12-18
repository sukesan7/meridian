# Data Input / Output
# Achieve a clean time-series dataframe
from __future__ import annotations
from pandas.api.types import DatetimeTZDtype
import pandas as pd

# Set required columns
REQ_COLS = ("open", "high", "low", "close", "volume")


def load_minute_df(path: str, tz: str = "America/New_York") -> pd.DataFrame:
    """
    Load 1-minute OHLCV (CSV or Parquet) and normalize:

    - Returns tz-aware DatetimeIndex in `tz` (default ET).
    - Accepts timestamp either as a column (timestamp/datetime/ts_event/etc) OR as the index.
    - Requires open, high, low, close, volume.
    """

    if path.lower().endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    df.columns = [str(c).strip().lower() for c in df.columns]

    # 1) If index is already datetime, use it
    if isinstance(df.index, pd.DatetimeIndex):
        idx = df.index
    else:
        # 2) Otherwise find a datetime column
        dt_col = None
        for c in ("ts_event", "datetime", "timestamp", "time", "date"):
            if c in df.columns:
                dt_col = c
                break
        if dt_col is None:
            raise ValueError(
                f"load_minute_df: could not find datetime column in {path!r}; "
                f"got columns={list(df.columns)}"
            )

        s = df[dt_col]

        # Parse with minimal ambiguity:
        # - If dtype already tz-aware -> keep
        # - If strings look like UTC/offset -> parse as UTC
        # - Else parse naive and localize to `tz`
        if isinstance(s.dtype, DatetimeTZDtype):
            idx = pd.DatetimeIndex(s)
        else:
            s_str = s.astype(str)
            looks_tz = (
                s_str.str.endswith("Z").any()
                or s_str.str.contains(r"[+-]\d{2}:\d{2}", regex=True).any()
            )
            if looks_tz:
                idx = pd.DatetimeIndex(pd.to_datetime(s, errors="coerce", utc=True))
            else:
                idx = pd.DatetimeIndex(pd.to_datetime(s, errors="coerce"))

        if idx.isna().any():
            raise ValueError(
                f"load_minute_df: datetime parse failed for {dt_col!r} in {path!r}"
            )

        df = df.drop(columns=[dt_col])

    # Convert/localize timezone
    if idx.tz is None:
        idx = idx.tz_localize(tz)
    else:
        idx = idx.tz_convert(tz)

    df.index = idx

    # Enforce OHLCV contract
    missing = set(REQ_COLS) - set(df.columns)
    if missing:
        raise ValueError(
            f"load_minute_df: missing required OHLCV columns {missing} in {path!r}; "
            f"got columns={list(df.columns)}"
        )

    # Clean index
    df = df[~df.index.duplicated(keep="last")].sort_index()
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
