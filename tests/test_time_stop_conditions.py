"""
Tests for s3a_backtester.time_stop_conditions
---------------------------------------------
Coverage:
- Time Stop Boolean Builders (VWAP Side, Trend, Sigma, Drawdown).
"""

import pandas as pd
from s3a_backtester.time_stop_conditions import build_time_stop_condition_series


def test_time_stop_builder_basic():
    idx = pd.date_range("2024-01-01", periods=5, freq="1min")
    df = pd.DataFrame(
        {"close": [100, 101, 102, 99, 100], "vwap": 100.0, "trend_5m": 1}, index=idx
    )

    # Long trade
    res = build_time_stop_condition_series(
        df, entry_idx=0, side_sign=1, entry_price=100, stop_price=99
    )

    # VWAP Side OK when Close >= VWAP
    assert res.vwap_side_ok.iloc[0]  # 100 >= 100
    assert not res.vwap_side_ok.iloc[3]  # 99 < 100

    # Trend OK (1 == 1)
    assert res.trend_ok.all()
