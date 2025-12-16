# Management Rules

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Mapping
from .config import MgmtCfg, TimeStopCfg

import numpy as np
import pandas as pd


@dataclass
class TP1Result:
    """Result of TP1 logic for a single trade."""

    hit: bool
    idx: Optional[int]  # integer position in session df (iloc)
    time: Optional[pd.Timestamp]  # timestamp of TP1 hit
    price: float  # TP1 price level
    t_to_tp1_min: Optional[float]  # minutes from entry to TP1 (None if no hit)
    stop_after_tp1: float  # updated stop price after TP1 (BE or original)


@dataclass
class TP2Result:
    """Selected TP2 target and which criterion produced it."""

    hit: bool
    idx: Optional[int]
    time: Optional[pd.Timestamp]
    price: Optional[float]
    label: Optional[str]  # "pdh_pdl" | "measured_move" | "r_multiple" | None


@dataclass
class TimeStopResult:
    """Result of time-stop logic."""

    idx: Optional[int]
    time: Optional[pd.Timestamp]
    reason: Optional[str]  # e.g. "no_tp1_15m", "extension_break", None


def _first_touch_idx(
    high: pd.Series,
    low: pd.Series,
    target: float,
    side: int,
    start_idx: int,
) -> Optional[int]:
    """
    Return the first index (iloc) AFTER start_idx where price touches target.

    For longs (side=+1): high >= target.
    For shorts (side=-1): low <= target.
    """
    if side not in (1, -1):
        raise ValueError(f"side must be +1 or -1, got {side!r}")

    if start_idx >= len(high) - 1:
        # no bars after entry
        return None

    if side == 1:
        mask = high.iloc[start_idx + 1 :] >= target
    else:
        mask = low.iloc[start_idx + 1 :] <= target

    if not mask.any():
        return None

    # mask is aligned with high/low; find first True position relative to its own index
    rel_positions = np.flatnonzero(mask.to_numpy())
    if len(rel_positions) == 0:
        return None

    hit_pos = start_idx + 1 + int(rel_positions[0])
    return hit_pos


def apply_tp1(
    bars: pd.DataFrame,
    entry_idx: int,
    side: int,
    entry_price: float,
    stop_price: float,
    mgmt_cfg: MgmtCfg,
) -> TP1Result:
    """
    Compute TP1 level and first-hit time for a single trade.

    Parameters
    ----------
    bars:
        Session-level OHLCV dataframe. Must have at least 'high' and 'low' columns.
        Index must be a DatetimeIndex, sorted ascending.
    entry_idx:
        Integer iloc position of the entry bar in `bars`.
    side:
        +1 for long, -1 for short.
    entry_price:
        Executed entry price (after slippage).
    stop_price:
        Initial stop price (1 tick beyond invalidation swing).
    mgmt_cfg:
        MgmtCfg with tp1_R, scale_at_tp1, move_to_BE_on_tp1.

    Returns
    -------
    TP1Result
        hit:
            True if TP1 is touched after entry, False otherwise.
        idx/time:
            Where TP1 is first hit (iloc + timestamp) or None.
        price:
            TP1 price level (even if not hit).
        t_to_tp1_min:
            Minutes from entry to TP1 if hit, else None.
        stop_after_tp1:
            New stop after TP1 (entry price if move_to_BE_on_tp1 else original stop).
    """
    if side not in (1, -1):
        raise ValueError(f"side must be +1 or -1, got {side!r}")

    high = bars["high"]
    low = bars["low"]

    risk_per_unit = float(abs(entry_price - stop_price))
    if not np.isfinite(risk_per_unit) or risk_per_unit <= 0.0:
        # Degenerate risk; define TP1 at entry to avoid explosions
        tp1_price = entry_price
    else:
        tp1_price = entry_price + side * mgmt_cfg.tp1_R * risk_per_unit

    hit_idx = _first_touch_idx(
        high=high, low=low, target=tp1_price, side=side, start_idx=entry_idx
    )

    if hit_idx is None:
        return TP1Result(
            hit=False,
            idx=None,
            time=None,
            price=tp1_price,
            t_to_tp1_min=None,
            stop_after_tp1=stop_price,
        )

    entry_time = bars.index[entry_idx]
    hit_time = bars.index[hit_idx]
    t_to_tp1_min = (hit_time - entry_time).total_seconds() / 60.0

    stop_after = entry_price if mgmt_cfg.move_to_BE_on_tp1 else stop_price

    return TP1Result(
        hit=True,
        idx=hit_idx,
        time=hit_time,
        price=tp1_price,
        t_to_tp1_min=t_to_tp1_min,
        stop_after_tp1=stop_after,
    )


