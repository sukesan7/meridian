# 3A Engine
# Strategy 3A Brain + State Machine
from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Any
from .config import Config
from .slippage import apply_slippage

_SIGNAL_COLS = [
    "time_window_ok",
    "or_break_unlock",
    "in_zone",
    "trigger_ok",
    "disqualified_±2σ",
    "riskcap_ok",
]

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
    Entry-only simulation for 3A.

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

    entries = df[mask].copy()
    if entries.empty:
        return pd.DataFrame(columns=_TRADE_COLS)

    # Tick size resolution
    tick_size = 0.25  # sensible default for NQ/ES
    if cfg is not None:
        tick_size = getattr(cfg, "tick_size", tick_size)
        inst = getattr(cfg, "instrument", None)
        if inst is not None:
            tick_size = getattr(inst, "tick_size", tick_size)
    tick_size = float(tick_size) if tick_size else 0.25

    records: list[dict[str, object]] = []

    for ts, row in entries.iterrows():
        dir_val = int(row["direction"])
        if dir_val == 0:
            continue

        side = "long" if dir_val > 0 else "short"

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

        # TP1 / TP2 in price terms
        direction_sign = 1.0 if dir_val > 0 else -1.0
        tp1 = entry_price + direction_sign * risk_per_unit * 1.0
        tp2 = entry_price + direction_sign * risk_per_unit * 2.0

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
            # could also take abs() if you want strictly non-negative

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
                    # choose label by proximity
                    location = (
                        "vwap" if abs(price - vwap) <= abs(price - v1u) else "+1σ"
                    )
            else:
                # Short: VWAP / -1σ zone
                if np.isfinite(v1d) and v1d <= price <= vwap:
                    location = (
                        "vwap" if abs(price - vwap) <= abs(price - v1d) else "-1σ"
                    )

        records.append(
            {
                "date": ts.date(),
                "entry_time": ts,
                "exit_time": pd.NaT,  # exits/time stops come later
                "side": side,
                "entry": float(entry_price),
                "stop": float(stop),
                "tp1": float(tp1),
                "tp2": float(tp2),
                "or_height": float(or_height) if np.isfinite(or_height) else np.nan,
                "sl_ticks": float(sl_ticks) if np.isfinite(sl_ticks) else np.nan,
                "risk_R": float(risk_R),
                "realized_R": 0.0,  # populated once exits are implemented
                "t_to_tp1_min": np.nan,
                "trigger_type": trigger_type,
                "location": location,
                "time_stop": "none",
                "disqualifier": "none",
                "slippage_entry_ticks": float(slip_ticks),
                "slippage_exit_ticks": 0.0,
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
    # 1) Time window (entry_window from cfg, or all True if no cfg)
    # ------------------------------------------------------------------
    idx = out.index
    if getattr(idx, "tz", None) is not None:
        idx_et = idx.tz_convert("America/New_York")
    else:
        idx_et = idx

    times = idx_et.time
    dates = pd.Index(idx_et.date, name="date")

    ew = getattr(cfg, "entry_window", None) if cfg is not None else None
    if ew is None:
        # Tests without cfg expect all bars to be time_window_ok == True
        time_ok = pd.Series(True, index=out.index)
    else:
        start_str = getattr(ew, "start", "09:35")
        end_str = getattr(ew, "end", "11:00")
        start_time = pd.Timestamp(start_str).time()
        end_time = pd.Timestamp(end_str).time()
        mask = (times >= start_time) & (times <= end_time)
        time_ok = pd.Series(mask, index=out.index)

    out["time_window_ok"] = time_ok

    # ------------------------------------------------------------------
    # 2) Direction (sign of trend) + OR break unlock
    # ------------------------------------------------------------------
    is_long_trend = trend > 0
    is_short_trend = trend < 0

    direction = np.where(is_long_trend, 1, np.where(is_short_trend, -1, 0)).astype(
        "int8"
    )
    out["direction"] = direction
    dir_series = out["direction"]

    breaks_long = close > orh
    breaks_short = close < orl
    above_vwap = close >= vwap
    below_vwap = close <= vwap

    long_unlock_raw = is_long_trend & breaks_long & above_vwap & time_ok
    short_unlock_raw = is_short_trend & breaks_short & below_vwap & time_ok
    unlock_raw = long_unlock_raw | short_unlock_raw

    unlock_count = pd.Series(unlock_raw, index=out.index).groupby(dates).cumsum()
    out["or_break_unlock"] = unlock_count.eq(1)

    # ------------------------------------------------------------------
    # 3) Opposite 2σ disqualifier (cumulative per day)
    # ------------------------------------------------------------------
    hit_opp_long = is_long_trend & (close <= v2d)  # long trend → watch lower band
    hit_opp_short = is_short_trend & (close >= v2u)  # short trend → watch upper band
    hit_opp = hit_opp_long | hit_opp_short

    disq = pd.Series(hit_opp, index=out.index).groupby(dates).cumsum().astype(bool)

    out["disqualified_2sigma"] = disq
    out["disqualified_±2σ"] = disq

    # ------------------------------------------------------------------
    # 4) Zone: first pullback into VWAP±1σ after unlock, if not disqualified
    # ------------------------------------------------------------------
    in_zone = pd.Series(False, index=out.index)

    for day_key, day in out.groupby(dates):
        unlock_mask = day["or_break_unlock"].astype(bool)
        if not unlock_mask.any():
            continue

        # If session is disqualified at any point, no zone is ever marked.
        if day["disqualified_2sigma"].any():
            continue

        unlock_ts = unlock_mask[unlock_mask].index[0]
        dir_val = int(day.loc[unlock_ts, "direction"])
        if dir_val == 0:
            continue

        after = day.loc[day.index > unlock_ts]
        if after.empty:
            continue

        if dir_val > 0:
            zone_mask = (after["close"] >= after["vwap"]) & (
                after["close"] <= after["vwap_1u"]
            )
        else:
            zone_mask = (after["close"] <= after["vwap"]) & (
                after["close"] >= after["vwap_1d"]
            )

        if not zone_mask.any():
            continue

        zone_ts = zone_mask[zone_mask].index[0]
        in_zone.loc[zone_ts] = True

    out["in_zone"] = in_zone

    # ------------------------------------------------------------------
    # 5) Trigger logic: engulf or micro-swing break at / near the zone
    # ------------------------------------------------------------------
    direction = out["direction"].astype("int8")

    # Pattern signals (use Series defaults, not scalars)
    if "micro_break_dir" in out.columns:
        micro_raw = out["micro_break_dir"]
    else:
        micro_raw = pd.Series(0, index=out.index)

    if "engulf_dir" in out.columns:
        engulf_raw = out["engulf_dir"]
    else:
        engulf_raw = pd.Series(0, index=out.index)

    micro_dir = pd.to_numeric(micro_raw, errors="coerce").fillna(0).astype("int8")
    engulf_dir = pd.to_numeric(engulf_raw, errors="coerce").fillna(0).astype("int8")

    # Once zone has been touched in a session, we are "armed"
    # `dates` is the ET date index we built earlier.
    zone_seen = out["in_zone"].astype(bool).groupby(dates).cummax()

    # Tick size for the "≤ 1 tick beyond band" rule
    tick_size = 1.0
    if cfg is not None:
        inst = getattr(cfg, "instrument", None)
        tick_size = getattr(inst, "tick_size", tick_size) or tick_size

    close = out["close"].astype(float)
    vwap = out["vwap"].astype(float)
    v1u = out["vwap_1u"].astype(float)
    v1d = out["vwap_1d"].astype(float)

    # Long side: inside [VWAP, +1σ] OR up to 1 tick above +1σ
    long_core = (direction > 0) & zone_seen & (close >= vwap) & (close <= v1u)
    long_plus = (direction > 0) & zone_seen & (close > v1u) & (close <= v1u + tick_size)
    long_near_zone = long_core | long_plus

    # Short side: inside [VWAP, -1σ] OR up to 1 tick below -1σ
    short_core = (direction < 0) & zone_seen & (close <= vwap) & (close >= v1d)
    short_plus = (
        (direction < 0) & zone_seen & (close < v1d) & (close >= v1d - tick_size)
    )
    short_near_zone = short_core | short_plus

    # Pattern must be in trade direction
    long_pattern = (micro_dir > 0) | (engulf_dir > 0)
    short_pattern = (micro_dir < 0) | (engulf_dir < 0)

    long_trig = (
        (direction > 0)
        & long_pattern
        & long_near_zone
        & out["time_window_ok"].astype(bool)
        & ~out["disqualified_2sigma"].astype(bool)
    )

    short_trig = (
        (direction < 0)
        & short_pattern
        & short_near_zone
        & out["time_window_ok"].astype(bool)
        & ~out["disqualified_2sigma"].astype(bool)
    )

    out["trigger_ok"] = long_trig | short_trig

    # ------------------------------------------------------------------
    # 6) Risk cap + stop_price (based on last swing)
    # ------------------------------------------------------------------
    tick_size = 0.25
    cap_mult = 1.25
    if cfg is not None:
        tick_size = getattr(cfg, "tick_size", tick_size) or tick_size
        cap_mult = getattr(cfg, "risk_cap_multiple", cap_mult) or cap_mult
    tick_size = float(tick_size)

    or_height = (orh - orl).abs()
    max_sl_dist = or_height * cap_mult

    swing_low_flag = (
        out["swing_low"].astype(bool)
        if "swing_low" in out.columns
        else pd.Series(False, index=out.index)
    )
    swing_high_flag = (
        out["swing_high"].astype(bool)
        if "swing_high" in out.columns
        else pd.Series(False, index=out.index)
    )

    last_swing_low = (
        out["low"].where(swing_low_flag).ffill()
        if "low" in out.columns
        else pd.Series(np.nan, index=out.index)
    )
    last_swing_high = (
        out["high"].where(swing_high_flag).ffill()
        if "high" in out.columns
        else pd.Series(np.nan, index=out.index)
    )

    stop_price = pd.Series(np.nan, index=out.index, dtype="float64")
    long_mask = dir_series > 0
    short_mask = dir_series < 0

    # Long: 1 tick below last swing low
    stop_price[long_mask] = last_swing_low[long_mask] - tick_size
    # Short: 1 tick above last swing high
    stop_price[short_mask] = last_swing_high[short_mask] + tick_size
    out["stop_price"] = stop_price

    sl_dist = pd.Series(np.nan, index=out.index, dtype="float64")
    sl_dist[long_mask] = close[long_mask] - stop_price[long_mask]
    sl_dist[short_mask] = stop_price[short_mask] - close[short_mask]

    # If stop_price is NaN, keep riskcap_ok == True (we don't have a valid stop yet)
    riskcap_ok = (~sl_dist.notna()) | (sl_dist <= max_sl_dist)
    out["riskcap_ok"] = riskcap_ok

    return out
