"""
Tests for s3a_backtester.cli
----------------------------
Coverage:
- Command: backtest.
- Command: walkforward.
- Command: monte-carlo.
"""

import json
import sys

import pandas as pd

from s3a_backtester.cli import cmd_backtest, cmd_walkforward, main


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


def test_main_records_argv_and_artifacts(tmp_path, synth_parquet, monkeypatch):
    out = tmp_path / "out"
    argv = [
        "backtest",
        "--config",
        "configs/base.yaml",
        "--data",
        str(synth_parquet),
        "--out-dir",
        str(out),
        "--run-id",
        "bt",
        "--no-write-signals",
    ]
    monkeypatch.setattr(sys, "argv", ["meridian"] + argv)

    main(None)

    meta_path = out / "bt" / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta["argv"] == argv
    assert "data_sha256" in meta
    artifacts = meta.get("artifacts")
    assert artifacts is not None
    assert "summary.json" in artifacts
    assert "trades.parquet" in artifacts
    assert artifacts["summary.json"]["bytes"] > 0


def test_main_can_disable_hash_data(tmp_path, synth_parquet, monkeypatch):
    out = tmp_path / "out"
    argv = [
        "backtest",
        "--config",
        "configs/base.yaml",
        "--data",
        str(synth_parquet),
        "--out-dir",
        str(out),
        "--run-id",
        "bt_nohash",
        "--no-hash-data",
    ]
    monkeypatch.setattr(sys, "argv", ["meridian"] + argv)

    main(None)

    meta_path = out / "bt_nohash" / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert "data_sha256" not in meta


def test_monte_carlo_accepts_trades_alias(tmp_path, monkeypatch):
    trades_path = tmp_path / "trades.parquet"
    trades = pd.DataFrame({"realized_R": [1.0, -0.5, 0.25]})
    trades.to_parquet(trades_path, index=False)

    out = tmp_path / "out"
    argv = [
        "monte-carlo",
        "--config",
        "configs/base.yaml",
        "--trades",
        str(trades_path),
        "--years",
        "1",
        "--seed",
        "123",
        "--out-dir",
        str(out),
        "--run-id",
        "mc",
    ]
    monkeypatch.setattr(sys, "argv", ["meridian"] + argv)

    main(None)

    assert (out / "mc" / "summary.json").exists()
