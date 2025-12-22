# Test file for Metrics
import pandas as pd

from s3a_backtester.metrics import (
    compute_summary,
    equity_curve_R,
    grouped_summary,
    max_drawdown_R,
    sqn,
)


def test_metrics_empty_safe():
    trades = pd.DataFrame()
    s = compute_summary(trades)
    assert s["trades"] == 0
    assert s["expectancy_R"] == 0.0
    curve = equity_curve_R(trades)
    assert float(max_drawdown_R(curve)) == 0.0
    assert float(sqn(trades)) == 0.0


def test_metrics_trades_per_month_and_expectancy():
    trades = pd.DataFrame(
        {
            "realized_R": [1.0, -1.0, 2.0],
            "entry_time": [
                "2025-01-03 10:00:00",
                "2025-01-15 11:00:00",
                "2025-02-01 10:00:00",
            ],
        }
    )
    s = compute_summary(trades)
    assert s["trades"] == 3
    assert s["trades_per_month"] == 1.5  # 3 trades over 2 months with trades
    assert abs(s["expectancy_R"] - (2.0 / 3.0)) < 1e-9


def test_grouped_summary_month():
    trades = pd.DataFrame(
        {
            "realized_R": [1.0, -1.0, 2.0, 0.5],
            "entry_time": [
                "2025-01-03 10:00:00",
                "2025-01-15 11:00:00",
                "2025-02-01 10:00:00",
                "2025-02-10 12:00:00",
            ],
            "or_height": [10, 20, 30, 40],
        }
    )
    out = grouped_summary(trades, by="month")
    assert set(out.index) == {"2025-01", "2025-02"}
    assert out.loc["2025-01", "trades"] == 2
    assert out.loc["2025-02", "trades"] == 2


def test_maxdd_r_anchors_at_zero_for_negative_start():
    import pandas as pd
    from s3a_backtester.metrics import equity_curve_R, max_drawdown_R

    trades = pd.DataFrame({"realized_R": [-1.0, 0.1]})
    curve = equity_curve_R(trades)  # [-1.0, -0.9]
    assert max_drawdown_R(curve) == 1.0
