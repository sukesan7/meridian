"""
Tests for s3a_backtester.metrics
--------------------------------
Coverage:
- Summary Statistics (Win Rate, Avg R, Expectancy).
- Equity Curve Calculation.
- Max Drawdown Calculation.
"""

import pandas as pd
from s3a_backtester.metrics import compute_summary


def test_metrics_calculation():
    trades = pd.DataFrame(
        {
            "realized_R": [1.0, -1.0, 2.0],
            "entry_time": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        }
    )
    s = compute_summary(trades)
    assert s["trades"] == 3
    assert s["sum_R"] == 2.0
    assert s["maxDD_R"] == 1.0  # 1.0 -> 0.0 -> 2.0


def test_metrics_empty():
    s = compute_summary(pd.DataFrame())
    assert s["trades"] == 0
    assert s["expectancy_R"] == 0.0
