# s3a_backtester/engine.py
from __future__ import annotations
import pandas as pd
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


def generate_signals(df1: pd.DataFrame, df5: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    Build the signal frame with required labels/booleans.
    v0: only time-window flag; rest are placeholders (False/True defaults).
    """
    start_t = pd.Timestamp(cfg.entry_window.start).time()
    end_t = pd.Timestamp(cfg.entry_window.end).time()

    sig = pd.DataFrame(index=df1.index)
    sig["time_window_ok"] = (df1.index.time >= start_t) & (df1.index.time <= end_t)
    sig["or_break_unlock"] = False
    sig["in_zone"] = False
    sig["trigger_ok"] = False
    sig["disqualified_±2σ"] = False
    sig["riskcap_ok"] = True
    return sig[_SIGNAL_COLS]


def simulate_trades(
    df1: pd.DataFrame, signals: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """
    Bar-close entries; management TBD.
    v0: return an empty but correctly-schematized DataFrame so downstream code/CLI works.
    """
    return pd.DataFrame(columns=_TRADE_COLS)
