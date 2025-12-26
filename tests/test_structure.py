"""
Tests for s3a_backtester.structure
----------------------------------
Coverage:
- 5-Minute Trend Detection (Higher Highs/Lows).
- Micro Swing Break Logic (Bullish/Bearish).
- Engulfing Candle Logic (Bullish/Bearish).
"""

import pandas as pd
from s3a_backtester.structure import trend_5m, Trend5mConfig, micro_swing_break


def test_trend_5m_detects_uptrend():
    idx = pd.date_range(
        "2024-01-01 09:30", periods=20, freq="5min", tz="America/New_York"
    )
    df = pd.DataFrame(
        {
            "high": range(20),
            "low": range(20),
            "close": range(20),
            "open": range(20),
            "volume": 1,
        },
        index=idx,
    )

    out = trend_5m(df, Trend5mConfig(lookback=3))
    assert out["trend_5m"].iloc[-1] == 1


def test_trend_5m_detects_downtrend():
    idx = pd.date_range(
        "2024-01-01 09:30", periods=20, freq="5min", tz="America/New_York"
    )
    vals = list(range(20, 0, -1))
    df = pd.DataFrame(
        {"high": vals, "low": vals, "close": vals, "open": vals, "volume": 1}, index=idx
    )

    out = trend_5m(df, Trend5mConfig(lookback=3))
    assert out["trend_5m"].iloc[-1] == -1


def test_micro_swing_break_up():
    idx = pd.date_range(
        "2024-01-01 09:30", periods=10, freq="1min", tz="America/New_York"
    )
    df = pd.DataFrame(
        {
            "high": [10, 11, 10, 12, 10],
            "low": [9, 9, 9, 9, 9],
            "close": 10,
            "open": 10,
            "volume": 1,
        },
        index=idx[:5],
    )
    df["swing_high"] = False
    df.loc[idx[1], "swing_high"] = True  # High at 11

    out = micro_swing_break(df)
    # Idx 3 (High 12) breaks Idx 1 (High 11)
    assert out["micro_break_dir"].iloc[3] == 1


def test_micro_swing_break_down():
    idx = pd.date_range(
        "2024-01-01 09:30", periods=10, freq="1min", tz="America/New_York"
    )
    df = pd.DataFrame(
        {
            "high": [12, 12, 12, 12, 12],
            "low": [10, 9, 10, 8, 10],
            "close": 10,
            "open": 10,
            "volume": 1,
        },
        index=idx[:5],
    )
    df["swing_high"] = False
    df["swing_low"] = False
    df.loc[idx[1], "swing_low"] = True  # Low at 9

    out = micro_swing_break(df)
    # Idx 3 (Low 8) breaks Idx 1 (Low 9)
    assert out["micro_break_dir"].iloc[3] == -1


def test_engulfing_pattern():
    idx = pd.date_range("2024-01-01 09:30", periods=2, freq="1min")
    # Bar 0: Red (Open 100, Close 99)
    # Bar 1: Green (Open 98, Close 101) -> Engulfs
    df = pd.DataFrame(
        {
            "open": [100, 98],
            "close": [99, 101],
            "high": [100, 101],
            "low": [99, 98],
            "volume": 1,
        },
        index=idx,
    )
    df["swing_high"] = False
    df["swing_low"] = False

    out = micro_swing_break(df)
    assert out["engulf_dir"].iloc[1] == 1
