# Tests for the features
import numpy as np
import pandas as pd
import pytest

from s3a_backtester.features import (
    compute_session_refs,
    compute_session_vwap_bands,
    compute_atr15,
    find_swings_1m,
)


# -----------------------------------
# Test Import and Shapes
# -----------------------------------
def test_features_import_and_shapes():
    idx = pd.date_range(
        "2024-01-02 09:30", periods=10, freq="1min", tz="America/New_York"
    )
    df = pd.DataFrame(
        {
            "open": [1] * 10,
            "high": [1] * 10,
            "low": [1] * 10,
            "close": [1] * 10,
            "volume": [1] * 10,
        },
        index=idx,
    )
    refs = compute_session_refs(df)
    bands = compute_session_vwap_bands(df)
    atr = compute_atr15(df)
    assert "or_high" in refs.columns and "or_low" in refs.columns
    assert "vwap" in bands.columns and "band_p2" in bands.columns
    assert atr.name == "atr15" and len(atr) == len(df)


# -----------------------------------
# Test computing ATR15's basic shape and values
# -----------------------------------
def test_compute_atr15_basic_shape_and_values():
    idx = pd.date_range(
        "2024-01-02 09:30",
        periods=30,
        freq="1min",
        tz="America/New_York",
    )

    # Synthetic series with constant 1.0 high-low range.
    base = np.linspace(100.0, 101.0, len(idx))
    close = pd.Series(base, index=idx)
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1,
        },
        index=idx,
    )

    atr = compute_atr15(df)

    # Same length, no NaNs, non-negative
    assert len(atr) == len(df)
    assert atr.isna().sum() == 0
    assert (atr >= 0).all()

    # With constant true range (=1.0), ATR should converge to ~1.0
    assert atr.iloc[-1] == pytest.approx(1.0, rel=1e-6)


# -----------------------------------
# Test swing 1m basics
# -----------------------------------
def test_find_swings_1m_basic():
    idx = pd.date_range(
        "2024-01-02 09:30",
        periods=7,
        freq="1min",
        tz="America/New_York",
    )
    # Shape highs so that bars at positions 1 and 3 are obvious peaks
    highs = [1.0, 3.0, 2.0, 4.0, 2.0, 1.0, 0.5]
    # Lows shaped so that positions 1 and 3 are obvious troughs as well
    lows = [1.0, 0.5, 1.2, 0.3, 1.1, 0.9, 0.8]

    df = pd.DataFrame(
        {
            "open": highs,
            "high": highs,
            "low": lows,
            "close": highs,
            "volume": 1,
        },
        index=idx,
    )

    out = find_swings_1m(df, lb=1, rb=1)

    swing_high_idx = list(out.index[out["swing_high"]])
    swing_low_idx = list(out.index[out["swing_low"]])

    assert swing_high_idx == [idx[1], idx[3]]
    assert swing_low_idx == [idx[1], idx[3]]


def test_find_swings_1m_respects_session_boundaries():
    idx_day1 = pd.date_range(
        "2024-01-02 09:30",
        periods=3,
        freq="1min",
        tz="America/New_York",
    )
    idx_day2 = pd.date_range(
        "2024-01-03 09:30",
        periods=3,
        freq="1min",
        tz="America/New_York",
    )
    idx = idx_day1.append(idx_day2)

    # Make the middle bar of each day a clear local high *within that day*
    highs = [1.0, 3.0, 1.0, 1.0, 5.0, 1.0]
    lows = [1.0, 0.5, 1.2, 1.0, 0.4, 1.1]

    df = pd.DataFrame(
        {
            "open": highs,
            "high": highs,
            "low": lows,
            "close": highs,
            "volume": 1,
        },
        index=idx,
    )

    out = find_swings_1m(df, lb=1, rb=1)

    swing_high_idx = list(out.index[out["swing_high"]])

    # Expect one swing high in each session (second bar of each day)
    assert swing_high_idx == [idx_day1[1], idx_day2[1]]
