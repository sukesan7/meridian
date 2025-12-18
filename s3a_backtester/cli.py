# Command Line
# Purpose of this file is to glue together config loading, data loading,
# engine calls, and output.
from __future__ import annotations

import argparse
import pandas as pd

from typing import List
from .config import load_config
from .data_io import load_minute_df, slice_rth, resample
from .features import (
    compute_session_refs,
    compute_session_vwap_bands,
    compute_atr15,
    find_swings_1m,
)
from .structure import trend_5m, micro_swing_break
from .engine import generate_signals, simulate_trades
from .metrics import compute_summary


def run_backtest(config_path: str, data_path: str) -> None:
    cfg = load_config(config_path)

    # 1) Load + RTH slice
    df1 = load_minute_df(data_path, tz=cfg.tz)
    df1 = slice_rth(df1)

    # 2) ATR and session reference levels
    #    compute_atr15 may return a Series or a DataFrame; attach, don't overwrite.
    atr = compute_atr15(df1)
    if isinstance(atr, pd.Series):
        df1["atr15"] = atr
    elif isinstance(atr, pd.DataFrame):
        for col in atr.columns:
            df1[col] = atr[col]

    # compute_session_refs should receive a full OHLCV DataFrame
    refs = compute_session_refs(df1)
    for col in refs.columns:
        df1[col] = refs[col]

    # 3) Session VWAP bands (also overlay)
    bands = compute_session_vwap_bands(df1)
    if not bands.empty:
        mapping = {
            "vwap": "vwap",
            "band_p1": "vwap_1u",
            "band_m1": "vwap_1d",
            "band_p2": "vwap_2u",
            "band_m2": "vwap_2d",
        }
        for src, dst in mapping.items():
            if src in bands.columns:
                df1[dst] = bands[src]

    # 4) 5-minute trend from resampled bars, then broadcast to 1m
    df5 = resample(df1, rule="5min")
    tr5 = trend_5m(df5)

    if isinstance(tr5, pd.DataFrame):
        if "trend_5m" in tr5.columns:
            trend_series = tr5["trend_5m"]
        else:
            trend_series = tr5.iloc[:, 0]
    else:
        # already a Series
        trend_series = tr5

    df1["trend_5m"] = trend_series.reindex(df1.index, method="ffill").fillna(0)

    # 5) 1-minute swings + micro-swing breaks
    swings_1m = find_swings_1m(df1)
    df1["swing_high"] = swings_1m["swing_high"]
    df1["swing_low"] = swings_1m["swing_low"]

    mb = micro_swing_break(df1)
    df1["micro_break_dir"] = mb["micro_break_dir"]

    # 6) Generate signals + simulate trades
    signals = generate_signals(df1, df5, cfg)

    # Temp Debug Code
    def _dbg(signals):
        print("ROWS:", len(signals))
        must = [
            "time_window_ok",
            "or_break_unlock",
            "trend_ok",
            "in_zone",
            "trigger_ok",
            "riskcap_ok",
            "disqualified_2sigma",
            "direction",
            "or_high",
            "or_low",
        ]
        present = [c for c in must if c in signals.columns]
        print("COLS_PRESENT:", present)

        for c in [
            "time_window_ok",
            "or_break_unlock",
            "trend_ok",
            "in_zone",
            "trigger_ok",
            "riskcap_ok",
        ]:
            if c in signals.columns:
                print(f"{c}: {int(signals[c].sum())}")

        if "direction" in signals.columns:
            print("direction!=0:", int((signals["direction"] != 0).sum()))

        if "disqualified_2sigma" in signals.columns:
            print("disqualified_2sigma:", int(signals["disqualified_2sigma"].sum()))

        # “final entry candidates” approximation (adjust if your engine differs)
        if set(["direction", "trigger_ok", "time_window_ok", "riskcap_ok"]).issubset(
            signals.columns
        ):
            ok = (
                (signals["direction"] != 0)
                & signals["trigger_ok"]
                & signals["time_window_ok"]
                & signals["riskcap_ok"]
            )
            if "disqualified_2sigma" in signals.columns:
                ok = ok & (~signals["disqualified_2sigma"])
            print("ENTRY_CANDIDATES:", int(ok.sum()))

        for c in ["micro_break_dir", "engulf_dir", "swing_hi", "swing_lo"]:
            if c in signals.columns:
                print(
                    c,
                    "present",
                    "nonzero",
                    (
                        int((signals[c] != 0).sum())
                        if signals[c].dtype != bool
                        else int(signals[c].sum())
                    ),
                )
            else:
                print(c, "MISSING")

    _dbg(signals)

    trades = simulate_trades(df1, signals, cfg)

    summary = compute_summary(trades)
    print("SUMMARY:", summary)

    # Optional: inspect trades
    # trades.to_csv("outputs/trades.csv", index=False)
    trades.to_csv("outputs/trades_debug.csv", index=False)


def run_walkforward(config_path: str, data_path: str) -> None:
    print("Walk-forward runner placeholder.")


def run_mc(config_path: str, trades_path: str) -> None:
    print("Monte Carlo runner placeholder.")


def main(argv: List[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="3A Backtester CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_bt = sub.add_parser("run-backtest", help="Run a single backtest")
    p_bt.add_argument("--config", required=True)
    p_bt.add_argument("--data", required=True)

    p_wf = sub.add_parser("run-walkforward", help="Run rolling IS/OOS")
    p_wf.add_argument("--config", required=True)
    p_wf.add_argument("--data", required=True)

    p_mc = sub.add_parser("run-mc", help="Run Monte Carlo on a trades file")
    p_mc.add_argument("--config", required=True)
    p_mc.add_argument("--trades", required=True)

    args = p.parse_args(argv)
    if args.cmd == "run-backtest":
        run_backtest(args.config, args.data)
    elif args.cmd == "run-walkforward":
        run_walkforward(args.config, args.data)
    elif args.cmd == "run-mc":
        run_mc(args.config, args.trades)


if __name__ == "__main__":
    main()
