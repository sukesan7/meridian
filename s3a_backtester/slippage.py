"""
Slippage Model
--------------
Implements time-dependent slippage logic.
Differentiates between 'normal' trading hours and 'hot' windows (e.g., market open).
"""

from __future__ import annotations

from datetime import time as dtime
from typing import Any, Literal

import pandas as pd

from .config import Config, SlippageCfg

Side = Literal["long", "short"]


def _get_tick_size(cfg: Config | None, slip_cfg: SlippageCfg | None) -> float:
    """
    Resolves tick size with priority:
    1. Instrument specific (cfg.instrument.tick_size)
    2. Slippage specific (cfg.slippage.tick_size)
    3. Global default (0.25)
    """
    default = 0.25

    if slip_cfg and slip_cfg.tick_size is not None:
        default = float(slip_cfg.tick_size)

    if cfg is None:
        return default

    inst = getattr(cfg, "instrument", None)
    if inst is not None:
        ts = getattr(inst, "tick_size", None)
        if ts is not None:
            return float(ts)

    return default


def _get_slip_cfg(cfg: Any) -> SlippageCfg:
    """
    Extracts slippage config.
    SAFEGUARD: If cfg is None, return a 0-tick config (no side effects).
    """
    if cfg is None:
        return SlippageCfg(normal_ticks=0, hot_ticks=0)

    default_vals = SlippageCfg()

    raw = getattr(cfg, "slippage", None)
    if raw is None:
        return default_vals

    if isinstance(raw, SlippageCfg):
        return raw

    return SlippageCfg(
        normal_ticks=int(getattr(raw, "normal_ticks", default_vals.normal_ticks)),
        hot_ticks=int(getattr(raw, "hot_ticks", default_vals.hot_ticks)),
        hot_start=str(getattr(raw, "hot_start", default_vals.hot_start)),
        hot_end=str(getattr(raw, "hot_end", default_vals.hot_end)),
        tick_size=float(getattr(raw, "tick_size", default_vals.tick_size)),
    )


def _is_hot_window(ts: pd.Timestamp, slip_cfg: SlippageCfg) -> bool:
    """Checks if the timestamp falls within the high-volatility window."""
    if ts.tzinfo is not None:
        ts_et = ts.tz_convert("America/New_York")
    else:
        ts_et = ts

    t: dtime = ts_et.to_pydatetime().time()
    try:
        start: dtime = pd.Timestamp(slip_cfg.hot_start).to_pydatetime().time()
        end: dtime = pd.Timestamp(slip_cfg.hot_end).to_pydatetime().time()
        return bool(start <= t < end)
    except ValueError:
        return False


def apply_slippage(
    side: Side,
    ts: pd.Timestamp,
    raw_price: float,
    cfg: Any | None = None,
) -> float:
    """Calculates executed price after applying slippage rules."""
    slip_cfg = _get_slip_cfg(cfg)
    tick_size = _get_tick_size(cfg, slip_cfg)

    ticks = slip_cfg.normal_ticks
    if _is_hot_window(ts, slip_cfg):
        ticks = slip_cfg.hot_ticks

    if ticks == 0:
        return float(raw_price)

    if side == "long":
        return float(raw_price + ticks * tick_size)
    if side == "short":
        return float(raw_price - ticks * tick_size)

    return float(raw_price)
