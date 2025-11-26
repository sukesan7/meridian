# Command Line
# Purpose of this file is to glue together config loading, data loading, engine calls, and output.
# Orchestrate: parse -> load -> run -> save.
from __future__ import annotations
import argparse
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
import pandas as pd


def run_backtest(config_path: str, data_path: str) -> None:
    cfg = load_config(config_path)

    # 1) Load + RTH slice
    df1 = load_minute_df(data_path, tz=cfg.tz)
    df1 = slice_rth(df1)

    # 2) Core session features
    df1 = compute_session_refs(df1)
    df1 = compute_session_vwap_bands(df1)
    df1["atr15"] = compute_atr15(df1)

    # 3) 5-minute resample for structure / trend
    df5 = resample(df1, rule="5min")

    # 4) 5m trend (HH/HL vs LH/LL) and broadcast to 1m
    tr5 = trend_5m(df5)  # your current implementation returns a DataFrame

    if isinstance(tr5, pd.DataFrame):
        # Prefer explicit 'trend_5m' column, fall back to first column if not found
        if "trend_5m" in tr5.columns:
            tr5 = tr5["trend_5m"]
        else:
            tr5 = tr5.iloc[:, 0]

    # Now tr5 is a Series indexed by the 5m timestamps
    df1["trend_5m"] = tr5.reindex(df1.index, method="ffill").fillna(0)

    # 5) 1m swings + micro swing breaks
    swings_1m = find_swings_1m(df1)
    df1["swing_high"] = swings_1m["swing_high"]
    df1["swing_low"] = swings_1m["swing_low"]

    micro = micro_swing_break(df1)
    df1["micro_break_dir"] = micro["micro_break_dir"]

    # 6) Generate signals + simulate trades
    signals = generate_signals(df1, df5, cfg)
    trades = simulate_trades(df1, signals, cfg)

    summary = compute_summary(trades)
    print("SUMMARY:", summary)

    # Optional: save trades to CSV for inspection
    # trades.to_csv("outputs/trades.csv", index=False)


def run_walkforward(config_path: str, data_path: str) -> None:
    print("Walk-forward runner placeholder.")


def run_mc(config_path: str, trades_path: str) -> None:
    print("Monte Carlo runner placeholder.")


def main(argv: list[str] | None = None) -> None:
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
