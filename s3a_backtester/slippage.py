"""
Slippage Model
--------------
Implements time-dependent slippage logic.
Differentiates between 'normal' trading hours and 'hot' windows (e.g., market open).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

Side = Literal["long", "short"]


@dataclass
class SlippageConfig:
    """Internal slippage parameters."""

    normal_ticks: int = 0
    hot_ticks: int = 0
    hot_start: str = "09:30"
    hot_end: str = "09:40"
    tick_size: float = 0.25


def _get_tick_size(cfg: Any, default: float) -> float:
    if cfg is None:
        return default
    inst = getattr(cfg, "instrument", None)
    if inst is not None:
        ts = getattr(inst, "tick_size", None)
        if ts is not None:
            return float(ts)
    ts = getattr(cfg, "tick_size", None)
    if ts is not None:
        return float(ts)
    return default


def _get_slip_cfg(cfg: Any) -> SlippageConfig | None:
    if cfg is None:
        return None
    raw = getattr(cfg, "slippage", None)
    if raw is None:
        return None
    if isinstance(raw, SlippageConfig):
        return raw

    return SlippageConfig(
        normal_ticks=getattr(raw, "normal_ticks", 0),
        hot_ticks=getattr(raw, "hot_ticks", getattr(raw, "normal_ticks", 0)),
        hot_start=getattr(raw, "hot_start", "09:30"),
        hot_end=getattr(raw, "hot_end", "09:40"),
        tick_size=getattr(raw, "tick_size", 0.25),
    )


def _is_hot_window(ts: pd.Timestamp, slip_cfg: SlippageConfig) -> bool:
    if ts.tzinfo is not None:
        ts_et = ts.tz_convert("America/New_York")
    else:
        ts_et = ts

    t = ts_et.time()
    start = pd.Timestamp(slip_cfg.hot_start).time()
    end = pd.Timestamp(slip_cfg.hot_end).time()
    return start <= t < end


def apply_slippage(
    side: Side,
    ts: pd.Timestamp,
    raw_price: float,
    cfg: Any | None = None,
) -> float:
    """Calculates executed price after applying slippage rules."""
    slip_cfg = _get_slip_cfg(cfg)
    if slip_cfg is None:
        return float(raw_price)

    tick_size = _get_tick_size(cfg, slip_cfg.tick_size)

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
