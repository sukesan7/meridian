# 3A Engine
# Strategy 3A Brain + State Machine
from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Any
from .config import Config

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


# Future place for actual trades, currently a stub
def simulate_trades(
    df1: pd.DataFrame, signals: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """
    Bar-close entries; management TBD.
    v0: return an empty but correctly-schematized DataFrame so downstream code/CLI works.
    """
    return pd.DataFrame(columns=_TRADE_COLS)


# Signal Generation for 3A
def generate_signals(
    df_1m: pd.DataFrame,
    df_5m: pd.DataFrame | None = None,
    cfg: Any | None = None,
) -> pd.DataFrame:
    out = df_1m.copy()

    # Ensure that the standard signal columns exist
    for col, default in [
        ("time_window_ok", True),
        ("or_break_unlock", False),
        ("in_zone", False),
        ("trigger_ok", True),
        ("disqualified_2sigma", False),
        ("disqualified_±2σ", False),
        ("riskcap_ok", True),
        ("direction", 0),  # +1 long, -1 short, 0 none
    ]:
        if col not in out:
            out[col] = default

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

    # Stub path: basic shape only, no feature logic
    if not required.issubset(out.columns):
        return out

    # ---------------------------------------------------------------
    # Index into dates + time_window_ok (acceptable condition for 3A)
    # Convert index to ET, pulling dates and clock times
    # ---------------------------------------------------------------
    idx = out.index
    if getattr(idx, "tz", None) is not None:
        idx_et = idx.tz_convert("America/New_York")
    else:
        idx_et = idx

    dates = pd.Index(idx_et.date, name="date")
    times = idx_et.time

    ew = getattr(cfg, "entry_window", None) if cfg is not None else None

    if ew is None:
        # No explicit entry window (unit tests), then all bars are allowed
        time_window = pd.Series(True, index=out.index)
    # create the actual 3A entry window
    else:
        start_str = getattr(ew, "start", "09:35")
        end_str = getattr(ew, "end", "11:00")
        start_time = pd.Timestamp(start_str).time()
        end_time = pd.Timestamp(end_str).time()
        mask = (times >= start_time) & (times <= end_time)
        time_window = pd.Series(mask, index=out.index)

    out["time_window_ok"] = time_window

    # ---------------------------------------------------------------
    # Direction & Unlock Logic
    # ---------------------------------------------------------------
    # figure out if we are in an uptrend or a downtrend for 5 min
    is_long_trend = out["trend_5m"] > 0
    is_short_trend = out["trend_5m"] < 0

    out.loc[is_long_trend, "direction"] = 1
    out.loc[is_short_trend, "direction"] = -1

    breaks_or_long = out["close"] > out["or_high"]
    breaks_or_short = out["close"] < out["or_low"]

    above_vwap = out["close"] >= out["vwap"]
    below_vwap = out["close"] <= out["vwap"]

    # inside window, 5-min trend upward, 1 min close > OR_high, and close >= VWAP (correct side)
    unlock_long = time_window & is_long_trend & breaks_or_long & above_vwap

    # inside window, 5-min trend downward, 1 min close < OR_low, and close <= VWAP (correct side)
    unlock_short = time_window & is_short_trend & breaks_or_short & below_vwap

    # combined
    unlock_raw = unlock_long | unlock_short

    # First unlock per session is real unlock
    unlock_order = unlock_raw.groupby(dates).cumsum()
    unlock_first = unlock_order.eq(1)
    out["or_break_unlock"] = unlock_first

    # ---------------------------------------------------------------
    # Opposite 2 sigma disqualifier (cumulative per day)
    # ---------------------------------------------------------------
    hit_opp_long = is_long_trend & (out["close"] <= out["vwap_2d"])
    hit_opp_short = is_short_trend & (out["close"] >= out["vwap_2u"])
    hit_opp = hit_opp_long | hit_opp_short

    disq = hit_opp.groupby(dates).cumsum().astype(bool)

    # Accept both σ and `sigma` labels
    out["disqualified_2sigma"] = disq
    out["disqualified_±2σ"] = disq

    # ---------------------------------------------------------------
    # Zone logic – first pullback into VWAP / +- 1 sigma after unlock
    # ---------------------------------------------------------------
    out["in_zone"] = False

    for date_val, grp in out.groupby(dates):
        # If there is no unlock, skip the session
        unlock_bars = grp.index[grp["or_break_unlock"]]
        if len(unlock_bars) == 0:
            continue

        # First unlock bar for the session
        unlock_ts = unlock_bars[0]
        dir_val = grp.loc[unlock_ts, "direction"]

        # Only look after the unlock bar
        after = grp.loc[grp.index > unlock_ts]
        if after.empty:
            continue

        if dir_val == 1:
            # Long: pullback down into [VWAP, +1 sigma]
            zone_mask = (
                (after["close"] >= after["vwap"])
                & (after["close"] <= after["vwap_1u"])
                & after["time_window_ok"]
                & (~after["disqualified_2sigma"])
            )
        elif dir_val == -1:
            # Short: pullback up into [-1 sigma, VWAP]
            zone_mask = (
                (after["close"] <= after["vwap"])
                & (after["close"] >= after["vwap_1d"])
                & after["time_window_ok"]
                & (~after["disqualified_2sigma"])
            )
        else:
            continue

        candidates = after[zone_mask]
        if not candidates.empty:
            zone_ts = candidates.index[0]  # first zone bar of the day
            out.loc[zone_ts, "in_zone"] = True  # mark exactly one bar

    # ------------------------------------------------------------------
    # Trigger logic: engulf or micro-swing break near the zone
    # ------------------------------------------------------------------
    # Ensure column exists even if inputs are missing these features
    if "trigger_ok" not in out:
        out["trigger_ok"] = False

    # Direction: 1 for long, -1 for short
    if "direction" not in out:
        out["direction"] = np.where(is_long_trend, 1, np.where(is_short_trend, -1, 0))

    # Pattern signals from structure.micro_swing_break
    micro_dir = out["micro_break_dir"].astype("int8") if "micro_break_dir" in out else 0
    engulf_dir = out["engulf_dir"].astype("int8") if "engulf_dir" in out else 0

    # Any pattern in the *trend* direction
    long_pattern = (micro_dir > 0) | (engulf_dir > 0)
    short_pattern = (micro_dir < 0) | (engulf_dir < 0)

    # Tick size (used for the "≤ 1 tick beyond zone" rule)
    tick_size = 1.0
    if cfg is not None:
        inst = getattr(cfg, "instrument", None)
        tick_size = getattr(inst, "tick_size", tick_size)

    close = out["close"]

    # Price near the long zone: inside [VWAP, +1σ] or up to 1 tick above +1σ
    long_zone_core = (close >= out["vwap"]) & (close <= out["vwap_1u"])
    long_zone_plus = (close > out["vwap_1u"]) & (close <= out["vwap_1u"] + tick_size)
    long_zone_ok = long_zone_core | long_zone_plus

    # Price near the short zone: inside [VWAP, -1σ] or up to 1 tick below -1σ
    short_zone_core = (close <= out["vwap"]) & (close >= out["vwap_1d"])
    short_zone_plus = (close < out["vwap_1d"]) & (close >= out["vwap_1d"] - tick_size)
    short_zone_ok = short_zone_core | short_zone_plus

    # trigger for longs
    long_trig = (
        (out["direction"] == 1)
        & long_pattern
        & long_zone_ok
        & out["time_window_ok"]
        & ~out["disqualified_2sigma"]
    )

    # trigger for shorts
    short_trig = (
        (out["direction"] == -1)
        & short_pattern
        & short_zone_ok
        & out["time_window_ok"]
        & ~out["disqualified_2sigma"]
    )

    out["trigger_ok"] = long_trig | short_trig

    # ------------------------------------------------------------------
    # Pre-entry: stop_price + riskcap_ok
    # ------------------------------------------------------------------
    # Defaults so older tests / minimal DataFrames don’t break.
    if "riskcap_ok" not in out:
        out["riskcap_ok"] = True
    if "stop_price" not in out:
        out["stop_price"] = np.nan

    needed = {"high", "low", "close", "or_high", "or_low", "swing_high", "swing_low"}
    if not needed.issubset(out.columns):
        # We don't have swing info or OR levels yet → nothing to do.
        return out

    # Latest swing highs/lows (1-min) carried forward per bar.
    last_swing_high = out["high"].where(out["swing_high"]).ffill()
    last_swing_low = out["low"].where(out["swing_low"]).ffill()

    # Direction for risk logic: use sign of 5-min trend.
    trend_sign = np.sign(out["trend_5m"].fillna(0.0))
    is_long = trend_sign > 0
    is_short = trend_sign < 0

    # Invalidation swing price: last swing low for longs, last swing high for shorts.
    invalidation = np.where(
        is_long,
        last_swing_low,
        np.where(is_short, last_swing_high, np.nan),
    )

    # Tick size: try to pull from cfg, otherwise fall back to a reasonable default.
    tick_size = 0.25  # sensible default for NQ/ES
    if cfg is not None:
        # Allow either cfg.tick_size or cfg.instrument.tick_size style configs.
        tick_size = getattr(cfg, "tick_size", tick_size)
        instr = getattr(cfg, "instrument", None)
        if instr is not None:
            tick_size = getattr(instr, "tick_size", tick_size)

    # Stop price: 1 tick beyond invalidation swing.
    stop_price = np.where(
        is_long,
        invalidation - tick_size,
        np.where(is_short, invalidation + tick_size, np.nan),
    )
    out["stop_price"] = stop_price

    # OR height per session (same all day, but computed per-bar for convenience).
    or_height = (out["or_high"] - out["or_low"]).groupby(dates).transform("first")

    # Risk-cap multiple: how many OR-heights we allow for SL distance.
    risk_cap_multiple = 1.25
    if cfg is not None:
        risk_cap_multiple = getattr(cfg, "risk_cap_multiple", risk_cap_multiple)

    # Stop-loss distance in price terms.
    sl_dist = (out["close"] - out["stop_price"]).abs()

    # Only evaluate riskcap where we have a trend, swings, and a defined stop.
    candidate = is_long | is_short
    candidate &= sl_dist.notna() & or_height.notna()

    # Default: everything is OK. We only flip to False where we exceed the cap.
    out["riskcap_ok"] = True
    too_wide = sl_dist > (risk_cap_multiple * or_height)
    out.loc[candidate & too_wide, "riskcap_ok"] = False

    return out
