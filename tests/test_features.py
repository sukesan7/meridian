from s3a_backtester.features import (
    compute_session_refs,
    compute_session_vwap_bands,
    compute_atr15,
)
import pandas as pd


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
