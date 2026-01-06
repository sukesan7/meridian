"""
CLI Entry Point
---------------
Command-line interface for running Backtests, Walk-Forward Analysis, and Monte Carlo.
Handles argument parsing, configuration loading, and artifact generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from .config import load_config
from .data_io import load_minute_df, resample, slice_rth
from .engine import generate_signals, simulate_trades
from .features import (
    compute_atr15,
    compute_session_refs,
    compute_session_vwap_bands,
    find_swings_1m,
)
from .metrics import compute_summary
from .monte_carlo import mc_simulate_R
from .run_meta import build_run_meta, write_run_meta
from .structure import micro_swing_break, trend_5m
from .walkforward import rolling_walkforward_frames


def _now_run_id() -> str:
    """Generates a timestamp-based run ID."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: Any) -> None:
    def _default(x: Any) -> Any:
        if is_dataclass(x):
            return asdict(cast(Any, x))
        if hasattr(x, "__dict__"):
            return dict(x.__dict__)
        return str(x)

    path.write_text(json.dumps(obj, indent=2, default=_default), encoding="utf-8")


def _print_compact_json(obj: Any) -> None:
    def _default(x: Any) -> Any:
        if is_dataclass(x):
            return asdict(cast(Any, x))
        if hasattr(x, "__dict__"):
            return dict(x.__dict__)
        return str(x)

    print(json.dumps(obj, default=_default, separators=(",", ":")))


def _parse_date(date_str: str, tz: str) -> pd.Timestamp:
    ts = pd.Timestamp(date_str)
    if ts.tzinfo is None:
        return ts.tz_localize(tz)
    return ts.tz_convert(tz)


def _slice_date_range(
    df: pd.DataFrame,
    date_from: str | None,
    date_to: str | None,
    *,
    tz: str,
) -> pd.DataFrame:
    """Slices DataFrame by date range, handling timezone normalization."""
    if df is None or df.empty:
        return df
    if date_from is None and date_to is None:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("date slicing requires a DatetimeIndex")

    start = _parse_date(date_from, tz).normalize() if date_from else df.index.min()

    end = (
        _parse_date(date_to, tz).normalize()
        + pd.Timedelta(days=1)
        - pd.Timedelta(1, unit="ns")
        if date_to
        else df.index.max()
    )

    return df.loc[(df.index >= start) & (df.index <= end)]


def _read_trades_file(path: str) -> pd.DataFrame:
    """Reads trades from CSV or Parquet."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)

    suf = p.suffix.lower()
    if suf == ".parquet":
        return pd.read_parquet(p)
    if suf == ".csv":
        return pd.read_csv(p)

    raise ValueError(f"Unsupported trades file type: {suf}")


def _overlay_cols(
    dst: pd.DataFrame, src: pd.DataFrame, cols: list[str]
) -> pd.DataFrame:
    """Merges selected columns from source DataFrame into destination."""
    out = dst.copy()
    for c in cols:
        if c in src.columns:
            out[c] = src[c]
    return out


def build_feature_frames(
    cfg: Any,
    data_path: str,
    *,
    do_slice_rth: bool = True,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pipeline: Load -> Slice -> Features (Refs, VWAP, ATR, Swings) -> Resample."""
    tz = getattr(cfg, "tz", "America/New_York")
    df1 = load_minute_df(data_path, tz=tz)
    df1 = df1.sort_index()
    df1 = df1[~df1.index.duplicated(keep="first")]

    df1 = _slice_date_range(df1, date_from, date_to, tz=tz)

    if do_slice_rth:
        df1 = slice_rth(df1)

    atr = compute_atr15(df1)
    if isinstance(atr, pd.Series):
        df1["atr15"] = atr
    elif isinstance(atr, pd.DataFrame):
        for col in atr.columns:
            df1[col] = atr[col]

    refs = compute_session_refs(df1)
    ref_cols = ["or_high", "or_low", "or_height", "pdh", "pdl", "onh", "onl"]
    df1 = _overlay_cols(df1, refs, ref_cols)

    bands = compute_session_vwap_bands(df1)
    if isinstance(bands, pd.DataFrame) and not bands.empty:
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

    df5 = resample(df1, rule="5min")
    tr5 = trend_5m(df5)

    if isinstance(tr5, pd.DataFrame):
        trend_series = tr5["trend_5m"] if "trend_5m" in tr5.columns else tr5.iloc[:, 0]
    else:
        trend_series = tr5

    trend_series = trend_series.shift(1)
    df1["trend_5m"] = trend_series.reindex(df1.index, method="ffill").fillna(0)

    swings_1m = find_swings_1m(df1)
    if isinstance(swings_1m, pd.DataFrame):
        if "swing_high_confirmed" in swings_1m.columns:
            df1["swing_high_confirmed"] = swings_1m["swing_high_confirmed"].astype(bool)
        if "swing_low_confirmed" in swings_1m.columns:
            df1["swing_low_confirmed"] = swings_1m["swing_low_confirmed"].astype(bool)

        if "last_swing_high_price" in swings_1m.columns:
            df1["last_swing_high_price"] = swings_1m["last_swing_high_price"]
        if "last_swing_low_price" in swings_1m.columns:
            df1["last_swing_low_price"] = swings_1m["last_swing_low_price"]

    mb = micro_swing_break(df1)
    if isinstance(mb, pd.DataFrame) and "micro_break_dir" in mb.columns:
        df1["micro_break_dir"] = mb["micro_break_dir"]

    return df1, df5


