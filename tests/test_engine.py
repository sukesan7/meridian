from s3a_backtester.engine import generate_signals, simulate_trades
import pandas as pd


def test_engine_stubs_run():
    idx = pd.date_range(
        "2024-01-02 09:30", periods=10, freq="1min", tz="America/New_York"
    )
    df1 = pd.DataFrame(
        {
            "open": [1] * 10,
            "high": [1] * 10,
            "low": [1] * 10,
            "close": [1] * 10,
            "volume": [1] * 10,
        },
        index=idx,
    )
    df5 = (
        df1.resample("5T", label="right", closed="right")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )

    class _Cfg:  # minimal shim
        entry_window = type("EW", (), {"start": "09:35", "end": "11:00"})()

    sig = generate_signals(df1, df5, _Cfg)
    assert {
        "time_window_ok",
        "or_break_unlock",
        "in_zone",
        "trigger_ok",
        "disqualified_±2σ",
        "riskcap_ok",
    } <= set(sig.columns)
    trades = simulate_trades(df1, sig, _Cfg)
    assert list(trades.columns)  # has schema
