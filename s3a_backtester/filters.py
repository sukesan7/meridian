"""
Session Filtering Logic
-----------------------
Determines if a trading day should be skipped entirely based on:
- Volatility (ATR, Opening Range).
- News events (Blackout flags).
- Market quality (DOM/Liquidity flags).
"""

from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd


def build_session_filter_mask(
    df: pd.DataFrame,
    filters_cfg: Any | None = None,
) -> pd.Series:
    """
    Constructs a boolean mask indicating valid trading sessions.
    Returns Series[bool]: True = Allowed, False = Skipped.
    """
    if df.empty:
        return pd.Series([], index=df.index, dtype=bool, name="session_filter_ok")

    if filters_cfg is None:
        return pd.Series(True, index=df.index, name="session_filter_ok")

    # Safe attribute access
    enable_tiny_or = bool(getattr(filters_cfg, "enable_tiny_or", True))
    tiny_or_mult = float(getattr(filters_cfg, "tiny_or_mult", 0.25))
    enable_low_atr = bool(getattr(filters_cfg, "enable_low_atr", True))
    low_atr_percentile = float(getattr(filters_cfg, "low_atr_percentile", 20.0))
    enable_news = bool(getattr(filters_cfg, "enable_news_blackout", True))
    enable_dom = bool(getattr(filters_cfg, "enable_dom_filter", True))

    session_idx = pd.Index([ts.date() for ts in df.index], name="session")
    grp = df.groupby(session_idx)

    if "or_high" in df.columns and "or_low" in df.columns:
        daily_or_high = grp["or_high"].max()
        daily_or_low = grp["or_low"].min()
        daily_or_height = daily_or_high - daily_or_low
    else:
        daily_or_height = pd.Series(np.nan, index=grp.groups.keys(), name="or_height")

    if "atr15" in df.columns:
        daily_atr15 = grp["atr15"].last()
    else:
        daily_atr15 = pd.Series(np.nan, index=grp.groups.keys(), name="atr15")

    stats = pd.DataFrame(
        {
            "or_height": daily_or_height,
            "atr15": daily_atr15,
        }
    ).sort_index()

    stats["or_med_15"] = (
        stats["or_height"].rolling(window=15, min_periods=5).median().shift(1)
    )

    p = max(0.0, min(100.0, low_atr_percentile)) / 100.0
    if p == 0.0 or stats["atr15"].isna().all():
        stats["atr_pXX_60"] = np.nan
    else:
        stats["atr_pXX_60"] = (
            stats["atr15"].rolling(window=60, min_periods=20).quantile(p).shift(1)
        )

    if "news_blackout" in df.columns:
        daily_news = grp["news_blackout"].max().astype(bool)
    else:
        daily_news = pd.Series(False, index=stats.index, name="news_blackout")

    if "dom_bad" in df.columns:
        daily_dom = grp["dom_bad"].max().astype(bool)
    else:
        daily_dom = pd.Series(False, index=stats.index, name="dom_bad")

    tiny_or_day = pd.Series(False, index=stats.index)
    if enable_tiny_or:
        tiny_or_day = (
            stats["or_height"].notna()
            & stats["or_med_15"].notna()
            & (stats["or_height"] < stats["or_med_15"] * tiny_or_mult)
        )

    low_atr_day = pd.Series(False, index=stats.index)
    if enable_low_atr:
        low_atr_day = (
            stats["atr15"].notna()
            & stats["atr_pXX_60"].notna()
            & (stats["atr15"] < stats["atr_pXX_60"])
        )

    news_day = daily_news if enable_news else pd.Series(False, index=stats.index)
    dom_day = daily_dom if enable_dom else pd.Series(False, index=stats.index)

    skip_session = tiny_or_day | low_atr_day | news_day | dom_day

    allowed = (~skip_session).reindex(session_idx).astype(bool)
    allowed.index = df.index
    allowed.name = "session_filter_ok"
    return allowed