def cmd_backtest(
    config_path: str,
    data_path: str,
    *,
    out_dir: str = "outputs/backtest",
    run_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    debug_signals: bool = False,
    write_signals: bool = True,
    write_trades: bool = True,
    seed: int | None = None,
    hash_data: bool = True,
    argv: list[str] | None = None,
) -> None:
    """Executes a single standard backtest run."""
    cfg = load_config(config_path)

    df1, df5 = build_feature_frames(
        cfg, data_path, do_slice_rth=True, date_from=date_from, date_to=date_to
    )

    signals = generate_signals(df1, df5, cfg)

    trades = simulate_trades(df1, signals, cfg)
    summary = compute_summary(trades)

    run_id = run_id or _now_run_id()
    root = Path(out_dir) / run_id
    _safe_mkdir(root)

    artifacts: dict[str, Path] = {}

    summary_path = root / "summary.json"
    _write_json(summary_path, summary)
    artifacts["summary.json"] = summary_path

    if write_signals:
        signals_path = root / "signals.parquet"
        signals.to_parquet(signals_path, index=True)
        artifacts["signals.parquet"] = signals_path

    if write_trades:
        trades_parquet_path = root / "trades.parquet"
        trades_csv_path = root / "trades.csv"
        trades.to_parquet(trades_parquet_path, index=False)
        trades.to_csv(trades_csv_path, index=False)
        artifacts["trades.parquet"] = trades_parquet_path
        artifacts["trades.csv"] = trades_csv_path

    meta = build_run_meta(
        cmd="backtest",
        argv=argv or [],
        run_id=run_id,
        outputs_dir=root,
        config_path=config_path,
        config_obj=cfg,
        data_path=data_path,
        seed=seed,
        hash_data=hash_data,
        artifacts=artifacts,
    )
    meta.update(
        {
            "date_from": date_from,
            "date_to": date_to,
            "debug_signals": debug_signals,
            "write_signals": write_signals,
            "write_trades": write_trades,
        }
    )
    write_run_meta(root, meta)

    _print_compact_json({"run_id": run_id, "artifacts_dir": str(root), **summary})


