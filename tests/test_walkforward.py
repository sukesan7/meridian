import pandas as pd

from s3a_backtester.walkforward import rolling_walkforward_frames


def test_walkforward_windowing_and_outputs():
    # 30 sessions, 1 bar per session at 10:00
    sessions = pd.date_range("2025-01-01", periods=30, freq="D")
    idx = sessions + pd.Timedelta(hours=10)
    df1 = pd.DataFrame({"open": 1.0}, index=idx)

    def fake_backtest(df1_in, df5_in, cfg, *, params, regime, window_id):
        # 3 trades per window, distinguish IS vs OOS by regime
        base = pd.to_datetime(df1_in.index.min()).normalize()
        entry = [base + pd.Timedelta(hours=10 + i) for i in range(3)]
        exit_ = [t + pd.Timedelta(minutes=5) for t in entry]
        r = [1.0, 1.0, 1.0] if regime == "IS" else [-1.0, -1.0, -1.0]
        return pd.DataFrame(
            {
                "entry_time": entry,
                "exit_time": exit_,
                "realized_R": r,
                "or_height": [10.0, 20.0, 30.0],
            }
        )

    out = rolling_walkforward_frames(
        df1,
        df5=None,
        cfg=None,
        is_days=10,
        oos_days=5,
        step=5,
        run_backtest_fn=fake_backtest,
    )

    is_summary = out["is_summary"]
    oos_summary = out["oos_summary"]
    wf_equity = out["wf_equity"]
    is_trades = out["is_trades"]
    oos_trades = out["oos_trades"]

    # 30 sessions with (10 IS + 5 OOS), step=5 -> window starts: 0,5,10,15 => 4 windows
    assert len(is_summary) == 4
    assert len(oos_summary) == 4

    # Each window: 3 trades, expectancy_R should match regime R
    assert (is_summary["trades"] == 3).all()
    assert (oos_summary["trades"] == 3).all()
    assert (is_summary["expectancy_R"] == 1.0).all()
    assert (oos_summary["expectancy_R"] == -1.0).all()

    # Trades should be labeled
    assert set(is_trades["regime"].unique()) == {"IS"}
    assert set(oos_trades["regime"].unique()) == {"OOS"}
    assert set(is_trades["window_id"].unique()) == {0, 1, 2, 3}
    assert set(oos_trades["window_id"].unique()) == {0, 1, 2, 3}

    # OOS equity steps exist: 4 windows * 3 trades = 12 rows
    assert len(wf_equity) == 12
    assert set(wf_equity["regime"].unique()) == {"OOS"}
    assert set(wf_equity["window_id"].unique()) == {0, 1, 2, 3}
