from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from s3a_backtester.cli import cmd_backtest, cmd_walkforward, cmd_mc


def read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def test_backtest_writes_artifacts(tmp_path: Path, synth_parquet: Path) -> None:
    out_dir = tmp_path / "outputs_backtest"

    cmd_backtest(
        "configs/base.yaml",
        str(synth_parquet),
        out_dir=str(out_dir),
        run_id="t_bt",
        date_from="2025-01-06",
        date_to="2025-01-08",
        write_signals=False,
        write_trades=True,
        seed=123,
        hash_data=False,
        argv=["backtest", "--seed", "123"],
    )

    root = out_dir / "t_bt"
    assert (root / "summary.json").exists()
    assert (root / "run_meta.json").exists()
    assert (root / "trades.parquet").exists()

    summary = read_json(root / "summary.json")
    for k in ("trades", "win_rate", "avg_R", "maxDD_R", "SQN"):
        assert k in summary


def test_walkforward_writes_artifacts(tmp_path: Path, synth_parquet: Path) -> None:
    out_dir = tmp_path / "outputs_wf"

    cmd_walkforward(
        "configs/base.yaml",
        str(synth_parquet),
        out_dir=str(out_dir),
        run_id="t_wf",
        date_from="2025-01-06",
        date_to="2025-01-08",
        is_days=2,
        oos_days=1,
        step=1,
        write_trades=True,
        write_equity=False,
        seed=123,
        hash_data=False,
        argv=["walkforward", "--seed", "123"],
    )

    root = out_dir / "t_wf"
    assert (root / "summary.json").exists()
    assert (root / "run_meta.json").exists()
    assert (root / "is_summary.csv").exists()
    assert (root / "oos_summary.csv").exists()
    assert (root / "oos_trades.parquet").exists()


def test_mc_deterministic_seed(tmp_path: Path, synth_parquet: Path) -> None:
    # 1) Generate a small trades file via backtest
    bt_out = tmp_path / "bt"
    cmd_backtest(
        "configs/base.yaml",
        str(synth_parquet),
        out_dir=str(bt_out),
        run_id="bt1",
        date_from="2025-01-06",
        date_to="2025-01-08",
        write_signals=False,
        write_trades=True,
        seed=123,
        argv=["backtest", "--seed", "123"],
    )
    trades_file = bt_out / "bt1" / "trades.parquet"

    # 2) Run MC twice with same seed
    mc_out = tmp_path / "mc"

    cmd_mc(
        "configs/base.yaml",
        str(trades_file),
        out_dir=str(mc_out),
        run_id="mc_a",
        n_paths=200,
        risk_per_trade=0.01,
        block_size=3,
        seed=999,
        years=None,
        keep_equity_paths=False,
        argv=["monte-carlo", "--seed", "999"],
    )
    cmd_mc(
        "configs/base.yaml",
        str(trades_file),
        out_dir=str(mc_out),
        run_id="mc_b",
        n_paths=200,
        risk_per_trade=0.01,
        block_size=3,
        seed=999,
        years=None,
        keep_equity_paths=False,
        argv=["monte-carlo", "--seed", "999"],
    )

    a = read_json(mc_out / "mc_a" / "summary.json")
    b = read_json(mc_out / "mc_b" / "summary.json")
    assert a == b

    sa = pd.read_parquet(mc_out / "mc_a" / "mc_samples.parquet")
    sb = pd.read_parquet(mc_out / "mc_b" / "mc_samples.parquet")
    assert sa.equals(sb)
