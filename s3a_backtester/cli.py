"""
Meridian CLI (formerly 3A Backtester)

Glue layer: config -> data -> features -> engine -> outputs.

Design goals:
- Deterministic pipeline (no hidden state).
- Clean artifacts per run: outputs/backtest/<run_id>/...
- Debug is opt-in.
- Avoid accidental column clobbering.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

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


# -----------------------------
# Helpers
# -----------------------------
def _now_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: Any) -> None:
    def _default(x: Any) -> Any:
        if is_dataclass(x):
            return asdict(x)
        if hasattr(x, "__dict__"):
            return dict(x.__dict__)
        return str(x)

    path.write_text(json.dumps(obj, indent=2, default=_default))


def _overlay_cols(
    dst: pd.DataFrame, src: pd.DataFrame, cols: list[str]
) -> pd.DataFrame:
    """Overlay specific columns from src onto dst (no accidental OHLCV overwrite)."""
    out = dst.copy()
    for c in cols:
        if c in src.columns:
            out[c] = src[c]
    return out


def _dbg_signals(signals: pd.DataFrame) -> None:
    print("ROWS:", len(signals))
    must = [
        "time_window_ok",
        "or_break_unlock",
        "unlocked",
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
        "unlocked",
        "in_zone",
        "trigger_ok",
        "riskcap_ok",
    ]:
        if c in signals.columns:
            # bool sum is fine; non-bool will error, so guard:
            s = signals[c]
            if s.dtype == bool:
                print(f"{c}: {int(s.sum())}")
            else:
                print(f"{c}: present")

    if "direction" in signals.columns:
        print("direction!=0:", int((signals["direction"] != 0).sum()))

    if "disqualified_2sigma" in signals.columns:
        s = signals["disqualified_2sigma"]
        if s.dtype == bool:
            print("disqualified_2sigma:", int(s.sum()))

    # “final entry candidates” approximation
    needed = {"direction", "trigger_ok", "time_window_ok", "riskcap_ok"}
    if needed.issubset(signals.columns):
        ok = (
            (signals["direction"] != 0)
            & signals["trigger_ok"].astype(bool)
            & signals["time_window_ok"].astype(bool)
            & signals["riskcap_ok"].astype(bool)
        )
        if "disqualified_2sigma" in signals.columns:
            ok = ok & (~signals["disqualified_2sigma"].astype(bool))
        print("ENTRY_CANDIDATES:", int(ok.sum()))

    for c in [
        "micro_break_dir",
        "engulf_dir",
        "swing_hi",
        "swing_lo",
        "swing_high",
        "swing_low",
    ]:
        if c in signals.columns:
            s = signals[c]
            if s.dtype == bool:
                print(c, "present", "true", int(s.sum()))
            else:
                print(c, "present", "nonzero", int((s != 0).sum()))
        else:
            print(c, "MISSING")


# -----------------------------
# Pipeline
# -----------------------------
def build_feature_frames(
    cfg: Any, data_path: str, *, do_slice_rth: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # 1) Load + optional RTH slice
    df1 = load_minute_df(data_path, tz=getattr(cfg, "tz", "America/New_York"))
    df1 = df1.sort_index()
    df1 = df1[~df1.index.duplicated(keep="first")]

    if do_slice_rth:
        df1 = slice_rth(df1)

    # 2) ATR15
    atr = compute_atr15(df1)
    if isinstance(atr, pd.Series):
        df1["atr15"] = atr
    elif isinstance(atr, pd.DataFrame):
        for col in atr.columns:
            df1[col] = atr[col]

    # 3) Session refs (overlay only the reference cols we care about)
    refs = compute_session_refs(df1)
    ref_cols = ["or_high", "or_low", "or_height", "pdh", "pdl", "onh", "onl"]
    df1 = _overlay_cols(df1, refs, ref_cols)

    # 4) Session VWAP bands (overlay only)
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

    # 5) 5-minute trend from resampled bars, then broadcast to 1m
    df5 = resample(df1, rule="5min")
    tr5 = trend_5m(df5)

    if isinstance(tr5, pd.DataFrame):
        trend_series = tr5["trend_5m"] if "trend_5m" in tr5.columns else tr5.iloc[:, 0]
    else:
        trend_series = tr5

    df1["trend_5m"] = trend_series.reindex(df1.index, method="ffill").fillna(0)

    # 6) 1-minute swings + micro-swing breaks
    swings_1m = find_swings_1m(df1)
    if isinstance(swings_1m, pd.DataFrame):
        if "swing_high" in swings_1m.columns:
            df1["swing_high"] = swings_1m["swing_high"].astype(bool)
        if "swing_low" in swings_1m.columns:
            df1["swing_low"] = swings_1m["swing_low"].astype(bool)

        # Also provide aliases some parts of the codebase/tests may use
        if "swing_high" in df1.columns:
            df1["swing_hi"] = df1["swing_high"]
        if "swing_low" in df1.columns:
            df1["swing_lo"] = df1["swing_low"]

    mb = micro_swing_break(df1)
    if isinstance(mb, pd.DataFrame) and "micro_break_dir" in mb.columns:
        df1["micro_break_dir"] = mb["micro_break_dir"]

    return df1, df5


# -----------------------------
# Commands
# -----------------------------
def cmd_backtest(
    config_path: str,
    data_path: str,
    *,
    out_dir: str = "outputs/backtest",
    run_id: str | None = None,
    debug_signals: bool = False,
    write_signals: bool = True,
    write_trades: bool = True,
) -> None:
    cfg = load_config(config_path)

    df1, df5 = build_feature_frames(cfg, data_path, do_slice_rth=True)

    signals = generate_signals(df1, df5, cfg)
    if debug_signals:
        _dbg_signals(signals)

    trades = simulate_trades(df1, signals, cfg)
    summary = compute_summary(trades)

    run_id = run_id or _now_run_id()
    root = Path(out_dir) / run_id
    _safe_mkdir(root)

    # artifacts
    _write_json(root / "summary.json", summary)
    _write_json(
        root / "run_meta.json",
        {"config": config_path, "data": data_path, "run_id": run_id},
    )

    if write_signals:
        signals.to_parquet(root / "signals.parquet", index=True)

    if write_trades:
        trades.to_parquet(root / "trades.parquet", index=False)
        trades.to_csv(root / "trades.csv", index=False)

    print("SUMMARY:", summary)
    print(f"[DONE] artifacts written under: {root}")


def cmd_walkforward(config_path: str, data_path: str) -> None:
    raise SystemExit("Walk-forward runner not implemented yet (Week 5+).")


def cmd_mc(config_path: str, trades_path: str) -> None:
    raise SystemExit("Monte Carlo runner not implemented yet (Week 5+).")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Meridian CLI (formerly 3A Backtester)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # New nicer command
    p_bt = sub.add_parser("backtest", help="Run a single backtest (writes artifacts)")
    p_bt.add_argument("--config", required=True)
    p_bt.add_argument("--data", required=True)
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

    # Backwards-compatible alias
    p_bt_old = sub.add_parser("run-backtest", help="Alias for backtest")
    p_bt_old.add_argument("--config", required=True)
    p_bt_old.add_argument("--data", required=True)
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

    p_wf = sub.add_parser("run-walkforward", help="Run rolling IS/OOS (placeholder)")
    p_wf.add_argument("--config", required=True)
    p_wf.add_argument("--data", required=True)

    p_mc = sub.add_parser(
        "run-mc", help="Run Monte Carlo on a trades file (placeholder)"
    )
    p_mc.add_argument("--config", required=True)
    p_mc.add_argument("--trades", required=True)

    args = p.parse_args(argv)

    if args.cmd in ("backtest", "run-backtest"):
        cmd_backtest(
            args.config,
            args.data,
            out_dir=args.out_dir,
            run_id=args.run_id,
            debug_signals=bool(args.debug_signals),
            write_signals=bool(args.write_signals),
            write_trades=bool(args.write_trades),
        )
        return

    if args.cmd == "run-walkforward":
        cmd_walkforward(args.config, args.data)
        return

    if args.cmd == "run-mc":
        cmd_mc(args.config, args.trades)
        return


if __name__ == "__main__":
    main()
