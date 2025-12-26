"""
Feature Engineering
-------------------
Computes core quantitative features for the strategy, including:
- Session Reference Levels (OR, PDH, PDL)
- VWAP Bands and standard deviations
- Volatility measures (ATR15)
- Swing detection
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import time
from typing import Any, cast


def compute_session_refs(df1: pd.DataFrame) -> pd.DataFrame:
    """Calculates session-specific reference levels like OR High/Low."""
    out = df1.copy()

    for col in ["or_high", "or_low", "or_height", "pdh", "pdl", "onh", "onl"]:
        if col not in out.columns:
            out[col] = np.nan

    idx = cast(pd.DatetimeIndex, out.index)
    grouped = out.groupby(idx.date, sort=False)

    or_start = time(9, 30)
    or_end = time(9, 35)

    for _, day in grouped:
        or_slice = day.between_time(or_start, or_end, inclusive="left")
        if or_slice.empty:
            continue

        or_high = or_slice["high"].max()
        or_low = or_slice["low"].min()
        or_height = or_high - or_low

        mask = out.index.isin(day.index)
        out.loc[mask, "or_high"] = or_high
        out.loc[mask, "or_low"] = or_low
        out.loc[mask, "or_height"] = or_height

    return out


def compute_session_vwap_bands(
    df1: pd.DataFrame, use_close: bool = True
) -> pd.DataFrame:
    """Computes intraday VWAP and standard deviation bands."""
    if "close" not in df1.columns:
        raise ValueError(f"compute_session_vwap_bands: columns={list(df1.columns)}")
    out = df1.copy()

    price = (
        out["close"] if use_close else (out["high"] + out["low"] + out["close"]) / 3.0
    )
    vol = out.get("volume", pd.Series(1.0, index=out.index)).astype(float)

    vwap = pd.Series(index=out.index, dtype="float64")
    sd = pd.Series(index=out.index, dtype="float64")

    idx = cast(pd.DatetimeIndex, out.index)
    grouped = out.groupby(idx.date, sort=False)
    or_start = time(9, 30)

    for _, day in grouped:
        day_idx = cast(pd.DatetimeIndex, day.index)
        day = day[day_idx.time >= or_start]
        if day.empty:
            continue

        p = price.loc[day.index]
        v = vol.loc[day.index]

        pv = (p * v).cumsum()
        cv = v.cumsum()

        vwap_day = pv / cv
        sd_day = p.expanding().std().fillna(0.0)

        vwap.loc[day.index] = vwap_day
        sd.loc[day.index] = sd_day

    out["vwap"] = vwap
    out["vwap_sd"] = sd
    out["band_p1"] = vwap + sd
    out["band_m1"] = vwap - sd
    out["band_p2"] = vwap + 2 * sd
    out["band_m2"] = vwap - 2 * sd

    return out


def compute_atr15(df1: pd.DataFrame, window: int = 15) -> pd.Series:
    """Computes a 15-period Average True Range on 1-minute data."""
    required = {"high", "low", "close"}
    missing = required - set(df1.columns)
    if missing:
        raise KeyError(f"Missing columns for ATR calc: {missing}")

    high = df1["high"].astype("float64")
    low = df1["low"].astype("float64")
    close = df1["close"].astype("float64")

    prev_close = close.shift(1)

    tr_components = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    )
    tr = tr_components.max(axis=1)

    atr = tr.rolling(window=window, min_periods=1).mean()
    atr.name = "atr15"
    return atr


def find_swings_1m(
    df1: pd.DataFrame,
    lb: int = 2,
    rb: int = 2,
    high_col: str = "high",
    low_col: str = "low",
) -> pd.DataFrame:
    """Identifies fractal swing points using a rolling window approach."""
    if lb < 1 or rb < 1:
        raise ValueError("lb and rb must be >= 1")

    df = df1.copy()
    df["swing_high"] = False
    df["swing_low"] = False

    idx = df.index
    # Explicit type annotation to handle Union type assignment
    day_keys: Any

    if isinstance(idx, pd.DatetimeIndex):
        day_keys = idx.normalize()
    else:
        dt = pd.to_datetime(idx, errors="coerce")
        if dt.isna().to_numpy().any():
            day_keys = pd.Series(0, index=idx)
        else:
            day_keys = dt.normalize()

    for _, day_df in df.groupby(day_keys):
        n = len(day_df)
        if n == 0:
            continue

        highs = day_df[high_col].to_numpy()
        lows = day_df[low_col].to_numpy()

        swing_high = np.zeros(n, dtype=bool)
        swing_low = np.zeros(n, dtype=bool)

        for i in range(lb, n - rb):
            hi = highs[i]
            lo = lows[i]

            if np.all(hi > highs[i - lb : i]) and np.all(
                hi >= highs[i + 1 : i + rb + 1]
            ):
                swing_high[i] = True

            if np.all(lo < lows[i - lb : i]) and np.all(lo <= lows[i + 1 : i + rb + 1]):
                swing_low[i] = True

        df.loc[day_df.index, "swing_high"] = swing_high
        df.loc[day_df.index, "swing_low"] = swing_low

    return df
