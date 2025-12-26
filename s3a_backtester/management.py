"""
Trade Management Logic
----------------------
Handles the full lifecycle of an active trade, including:
- Take Profit (TP1/TP2) execution.
- Stop Loss trailing and Breakeven adjustments.
- Time-based exits and extensions.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Mapping
from .config import MgmtCfg, TimeStopCfg

import numpy as np
import pandas as pd


@dataclass
class TP1Result:
    hit: bool
    idx: Optional[int]
    time: Optional[pd.Timestamp]
    price: float
    t_to_tp1_min: Optional[float]
    stop_after_tp1: float


@dataclass
class TP2Result:
    hit: bool
    idx: Optional[int]
    time: Optional[pd.Timestamp]
    price: Optional[float]
    label: Optional[str]


@dataclass
class TimeStopResult:
    idx: Optional[int]
    time: Optional[pd.Timestamp]
    reason: Optional[str]


def _first_touch_idx(
    high: pd.Series,
    low: pd.Series,
    target: float,
    side: int,
    start_idx: int,
) -> Optional[int]:
    """Find the index of the first bar that touches a target price."""
    if side not in (1, -1):
        raise ValueError(f"side must be +1 or -1, got {side!r}")

    if start_idx >= len(high) - 1:
        return None

    if side == 1:
        mask = high.iloc[start_idx + 1 :] >= target
    else:
        mask = low.iloc[start_idx + 1 :] <= target

    if not mask.any():
        return None

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
    """Calculates if and when the first Take Profit level was hit."""
    if side not in (1, -1):
        raise ValueError(f"side must be +1 or -1, got {side!r}")

    high = bars["high"]
    low = bars["low"]

    risk_per_unit = float(abs(entry_price - stop_price))
    if not np.isfinite(risk_per_unit) or risk_per_unit <= 0.0:
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
    """Determines the TP2 target based on structure priority."""
    high = bars["high"]
    low = bars["low"]

    risk_per_unit = float(abs(entry_price - stop_price))
    if not np.isfinite(risk_per_unit) or risk_per_unit <= 0.0:
        risk_per_unit = 0.0

    candidates: list[tuple[str, float, Optional[int]]] = []

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

    or_height = refs.get("or_height")
    if or_height is not None and np.isfinite(or_height) and or_height > 0:
        mm_target = entry_price + side * float(or_height)
        idx_mm = _first_touch_idx(
            high=high, low=low, target=mm_target, side=side, start_idx=entry_idx
        )
        candidates.append(("measured_move", mm_target, idx_mm))

    if risk_per_unit > 0:
        r_target = entry_price + side * mgmt_cfg.tp2_R * risk_per_unit
        idx_r = _first_touch_idx(
            high=high, low=low, target=r_target, side=side, start_idx=entry_idx
        )
        candidates.append(("r_multiple", r_target, idx_r))

    valid_hits = [
        (label, price, idx) for (label, price, idx) in candidates if idx is not None
    ]
    if not valid_hits:
        return TP2Result(hit=False, idx=None, time=None, price=None, label=None)

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
    """Evaluates time-based exit conditions, including optional extensions."""
    if getattr(time_cfg, "mode", "15m") == "none":
        return TimeStopResult(idx=None, time=None, reason=None)

    idx = bars.index

    entry_time = idx[entry_idx]
    tp1_timeout_min = getattr(time_cfg, "tp1_timeout_min", 15)
    max_holding_min = getattr(time_cfg, "max_holding_min", 45)
    allow_extension = getattr(time_cfg, "allow_extension", True)

    tp1_deadline = entry_time + pd.Timedelta(minutes=tp1_timeout_min)
    hard_deadline = entry_time + pd.Timedelta(minutes=max_holding_min)

    if tp1_idx is not None:
        tp1_time = idx[tp1_idx]
        if tp1_time > tp1_deadline:
            tp1_idx = None

    def _first_bar_at_or_after(ts: pd.Timestamp) -> Optional[int]:
        pos = idx.searchsorted(ts, side="left")
        if pos >= len(idx):
            return None
        return int(pos)

    if tp1_idx is None:
        stop_idx = _first_bar_at_or_after(tp1_deadline)
        if stop_idx is None:
            return TimeStopResult(idx=None, time=None, reason=None)

        # Mypy override: explicit check + ignore
        safe_idx = int(stop_idx)
        exit_time = idx[safe_idx]  # type: ignore
        return TimeStopResult(idx=safe_idx, time=exit_time, reason="no_tp1_15m")

    if not allow_extension:
        stop_idx = _first_bar_at_or_after(hard_deadline)
        if stop_idx is None:
            return TimeStopResult(idx=None, time=None, reason=None)

        # Mypy override: explicit check + ignore
        safe_idx = int(stop_idx)
        exit_time = idx[safe_idx]  # type: ignore
        return TimeStopResult(idx=safe_idx, time=exit_time, reason="max_hold")

    start = tp1_idx + 1
    if start >= len(idx):
        return TimeStopResult(idx=None, time=None, reason=None)

    def _cond(series: Optional[pd.Series], i: int) -> bool:
        if series is None:
            return True
        val = series.iloc[i]
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

    return TimeStopResult(idx=None, time=None, reason=None)


def _first_stop_idx(
    high: pd.Series,
    low: pd.Series,
    stop_price: float,
    side: int,
    start_idx: int,
) -> Optional[int]:
    """Find index of the first bar that violates the stop price."""
    if side not in (1, -1):
        raise ValueError(f"side must be +1 or -1, got {side!r}")

    if start_idx >= len(high) - 1:
        return None

    if side == 1:
        mask = low.iloc[start_idx + 1 :] <= stop_price
    else:
        mask = high.iloc[start_idx + 1 :] >= stop_price

    if not mask.any():
        return None

    rel = np.flatnonzero(mask.to_numpy())
    if len(rel) == 0:
        return None

    return start_idx + 1 + int(rel[0])


def manage_trade_lifecycle(
    bars: pd.DataFrame,
    entry_idx: int,
    side: int,
    entry_price: float,
    stop_price: float,
    mgmt_cfg: MgmtCfg,
    time_cfg: TimeStopCfg,
    refs: Mapping[str, float],
    vwap_side_ok: Optional[pd.Series] = None,
    trend_ok: Optional[pd.Series] = None,
    sigma_ok: Optional[pd.Series] = None,
    dd_ok: Optional[pd.Series] = None,
) -> dict:
    """Computes the complete outcome of a trade given full session data."""
    high = bars["high"]
    low = bars["low"]
    idx = bars.index

    risk_per_unit = float(abs(entry_price - stop_price))
    if risk_per_unit <= 0 or not np.isfinite(risk_per_unit):
        return {
            "exit_idx": entry_idx,
            "exit_time": idx[entry_idx],
            "exit_price": entry_price,
            "realized_R": 0.0,
            "tp1_price": entry_price,
            "tp2_price": None,
            "t_to_tp1_min": None,
            "time_stop_reason": "degenerate_risk",
            "tp2_label": None,
        }

    orig_stop_idx = _first_stop_idx(
        high=high,
        low=low,
        stop_price=stop_price,
        side=side,
        start_idx=entry_idx,
    )

    tp1_res = apply_tp1(
        bars=bars,
        entry_idx=entry_idx,
        side=side,
        entry_price=entry_price,
        stop_price=stop_price,
        mgmt_cfg=mgmt_cfg,
    )

    tp2_res = compute_tp2_target(
        bars=bars,
        entry_idx=entry_idx,
        side=side,
        entry_price=entry_price,
        stop_price=stop_price,
        mgmt_cfg=mgmt_cfg,
        refs=refs,
    )

    ts_res = run_time_stop(
        bars=bars,
        entry_idx=entry_idx,
        tp1_idx=tp1_res.idx,
        side=side,
        entry_price=entry_price,
        stop_price=stop_price,
        time_cfg=time_cfg,
        vwap_side_ok=vwap_side_ok,
        trend_ok=trend_ok,
        sigma_ok=sigma_ok,
        dd_ok=dd_ok,
    )

    def _earliest(
        events: list[tuple[str, Optional[int]]],
    ) -> tuple[Optional[str], Optional[int]]:
        valid = [(label, i) for (label, i) in events if i is not None]
        if not valid:
            return None, None
        prio = {"stop": 0, "tp2": 1, "time_stop": 2, "tp1": 3}
        label, i = sorted(valid, key=lambda x: (x[1], prio[x[0]]))[0]
        return label, i

    earliest_label, earliest_idx = _earliest(
        [
            ("stop", orig_stop_idx),
            ("tp2", tp2_res.idx if tp2_res.hit else None),
            ("time_stop", ts_res.idx),
            ("tp1", tp1_res.idx if tp1_res.hit else None),
        ]
    )

    if earliest_label is None:
        return {
            "exit_idx": entry_idx,
            "exit_time": idx[entry_idx],
            "exit_price": entry_price,
            "realized_R": 0.0,
            "tp1_price": tp1_res.price,
            "tp2_price": tp2_res.price if tp2_res.hit else None,
            "t_to_tp1_min": None,
            "time_stop_reason": "no_event",
            "tp2_label": tp2_res.label if tp2_res.hit else None,
        }

    if earliest_label != "tp1":
        if earliest_label == "stop":
            exit_price = stop_price
            reason = "stop"
        elif earliest_label == "tp2":
            exit_price = float(tp2_res.price) if tp2_res.price else 0.0
            reason = f"tp2_{tp2_res.label}"
        else:
            if earliest_idx is not None:
                exit_price = float(bars["close"].iloc[earliest_idx])
            else:
                exit_price = entry_price
            reason = ts_res.reason or "time_stop"

        realized_R = side * (exit_price - entry_price) / risk_per_unit

        return {
            "exit_idx": earliest_idx,
            "exit_time": idx[earliest_idx] if earliest_idx is not None else None,
            "exit_price": exit_price,
            "realized_R": realized_R,
            "tp1_price": tp1_res.price,
            "tp2_price": tp2_res.price if tp2_res.hit else None,
            "t_to_tp1_min": None,
            "time_stop_reason": reason if earliest_label == "time_stop" else "none",
            "tp2_label": tp2_res.label if tp2_res.hit else None,
        }

    scale = float(mgmt_cfg.scale_at_tp1)
    r_tp1 = float(mgmt_cfg.tp1_R)
    locked_R = scale * r_tp1

    runner_stop_price = tp1_res.stop_after_tp1

    runner_stop_idx = _first_stop_idx(
        high=high,
        low=low,
        stop_price=runner_stop_price,
        side=side,
        start_idx=int(tp1_res.idx) if tp1_res.idx is not None else 0,
    )

    runner_tp2_idx = None
    if (
        tp2_res.hit
        and tp2_res.idx is not None
        and tp1_res.idx is not None
        and tp2_res.idx > tp1_res.idx
    ):
        runner_tp2_idx = tp2_res.idx

    runner_ts_idx = None
    runner_ts_reason = "none"
    if ts_res.idx is not None and tp1_res.idx is not None and ts_res.idx > tp1_res.idx:
        runner_ts_idx = ts_res.idx
        runner_ts_reason = ts_res.reason or "time_stop"

    runner_label, runner_idx = _earliest(
        [
            ("stop", runner_stop_idx),
            ("tp2", runner_tp2_idx),
            ("time_stop", runner_ts_idx),
        ]
    )

    if runner_label is None:
        runner_idx = len(idx) - 1
        runner_exit_price = float(bars["close"].iloc[runner_idx])
        runner_reason = "no_event"
    else:
        if runner_label == "stop":
            runner_exit_price = runner_stop_price
            runner_reason = "stop"
        elif runner_label == "tp2":
            runner_exit_price = float(tp2_res.price) if tp2_res.price else 0.0
            runner_reason = f"tp2_{tp2_res.label}"
        else:
            if runner_ts_idx is not None:
                runner_exit_price = float(bars["close"].iloc[int(runner_ts_idx)])
            else:
                runner_exit_price = entry_price

            runner_reason = runner_ts_reason

    runner_R = side * (runner_exit_price - entry_price) / risk_per_unit
    total_R = locked_R + (1.0 - scale) * runner_R

    if runner_idx is None:
        runner_idx = len(idx) - 1

    final_idx = int(runner_idx)
    final_time = idx[final_idx]

    time_reason = (
        runner_reason
        if runner_label == "time_stop"
        else ("none" if ts_res.reason is None else ts_res.reason)
    )

    return {
        "exit_idx": final_idx,
        "exit_time": final_time,
        "exit_price": runner_exit_price,
        "realized_R": total_R,
        "tp1_price": tp1_res.price,
        "tp2_price": tp2_res.price if tp2_res.hit else None,
        "t_to_tp1_min": tp1_res.t_to_tp1_min,
        "time_stop_reason": time_reason,
        "tp2_label": tp2_res.label if tp2_res.hit else None,
    }
