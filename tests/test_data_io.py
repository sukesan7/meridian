"""
Tests for s3a_backtester.data_io
--------------------------------
Coverage:
- RTH Slicing.
- Resampling (Right-labeled).
- Loading & Normalization.
"""

import pandas as pd
import pytest
from datetime import time
from s3a_backtester.data_io import (
    load_minute_df,
    slice_rth,
    resample,
    validate_rth_completeness,
)


def test_io_integration(tmp_path, sample_minute_df):
    p = tmp_path / "test.csv"
    csv = sample_minute_df.copy()
    csv.insert(0, "datetime", csv.index)
    csv.to_csv(p, index=False)

    df = load_minute_df(str(p), tz="America/New_York")
    assert not df.empty

    rth = slice_rth(df)
    assert not rth.empty

    df5 = resample(rth, "5min")
    assert df5.index[0].minute % 5 == 0


def test_rth_validation_raises_error():
    """
    Ensure the system RAISES A VALUE ERROR if we feed it incomplete data.
    (Updated for Phase 2 Strict Contract)
    """
    # Create a dummy dataframe with 10 rows (Standard day needs 390)
    dates = pd.date_range("2024-01-01 09:30", periods=10, freq="1min")
    df = pd.DataFrame({"close": 100}, index=dates)

    # We now expect a hard crash (ValueError), not just a log warning
    with pytest.raises(ValueError, match="Data Contract Violation"):
        validate_rth_completeness(df)


def test_slice_rth_enforces_contract():
    """
    CRITICAL: Verifies that slice_rth strictly enforces 390 bars (09:30-15:59).
    It MUST drop the 16:00:00 closing print and any pre-market data.
    """
    # 1. Setup Data: A full day + noise
    # Range: 09:00 to 16:00 (421 bars)
    dates = pd.date_range("2024-01-03 09:00", "2024-01-03 16:00", freq="1min")
    df = pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000},
        index=dates,
    )

    # 2. Run Slicing
    clean_df = slice_rth(df)

    # 3. Assertions
    # First bar must be 09:30
    assert clean_df.index[0].time() == time(9, 30), "Failed to drop pre-market"

    # Last bar must be 15:59
    assert clean_df.index[-1].time() == time(15, 59), "Failed to drop 16:00 close"

    # Total count must be exactly 390
    assert len(clean_df) == 390, f"Expected 390 bars, got {len(clean_df)}"


def test_validation_raises_on_missing_bars():
    """
    Verifies that we FAIL HARD if a day has 389 bars (missing data).
    """
    # Create a day with 389 bars (09:30 to 15:58)
    dates = pd.date_range("2024-01-03 09:30", periods=389, freq="1min")
    df = pd.DataFrame(
        {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 100}, index=dates
    )

    # Validation should crash
    with pytest.raises(ValueError, match="Data Contract Violation"):
        validate_rth_completeness(df)


def test_load_minute_df_deduplication(tmp_path):
    """
    Verifies that load_minute_df handles duplicate timestamps by keeping the LAST one.
    """
    # 1. Create duplicate data
    # Two entries for 09:30.
    # First: Close = 100 (Bad)
    # Second: Close = 200 (Correct)
    dates = [
        pd.Timestamp("2024-01-01 09:30"),
        pd.Timestamp("2024-01-01 09:30"),  # Duplicate
        pd.Timestamp("2024-01-01 09:31"),
    ]
    df = pd.DataFrame(
        {
            "open": [100, 100, 100],
            "high": [100, 100, 100],
            "low": [100, 100, 100],
            "close": [100, 200, 100],  # 200 is the corrected value
            "volume": [100, 100, 100],
        },
        index=dates,
    )

    # Save to parquet
    p = tmp_path / "dupes.parquet"
    df.to_parquet(p)

    # 2. Load
    loaded_df = load_minute_df(str(p))

    # 3. Assertions
    # Should only have 2 rows (09:30 and 09:31)
    assert len(loaded_df) == 2

    # The 09:30 row should have Close = 200 (Keep Last)
    val_at_930 = loaded_df.loc[
        pd.Timestamp("2024-01-01 09:30", tz="America/New_York"), "close"
    ]
    assert val_at_930 == 200.0, "Failed to keep the last duplicate"