def cmd_walkforward(
    config_path: str,
    data_path: str,
    *,
    out_dir: str = "outputs/walkforward",
    run_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    is_days: int = 63,
    oos_days: int = 21,
    step: int | None = None,
    write_trades: bool = True,
    write_equity: bool = True,
    seed: int | None = None,
    hash_data: bool = True,
    argv: list[str] | None = None,
) -> None:
    """Executes rolling walk-forward analysis (IS/OOS)."""
    cfg = load_config(config_path)

    df1, df5 = build_feature_frames(
        cfg, data_path, do_slice_rth=True, date_from=date_from, date_to=date_to
    )

    def _wf_backtest_fn(
        df1: pd.DataFrame,
        df5: pd.DataFrame | None,
        cfg: Any | None,
        *,
        params: dict[str, Any] | None,
        regime: str,
        window_id: int,
    ) -> pd.DataFrame:
        _ = params, regime, window_id
        sig = generate_signals(df1, df5, cfg)
        return simulate_trades(df1, sig, cfg)

    out = rolling_walkforward_frames(
        df1,
        df5,
        cfg,
        is_days=is_days,
        oos_days=oos_days,
        step=step,
        run_backtest_fn=_wf_backtest_fn,
        tune_fn=None,
    )

    is_summary = out["is_summary"]
    oos_summary = out["oos_summary"]
    wf_equity = out["wf_equity"]
    is_trades = out["is_trades"]
    oos_trades = out["oos_trades"]

    overall_oos = compute_summary(oos_trades)

    run_id = run_id or _now_run_id()
    root = Path(out_dir) / run_id
    _safe_mkdir(root)

    artifacts: dict[str, Path] = {}

    summary_path = root / "summary.json"
    _write_json(summary_path, overall_oos)
    artifacts["summary.json"] = summary_path

    is_summary_path = root / "is_summary.csv"
    oos_summary_path = root / "oos_summary.csv"
    is_summary.to_csv(is_summary_path, index=False)
    oos_summary.to_csv(oos_summary_path, index=False)
    artifacts["is_summary.csv"] = is_summary_path
    artifacts["oos_summary.csv"] = oos_summary_path

    if write_equity:
        wf_equity_path = root / "wf_equity.parquet"
        wf_equity.to_parquet(wf_equity_path, index=False)
        artifacts["wf_equity.parquet"] = wf_equity_path

    if write_trades:
        is_trades_path = root / "is_trades.parquet"
        oos_trades_path = root / "oos_trades.parquet"
        is_trades.to_parquet(is_trades_path, index=False)
        oos_trades.to_parquet(oos_trades_path, index=False)
        artifacts["is_trades.parquet"] = is_trades_path
        artifacts["oos_trades.parquet"] = oos_trades_path

    meta = build_run_meta(
        cmd="walkforward",
        argv=argv or [],
        run_id=run_id,
        outputs_dir=root,
        config_path=config_path,
        config_obj=cfg,
        data_path=data_path,
        seed=seed,
        hash_data=hash_data,
        artifacts=artifacts,
    )
    meta.update(
        {
            "date_from": date_from,
            "date_to": date_to,
            "is_days": is_days,
            "oos_days": oos_days,
            "step": step,
            "write_trades": write_trades,
            "write_equity": write_equity,
        }
    )
    write_run_meta(root, meta)

    _print_compact_json({"run_id": run_id, "artifacts_dir": str(root), **overall_oos})


