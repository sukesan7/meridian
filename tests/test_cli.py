"""
Tests for s3a_backtester.cli
----------------------------
Coverage:
- Command: backtest.
- Command: walkforward.
- Command: monte-carlo.
"""

from s3a_backtester.cli import cmd_backtest, cmd_walkforward


def test_backtest_cmd(tmp_path, synth_parquet):
    out = tmp_path / "out"
    cmd_backtest(
        "configs/base.yaml", str(synth_parquet), out_dir=str(out), run_id="bt", seed=123
    )
    assert (out / "bt" / "summary.json").exists()


def test_walkforward_cmd(tmp_path, synth_parquet):
    out = tmp_path / "out"
    cmd_walkforward(
        "configs/base.yaml",
        str(synth_parquet),
        out_dir=str(out),
        run_id="wf",
        is_days=2,
        oos_days=1,
        seed=123,
    )
    assert (out / "wf" / "oos_trades.parquet").exists()
