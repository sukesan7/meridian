"""
Data IO Layer
-------------
Robust loading, validation, and normalization of OHLCV data.
Supports CSV/Parquet formats, timezone localization, and strict RTH slicing.
"""

from __future__ import annotations
from typing import cast, Any
from pandas.api.types import DatetimeTZDtype
import pandas as pd

REQ_COLS = ("open", "high", "low", "close", "volume")


def load_minute_df(path: str, tz: str = "America/New_York") -> pd.DataFrame:
    """Loads a 1-minute OHLCV file, ensuring correct indexing and required columns."""
    if path.lower().endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    df.columns = [str(c).strip().lower() for c in df.columns]

    if isinstance(df.index, pd.DatetimeIndex):
        idx = df.index
    else:
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

        if bool(pd.isna(idx).any()):
            raise ValueError(
                f"load_minute_df: datetime parse failed for {dt_col!r} in {path!r}"
            )

        df = df.drop(columns=[dt_col])

    if idx.tz is None:
        idx = idx.tz_localize(tz)
    else:
        idx = idx.tz_convert(tz)

    df.index = idx

    missing = set(REQ_COLS) - set(df.columns)
    if missing:
        raise ValueError(
            f"load_minute_df: missing required OHLCV columns {missing} in {path!r}; "
            f"got columns={list(df.columns)}"
        )

    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def slice_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Filters data for US Regular Trading Hours (09:30 - 16:00 ET)."""
    return df.between_time("09:30", "16:00", inclusive="both")


def resample(df1: pd.DataFrame, rule: str = "5min") -> pd.DataFrame:
    """Resamples 1-minute data to higher timeframes with 'right' labeling."""
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return cast(
        pd.DataFrame,
        df1.resample(rule, label="right", closed="right")
        .agg(cast(Any, agg))
        .dropna(how="all"),
    )
