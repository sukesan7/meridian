"""
Tests for s3a_backtester.walkforward
------------------------------------
Coverage:
- Rolling Window Iterator.
- IS/OOS Data Slicing.
"""

import pandas as pd
from s3a_backtester.walkforward import rolling_walkforward_frames


def mock_backtest(df1, df5, cfg, params, regime, window_id):
    return pd.DataFrame({"entry_time": df1.index, "realized_R": 1.0})


def test_wf_rolling_logic():
    # 10 days
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    df1 = pd.DataFrame({"close": 100}, index=idx)

    # 3 Days IS, 1 Day OOS, Step 1
    out = rolling_walkforward_frames(
        df1, None, None, is_days=3, oos_days=1, step=1, run_backtest_fn=mock_backtest
    )

    # Windows: [0-3,3], [1-4,4], [2-5,5] ... approx 6-7 windows
    assert len(out["oos_summary"]) >= 6
    assert "is_trades" in out
