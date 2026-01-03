"""
Data IO Layer
-------------
Robust loading, validation, and normalization of OHLCV data.
Supports CSV/Parquet formats, timezone localization, and strict RTH slicing.
"""

from __future__ import annotations
from typing import cast, Any
from pandas.api.types import DatetimeTZDtype
from datetime import time
import pandas as pd
import logging

REQ_COLS = ("open", "high", "low", "close", "volume")

logger = logging.getLogger(__name__)


def validate_rth_completeness(df: pd.DataFrame) -> None:
    """
    Audits the DataFrame to ensure every trading session has exactly 390 minutes
    (09:30 - 16:00 ET). Logs warnings for any incomplete days.
    """
    if df.empty:
        return

    idx = cast(pd.DatetimeIndex, df.index)
    daily_counts = df.groupby(idx.date).size()

    incomplete_days = daily_counts[daily_counts != 390]

    if not incomplete_days.empty:
        details = []
        for date_val, count in incomplete_days.head(3).items():
            details.append(f"{date_val}: {count} bars")

        remaining = len(incomplete_days) - 3
        if remaining > 0:
            details.append(f"... and {remaining} more.")

        msg = (
            f"Data Contract Violation: Found {len(incomplete_days)} sessions with != 390 bars. "
            f"Examples: {', '.join(details)}"
        )
        raise ValueError(msg)


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
    """
    Filters data for US Regular Trading Hours (09:30 - 16:00 ET).
    Automatically validates data completeness post-slice.
    """
    df_rth = df.between_time("09:30", "16:00", inclusive="both")
    idx = cast(pd.DatetimeIndex, df_rth.index)
    df_rth = df_rth[idx.time != time(16, 0)]
    validate_rth_completeness(df_rth)
    return cast(pd.DataFrame, df_rth)


def resample(df1: pd.DataFrame, rule: str = "5min") -> pd.DataFrame:
    """Resamples 1-minute data to higher timeframes with 'right' labeling."""
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return (
        df1.resample(rule, label="right", closed="right")
        .agg(cast(Any, agg))
        .dropna(how="all")
    )