def compute_tp2_target(
    bars: pd.DataFrame,
    entry_idx: int,
    side: int,
    entry_price: float,
    stop_price: float,
    mgmt_cfg: MgmtCfg,
    refs: Mapping[str, float],
) -> TP2Result:
    """
    Choose TP2 as the earliest hit among:
      - PDH/PDL (if provided & in-play),
      - OR measured move,
      - +tp2_R multiple of initial risk.

    This is intentionally written as a simple, per-trade function. The engine is
    expected to call this with per-session bars and a dict of refs, e.g.:

        refs = {
            "pdh": float,
            "pdl": float,
            "or_height": float,
        }

    Priority when multiple criteria hit on the same bar:
        PDH/PDL > measured move > R-multiple.

    NOTE: This is a building block; realized_R / scaling is computed at the
    engine level once TP1/TP2/time-stop are combined.
    """
    high = bars["high"]
    low = bars["low"]

    risk_per_unit = float(abs(entry_price - stop_price))
    if not np.isfinite(risk_per_unit) or risk_per_unit <= 0.0:
        risk_per_unit = 0.0

    candidates: list[tuple[str, float, Optional[int]]] = []

    # 1) PDH/PDL
    pdh = refs.get("pdh")
    pdl = refs.get("pdl")
    if side == 1 and pdh is not None and np.isfinite(pdh) and pdh > entry_price:
        idx_pdh = _first_touch_idx(
            high=high, low=low, target=pdh, side=side, start_idx=entry_idx
        )
        candidates.append(("pdh_pdl", pdh, idx_pdh))
    if side == -1 and pdl is not None and np.isfinite(pdl) and pdl < entry_price:
        idx_pdl = _first_touch_idx(
            high=high, low=low, target=pdl, side=side, start_idx=entry_idx
        )
        candidates.append(("pdh_pdl", pdl, idx_pdl))

    # 2) OR measured move
    or_height = refs.get("or_height")
    if or_height is not None and np.isfinite(or_height) and or_height > 0:
        mm_target = entry_price + side * float(or_height)
        idx_mm = _first_touch_idx(
            high=high, low=low, target=mm_target, side=side, start_idx=entry_idx
        )
        candidates.append(("measured_move", mm_target, idx_mm))

    # 3) R-multiple target
    if risk_per_unit > 0:
        r_target = entry_price + side * mgmt_cfg.tp2_R * risk_per_unit
        idx_r = _first_touch_idx(
            high=high, low=low, target=r_target, side=side, start_idx=entry_idx
        )
        candidates.append(("r_multiple", r_target, idx_r))

    # Filter out candidates that never hit
    valid_hits = [
        (label, price, idx) for (label, price, idx) in candidates if idx is not None
    ]
    if not valid_hits:
        return TP2Result(hit=False, idx=None, time=None, price=None, label=None)

    # Choose earliest hit by idx; break ties by fixed priority.
    priority = {"pdh_pdl": 0, "measured_move": 1, "r_multiple": 2}

    def sort_key(item: tuple[str, float, int]) -> tuple[int, int]:
        label, _price, idx = item
        return (idx, priority[label])

    best_label, best_price, best_idx = sorted(valid_hits, key=sort_key)[0]
    best_time = bars.index[int(best_idx)]

    return TP2Result(
        hit=True,
        idx=int(best_idx),
        time=best_time,
        price=float(best_price),
        label=best_label,
    )


