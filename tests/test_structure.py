"""
Tests for s3a_backtester.structure
----------------------------------
Coverage:
- 5-minute Trend Detection (HH/HL, LH/LL).
- Micro-structure breaks (BOS) using Delayed/Confirmed logic.
- Engulfing Candle detection.
"""

import pandas as pd
import numpy as np
from s3a_backtester.structure import trend_5m, micro_swing_break, Trend5mConfig


def test_trend_5m_uptrend():
    """
    Simulate a perfect uptrend: Higher Highs + Higher Lows.
    """
    # Create 5-minute bars
    dates = pd.date_range("2023-01-01 09:30", periods=10, freq="5min")

    # Prices climbing steadily
    highs = np.linspace(100, 110, 10)
    lows = np.linspace(90, 100, 10)
    closes = highs - 1  # Close near high

    df = pd.DataFrame(
        {"high": highs, "low": lows, "close": closes, "vwap": 100.0},  # Dummy
        index=dates,
    )

    # Use a short lookback so trend establishes quickly
    cfg = Trend5mConfig(lookback=2)
    res = trend_5m(df, cfg)

    # By the end, we should be in an uptrend (1)
    assert res["trend_5m"].iloc[-1] == 1
    assert res["trend_hh_hl"].iloc[-1]


def test_trend_5m_downtrend():
    """
    Simulate a perfect downtrend: Lower Highs + Lower Lows.
    """
    dates = pd.date_range("2023-01-01 09:30", periods=10, freq="5min")

    # Prices falling steadily
    highs = np.linspace(110, 100, 10)
    lows = np.linspace(100, 90, 10)
    closes = lows + 1

    df = pd.DataFrame(
        {"high": highs, "low": lows, "close": closes, "vwap": 100.0}, index=dates
    )

    cfg = Trend5mConfig(lookback=2)
    res = trend_5m(df, cfg)

    assert res["trend_5m"].iloc[-1] == -1
    assert res["trend_lh_ll"].iloc[-1]


def test_micro_swing_break_up():
    """
    Test delayed swing break to the upside.
    We must manually mock 'last_swing_high_price' to simulate feature engineering.
    """
    dates = pd.date_range("2023-01-01 09:30", periods=5, freq="1min")
    df = pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 90.0, "close": 95.0}, index=dates
    )

    # 1. Setup: A Swing High exists at 105.0 (established in the past)
    df["last_swing_high_price"] = 105.0
    df["last_swing_low_price"] = 85.0

    # 2. Action: Price breaks 105.0 on the last bar
    df.loc[dates[-1], "high"] = 106.0

    # Run logic
    res = micro_swing_break(df)

    # Expectation: micro_break_dir == 1 on the last bar
    assert res["micro_break_dir"].iloc[-1] == 1


def test_micro_swing_break_down():
    """
    Test delayed swing break to the downside.
    """
    dates = pd.date_range("2023-01-01 09:30", periods=5, freq="1min")
    df = pd.DataFrame(
        {"open": 100.0, "high": 110.0, "low": 100.0, "close": 105.0}, index=dates
    )

    # 1. Setup: Swing Low exists at 95.0
    df["last_swing_high_price"] = 115.0
    df["last_swing_low_price"] = 95.0

    # 2. Action: Price breaks 95.0 on the last bar
    df.loc[dates[-1], "low"] = 94.0

    res = micro_swing_break(df)

    assert res["micro_break_dir"].iloc[-1] == -1


def test_engulfing_candle():
    """
    Test Bullish Engulfing pattern.
    """
    dates = pd.date_range("2023-01-01 09:30", periods=2, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 95.0],  # Bar 2 opens exactly at Bar 1 close (or lower)
            "high": [100.0, 102.0],
            "low": [90.0, 90.0],
            "close": [95.0, 101.0],
        },
        index=dates,
    )

    # 1st Bar: Red (Open 100 -> Close 95)
    # 2nd Bar: Green (Open 95 -> Close 101)
    # Bull Engulf Rule: Curr Open (95) <= Prev Close (95) AND Curr Close (101) >= Prev Open (100)

    res = micro_swing_break(df)

    # Expect 1 (Bull Engulf)
    assert res["engulf_dir"].iloc[-1] == 1
