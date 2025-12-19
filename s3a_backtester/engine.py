# 3A Engine
# Strategy 3A Brain + State Machine
from __future__ import annotations
from typing import Any
from datetime import date
from .config import Config
from .slippage import apply_slippage
from .management import manage_trade_lifecycle
from .filters import build_session_filter_mask
from .time_stop_conditions import build_time_stop_condition_series

import pandas as pd
import numpy as np

_TRADE_COLS = [
    "date",
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


# ----------------------------------------------
# Simluation for Trades
# ----------------------------------------------
def simulate_trades(
    df1: pd.DataFrame, signals: pd.DataFrame, cfg: Config | None
) -> pd.DataFrame:
    """
    Simulate 3A trades, including entry, management, and exits.

    We assume `signals` is the 1-minute DataFrame returned by `generate_signals`,
    i.e. it already contains OHLCV plus:
        - direction        (+1 long, -1 short, 0 flat)
        - trigger_ok       (bool)
        - riskcap_ok       (bool)
        - time_window_ok   (bool)
        - disqualified_2sigma (bool)
        - stop_price       (float)
        - or_high / or_low (float)
        - vwap, vwap_1u, vwap_1d
        - micro_break_dir, engulf_dir (optional)

    This function:
        - filters valid entry bars
        - applies slippage on entry using `apply_slippage`
        - computes R distance and TP1/TP2
        - if management config is present, runs full lifecycle:
            TP1 scale-out, BE move, TP2, time-stop,
            and writes realized_R / exit_time.
        - returns a normalized trade log DataFrame.
    """
    # Work off the signals frame; df1 is kept for signature compatibility.
    if signals is None or signals.empty:
        return pd.DataFrame(columns=_TRADE_COLS)

    df = signals.copy()

    # Ensure expected columns exist with safe defaults.
    defaults: dict[str, object] = {
        "direction": 0,
        "trigger_ok": False,
        "riskcap_ok": True,
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
            df[col] = val

    # Direction flags
    direction = pd.to_numeric(df["direction"], errors="coerce").fillna(0).astype(int)

    # Candidate entries: direction present, trigger, riskcap, time window, not disqualified.
    mask = (
        direction.ne(0)
        & df["trigger_ok"].astype(bool)
        & df["riskcap_ok"].astype(bool)
        & df["time_window_ok"].astype(bool)
        & ~df["disqualified_2sigma"].astype(bool)
    )

    # Session-level filters (tiny-day, low ATR, news blackout, DOM)
    filters_cfg = getattr(cfg, "filters", None) if cfg is not None else None
    if filters_cfg is not None:
        session_mask = build_session_filter_mask(df, filters_cfg)
        mask &= session_mask

    entries = df[mask].copy()
    if entries.empty:
        return pd.DataFrame(columns=_TRADE_COLS)

    # Tick size resolution
    tick_size = 0.25  # sensible default for NQ/ES
    mgmt_cfg = None
    time_cfg = None
    if cfg is not None:
        tick_size = getattr(cfg, "tick_size", tick_size)
        inst = getattr(cfg, "instrument", None)
        if inst is not None:
            tick_size = getattr(inst, "tick_size", tick_size)
        mgmt_cfg = getattr(cfg, "management", None)
        time_cfg = getattr(cfg, "time_stop", None)

    tick_size = float(tick_size) if tick_size else 0.25
    use_management = mgmt_cfg is not None and time_cfg is not None

    records: list[dict[str, object]] = []

    # Cache per-session views so we don't slice df on every trade.
    session_cache: dict[date, pd.DataFrame] = {}

    for ts, row in entries.iterrows():
        dir_val = int(row["direction"])
        if dir_val == 0:
            continue

        side = "long" if dir_val > 0 else "short"
        side_sign = 1 if dir_val > 0 else -1

        raw_price = float(row["close"])
        stop = float(row["stop_price"]) if pd.notna(row["stop_price"]) else np.nan
        if not np.isfinite(stop):
            # Without a valid stop we cannot define R; skip this bar.
            continue

        # Apply slippage on entry
        entry_price = apply_slippage(side, ts, raw_price, cfg)

        risk_per_unit = abs(entry_price - stop)
        if risk_per_unit <= 0:
            # Degenerate; skip
            continue

        # Planned R per trade (in R-space; sizing is a later concern)
        risk_R = 1.0

        # OR height for logging
        or_high = float(row.get("or_high", np.nan))
        or_low = float(row.get("or_low", np.nan))
        or_height = (
            or_high - or_low if np.isfinite(or_high) and np.isfinite(or_low) else np.nan
        )

        # SL in ticks
        sl_ticks = risk_per_unit / tick_size if tick_size > 0 else np.nan

        # Slippage in ticks at entry (signed adverse ticks)
        slip_ticks = 0.0
        if tick_size > 0:
            slip_ticks = (entry_price - raw_price) / tick_size

        # Trigger type heuristic
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

        # Location: coarse classification relative to VWAP bands
        vwap = float(row.get("vwap", np.nan))
        v1u = float(row.get("vwap_1u", np.nan))
        v1d = float(row.get("vwap_1d", np.nan))
        location = "none"
        if np.isfinite(vwap):
            price = float(row["close"])
            if dir_val > 0:
                # Long: VWAP / +1σ zone
                if np.isfinite(v1u) and vwap <= price <= v1u:
                    location = (
                        "vwap" if abs(price - vwap) <= abs(price - v1u) else "+1σ"
                    )
            else:
                # Short: VWAP / -1σ zone
                if np.isfinite(v1d) and v1d <= price <= vwap:
                    location = (
                        "vwap" if abs(price - vwap) <= abs(price - v1d) else "-1σ"
                    )

        # ---- Management & exits ----
        exit_time = pd.NaT
        realized_R = 0.0
        tp1_price = entry_price + side_sign * risk_per_unit * 1.0
        tp2_price = entry_price + side_sign * risk_per_unit * 2.0
        t_to_tp1_min = np.nan
        time_stop_reason = "none"

        if use_management:
            trade_date = ts.date()
            if trade_date not in session_cache:
                # Session-scoped slice: all bars for that trading day
                mask_session = df.index.date == trade_date
                session_cache[trade_date] = df.loc[mask_session]

            session_df = session_cache[trade_date]
            # locate entry within that session
            try:
                entry_idx = session_df.index.get_loc(ts)
            except KeyError:
                # Shouldn't happen if signals are consistent, but be defensive
                entry_idx = 0

            # build refs for TP2
            pdh = float(row.get("pdh", np.nan))
            pdl = float(row.get("pdl", np.nan))
            refs = {
                "pdh": pdh if np.isfinite(pdh) else None,
                "pdl": pdl if np.isfinite(pdl) else None,
                "or_height": or_height if np.isfinite(or_height) else None,
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
                "date": ts.date(),
                "entry_time": ts,
                "exit_time": exit_time,
                "side": side,
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
                "slippage_exit_ticks": 0.0,  # exit slippage model can be added later
            }
        )

    if not records:
        return pd.DataFrame(columns=_TRADE_COLS)

    trades = pd.DataFrame.from_records(records)

    # Enforce column order / presence as per schema
    for col in _TRADE_COLS:
        if col not in trades:
            trades[col] = np.nan

    trades = trades[_TRADE_COLS]
    return trades


# ----------------------------------------------
# Signal Generation for 3A
# ----------------------------------------------
def generate_signals(
    df_1m: pd.DataFrame,
    df_5m: pd.DataFrame | None = None,
    cfg: Any | None = None,
) -> pd.DataFrame:
    """
    Core 3A signal engine.

    Works in two modes:
    - Stub mode: if OR/VWAP/trend columns are missing, just ensure the standard
      signal columns exist and return.
    - Full mode: when all required feature columns are present, compute
      unlock / zone / trigger / risk-cap flags in the way the tests expect.
    """
    out = df_1m.copy()

    # ------------------------------------------------------------------
    # Standard columns (for both stub & full modes)
    # ------------------------------------------------------------------
    std_defaults: dict[str, object] = {
        "time_window_ok": True,
        "or_break_unlock": False,
        "in_zone": False,
        "trigger_ok": False,
        "disqualified_±2σ": False,
        "disqualified_2sigma": False,
        "riskcap_ok": True,
        "direction": 0,
        "stop_price": np.nan,
    }
    for col, val in std_defaults.items():
        if col not in out:
            out[col] = val

    # --- Safe Apply Wrapper ---
    def _safe_apply(builder, frame: pd.DataFrame, *args, **kwargs) -> pd.DataFrame:
        """Call a feature builder that might return None (in-place mutation)."""
        res = builder(frame, *args, **kwargs)
        return frame if res is None else res

    # --- Make sure index is ET for session grouping ---
    idx = out.index
    if getattr(idx, "tz", None) is not None:
        idx_et = idx.tz_convert("America/New_York")
    else:
        idx_et = idx
    dates = pd.Index(idx_et.date, name="date")
    times = idx_et.time

    # ------------------------------------------------------------------
    # (Optional) try to build missing features if you have builders imported
    # IMPORTANT: do NOT let out become None
    # ------------------------------------------------------------------
    # Example (only if you actually have these imported):
    # if "or_high" not in out.columns or "or_low" not in out.columns:
    #     out = _safe_apply(compute_session_refs, out)
    # if "vwap" not in out.columns or "vwap_1u" not in out.columns:
    #     out = _safe_apply(compute_session_vwap_bands, out)

    # If trend is provided on df_5m, align it (tests often pass df_5m=None)
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

    # ------------------------------------------------------------------
    # Decide whether we have enough columns for FULL logic
    # ------------------------------------------------------------------
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
        # Stub path: just return with the standard columns present.
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

    # ------------------------------------------------------------------
    # 1) Time window
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 2) Direction + first unlock event
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 3) Opposite 2σ disqualifier (session-scoped cumulative)
    # ------------------------------------------------------------------
    hit_opp_long = is_long_trend & (close <= v2d)
    hit_opp_short = is_short_trend & (close >= v2u)
    hit_opp = (hit_opp_long | hit_opp_short).astype(bool)

    # Optional: relax for real runs ONLY (defaults keep tests the same)
    rules = getattr(cfg, "signals", None) if cfg is not None else None
    disq_after_unlock = bool(getattr(rules, "disqualify_after_unlock", False))

    unlocked = out.get("unlocked", pd.Series(False, index=out.index)).astype(bool)
    hit_for_disq = (hit_opp & unlocked) if disq_after_unlock else hit_opp

    disq = hit_for_disq.groupby(dates).cummax().astype(bool)
    out["disqualified_2sigma"] = disq
    out["disqualified_±2σ"] = disq  # backwards compatibility

    # ------------------------------------------------------------------
    # 4) Zone: first pullback into VWAP±1σ after unlock (one event per day)
    # ------------------------------------------------------------------
    direction = out["direction"].astype("int8")
    unlock_event = out["or_break_unlock"].astype(bool)  # event
    unlocked = out.get("unlocked", unlock_event).astype(bool)  # state fallback
    disq = out["disqualified_2sigma"].astype(bool)

    # Optional: "range" zone touch for real runs (defaults keep tests the same)
    zone_touch_mode = str(getattr(rules, "zone_touch_mode", "close")).lower()

    if zone_touch_mode == "range" and {"high", "low"}.issubset(out.columns):
        hi = out["high"].astype(float)
        lo = out["low"].astype(float)
        long_zone_touch = (lo <= v1u) & (hi >= vwap)
        short_zone_touch = (hi >= v1d) & (lo <= vwap)
    else:
        # test-compatible default: close-based touch
        long_zone_touch = (close >= vwap) & (close <= v1u)
        short_zone_touch = (close <= vwap) & (close >= v1d)

    zone_touch = ((direction > 0) & long_zone_touch) | (
        (direction < 0) & short_zone_touch
    )

    # must be AFTER unlock bar, must not already be disqualified on that bar
    zone_candidate = (unlocked & ~unlock_event & ~disq & zone_touch).astype(bool)

    # exactly one zone event per session/day:
    # cumsum==1 "sticks" after the first True, so we MUST AND with zone_candidate
    zone_count = zone_candidate.groupby(dates).cumsum()
    in_zone = (zone_count == 1) & zone_candidate

    out["in_zone"] = in_zone.astype(bool)

    # ------------------------------------------------------------------
    # 5) Trigger: micro-break or engulf after zone touch (breakout bar allowed)
    # ------------------------------------------------------------------
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

    # Optional: widen trigger lookback for real runs (defaults keep tests the same)
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

    # ------------------------------------------------------------------
    # 6) Stop + risk-cap
    #     - Keep any pre-set stop_price (tests sometimes set it)
    #     - If missing, infer from latest swing (session-scoped)
    #     - riskcap_ok is evaluated on any bar where stop_price is known
    # ------------------------------------------------------------------
    tick_size = 1.0
    inst = getattr(cfg, "instrument", None) if cfg is not None else None
    tick_size = float(getattr(inst, "tick_size", tick_size) or tick_size)

    max_mult = 1.25
    risk_cfg = getattr(cfg, "risk", None) if cfg is not None else None
    max_mult = float(getattr(risk_cfg, "max_stop_or_mult", max_mult) or max_mult)

    # Ensure or_height exists
    if "or_height" not in out.columns:
        out["or_height"] = out["or_high"].astype(float) - out["or_low"].astype(float)

    # Start from existing stop_price if present; DO NOT overwrite test-provided stops
    if "stop_price" in out.columns:
        stop_price = pd.to_numeric(out["stop_price"], errors="coerce").astype(float)
    else:
        stop_price = pd.Series(np.nan, index=out.index, dtype=float)

    direction = out["direction"].astype("int8")

    # ---- infer missing stops from swings (if swing markers exist) ----
    if (
        ("swing_lo" in out.columns)
        or ("swing_low" in out.columns)
        or ("swing_hi" in out.columns)
        or ("swing_high" in out.columns)
    ):
        # resolve swing marker columns
        swing_lo = (
            out["swing_lo"].astype(bool)
            if "swing_lo" in out.columns
            else (
                out["swing_low"].astype(bool)
                if "swing_low" in out.columns
                else pd.Series(False, index=out.index)
            )
        )
        swing_hi = (
            out["swing_hi"].astype(bool)
            if "swing_hi" in out.columns
            else (
                out["swing_high"].astype(bool)
                if "swing_high" in out.columns
                else pd.Series(False, index=out.index)
            )
        )

        # session-scoped latest swing values
        last_swing_lo = out["low"].where(swing_lo).groupby(dates).ffill()
        last_swing_hi = out["high"].where(swing_hi).groupby(dates).ffill()

        cand_stop = pd.Series(np.nan, index=out.index, dtype=float)
        longs = direction > 0
        shorts = direction < 0
        cand_stop.loc[longs] = (last_swing_lo.loc[longs] - tick_size).astype(float)
        cand_stop.loc[shorts] = (last_swing_hi.loc[shorts] + tick_size).astype(float)

        # only fill missing
        stop_price = stop_price.where(stop_price.notna(), cand_stop)

    # ---- risk-cap (evaluate whenever stop exists) ----
    entry_px = out["close"].astype(float)
    or_h = out["or_height"].astype(float).abs()
    cap = max_mult * or_h

    risk_dist = pd.Series(np.nan, index=out.index, dtype=float)
    longs = direction > 0
    shorts = direction < 0
    risk_dist.loc[longs] = entry_px.loc[longs] - stop_price.loc[longs]
    risk_dist.loc[shorts] = stop_price.loc[shorts] - entry_px.loc[shorts]

    cap_ok = stop_price.notna() & (risk_dist > 0) & (risk_dist <= cap)

    # If stop is unknown, we leave riskcap_ok=True (not evaluated yet).
    riskcap_ok = stop_price.isna() | cap_ok

    out["stop_price"] = stop_price
    out["riskcap_ok"] = riskcap_ok.astype(bool)

    return out
