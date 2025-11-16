from __future__ import annotations
import pandas as pd
import numpy as np


def compute_session_refs(df1: pd.DataFrame) -> pd.DataFrame:
    """
    OR (09:30-09:35 left-inclusive), plus PDH/PDL carry-forward from prior RTH session.
    """
    out = pd.DataFrame(index=df1.index)
    out["or_high"] = np.nan
    out["or_low"] = np.nan
    out["or_height"] = np.nan

    # OR per calendar day
    for _, daydf in df1.groupby(df1.index.date, sort=False):
        or_slice = daydf.between_time("09:30", "09:35", inclusive="left")
        if not or_slice.empty:
            hi, lo = or_slice["high"].max(), or_slice["low"].min()
            out.loc[or_slice.index, "or_high"] = hi
            out.loc[or_slice.index, "or_low"] = lo
            out.loc[or_slice.index, "or_height"] = hi - lo

    # PDH/PDL from prior RTH session
    rth = df1.between_time("09:30", "16:00", inclusive="both")
    sess_hi = rth["high"].groupby(rth.index.date).max()
    sess_lo = rth["low"].groupby(rth.index.date).min()
    pdh_map = sess_hi.shift(1)  # prior session’s high
    pdl_map = sess_lo.shift(1)  # prior session’s low

    # broadcast back to minutes
    dates = pd.Series(df1.index.date, index=df1.index)
    out["pdh"] = dates.map(pdh_map).astype(float)
    out["pdl"] = dates.map(pdl_map).astype(float)

    # placeholders for ONH/ONL if you want later
    out["onh"] = np.nan
    out["onl"] = np.nan
    return out


def compute_session_vwap_bands(
    df1: pd.DataFrame, use_close: bool = True
) -> pd.DataFrame:
    price = (
        df1["close"] if use_close else (df1["high"] + df1["low"] + df1["close"]) / 3.0
    )
    vol = df1.get("volume", pd.Series(1.0, index=df1.index)).astype(float)
    parts = []
    for _, day in df1.groupby(df1.index.date, sort=False):
        day = day[day.index.time >= pd.Timestamp("09:30").time()]
        if day.empty:
            continue
        pv = (price.loc[day.index] * vol.loc[day.index]).cumsum()
        cv = vol.loc[day.index].cumsum()
        vwap = pv / cv
        sd = price.loc[day.index].expanding().std().fillna(0.0)
        tmp = pd.DataFrame(index=day.index)
        tmp["vwap"] = vwap
        tmp["vwap_sd"] = sd
        tmp["band_p1"] = vwap + sd
        tmp["band_m1"] = vwap - sd
        tmp["band_p2"] = vwap + 2 * sd
        tmp["band_m2"] = vwap - 2 * sd
        parts.append(tmp)
    out = pd.concat(parts) if parts else pd.DataFrame(index=df1.index)
    return out.reindex(df1.index)


def compute_atr15(df1: pd.DataFrame, window: int = 15) -> pd.Series:
    """Compute a 15-bar ATR-style volatility from 1-minute OHLC.

    True range per bar is max of:
      * high - low
      * abs(high - prev_close)
      * abs(low - prev_close)

    Then we take a simple rolling mean over `window` bars.
    Result is aligned to df1.index and named 'atr15'.
    """
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