def run_time_stop(
    bars: pd.DataFrame,
    entry_idx: int,
    tp1_idx: Optional[int],
    side: int,
    entry_price: float,
    stop_price: float,
    time_cfg: TimeStopCfg,
    vwap_side_ok: Optional[pd.Series] = None,
    trend_ok: Optional[pd.Series] = None,
    sigma_ok: Optional[pd.Series] = None,
    dd_ok: Optional[pd.Series] = None,
) -> TimeStopResult:
    """
    Enforce time-based exit rules:

      - Must hit TP1 within `time_cfg.tp1_timeout_min` minutes or exit at market.
      - Optional 30-minute extension if all of:
          vwap_side_ok, trend_ok, sigma_ok, dd_ok
        remain True bar-by-bar.

    This function **only** decides a time-stop exit; the engine should compare
    the returned index with stop-loss/TP hits and choose the earliest exit.

    Assumptions about TimeStopCfg (adapt to your actual config):
      - tp1_timeout_min: int, minutes allowed to reach TP1.
      - max_holding_min: int, hard cap on minutes in trade (incl. extension).
      - allow_extension: bool, whether the 30m extension is used.

    The series vwap_side_ok / trend_ok / sigma_ok / dd_ok are expected to be
    boolean Series indexed like `bars`. If any is None, it is treated as True.
    """

    # If time-stop is disabled, nothing to do.
    if getattr(time_cfg, "mode", "15m") == "none":
        return TimeStopResult(idx=None, time=None, reason=None)

    idx = bars.index

    entry_time = idx[entry_idx]
    tp1_timeout_min = getattr(time_cfg, "tp1_timeout_min", 15)
    max_holding_min = getattr(time_cfg, "max_holding_min", 45)
    allow_extension = getattr(time_cfg, "allow_extension", True)

    tp1_deadline = entry_time + pd.Timedelta(minutes=tp1_timeout_min)
    hard_deadline = entry_time + pd.Timedelta(minutes=max_holding_min)

    # Helper to find first bar at/after a given timestamp
    def _first_bar_at_or_after(ts: pd.Timestamp) -> Optional[int]:
        # idx is sorted ascending DatetimeIndex
        pos = idx.searchsorted(ts, side="left")
        if pos >= len(idx):
            return None
        return int(pos)

    # 1) If TP1 never hit within timeout: exit at first bar at/after tp1_deadline.
    if tp1_idx is None:
        stop_idx = _first_bar_at_or_after(tp1_deadline)
        if stop_idx is None:
            return TimeStopResult(idx=None, time=None, reason=None)
        return TimeStopResult(idx=stop_idx, time=idx[stop_idx], reason="no_tp1_15m")

    # 2) TP1 hit: optionally allow extension, but enforce hard max holding time.
    if not allow_extension:
        # No extension logic; only enforce hard cap.
        stop_idx = _first_bar_at_or_after(hard_deadline)
        if stop_idx is None:
            return TimeStopResult(idx=None, time=None, reason=None)
        return TimeStopResult(idx=stop_idx, time=idx[stop_idx], reason="max_hold")

    # 3) Extension: walk forward bar by bar until either
    #    - conditions fail; or
    #    - hard_deadline is reached.
    # We start checking from the bar AFTER TP1.
    start = tp1_idx + 1
    if start >= len(idx):
        return TimeStopResult(idx=None, time=None, reason=None)

    def _cond(series: Optional[pd.Series], i: int) -> bool:
        if series is None:
            return True
        val = series.iloc[i]
        # treat NaN as False (fail-safe)
        return bool(val) and not pd.isna(val)

    for i in range(start, len(idx)):
        t = idx[i]
        if t > hard_deadline:
            return TimeStopResult(idx=i, time=t, reason="max_hold")

        if not (
            _cond(vwap_side_ok, i)
            and _cond(trend_ok, i)
            and _cond(sigma_ok, i)
            and _cond(dd_ok, i)
        ):
            return TimeStopResult(idx=i, time=t, reason="extension_break")

    # Session ended before hard_deadline or any condition break.
    return TimeStopResult(idx=None, time=None, reason=None)
