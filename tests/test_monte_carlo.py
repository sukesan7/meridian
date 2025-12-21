# Test for Monte Carlo Simulation
from __future__ import annotations

import pandas as pd

from s3a_backtester.monte_carlo import mc_simulate_R


def _toy_trades() -> pd.DataFrame:
    # ~1 year span so CAGR annualization is sensible
    entry = pd.date_range("2025-01-01", periods=10, freq="30D")
    exit_ = entry + pd.Timedelta(minutes=5)
    r = [1.0, -0.5, 0.8, -1.2, 1.5, -0.7, 0.4, 0.2, -0.3, 0.9]
    return pd.DataFrame({"entry_time": entry, "exit_time": exit_, "realized_R": r})


def test_mc_deterministic_with_seed():
    trades = _toy_trades()
    out1 = mc_simulate_R(trades, n_paths=200, risk_per_trade=0.01, seed=123)
    out2 = mc_simulate_R(trades, n_paths=200, risk_per_trade=0.01, seed=123)

    pd.testing.assert_frame_equal(out1["samples"], out2["samples"])
    assert out1["summary"] == out2["summary"]


def test_mc_block_bootstrap_runs():
    trades = _toy_trades()
    out = mc_simulate_R(trades, n_paths=100, risk_per_trade=0.01, block_size=3, seed=7)
    samples = out["samples"]
    assert len(samples) == 100
    assert samples["maxDD_pct"].between(0.0, 1.0).all()
    assert samples["final_equity"].ge(0.0).all()


def test_mc_zero_r_is_zero_risk():
    entry = pd.date_range("2025-01-01", periods=20, freq="7D")
    exit_ = entry + pd.Timedelta(minutes=1)
    trades = pd.DataFrame({"entry_time": entry, "exit_time": exit_, "realized_R": 0.0})

    out = mc_simulate_R(trades, n_paths=50, risk_per_trade=0.02, seed=1)
    samples = out["samples"]

    assert (samples["maxDD_pct"] == 0.0).all()
    assert (samples["cagr"] == 0.0).all()
    assert (samples["final_equity"] == 1.0).all()
    assert out["summary"]["blowup_rate"] == 0.0
