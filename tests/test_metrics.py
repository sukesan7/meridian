from s3a_backtester.metrics import compute_summary, equity_curve_R, max_drawdown_R, sqn
import pandas as pd


def test_metrics_empty_safe():
    trades = pd.DataFrame()
    s = compute_summary(trades)
    assert s["trades"] == 0
    curve = equity_curve_R(trades)
    assert float(max_drawdown_R(curve)) == 0.0
    assert float(sqn(trades)) == 0.0
