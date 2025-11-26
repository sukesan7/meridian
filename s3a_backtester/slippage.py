from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

Side = Literal["long", "short"]


@dataclass
class SlippageConfig:
    """
    Simple slippage model:

    - normal_ticks: slippage (in ticks) during regular periods.
    - hot_ticks:    slippage (in ticks) during the "hot" window.
    - hot_start:    start of hot window (clock time, ET) e.g. "09:30".
    - hot_end:      end of hot window (clock time, ET) e.g. "09:40".
    - tick_size:    fallback tick size if cfg.instrument.tick_size is absent.

    This is *intentionally* very small and declarative; the real config object
    will usually wrap this as cfg.slippage.
    """

    normal_ticks: int = 0
    hot_ticks: int = 0
    hot_start: str = "09:30"
    hot_end: str = "09:40"
    tick_size: float = 0.25


def _get_tick_size(cfg: Any, default: float) -> float:
    """Resolve tick size from cfg.instrument.tick_size or cfg.tick_size."""
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
    """
    Extract a SlippageConfig view from cfg.slippage, or None if no
    slippage should be applied.
    """
    if cfg is None:
        return None
    raw = getattr(cfg, "slippage", None)
    if raw is None:
        return None
    if isinstance(raw, SlippageConfig):
        return raw

    # Allow plain objects / namespaces with matching attributes.
    return SlippageConfig(
        normal_ticks=getattr(raw, "normal_ticks", 0),
        hot_ticks=getattr(raw, "hot_ticks", getattr(raw, "normal_ticks", 0)),
        hot_start=getattr(raw, "hot_start", "09:30"),
        hot_end=getattr(raw, "hot_end", "09:40"),
        tick_size=getattr(raw, "tick_size", 0.25),
    )


def _is_hot_window(ts: pd.Timestamp, slip_cfg: SlippageConfig) -> bool:
    """
    Decide whether a timestamp is in the configured 'hot' window.

    All comparisons are done in America/New_York clock time.
    """
    if ts.tzinfo is not None:
        ts_et = ts.tz_convert("America/New_York")
    else:
        ts_et = ts  # assume already ET

    t = ts_et.time()
    start = pd.Timestamp(slip_cfg.hot_start).time()
    end = pd.Timestamp(slip_cfg.hot_end).time()
    # Treat window as [start, end); tweak if you want end-inclusive.
    return start <= t < end


def apply_slippage(
    side: Side,
    ts: pd.Timestamp,
    raw_price: float,
    cfg: Any | None = None,
) -> float:
    """
    Apply simple time-of-day based slippage to a raw price.

    Parameters
    ----------
    side:
        "long" or "short". Unknown values → no slippage.
    ts:
        Bar timestamp (tz-aware preferred). Hot vs normal windows are
        evaluated in America/New_York clock time.
    raw_price:
        The un-slipped price (e.g. bar-close).
    cfg:
        Global config object. We look for:
            - cfg.slippage.normal_ticks / hot_ticks / hot_start / hot_end
            - cfg.instrument.tick_size or cfg.tick_size
        If cfg.slippage is missing, this function returns raw_price.

    Returns
    -------
    float
        Slipped price (worse than raw_price in the direction of the trade).
    """
    slip_cfg = _get_slip_cfg(cfg)
    if slip_cfg is None:
        return float(raw_price)

    tick_size = _get_tick_size(cfg, slip_cfg.tick_size)

    ticks = slip_cfg.normal_ticks
    if _is_hot_window(ts, slip_cfg):
        ticks = slip_cfg.hot_ticks

    if ticks == 0:
        return float(raw_price)

    # Pay worse price in direction of the trade.
    if side == "long":
        return float(raw_price + ticks * tick_size)
    if side == "short":
        return float(raw_price - ticks * tick_size)

    # Unknown side → no slippage.
    return float(raw_price)
