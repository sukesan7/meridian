from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from s3a_backtester.cli import cmd_mc


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def test_cmd_mc_smoke_and_determinism(tmp_path: Path) -> None:
    # Tiny trades input (avoid needing timestamps by passing years=1.0)
    trades = pd.DataFrame(
        {
            "entry_time": pd.date_range("2025-01-01", periods=10, freq="D", tz="UTC"),
            "realized_R": [0.5, -1.0, 1.2, 0.3, -0.2, 0.8, -0.6, 1.0, 0.1, -0.4],
        }
    )
    trades_path = tmp_path / "trades.parquet"
    trades.to_parquet(trades_path, index=False)

    out_dir = tmp_path / "mc_out"

    # Run twice with same seed, expect identical outputs
    cmd_mc(
        "configs/base.yaml",
        str(trades_path),
        out_dir=str(out_dir),
        run_id="mc_a",
        n_paths=300,
        risk_per_trade=0.01,
        block_size=3,
        seed=123,
        years=1.0,  # fixed to avoid any dependency on trade time span
        keep_equity_paths=False,
        hash_data=False,
        argv=["monte-carlo", "--seed", "123"],
    )
    cmd_mc(
        "configs/base.yaml",
        str(trades_path),
        out_dir=str(out_dir),
        run_id="mc_b",
        n_paths=300,
        risk_per_trade=0.01,
        block_size=3,
        seed=123,
        years=1.0,
        keep_equity_paths=False,
        hash_data=False,
        argv=["monte-carlo", "--seed", "123"],
    )

    a_root = out_dir / "mc_a"
    b_root = out_dir / "mc_b"

    # smoke: artifacts exist
    assert (a_root / "summary.json").exists()
    assert (a_root / "run_meta.json").exists()
    assert (a_root / "mc_samples.parquet").exists()

    # determinism: summaries match exactly
    a = _read_json(a_root / "summary.json")
    b = _read_json(b_root / "summary.json")
    assert a == b
