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
from s3a_backtester.features import (
    compute_session_refs,
    compute_session_vwap_bands,
    compute_atr15,
    find_swings_1m,
)


def test_session_refs_columns(sample_minute_df):
    refs = compute_session_refs(sample_minute_df)
    assert {"or_high", "or_low", "or_height"}.issubset(refs.columns)


def test_vwap_bands_logic(sample_minute_df):
    bands = compute_session_vwap_bands(sample_minute_df)
    valid = bands.dropna()
    if not valid.empty:
        assert (valid["band_p1"] >= valid["vwap"]).all()
        assert (valid["vwap"] >= valid["band_m1"]).all()


def test_atr15_shape(sample_minute_df):
    atr = compute_atr15(sample_minute_df)
    assert len(atr) == len(sample_minute_df)
    assert atr.name == "atr15"


def test_find_swings_1m():
    idx = pd.date_range(
        "2024-01-01 09:30", periods=5, freq="1min", tz="America/New_York"
    )
    df = pd.DataFrame(
        {
            "high": [1, 5, 1, 1, 1],
            "low": [1, 1, 1, 1, 1],
            "close": 1,
            "open": 1,
            "volume": 1,
        },
        index=idx,
    )
    sw = find_swings_1m(df, lb=1, rb=1)
    # Middle bar (idx 1) is high (5 > 1)
    assert sw["swing_high"].iloc[1]
