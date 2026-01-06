"""
Feature Engineering
-------------------
Computes core quantitative features for the strategy, including:
- Session Reference Levels (OR, PDH, PDL)
- VWAP Bands and standard deviations
- Volatility measures (ATR15)
- Swing detection (Strictly Delayed/Confirmed)
"""

from __future__ import annotations

from datetime import time
from typing import Any, cast

import numpy as np
import pandas as pd


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

        day_idx = cast(pd.DatetimeIndex, day.index)
        valid_indices = day_idx[day_idx.time >= or_end]

        if not valid_indices.empty:
            out.loc[valid_indices, "or_high"] = or_high
            out.loc[valid_indices, "or_low"] = or_low
            out.loc[valid_indices, "or_height"] = or_height

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
    """
    Identifies fractal swing points using a STRICTLY DELAYED (Past-Only) approach.

    A swing is only marked at index `t` if the pivot at `t - rb` is confirmed.
    This eliminates look-ahead bias.

    Outputs:
    - swing_high_confirmed (bool): Event trigger at confirmation time.
    - swing_low_confirmed (bool): Event trigger at confirmation time.
    - last_swing_high_price (float): Forward-filled price of the last confirmed pivot.
    - last_swing_low_price (float): Forward-filled price of the last confirmed pivot.
    """
    if lb < 1 or rb < 1:
        raise ValueError("lb and rb must be >= 1")

    df = df1.copy()

    df["swing_high_confirmed"] = False
    df["swing_low_confirmed"] = False
    df["last_swing_high_price"] = np.nan
    df["last_swing_low_price"] = np.nan

    idx = df.index
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
        if n < lb + rb + 1:
            continue

        highs = day_df[high_col].to_numpy()
        lows = day_df[low_col].to_numpy()

        day_indices = day_df.index

        s_high_conf = np.zeros(n, dtype=bool)
        s_low_conf = np.zeros(n, dtype=bool)

        s_last_high = np.full(n, np.nan, dtype=np.float64)
        s_last_low = np.full(n, np.nan, dtype=np.float64)

        for i in range(lb + rb, n):
            pivot_idx = i - rb

            pivot_h = highs[pivot_idx]

            left_side_h = highs[pivot_idx - lb : pivot_idx]
            right_side_h = highs[pivot_idx + 1 : pivot_idx + rb + 1]

            if np.all(pivot_h > left_side_h) and np.all(pivot_h >= right_side_h):
                s_high_conf[i] = True
                s_last_high[i] = pivot_h

            pivot_l = lows[pivot_idx]
            left_side_l = lows[pivot_idx - lb : pivot_idx]
            right_side_l = lows[pivot_idx + 1 : pivot_idx + rb + 1]

            if np.all(pivot_l < left_side_l) and np.all(pivot_l <= right_side_l):
                s_low_conf[i] = True
                s_last_low[i] = pivot_l

        df.loc[day_indices, "swing_high_confirmed"] = s_high_conf
        df.loc[day_indices, "swing_low_confirmed"] = s_low_conf

        temp_high = pd.Series(s_last_high, index=day_indices)
        temp_low = pd.Series(s_last_low, index=day_indices)

        df.loc[day_indices, "last_swing_high_price"] = temp_high.ffill()
        df.loc[day_indices, "last_swing_low_price"] = temp_low.ffill()

    return df
