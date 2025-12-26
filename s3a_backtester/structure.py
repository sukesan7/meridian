"""
Market Structure Analysis
-------------------------
Implements vector-based logic for identifying higher-order market structures.
Includes 5-minute trend detection, micro-swing identification, and candlestick patterns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, cast

import numpy as np
import pandas as pd


@dataclass
class Trend5mConfig:
    """
    Configuration for 5-minute trend detection logic.
    """

    lookback: int = 3
    high_col: str = "high"
    low_col: str = "low"
    close_col: str = "close"
    vwap_col: str = "vwap"


def _trend_for_day(
    day: pd.DataFrame, cfg: Trend5mConfig
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute trend direction, HH/HL status, and LH/LL status for a single day."""
    h = day[cfg.high_col]
    lo = day[cfg.low_col]

    prev_high = h.shift(1).rolling(cfg.lookback, min_periods=cfg.lookback).max()
    prev_low = lo.shift(1).rolling(cfg.lookback, min_periods=cfg.lookback).min()

    hh = h > prev_high
    hl = lo > prev_low
    lh = h < prev_high
    ll = lo < prev_low

    up_mask = hh & hl
    down_mask = lh & ll

    trend_vals = np.zeros(len(day), dtype=int)

    for i in range(len(day)):
        if i == 0:
            trend_vals[i] = 0
            continue

        if up_mask.iloc[i] and not down_mask.iloc[i]:
            trend_vals[i] = 1
        elif down_mask.iloc[i] and not up_mask.iloc[i]:
            trend_vals[i] = -1
        else:
            trend_vals[i] = trend_vals[i - 1]

    trend = pd.Series(trend_vals, index=day.index, name="trend_5m")
    hh_hl = pd.Series(up_mask.to_numpy(), index=day.index, name="trend_hh_hl")
    lh_ll = pd.Series(down_mask.to_numpy(), index=day.index, name="trend_lh_ll")
    return trend, hh_hl, lh_ll


def trend_5m(df_5m: pd.DataFrame, cfg: Optional[Trend5mConfig] = None) -> pd.DataFrame:
    """
    Calculate 5-minute trend direction over the provided OHLCV data.
    """
    if cfg is None:
        cfg = Trend5mConfig()

    out = df_5m.copy()

    trend = pd.Series(0, index=out.index, name="trend_5m")
    hh_hl = pd.Series(False, index=out.index, name="trend_hh_hl")
    lh_ll = pd.Series(False, index=out.index, name="trend_lh_ll")

    idx = cast(pd.DatetimeIndex, out.index)

    for _, day in out.groupby(idx.normalize()):
        day_trend, day_hh_hl, day_lh_ll = _trend_for_day(day, cfg)
        trend.loc[day.index] = day_trend
        hh_hl.loc[day.index] = day_hh_hl
        lh_ll.loc[day.index] = day_lh_ll

    out["trend_5m"] = trend
    out["trend_hh_hl"] = hh_hl
    out["trend_lh_ll"] = lh_ll

    if cfg.vwap_col in out.columns:
        vwap = out[cfg.vwap_col]
        close = out[cfg.close_col]

        side_ok = np.where(
            trend > 0,
            close >= vwap,
            np.where(trend < 0, close <= vwap, False),
        )
        out["trend_vwap_ok"] = side_ok.astype(bool)
    else:
        out["trend_vwap_ok"] = False

    return out


def micro_swing_break(
    df: pd.DataFrame,
    swing_high_col: str = "swing_high",
    swing_low_col: str = "swing_low",
) -> pd.DataFrame:
    """
    Identify micro-structure breaks (BOS) and engulfing candles on 1-minute data.
    """
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"micro_swing_break: missing columns: {sorted(missing)}")

    high = df["high"].to_numpy(dtype="float64")
    low = df["low"].to_numpy(dtype="float64")

    swing_high = (
        df.get(swing_high_col, pd.Series(False, index=df.index))
        .fillna(False)
        .to_numpy(dtype="bool")
    )
    swing_low = (
        df.get(swing_low_col, pd.Series(False, index=df.index))
        .fillna(False)
        .to_numpy(dtype="bool")
    )

    n = len(df)
    micro_dir = np.zeros(n, dtype="int8")

    last_swing_high = np.nan
    last_swing_low = np.nan
    high_broken = False
    low_broken = False

    for i in range(n):
        if swing_high[i]:
            last_swing_high = high[i]
            high_broken = False

        if swing_low[i]:
            last_swing_low = low[i]
            low_broken = False

        broke_up = (
            not np.isnan(last_swing_high)
            and not high_broken
            and high[i] > last_swing_high
        )
        broke_down = (
            not np.isnan(last_swing_low) and not low_broken and low[i] < last_swing_low
        )

        if broke_up and not broke_down:
            micro_dir[i] = 1
            high_broken = True
        elif broke_down and not broke_up:
            micro_dir[i] = -1
            low_broken = True

    op = df["open"]
    cl = df["close"]
    prev_op = op.shift(1)
    prev_cl = cl.shift(1)

    has_prev = prev_op.notna() & prev_cl.notna()

    bull = (
        has_prev & (prev_cl < prev_op) & (cl > op) & (op <= prev_cl) & (cl >= prev_op)
    )

    bear = (
        has_prev & (prev_cl > prev_op) & (cl < op) & (op >= prev_cl) & (cl <= prev_op)
    )

    engulf_dir = np.where(bull, 1, np.where(bear, -1, 0)).astype("int8")

    out = pd.DataFrame(
        {
            "micro_break_dir": micro_dir,
            "engulf_dir": engulf_dir,
        },
        index=df.index,
    )
    return out
