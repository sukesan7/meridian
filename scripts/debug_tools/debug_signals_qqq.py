"""
Script: QQQ Signal Debugger (Equity Mode)
Purpose: Lightweight harness to step-through Strategy 3A logic using static Equity data (QQQ).

Description:
    Bypasses the Futures/Parquet pipeline to run the engine on simple CSV data.
    Useful for:
    1. Verifying signal logic without needing Databento API credits.
    2. Debugging specific edge cases (e.g., OR Break failures) in a controlled environment.
    3. Demonstrating Multi-Asset capability (Equity ETF vs. Futures).

Usage:
    python scripts/debug_tools/debug_signals_qqq.py --csv data/sample/QQQ_1min.csv
"""

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass

# Adjust path to find local package if running from root
sys.path.append(".")

from s3a_backtester.engine import generate_signals
from s3a_backtester.data_io import load_minute_df, slice_rth, resample
from s3a_backtester.features import (
    compute_session_vwap_bands,
    compute_session_refs,
    find_swings_1m,
)
from s3a_backtester.structure import trend_5m, micro_swing_break


@dataclass
class MockConfig:
    """Minimal config to put engine in 'Production' mode."""

    class Signals:
        disqualify_after_unlock = True
        zone_touch_mode = "range"
        trigger_lookback_bars = 3

    class Instrument:
        tick_size = 0.01  # Equity tick size

    class Risk:
        max_stop_or_mult = 1.25

    signals = Signals()
    instrument = Instrument()
    risk = Risk()
    entry_window = None  # Use default 09:35-11:00


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to 1-min OHLCV CSV file")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"[ERROR] File not found: {csv_path}")
        sys.exit(1)

    print(f"[INFO] Loading {csv_path}...")

    # 1) Load and slice to RTH
    # Note: CSV must have columns: date/time or datetime, open, high, low, close, volume
    df1 = load_minute_df(str(csv_path))
    df1 = slice_rth(df1)

    if df1.empty:
        print("[WARN] DataFrame empty after RTH slice. Check timestamps/timezone.")
        sys.exit(0)

    # 2) Feature Engineering (Manual Scaffolding)
    print("[INFO] Computing Session Refs & VWAP...")
    df1 = compute_session_refs(df1)

    bands = compute_session_vwap_bands(df1)
    df1["vwap"] = bands["vwap"]
    df1["vwap_1u"] = bands["band_p1"]
    df1["vwap_1d"] = bands["band_m1"]
    df1["vwap_2u"] = bands["band_p2"]
    df1["vwap_2d"] = bands["band_m2"]

    # 4) 5-minute trend structure
    print("[INFO] Resampling & Trend...")
    df5 = resample(df1, "5min")
    tr5 = trend_5m(df5)

    # Forward fill 5m trend to 1m
    df1["trend_5m"] = tr5["trend_5m"].reindex(df1.index, method="ffill").fillna(0)

    # 5) Micro-structure
    print("[INFO] Swings & Micro-Breaks...")
    sw = find_swings_1m(df1)
    df1["swing_high"] = sw["swing_high"]
    df1["swing_low"] = sw["swing_low"]

    mb = micro_swing_break(df1)
    df1["micro_break_dir"] = mb["micro_break_dir"]

    # 6) Engine Execution
    print("[INFO] Generating Signals...")
    cfg = MockConfig()
    sig = generate_signals(df1, cfg=cfg)

    # 7) Diagnostics
    print("-" * 40)
    print(f"Total Bars: {len(sig)}")
    print(f"Unlock Events: {sig['or_break_unlock'].sum()}")
    print(f"Zone Touches:  {sig['in_zone'].sum()}")
    print(f"Valid Triggers: {sig['trigger_ok'].sum()}")
    print("-" * 40)

    # Show first few triggers if any
    # FIX: Cast to bool to satisfy linter (E712) and ensure safety
    triggers = sig[sig["trigger_ok"].astype(bool)]

    if not triggers.empty:
        print("\nSample Triggers:")
        cols = ["close", "direction", "vwap", "or_break_unlock", "in_zone"]
        print(triggers[cols].head())
    else:
        print("\n(No triggers found in this dataset)")


if __name__ == "__main__":
    main()
