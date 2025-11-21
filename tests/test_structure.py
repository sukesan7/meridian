import pandas as pd

from s3a_backtester.structure import trend_5m, Trend5mConfig


def _make_simple_day(direction: str = "up") -> pd.DataFrame:
    idx = pd.date_range(
        "2024-01-02 09:30",
        periods=10,
        freq="5min",
        tz="America/New_York",
    )

    if direction == "up":
        highs = range(1, 11)
        lows = range(0, 10)
    else:
        highs = range(11, 1, -1)
        lows = range(10, 0, -1)

    df = pd.DataFrame(
        {
            "open": list(highs),
            "high": list(highs),
            "low": list(lows),
            "close": list(highs),
        },
        index=idx,
    )
    # simple flat VWAP in the middle so VWAP-side check is deterministic
    df["vwap"] = 5.0
    return df


def test_trend_5m_uptrend_basic():
    df = _make_simple_day("up")
    cfg = Trend5mConfig(lookback=3)
    out = trend_5m(df, cfg)

    assert "trend_5m" in out.columns
    assert "trend_vwap_ok" in out.columns

    # After a few bars the trend should lock in as +1
    assert out["trend_5m"].iloc[-1] == 1
    # In this synthetic series all closes are above VWAP=5 after the early bars
    assert out["trend_vwap_ok"].iloc[-1]


def test_trend_5m_downtrend_basic():
    df = _make_simple_day("down")
    cfg = Trend5mConfig(lookback=3)
    out = trend_5m(df, cfg)

    # Trend should end as -1
    assert out["trend_5m"].iloc[-1] == -1
    # Closes are below VWAP=5 for most of the series → last bar OK for downtrend
    assert out["trend_vwap_ok"].iloc[-1]
