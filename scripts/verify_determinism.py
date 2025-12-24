# Script to verify the determinism
from __future__ import annotations

import json
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
    # EDIT these to match the local paths
    trades_file = r"outputs\walkforward\nq_12m_wf\oos_trades.parquet"
    seed = 123
    base = "determinism_mc"

    run1 = base + "_a"
    run2 = base + "_b"

    cli_main(
        [
            "monte-carlo",
            "--config",
            "configs/base.yaml",
            "--trades-file",
            trades_file,
            "--n-paths",
            "2000",
            "--risk-per-trade",
            "0.01",
            "--block-size",
            "5",
            "--seed",
            str(seed),
            "--run-id",
            run1,
        ]
    )

    cli_main(
        [
            "monte-carlo",
            "--config",
            "configs/base.yaml",
            "--trades-file",
            trades_file,
            "--n-paths",
            "2000",
            "--risk-per-trade",
            "0.01",
            "--block-size",
            "5",
            "--seed",
            str(seed),
            "--run-id",
            run2,
        ]
    )

    p1 = Path("outputs") / "monte-carlo" / run1
    p2 = Path("outputs") / "monte-carlo" / run2

    s1 = read_json(p1 / "summary.json")
    s2 = read_json(p2 / "summary.json")

    if s1 != s2:
        raise SystemExit("FAIL: summary.json differs across identical seeded runs")

    df1 = pd.read_parquet(p1 / "mc_samples.parquet")
    df2 = pd.read_parquet(p2 / "mc_samples.parquet")

    if df_fingerprint(df1) != df_fingerprint(df2):
        raise SystemExit(
            "FAIL: mc_samples.parquet content differs across identical seeded runs"
        )

    print("PASS: MC determinism verified (summary + samples match).")


if __name__ == "__main__":
    main()
