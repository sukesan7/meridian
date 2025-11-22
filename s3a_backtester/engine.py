# s3a_backtester/engine.py
from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Any
from .config import Config

# Column contracts we’ll fill out later
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


def simulate_trades(
    df1: pd.DataFrame, signals: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """
    Bar-close entries; management TBD.
    v0: return an empty but correctly-schematized DataFrame so downstream code/CLI works.
    """
    return pd.DataFrame(columns=_TRADE_COLS)


def generate_signals(
    df_1m: pd.DataFrame,
    df_5m: pd.DataFrame | None = None,
    cfg: Any | None = None,
) -> pd.DataFrame:
    """
    Generate basic 3A engine signals.

    Supports both the old stub signature `(df_1m, df_5m, cfg)` and the
    newer `(df_1m,)` form used in unit tests. `df_5m` and `cfg` are
    currently optional and only used for the entry-window times.

    Required columns (to get full behaviour):
      - close
      - or_high, or_low
      - vwap, vwap_2u, vwap_2d
      - trend_5m

    If these are missing, the function degrades gracefully and just
    returns the input with boolean signal columns added.
    """
    out = df_1m.copy()

    # Ensure all signal columns exist with sane defaults so the stub test passes
    for col in _SIGNAL_COLS:
        if col not in out:
            if col == "time_window_ok":
                out[col] = True  # will be refined if we have cfg
            else:
                out[col] = False  # default "no signal"

    # If we don't have the full feature set yet (e.g. stub test),
    # just return the frame with placeholder columns.
    required = {
        "close",
        "or_high",
        "or_low",
        "vwap",
        "vwap_2u",
        "vwap_2d",
        "trend_5m",
    }
    if not required.issubset(out.columns):
        return out

        # 1) Session grouping + time_window_ok
    idx = out.index
    if getattr(idx, "tz", None) is not None:
        idx_et = idx.tz_convert("America/New_York")
    else:
        idx_et = idx

    dates = pd.Index(idx_et.date, name="date")

    # For now, assume df_1m is already RTH-sliced, so every bar is "ok"
    out["time_window_ok"] = True

    # ------------------------------------------------------------------
    # 2) Unlock condition: first OR break in trend direction & VWAP side
    # ------------------------------------------------------------------
    is_long = out["trend_5m"] > 0
    is_short = out["trend_5m"] < 0

    breaks_or_long = out["close"] > out["or_high"]
    breaks_or_short = out["close"] < out["or_low"]

    above_vwap = out["close"] >= out["vwap"]
    below_vwap = out["close"] <= out["vwap"]

    unlock_raw_long = is_long & breaks_or_long & above_vwap
    unlock_raw_short = is_short & breaks_or_short & below_vwap
    unlock_raw = unlock_raw_long | unlock_raw_short

    # Only the first unlock per session
    unlock_first = unlock_raw.groupby(dates).cumsum().eq(1)
    out["or_break_unlock"] = unlock_first

    # Direction label: 0 = none, +1 = long, -1 = short (at unlock bar only for now)
    direction = np.zeros(len(out), dtype=int)
    direction[(unlock_first & unlock_raw_long).to_numpy()] = 1
    direction[(unlock_first & unlock_raw_short).to_numpy()] = -1
    out["direction"] = direction

    # ------------------------------------------------------------------
    # 3) 2σ disqualifier: any opposite 2σ breach *before* trigger
    # ------------------------------------------------------------------
    hit_opp_2sig_long = is_long & (out["close"] <= out["vwap_2d"])
    hit_opp_2sig_short = is_short & (out["close"] >= out["vwap_2u"])
    hit_opp_2sig = hit_opp_2sig_long | hit_opp_2sig_short

    # Once opposite 2σ has been hit in a session, we stay disqualified
    disq_cum = hit_opp_2sig.groupby(dates).cumsum().astype(bool)

    # Official spec name:
    out["disqualified_±2σ"] = disq_cum
    # Backwards compatibility for our Week-2 test naming:
    out["disqualified_2sigma"] = disq_cum

    # ------------------------------------------------------------------
    # 4) Zone: first pullback into VWAP / ±1σ in trend direction
    # ------------------------------------------------------------------
    # Only apply if we actually have the 1σ band columns
    if {"vwap_1u", "vwap_1d"}.issubset(out.columns):
        # Reset to False so we don't carry any previous values
        out["in_zone"] = False

        for day_val, grp in out.groupby(dates):
            # Find unlock bar for this day
            unlock_rows = grp[grp["or_break_unlock"]]
            if unlock_rows.empty:
                continue

            unlock_ts = unlock_rows.index[0]
            direction_val = grp.loc[unlock_ts, "direction"]
            if direction_val == 0:
                continue

            # Only consider bars strictly AFTER the unlock bar
            after_unlock = grp.loc[grp.index > unlock_ts]
            if after_unlock.empty:
                continue

            if direction_val == 1:
                # Long: pullback DOWN into [VWAP, +1σ]
                zone_mask = (after_unlock["close"] >= after_unlock["vwap"]) & (
                    after_unlock["close"] <= after_unlock["vwap_1u"]
                )
            else:
                # Short: pullback UP into [-1σ, VWAP]
                zone_mask = (after_unlock["close"] <= after_unlock["vwap"]) & (
                    after_unlock["close"] >= after_unlock["vwap_1d"]
                )

            zone_candidates = after_unlock[zone_mask]
            if not zone_candidates.empty:
                zone_ts = zone_candidates.index[0]
                out.loc[zone_ts, "in_zone"] = True

    # 'trigger_ok' and 'riskcap_ok' stay as stub False for now

    return out
