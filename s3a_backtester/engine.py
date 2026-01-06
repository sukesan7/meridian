"""
Core Strategy Engine
--------------------
Orchestrates the signal generation and trade simulation phases.
Includes the primary State Machine (Unlock -> Zone -> Trigger) and Trade Builder.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

from .config import Config, MgmtCfg, TimeStopCfg
from .filters import build_session_filter_mask
from .management import manage_trade_lifecycle
from .slippage import apply_slippage
from .time_stop_conditions import build_time_stop_condition_series

_TRADE_COLS = [
    "date",
    "signal_time",
    "entry_time",
    "exit_time",
    "side",
    "entry",
    "stop",
    "tp1",
    "tp2",
    "or_height",
    "sl_ticks",
    "risk_R",
    "realized_R",
    "t_to_tp1_min",
    "trigger_type",
    "location",
    "time_stop",
    "disqualifier",
    "slippage_entry_ticks",
    "slippage_exit_ticks",
]


def simulate_trades(
    df1: pd.DataFrame, signals: pd.DataFrame, cfg: Config | None
) -> pd.DataFrame:
    """
    Iterates through signal events to build executed trades.
    Applies slippage, risk checks, and full lifecycle management.
    """
    if signals is None or signals.empty:
        return pd.DataFrame(columns=_TRADE_COLS)

    mkt = df1
    sig = signals

    if not isinstance(mkt.index, pd.DatetimeIndex) or not isinstance(
        sig.index, pd.DatetimeIndex
    ):
        raise TypeError("df1/signals must be indexed by DatetimeIndex")
    if not mkt.index.is_monotonic_increasing:
        raise ValueError("df1 index must be strictly increasing")
    if not mkt.index.equals(sig.index):
        raise ValueError(
            "df1 and signals index must match exactly (no filtering/reindexing)"
        )

    mkt_idx: pd.DatetimeIndex = mkt.index

    df = sig.copy()
    defaults: dict[str, object] = {
        "direction": 0,
        "trigger_ok": False,
        "time_window_ok": True,
        "disqualified_2sigma": False,
        "stop_price": np.nan,
        "or_high": np.nan,
        "or_low": np.nan,
        "vwap": np.nan,
        "vwap_1u": np.nan,
        "vwap_1d": np.nan,
        "micro_break_dir": 0,
        "engulf_dir": 0,
        "pdh": np.nan,
        "pdl": np.nan,
        "atr15": np.nan,
        "news_blackout": False,
        "dom_bad": False,
    }
    for col, val in defaults.items():
        if col not in df:
            df[col] = cast(Any, val)

    direction = pd.to_numeric(df["direction"], errors="coerce").fillna(0).astype(int)
    mask = (
        direction.ne(0)
        & df["trigger_ok"].astype(bool)
        & df["time_window_ok"].astype(bool)
        & ~df["disqualified_2sigma"].astype(bool)
    )

    filters_cfg = getattr(cfg, "filters", None) if cfg is not None else None
    if filters_cfg is not None:
        session_mask = build_session_filter_mask(df, filters_cfg)
        mask &= session_mask

    entries = df.loc[mask].copy()
    if entries.empty:
        return pd.DataFrame(columns=_TRADE_COLS)

    tick_size = 0.25
    mgmt_cfg: MgmtCfg | None = None
    time_cfg: TimeStopCfg | None = None
    fill_mode = "next_open"
    max_risk_mult = 1.25

    if cfg is not None:
        inst = getattr(cfg, "instrument", None)
        if inst is not None:
            tick_size = getattr(inst, "tick_size", tick_size)

        if hasattr(cfg, "slippage"):
            slip = getattr(cfg, "slippage")
            tick_size = getattr(slip, "tick_size", tick_size)
            fill_mode = getattr(slip, "mode", "next_open")

        tick_size = getattr(cfg, "tick_size", tick_size)

        mgmt_cfg = getattr(cfg, "management", None)
        time_cfg = getattr(cfg, "time_stop", None)

        risk_cfg = getattr(cfg, "risk", None)
        if risk_cfg is not None:
            max_risk_mult = float(getattr(risk_cfg, "max_stop_or_mult", 1.25))

    tick_size = float(tick_size) if tick_size else 0.25
    use_management = mgmt_cfg is not None and time_cfg is not None

    entry_pos = mkt_idx.get_indexer(cast(pd.DatetimeIndex, entries.index))
    mkt_len = len(mkt)

    records: list[dict[str, object]] = []
    session_cache: dict[date, pd.DataFrame] = {}

    feature_cols_needed = (
        "vwap",
        "vwap_1u",
        "vwap_1d",
        "vwap_2u",
        "vwap_2d",
        "trend_5m",
        "trend_dir_5m",
        "trend5",
        "trend_dir",
        "trend5_dir",
    )

    for (_ts, row), pos in zip(entries.iterrows(), entry_pos):
        pos_i = int(pos)
        if pos_i < 0:
            continue

        ts_idx: pd.Timestamp = mkt_idx[pos_i]

        dir_val = int(row["direction"])
        if dir_val == 0:
            continue

        side_lit: Literal["long", "short"] = "long" if dir_val > 0 else "short"
        side_sign = 1 if dir_val > 0 else -1

        raw_price: float
        fill_ts: pd.Timestamp = ts_idx

        if fill_mode == "next_open":
            next_pos = pos_i + 1
            if "open" in mkt.columns and next_pos < mkt_len:
                raw_price = float(mkt["open"].iloc[next_pos])
                fill_ts = mkt_idx[next_pos]
            else:
                if "close" in mkt.columns:
                    raw_price = float(mkt["close"].iloc[pos_i])
                else:
                    raw_price = float(row.get("close", np.nan))
                fill_ts = ts_idx
        else:
            if "close" in mkt.columns:
                raw_price = float(mkt["close"].iloc[pos_i])
            else:
                raw_price = float(row.get("close", np.nan))
            fill_ts = ts_idx

        if not np.isfinite(raw_price):
            continue

        stop = float(row["stop_price"]) if pd.notna(row["stop_price"]) else np.nan
        if not np.isfinite(stop):
            continue

        entry_price = apply_slippage(side_lit, fill_ts, raw_price, cfg)

        risk_per_unit = abs(entry_price - stop)
        if risk_per_unit <= 0 or not np.isfinite(risk_per_unit):
            continue

        or_high = float(row.get("or_high", np.nan))
        or_low = float(row.get("or_low", np.nan))
        or_height = (
            (or_high - or_low)
            if np.isfinite(or_high) and np.isfinite(or_low)
            else np.nan
        )

        if np.isfinite(or_height) and or_height > 0:
            risk_cap = float(or_height) * float(max_risk_mult)
            if risk_per_unit > risk_cap:
                continue

        risk_R = 1.0
        sl_ticks = risk_per_unit / tick_size if tick_size > 0 else np.nan

        slip_ticks = 0.0
        if tick_size > 0:
            slip_ticks = (entry_price - raw_price) / tick_size

        micro_dir = int(row.get("micro_break_dir", 0) or 0)
        engulf_dir = int(row.get("engulf_dir", 0) or 0)
        trigger_type = "unknown"
        if dir_val > 0:
            if micro_dir > 0:
                trigger_type = "swingbreak"
            elif engulf_dir > 0:
                trigger_type = "engulf"
        else:
            if micro_dir < 0:
                trigger_type = "swingbreak"
            elif engulf_dir < 0:
                trigger_type = "engulf"

        vwap = float(row.get("vwap", np.nan))
        v1u = float(row.get("vwap_1u", np.nan))
        v1d = float(row.get("vwap_1d", np.nan))
        location = "none"
        if np.isfinite(vwap):
            price = float(row.get("close", np.nan))
            if np.isfinite(price):
                if dir_val > 0:
                    if np.isfinite(v1u) and vwap <= price <= v1u:
                        location = (
                            "vwap"
                            if abs(price - vwap) <= abs(price - v1u)
                            else "+1sigma"
                        )
                else:
                    if np.isfinite(v1d) and v1d <= price <= vwap:
                        location = (
                            "vwap"
                            if abs(price - vwap) <= abs(price - v1d)
                            else "-1sigma"
                        )

        exit_time = pd.NaT
        realized_R = 0.0
        tp1_price = entry_price + side_sign * risk_per_unit * 1.0
        tp2_price = entry_price + side_sign * risk_per_unit * 2.0
        t_to_tp1_min = np.nan
        time_stop_reason = "none"

        entry_time = fill_ts
        trade_date = entry_time.date()

        if use_management and mgmt_cfg and time_cfg:
            if trade_date not in session_cache:
                idx_all = mkt_idx
                mask_session = idx_all.date == trade_date

                session_df = mkt.loc[mask_session].copy()

                for c in feature_cols_needed:
                    if c not in session_df.columns and c in sig.columns:
                        session_df[c] = sig.loc[mask_session, c]

                session_cache[trade_date] = session_df

            session_df = session_cache[trade_date]

            entry_idx_arr = session_df.index.get_indexer(pd.DatetimeIndex([entry_time]))
            entry_idx = int(entry_idx_arr[0]) if len(entry_idx_arr) else -1
            if entry_idx < 0:
                continue

            pdh = float(row.get("pdh", np.nan))
            pdl = float(row.get("pdl", np.nan))
            refs = {
                "pdh": pdh if np.isfinite(pdh) else 0.0,
                "pdl": pdl if np.isfinite(pdl) else 0.0,
                "or_height": float(or_height) if np.isfinite(or_height) else 0.0,
            }

            conds = build_time_stop_condition_series(
                session_df=session_df,
                entry_idx=entry_idx,
                side_sign=side_sign,
                entry_price=float(entry_price),
                stop_price=float(stop),
            )

            lifecycle = manage_trade_lifecycle(
                bars=session_df,
                entry_idx=entry_idx,
                side=side_sign,
                entry_price=float(entry_price),
                stop_price=float(stop),
                mgmt_cfg=mgmt_cfg,
                time_cfg=time_cfg,
                refs=refs,
                vwap_side_ok=conds.vwap_side_ok,
                trend_ok=conds.trend_ok,
                sigma_ok=conds.sigma_ok,
                dd_ok=conds.dd_ok,
            )

            exit_time = lifecycle["exit_time"]
            realized_R = float(lifecycle["realized_R"])
            tp1_price = float(lifecycle["tp1_price"])
            tp2_price = (
                float(lifecycle["tp2_price"])
                if lifecycle["tp2_price"] is not None
                else tp2_price
            )
            t_to_tp1_min = (
                float(lifecycle["t_to_tp1_min"])
                if lifecycle["t_to_tp1_min"] is not None
                else np.nan
            )
            time_stop_reason = lifecycle["time_stop_reason"] or "none"

        records.append(
            {
                "date": trade_date,
                "signal_time": ts_idx,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "side": side_lit,
                "entry": float(entry_price),
                "stop": float(stop),
                "tp1": float(tp1_price),
                "tp2": float(tp2_price),
                "or_height": float(or_height) if np.isfinite(or_height) else np.nan,
                "sl_ticks": float(sl_ticks) if np.isfinite(sl_ticks) else np.nan,
                "risk_R": float(risk_R),
                "realized_R": float(realized_R),
                "t_to_tp1_min": t_to_tp1_min,
                "trigger_type": trigger_type,
                "location": location,
                "time_stop": time_stop_reason,
                "disqualifier": "none",
                "slippage_entry_ticks": float(slip_ticks),
                "slippage_exit_ticks": 0.0,
            }
        )

    if not records:
        return pd.DataFrame(columns=_TRADE_COLS)

    trades = pd.DataFrame.from_records(records)
    for col in _TRADE_COLS:
        if col not in trades:
            trades[col] = np.nan

    return trades[_TRADE_COLS]


def generate_signals(
    df_1m: pd.DataFrame,
    df_5m: pd.DataFrame | None = None,
    cfg: Any | None = None,
) -> pd.DataFrame:
    """
    Computes all signal columns (Unlock, Zone, Trigger) in a vectorized manner.
    """
    out = df_1m.copy()

    std_defaults: dict[str, object] = {
        "time_window_ok": True,
        "or_break_unlock": False,
        "in_zone": False,
        "trigger_ok": False,
        "disqualified_2sigma": False,
        "direction": 0,
        "stop_price": np.nan,
    }
    for col, val in std_defaults.items():
        if col not in out:
            out[col] = cast(Any, val)

    idx = cast(pd.DatetimeIndex, out.index)
    if idx.tz is not None:
        idx_et = idx.tz_convert("America/New_York")
    else:
        idx_et = idx
    dates = pd.Index(idx_et.date, name="date")
    times = idx_et.time

    if (
        "trend_5m" not in out.columns
        and df_5m is not None
        and "trend_5m" in df_5m.columns
    ):
        out["trend_5m"] = df_5m["trend_5m"].reindex(out.index, method="ffill")
    if (
        "trend_dir_5m" not in out.columns
        and df_5m is not None
        and "trend_dir_5m" in df_5m.columns
    ):
        out["trend_dir_5m"] = df_5m["trend_dir_5m"].reindex(out.index, method="ffill")

    required = {
        "close",
        "or_high",
        "or_low",
        "vwap",
        "vwap_1u",
        "vwap_1d",
        "vwap_2u",
        "vwap_2d",
        "trend_5m",
    }
    if not required.issubset(out.columns):
        return out

    close = out["close"].astype(float)
    orh = out["or_high"].astype(float)
    orl = out["or_low"].astype(float)
    vwap = out["vwap"].astype(float)
    v1u = out["vwap_1u"].astype(float)
    v1d = out["vwap_1d"].astype(float)
    v2u = out["vwap_2u"].astype(float)
    v2d = out["vwap_2d"].astype(float)
    trend = out["trend_5m"].astype(float)

    ew = getattr(cfg, "entry_window", None) if cfg is not None else None
    if ew is None:
        time_ok = pd.Series(True, index=out.index)
    else:
        start_time = pd.Timestamp(getattr(ew, "start", "09:35")).time()
        end_time = pd.Timestamp(getattr(ew, "end", "11:00")).time()
        time_ok = pd.Series(
            (times >= start_time) & (times <= end_time), index=out.index
        )
    out["time_window_ok"] = time_ok

    is_long_trend = trend > 0
    is_short_trend = trend < 0

    dir_series = pd.Series(
        np.where(is_long_trend, 1, np.where(is_short_trend, -1, 0)).astype("int8"),
        index=out.index,
    )
    out["direction"] = dir_series

    breaks_long = close > orh
    breaks_short = close < orl
    above_vwap = close >= vwap
    below_vwap = close <= vwap

    long_unlock_raw = is_long_trend & breaks_long & above_vwap & time_ok
    short_unlock_raw = is_short_trend & breaks_short & below_vwap & time_ok
    unlock_raw = pd.Series(
        (long_unlock_raw | short_unlock_raw).astype(bool), index=out.index
    )

    out["unlocked"] = unlock_raw.groupby(dates).cummax()
    prev = unlock_raw.groupby(dates).shift(1, fill_value=False)
    out["or_break_unlock"] = unlock_raw & ~prev

    hit_opp_long = is_long_trend & (close <= v2d)
    hit_opp_short = is_short_trend & (close >= v2u)
    hit_opp = (hit_opp_long | hit_opp_short).astype(bool)

    rules = getattr(cfg, "signals", None) if cfg is not None else None
    disq_after_unlock = bool(getattr(rules, "disqualify_after_unlock", False))

    unlocked = out.get("unlocked", pd.Series(False, index=out.index)).astype(bool)
    hit_for_disq = (hit_opp & unlocked) if disq_after_unlock else hit_opp

    disq = hit_for_disq.groupby(dates).cummax().astype(bool)
    out["disqualified_2sigma"] = disq

    direction = out["direction"].astype("int8")
    unlock_event = out["or_break_unlock"].astype(bool)
    unlocked = out.get("unlocked", unlock_event).astype(bool)
    disq = out["disqualified_2sigma"].astype(bool)

    zone_touch_mode = str(getattr(rules, "zone_touch_mode", "close")).lower()

    if zone_touch_mode == "range" and {"high", "low"}.issubset(out.columns):
        hi = out["high"].astype(float)
        lo = out["low"].astype(float)
        long_zone_touch = (lo <= v1u) & (hi >= vwap)
        short_zone_touch = (hi >= v1d) & (lo <= vwap)
    else:
        long_zone_touch = (close >= vwap) & (close <= v1u)
        short_zone_touch = (close <= vwap) & (close >= v1d)

    zone_touch = ((direction > 0) & long_zone_touch) | (
        (direction < 0) & short_zone_touch
    )

    zone_candidate = (unlocked & ~unlock_event & ~disq & zone_touch).astype(bool)

    zone_count = zone_candidate.groupby(dates).cumsum()
    in_zone = (zone_count == 1) & zone_candidate

    out["in_zone"] = in_zone.astype(bool)

    micro_raw = (
        out["micro_break_dir"]
        if "micro_break_dir" in out.columns
        else pd.Series(0, index=out.index)
    )
    engulf_raw = (
        out["engulf_dir"]
        if "engulf_dir" in out.columns
        else pd.Series(0, index=out.index)
    )

    micro_dir = pd.to_numeric(micro_raw, errors="coerce").fillna(0).astype("int8")
    engulf_dir = pd.to_numeric(engulf_raw, errors="coerce").fillna(0).astype("int8")

    in_zone = out["in_zone"].astype(bool)
    zone_seen = in_zone.groupby(dates).cummax().astype(bool)

    lookback = int(getattr(rules, "trigger_lookback_bars", 2))
    lookback = max(0, min(lookback, 10))

    zone_recent = in_zone.copy()
    for k in range(1, lookback + 1):
        zone_recent = zone_recent | in_zone.groupby(dates).shift(
            k, fill_value=False
        ).astype(bool)

    direction = out["direction"].astype("int8")
    pattern_ok = ((micro_dir != 0) & (micro_dir == direction)) | (
        (engulf_dir != 0) & (engulf_dir == direction)
    )

    time_ok = out["time_window_ok"].astype(bool)
    disq = out["disqualified_2sigma"].astype(bool)

    out["trigger_ok"] = (
        (direction != 0) & zone_seen & zone_recent & pattern_ok & time_ok & ~disq
    )

    tick_size = 1.0
    inst = getattr(cfg, "instrument", None) if cfg is not None else None
    tick_size = float(getattr(inst, "tick_size", tick_size) or tick_size)

    if hasattr(cfg, "slippage"):
        slip = getattr(cfg, "slippage")
        tick_size = float(getattr(slip, "tick_size", tick_size) or tick_size)

    max_mult = 1.25
    risk_cfg = getattr(cfg, "risk", None) if cfg is not None else None
    max_mult = float(getattr(risk_cfg, "max_stop_or_mult", max_mult) or max_mult)

    if "or_height" not in out.columns:
        out["or_height"] = out["or_high"].astype(float) - out["or_low"].astype(float)

    if "stop_price" in out.columns:
        stop_price = pd.to_numeric(out["stop_price"], errors="coerce").astype(float)
    else:
        stop_price = pd.Series(np.nan, index=out.index, dtype=float)

    direction = out["direction"].astype("int8")

    if "last_swing_low_price" in out.columns and "last_swing_high_price" in out.columns:
        last_swing_lo = out["last_swing_low_price"].astype(float)
        last_swing_hi = out["last_swing_high_price"].astype(float)

        cand_stop = pd.Series(np.nan, index=out.index, dtype=float)
        longs = direction > 0
        shorts = direction < 0

        cand_stop.loc[longs] = last_swing_lo.loc[longs] - tick_size
        cand_stop.loc[shorts] = last_swing_hi.loc[shorts] + tick_size

        stop_price = stop_price.where(stop_price.notna(), cand_stop)

    out["stop_price"] = stop_price

    return out
