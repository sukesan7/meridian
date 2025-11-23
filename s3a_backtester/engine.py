# 3A Engine
# Strategy 3A Brain + State Machine
from __future__ import annotations
import pandas as pd
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

    return out
