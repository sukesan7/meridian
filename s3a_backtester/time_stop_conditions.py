# Time Stop Conditions for the Engine
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TimeStopConditionSeries:
    vwap_side_ok: Optional[pd.Series]
    trend_ok: Optional[pd.Series]
    sigma_ok: Optional[pd.Series]
    dd_ok: Optional[pd.Series]


def _infer_trend_ok(session_df: pd.DataFrame, side_sign: int) -> Optional[pd.Series]:
    candidates = [
        "trend_dir_5m",
        "trend5_dir",
        "trend_5m_dir",
        "trend_dir",
        "trend5",
        "trend_5m",
    ]
    col = next((c for c in candidates if c in session_df.columns), None)
    if col is None:
        return None

    s = session_df[col]

    # Numeric convention (+1 bull, -1 bear)
    if pd.api.types.is_numeric_dtype(s):
        return s.astype("float").fillna(0).astype(int).eq(side_sign)

    # String convention
    vals = s.astype(str).str.lower()
    if side_sign == 1:
        return vals.isin({"bull", "up", "long", "uptrend"})
    return vals.isin({"bear", "down", "short", "downtrend"})


def build_time_stop_condition_series(
    session_df: pd.DataFrame,
    entry_idx: int,
    side_sign: int,
    entry_price: float,
    stop_price: float,
) -> TimeStopConditionSeries:
    """
    Build the 4 boolean series used by time-stop extension:

      - VWAP side intact:
          long: close >= vwap
          short: close <= vwap

      - 5-min trend intact: inferred from available trend column.

      - No close beyond ±1σ against:
          long: close >= vwap_1d
          short: close <= vwap_1u

      - DD <= 0.5R:
          MAE since entry in R-units <= 0.5.
    """
    if session_df.empty:
        return TimeStopConditionSeries(None, None, None, None)

    if side_sign not in (1, -1):
        raise ValueError(f"side_sign must be +1 or -1, got {side_sign!r}")

    # Safety
    entry_idx = int(entry_idx)
    entry_idx = max(0, min(entry_idx, len(session_df) - 1))

    risk_per_unit = float(abs(entry_price - stop_price))
    if not np.isfinite(risk_per_unit) or risk_per_unit <= 0:
        # Degenerate risk -> can't compute MAE in R
        dd_ok = None
    else:
        dd_ok = pd.Series(True, index=session_df.index)
        if "high" in session_df.columns and "low" in session_df.columns:
            if side_sign == 1:
                run_min = session_df["low"].iloc[entry_idx:].cummin()
                mae_r = (entry_price - run_min) / risk_per_unit
            else:
                run_max = session_df["high"].iloc[entry_idx:].cummax()
                mae_r = (run_max - entry_price) / risk_per_unit

            dd_ok.iloc[entry_idx:] = mae_r <= 0.5
        else:
            dd_ok = None

    # VWAP side intact
    vwap_side_ok = None
    if "close" in session_df.columns and "vwap" in session_df.columns:
        if side_sign == 1:
            vwap_side_ok = session_df["close"] >= session_df["vwap"]
        else:
            vwap_side_ok = session_df["close"] <= session_df["vwap"]

    # ±1σ against rule
    sigma_ok = None
    if "close" in session_df.columns:
        if side_sign == 1 and "vwap_1d" in session_df.columns:
            sigma_ok = session_df["close"] >= session_df["vwap_1d"]
        elif side_sign == -1 and "vwap_1u" in session_df.columns:
            sigma_ok = session_df["close"] <= session_df["vwap_1u"]

    # Trend
    trend_ok = _infer_trend_ok(session_df, side_sign)

    return TimeStopConditionSeries(
        vwap_side_ok=vwap_side_ok,
        trend_ok=trend_ok,
        sigma_ok=sigma_ok,
        dd_ok=dd_ok,
    )
