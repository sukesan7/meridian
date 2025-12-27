"""
Script: Verify Determinism
Purpose: Validates that the engine produces bit-exact outputs given the same seed.

Description:
    Runs the Monte Carlo engine twice with identical configuration and seeds.
    Compares the resulting `summary.json` and `mc_samples.parquet` binary fingerprints.
    Crucial for regression testing in CI/CD pipelines.

Usage:
    python scripts/verify_determinism.py --trades-file outputs/backtest/quickstart_bt/trades.parquet
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import pandas as pd
from s3a_backtester.cli import main as cli_main


def read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def df_fingerprint(df: pd.DataFrame) -> str:
    # Stable fingerprint based on values+index
    h = pd.util.hash_pandas_object(df, index=True).values
    return str(int(h.sum()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--trades-file",
        required=True,
        help="Path to a trades.parquet file to bootstrap from.",
    )
    ap.add_argument("--seed", type=int, default=123)
    args = ap.parse_args()

    trades_path = Path(args.trades_file).resolve()
    if not trades_path.exists():
        print(f"[ERROR] Trades file not found: {trades_path}")
        sys.exit(1)

    base = "determinism_check"
    run1 = base + "_a"
    run2 = base + "_b"

    print(f"[INFO] verifying MC determinism using source: {trades_path.name}")

    # Run 1
    cli_main(
        [
            "monte-carlo",
            "--config",
            "configs/base.yaml",
            "--trades-file",
            str(trades_path),
            "--n-paths",
            "500",  # Lower count for speed
            "--risk-per-trade",
            "0.01",
            "--block-size",
            "5",
            "--seed",
            str(args.seed),
            "--run-id",
            run1,
        ]
    )

    # Run 2
    cli_main(
        [
            "monte-carlo",
            "--config",
            "configs/base.yaml",
            "--trades-file",
            str(trades_path),
            "--n-paths",
            "500",
            "--risk-per-trade",
            "0.01",
            "--block-size",
            "5",
            "--seed",
            str(args.seed),
            "--run-id",
            run2,
        ]
    )

    p1 = Path("outputs") / "monte-carlo" / run1
    p2 = Path("outputs") / "monte-carlo" / run2

    # Compare Summaries
    s1 = read_json(p1 / "summary.json")
    s2 = read_json(p2 / "summary.json")

    # Remove dynamic run_id for comparison
    s1.pop("run_id", None)
    s2.pop("run_id", None)

    if s1 != s2:
        print("[FAIL] summary.json differs across identical seeded runs")
        sys.exit(1)

    # Compare Parquet Content
    df1 = pd.read_parquet(p1 / "mc_samples.parquet")
    df2 = pd.read_parquet(p2 / "mc_samples.parquet")

    if df_fingerprint(df1) != df_fingerprint(df2):
        print("[FAIL] mc_samples.parquet binary content differs")
        sys.exit(1)

    print(f"[PASS] Determinism verified. Seed {args.seed} produces identical outputs.")


if __name__ == "__main__":
    main()