def cmd_mc(
    config_path: str,
    trades_path: str,
    *,
    out_dir: str = "outputs/monte-carlo",
    run_id: str | None = None,
    n_paths: int = 1000,
    risk_per_trade: float = 0.01,
    block_size: int | None = None,
    seed: int | None = None,
    years: float | None = None,
    keep_equity_paths: bool = False,
    hash_data: bool = True,
    argv: list[str] | None = None,
) -> None:
    """Executes Monte Carlo simulation on an existing trades file."""
    cfg = load_config(config_path)

    if not isinstance(trades_path, str):
        raise TypeError("trades_path must be a string path")
    trades = _read_trades_file(trades_path)

    out = mc_simulate_R(
        trades,
        n_paths=n_paths,
        risk_per_trade=risk_per_trade,
        block_size=block_size,
        seed=seed,
        years=years,
        keep_equity_paths=keep_equity_paths,
    )

    summary = out["summary"]
    samples = out["samples"]
    equity_paths = out.get("equity_paths")

    run_id = run_id or _now_run_id()
    root = Path(out_dir) / run_id
    _safe_mkdir(root)

    artifacts: dict[str, Path] = {}

    summary_path = root / "summary.json"
    _write_json(summary_path, summary)
    artifacts["summary.json"] = summary_path

    samples_parquet_path = root / "mc_samples.parquet"
    samples_csv_path = root / "mc_samples.csv"
    samples.to_parquet(samples_parquet_path, index=False)
    samples.to_csv(samples_csv_path, index=False)
    artifacts["mc_samples.parquet"] = samples_parquet_path
    artifacts["mc_samples.csv"] = samples_csv_path

    if equity_paths is not None:
        equity_paths_path = root / "mc_equity_paths.parquet"
        equity_paths.to_parquet(equity_paths_path, index=False)
        artifacts["mc_equity_paths.parquet"] = equity_paths_path

    meta = build_run_meta(
        cmd="monte-carlo",
        argv=argv or [],
        run_id=run_id,
        outputs_dir=root,
        config_path=config_path,
        config_obj=cfg,
        data_path=trades_path,
        seed=seed,
        hash_data=hash_data,
        artifacts=artifacts,
    )
    meta.update(
        {
            "trades_file": trades_path,
            "n_paths": n_paths,
            "risk_per_trade": risk_per_trade,
            "block_size": block_size,
            "years": years,
            "keep_equity_paths": keep_equity_paths,
        }
    )
    write_run_meta(root, meta)

    _print_compact_json({"run_id": run_id, "artifacts_dir": str(root), **summary})


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Meridian CLI (formerly 3A Backtester)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # ---------------- backtest ----------------
    p_bt = sub.add_parser("backtest", help="Run a single backtest")
    p_bt.add_argument("--config", required=True)
    p_bt.add_argument("--data", required=True)
    p_bt.add_argument("--from", dest="date_from", default=None)
    p_bt.add_argument("--to", dest="date_to", default=None)
    p_bt.add_argument("--out-dir", default="outputs/backtest")
    p_bt.add_argument("--run-id", default=None)
    p_bt.add_argument(
        "--debug-signals", action=argparse.BooleanOptionalAction, default=False
    )
    p_bt.add_argument(
        "--write-signals", action=argparse.BooleanOptionalAction, default=True
    )
    p_bt.add_argument(
        "--write-trades", action=argparse.BooleanOptionalAction, default=True
    )
    p_bt.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Determinism seed.",
    )
    p_bt.add_argument(
        "--hash-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Compute SHA256 of data file (can be slow for large files).",
    )

    p_bt_old = sub.add_parser("run-backtest", help="Alias for backtest")
    p_bt_old.add_argument("--config", required=True)
    p_bt_old.add_argument("--data", required=True)
    p_bt_old.add_argument("--from", dest="date_from", default=None)
    p_bt_old.add_argument("--to", dest="date_to", default=None)
    p_bt_old.add_argument("--out-dir", default="outputs/backtest")
    p_bt_old.add_argument("--run-id", default=None)
    p_bt_old.add_argument(
        "--debug-signals", action=argparse.BooleanOptionalAction, default=False
    )
    p_bt_old.add_argument(
        "--write-signals", action=argparse.BooleanOptionalAction, default=True
    )
    p_bt_old.add_argument(
        "--write-trades", action=argparse.BooleanOptionalAction, default=True
    )
    p_bt_old.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Determinism seed.",
    )
    p_bt_old.add_argument(
        "--hash-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Compute SHA256 of data file (can be slow for large files).",
    )

    # ---------------- walkforward ----------------
    p_wf = sub.add_parser("walkforward", help="Run rolling 3m IS / 1m OOS walk-forward")
    p_wf.add_argument("--config", required=True)
    p_wf.add_argument("--data", required=True)
    p_wf.add_argument("--from", dest="date_from", default=None)
    p_wf.add_argument("--to", dest="date_to", default=None)
    p_wf.add_argument("--out-dir", default="outputs/walkforward")
    p_wf.add_argument("--run-id", default=None)
    p_wf.add_argument("--is-days", type=int, default=63)
    p_wf.add_argument("--oos-days", type=int, default=21)
    p_wf.add_argument("--step", type=int, default=None)
    p_wf.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Determinism seed.",
    )
    p_wf.add_argument(
        "--hash-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Compute SHA256 of data file (can be slow for large files).",
    )
    p_wf.add_argument(
        "--write-trades", action=argparse.BooleanOptionalAction, default=True
    )
    p_wf.add_argument(
        "--write-equity", action=argparse.BooleanOptionalAction, default=True
    )

    p_wf_old = sub.add_parser("run-walkforward", help="Alias for walkforward")
    p_wf_old.add_argument("--config", required=True)
    p_wf_old.add_argument("--data", required=True)
    p_wf_old.add_argument("--from", dest="date_from", default=None)
    p_wf_old.add_argument("--to", dest="date_to", default=None)
    p_wf_old.add_argument("--out-dir", default="outputs/walkforward")
    p_wf_old.add_argument("--run-id", default=None)
    p_wf_old.add_argument("--is-days", type=int, default=63)
    p_wf_old.add_argument("--oos-days", type=int, default=21)
    p_wf_old.add_argument("--step", type=int, default=None)
    p_wf_old.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Determinism seed (stored in run_meta; WF is deterministic today).",
    )
    p_wf_old.add_argument(
        "--hash-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Compute SHA256 of data file (can be slow for large files).",
    )
    p_wf_old.add_argument(
        "--write-trades", action=argparse.BooleanOptionalAction, default=True
    )
    p_wf_old.add_argument(
        "--write-equity", action=argparse.BooleanOptionalAction, default=True
    )

    # ---------------- monte-carlo ----------------
    p_mc = sub.add_parser("monte-carlo", help="Run Monte Carlo on a trades file")
    p_mc.add_argument("--config", required=True)
    p_mc.add_argument("--trades-file", "--trades", dest="trades_file", required=True)
    p_mc.add_argument("--out-dir", default="outputs/monte-carlo")
    p_mc.add_argument("--run-id", default=None)
    p_mc.add_argument("--n-paths", type=int, default=1000)
    p_mc.add_argument("--risk-per-trade", type=float, default=0.01)
    p_mc.add_argument("--block-size", type=int, default=None)
    p_mc.add_argument("--years", type=float, default=None)
    p_mc.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed controlling Monte Carlo sampling (deterministic).",
    )
    p_mc.add_argument(
        "--hash-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Compute SHA256 of trades file (can be slow).",
    )
    p_mc.add_argument(
        "--keep-equity-paths", action=argparse.BooleanOptionalAction, default=False
    )

    p_mc_old = sub.add_parser("run-mc", help="Alias for monte-carlo")
    p_mc_old.add_argument("--config", required=True)
    p_mc_old.add_argument("--trades", dest="trades_file", required=True)
    p_mc_old.add_argument("--out-dir", default="outputs/monte-carlo")
    p_mc_old.add_argument("--run-id", default=None)
    p_mc_old.add_argument("--n-paths", type=int, default=1000)
    p_mc_old.add_argument("--risk-per-trade", type=float, default=0.01)
    p_mc_old.add_argument("--block-size", type=int, default=None)
    p_mc_old.add_argument("--years", type=float, default=None)
    p_mc_old.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed controlling Monte Carlo sampling (deterministic).",
    )
    p_mc_old.add_argument(
        "--hash-data",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Compute SHA256 of trades file (can be slow).",
    )
    p_mc_old.add_argument(
        "--keep-equity-paths", action=argparse.BooleanOptionalAction, default=False
    )

    args = p.parse_args(argv)

    argv_list = list(argv) if argv is not None else sys.argv[1:]

    if args.cmd in ("backtest", "run-backtest"):
        cmd_backtest(
            args.config,
            args.data,
            out_dir=args.out_dir,
            run_id=args.run_id,
            date_from=args.date_from,
            date_to=args.date_to,
            debug_signals=bool(args.debug_signals),
            write_signals=bool(args.write_signals),
            write_trades=bool(args.write_trades),
            seed=getattr(args, "seed", None),
            hash_data=bool(getattr(args, "hash_data", False)),
            argv=argv_list,
        )
        return

    if args.cmd in ("walkforward", "run-walkforward"):
        cmd_walkforward(
            args.config,
            args.data,
            out_dir=args.out_dir,
            run_id=args.run_id,
            date_from=args.date_from,
            date_to=args.date_to,
            is_days=int(args.is_days),
            oos_days=int(args.oos_days),
            step=args.step,
            write_trades=bool(args.write_trades),
            write_equity=bool(args.write_equity),
            seed=getattr(args, "seed", None),
            hash_data=bool(getattr(args, "hash_data", False)),
            argv=argv_list,
        )
        return

    if args.cmd in ("monte-carlo", "run-mc"):
        trades_file_arg = getattr(args, "trades_file", None)
        if not isinstance(trades_file_arg, str):
            raise ValueError("trades_file is required")

        cmd_mc(
            args.config,
            trades_file_arg,
            out_dir=args.out_dir,
            run_id=args.run_id,
            n_paths=int(args.n_paths),
            risk_per_trade=float(args.risk_per_trade),
            block_size=args.block_size,
            seed=getattr(args, "seed", None),
            hash_data=bool(getattr(args, "hash_data", False)),
            years=args.years,
            keep_equity_paths=bool(args.keep_equity_paths),
            argv=argv_list,
        )
        return


if __name__ == "__main__":
    main()
