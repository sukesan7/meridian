from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class Trend5mConfig:
    """
    Configuration for 5-minute trend detection.

    Attributes
    ----------
    lookback : int
        Number of prior 5-minute bars to use when comparing highs/lows.
        Higher = slower, smoother trend. Must be >= 1.
    high_col, low_col, close_col : str
        Column names for OHLC data.
    vwap_col : str
        Column name for session VWAP. If missing in the DataFrame,
        the VWAP-side check will be skipped.
    """

    lookback: int = 3
    high_col: str = "high"
    low_col: str = "low"
    close_col: str = "close"
    vwap_col: str = "vwap"


# ------------------------------------
# Compute intraday HH/HL vs LH/LL trend for a singular trading day
# ------------------------------------
def _trend_for_day(
    day: pd.DataFrame, cfg: Trend5mConfig
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Returns
    -------
    trend : Series[int]
        +1 uptrend, -1 downtrend, 0 neutral.
    hh_hl : Series[bool]
        True on bars where we see HH & HL vs the rolling window.
    lh_ll : Series[bool]
        True on bars where we see LH & LL vs the rolling window.
    """
    h = day[cfg.high_col]
    lo = day[cfg.low_col]

    # Previous highs/lows based only on *past* bars (no look-ahead)
    prev_high = h.shift(1).rolling(cfg.lookback, min_periods=cfg.lookback).max()
    prev_low = lo.shift(1).rolling(cfg.lookback, min_periods=cfg.lookback).min()

    # Structural comparisons
    hh = h > prev_high  # higher high
    hl = lo > prev_low  # higher low
    lh = h < prev_high  # lower high
    ll = lo < prev_low  # lower low

    up_mask = hh & hl
    down_mask = lh & ll

    trend_vals = np.zeros(len(day), dtype=int)

    for i, idx in enumerate(day.index):
        if i == 0:
            trend_vals[i] = 0
            continue

        if up_mask.iloc[i] and not down_mask.iloc[i]:
            trend_vals[i] = 1
        elif down_mask.iloc[i] and not up_mask.iloc[i]:
            trend_vals[i] = -1
        else:
            # carry the prior state when structure is ambiguous
            trend_vals[i] = trend_vals[i - 1]

    trend = pd.Series(trend_vals, index=day.index, name="trend_5m")
    hh_hl = pd.Series(up_mask.to_numpy(), index=day.index, name="trend_hh_hl")
    lh_ll = pd.Series(down_mask.to_numpy(), index=day.index, name="trend_lh_ll")
    return trend, hh_hl, lh_ll


# ------------------------------------
# 5-minute bar Trend Direction
# ------------------------------------
def trend_5m(df_5m: pd.DataFrame, cfg: Optional[Trend5mConfig] = None) -> pd.DataFrame:
    """
    Parameters
    ----------
    df_5m : DataFrame
        5-minute OHLCV data, already RTH-sliced (e.g. 09:30-16:00 ET),
        index is tz-aware datetime. Must contain columns for high/low/close.
        If a VWAP column is present (cfg.vwap_col), we also add a VWAP-side flag.
    cfg : Trend5mConfig, optional
        Optional configuration; if omitted, uses Trend5mConfig() defaults.

    Returns
    -------
    DataFrame
        A copy of ``df_5m`` with extra columns:

        - ``trend_5m``        : +1 uptrend, -1 downtrend, 0 neutral.
        - ``trend_hh_hl``     : True where bar forms HH&HL vs rolling window.
        - ``trend_lh_ll``     : True where bar forms LH&LL vs rolling window.
        - ``trend_vwap_ok``   : True when bar closes on the "correct" side of
                                VWAP for the current trend (False if no VWAP).
    """
    if cfg is None:
        cfg = Trend5mConfig()

    out = df_5m.copy()

    trend = pd.Series(0, index=out.index, name="trend_5m")
    hh_hl = pd.Series(False, index=out.index, name="trend_hh_hl")
    lh_ll = pd.Series(False, index=out.index, name="trend_lh_ll")

    # Work per trading day to avoid look-through across sessions
    for _, day in out.groupby(out.index.normalize()):
        day_trend, day_hh_hl, day_lh_ll = _trend_for_day(day, cfg)
        trend.loc[day.index] = day_trend
        hh_hl.loc[day.index] = day_hh_hl
        lh_ll.loc[day.index] = day_lh_ll

    out["trend_5m"] = trend
    out["trend_hh_hl"] = hh_hl
    out["trend_lh_ll"] = lh_ll

    # VWAP-side check: only if VWAP column is present
    if cfg.vwap_col in out.columns:
        vwap = out[cfg.vwap_col]
        close = out[cfg.close_col]

        # Correct side: uptrend → close >= vwap; downtrend → close <= vwap
        side_ok = np.where(
            trend > 0,
            close >= vwap,
            np.where(trend < 0, close <= vwap, False),
        )
        out["trend_vwap_ok"] = side_ok.astype(bool)
    else:
        # If we don't have VWAP yet, just set False; engine can decide how to use it
        out["trend_vwap_ok"] = False

    return out


# ------------------------------------
# 1-minute Bar Tagging (engulfing candle detection)
# ------------------------------------
def micro_swing_break(
    df: pd.DataFrame,
    swing_high_col: str = "swing_high",
    swing_low_col: str = "swing_low",
) -> pd.DataFrame:
    """
    Parameters
    ----------
    df :
        1-minute OHLCV dataframe. Must contain at least:
        - 'open', 'high', 'low', 'close'
        - boolean swing marker columns:
          * swing_high_col (default 'swing_high')
          * swing_low_col  (default 'swing_low')
        Typically these come from `features.find_swings_1m`.

    Returns
    -------
    out : pd.DataFrame
        Index matches `df.index` with columns:

        - ``micro_break_dir`` : int in {-1, 0, 1}
            +1  → current bar breaks the most recent swing high
            -1  → current bar breaks the most recent swing low
             0  → no break

        - ``engulf_dir`` : int in {-1, 0, 1}
            +1  → bullish engulf vs previous bar
            -1  → bearish engulf vs previous bar
             0  → no engulf

    Notes
    -----
    - No look-ahead: only information up to the current bar is used.
    - If both an up-break and down-break would trigger on the same bar
      (pathological), up-break wins; this is extremely rare on 1-min data.
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
    high_broken = False  # check if current swing high is broken
    low_broken = False  # check if current swing low is broken

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

    # -------- Engulf detection (body engulf of previous bar) --------
    op = df["open"]
    cl = df["close"]
    prev_op = op.shift(1)
    prev_cl = cl.shift(1)

    # Previous bar must exist
    has_prev = prev_op.notna() & prev_cl.notna()

    # Bullish engulf: previous red, current green, current body fully contains previous body
    bull = (
        has_prev & (prev_cl < prev_op) & (cl > op) & (op <= prev_cl) & (cl >= prev_op)
    )

    # Bearish engulf: previous green, current red, current body fully contains previous body
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
