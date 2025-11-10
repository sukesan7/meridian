# s3a_backtester/cli.py
from __future__ import annotations
import argparse
from .config import load_config
from .data_io import load_minute_df, slice_rth, resample
from .features import compute_session_refs, compute_session_vwap_bands, compute_atr15
from .engine import generate_signals, simulate_trades
from .metrics import compute_summary


def run_backtest(config_path: str, data_path: str) -> None:
    cfg = load_config(config_path)
    df1 = load_minute_df(data_path, tz=cfg.tz)
    df1 = slice_rth(df1)
    df5 = resample(df1, "5T")

    refs = compute_session_refs(df1)
    bands = compute_session_vwap_bands(df1)

    df1 = df1.join(
        [
            refs[["or_high", "or_low", "or_height", "pdh", "pdl", "onh", "onl"]],
            bands[["vwap", "vwap_sd", "band_p1", "band_m1", "band_p2", "band_m2"]],
        ]
    )
    df1["atr15"] = compute_atr15(df1)

    sig = generate_signals(df1, df5, cfg)
    trades = simulate_trades(df1, sig, cfg)
    summary = compute_summary(trades)
    print("SUMMARY:", summary)


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
