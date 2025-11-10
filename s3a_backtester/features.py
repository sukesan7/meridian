# s3a_backtester/features.py
from __future__ import annotations
import pandas as pd
import numpy as np


def compute_session_refs(df1: pd.DataFrame) -> pd.DataFrame:
    """Compute OR(09:30–09:35) and placeholders for PDH/PDL/ONH/ONL."""
    out = df1.copy()
    out["or_high"] = np.nan
    out["or_low"] = np.nan
    out["or_height"] = np.nan
    out["pdh"] = np.nan
    out["pdl"] = np.nan
    out["onh"] = np.nan
    out["onl"] = np.nan

    # OR = [09:30, 09:35)  (include start, exclude end)
    for _, daydf in df1.groupby(df1.index.date, sort=False):
        slice_ = daydf.between_time("09:30", "09:35", inclusive="left")
        if not slice_.empty:
            hi = slice_["high"].max()
            lo = slice_["low"].min()
            out.loc[slice_.index, "or_high"] = hi
            out.loc[slice_.index, "or_low"] = lo
            out.loc[slice_.index, "or_height"] = hi - lo
    return out


def compute_session_vwap_bands(
    df1: pd.DataFrame, use_close: bool = True
) -> pd.DataFrame:
    """Session-anchored VWAP from 09:30 and simple expanding stdev bands (±1σ/±2σ)."""
    price = df1["close"] if use_close else (df1["high"] + df1["low"] + df1["close"]) / 3
    vol = (
        df1["volume"].astype(float)
        if "volume" in df1.columns
        else pd.Series(1.0, index=df1.index)
    )
    out_parts = []
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
        out_parts.append(tmp)
    out = pd.concat(out_parts) if out_parts else pd.DataFrame(index=df1.index)
    return out.reindex(df1.index)


def compute_atr15(df1: pd.DataFrame) -> pd.Series:
    """Simple EMA-based ATR proxy on 1m bars."""
    hi, lo, cl = df1.get("high"), df1.get("low"), df1.get("close")
    if hi is None or lo is None or cl is None:
        return pd.Series(index=df1.index, dtype=float, name="atr15")
    tr = pd.concat(
        [(hi - lo).abs(), (hi - cl.shift()).abs(), (lo - cl.shift()).abs()], axis=1
    ).max(axis=1)
    atr = tr.ewm(span=15, adjust=False).mean()
    return atr.rename("atr15")
