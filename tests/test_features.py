import numpy as np
import pandas as pd
import pytest

from s3a_backtester.features import (
    compute_session_refs,
    compute_session_vwap_bands,
    compute_atr15,
)


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
