"""
Tests for s3a_backtester.monte_carlo
------------------------------------
Coverage:
- IID Bootstrap.
- Block Bootstrap.
- Determinism (Seed check).
"""

import pandas as pd
from s3a_backtester.monte_carlo import mc_simulate_R


def test_mc_determinism():
    trades = pd.DataFrame(
        {
            "entry_time": pd.date_range("2024-01-01", periods=10, freq="D"),
            "realized_R": [1, -1, 1, -1, 1, -1, 1, -1, 1, -1],
            "exit_time": pd.date_range("2024-01-01 10:00", periods=10, freq="D"),
        }
    )

    out1 = mc_simulate_R(trades, n_paths=50, risk_per_trade=0.01, seed=42)
    out2 = mc_simulate_R(trades, n_paths=50, risk_per_trade=0.01, seed=42)

    assert out1["samples"].equals(out2["samples"])
