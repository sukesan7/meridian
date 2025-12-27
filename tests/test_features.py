"""
Tests for s3a_backtester.features
---------------------------------
Coverage:
- Session Reference Levels (OR High/Low).
- VWAP Band Computation.
- ATR15 Calculation.
- Swing High/Low Detection.
"""

import pandas as pd
import numpy as np
from s3a_backtester.features import (
    compute_session_refs,
    compute_session_vwap_bands,
    compute_atr15,
    find_swings_1m,
)


def test_compute_session_refs():
    dates = pd.date_range("2023-01-01 09:30", periods=10, freq="1min")
    df = pd.DataFrame(
        {"open": 100, "high": 105, "low": 95, "close": 100, "volume": 100}, index=dates
    )

    res = compute_session_refs(df)
    assert "or_high" in res.columns
    assert res["or_high"].iloc[-1] == 105
    assert res["or_low"].iloc[-1] == 95
    assert res["or_height"].iloc[-1] == 10


def test_compute_session_vwap_bands():
    dates = pd.date_range("2023-01-01 09:30", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "open": 100,
            "high": 100,
            "low": 100,
            "close": 100,
            "volume": [100, 100, 100, 100, 100],
        },
        index=dates,
    )

    res = compute_session_vwap_bands(df)
    assert "vwap" in res.columns
    assert "vwap_sd" in res.columns
    assert res["vwap"].iloc[-1] == 100.0
    assert res["vwap_sd"].iloc[-1] == 0.0


def test_compute_atr15():
    dates = pd.date_range("2023-01-01 09:30", periods=20, freq="1min")
    df = pd.DataFrame(
        {
            "high": np.linspace(101, 120, 20),
            "low": np.linspace(99, 118, 20),
            "close": np.linspace(100, 119, 20),
        },
        index=dates,
    )
    atr = compute_atr15(df, window=14)
    assert not atr.isna().all()
    assert abs(atr.iloc[-1] - 2.0) < 0.1


def test_find_swings_1m():
    prices = [10, 11, 12, 15, 12, 11, 10]
    dates = pd.date_range("2023-01-01 09:30", periods=len(prices), freq="1min")
    df = pd.DataFrame({"high": prices, "low": prices, "close": prices}, index=dates)

    res = find_swings_1m(df, lb=1, rb=1)

    assert "swing_high_confirmed" in res.columns
    assert not res["swing_high_confirmed"].iloc[3]
    assert res["swing_high_confirmed"].iloc[4]
    assert res["last_swing_high_price"].iloc[4] == 15.0
