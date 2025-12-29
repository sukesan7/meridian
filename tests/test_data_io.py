"""
Tests for s3a_backtester.data_io
--------------------------------
Coverage:
- RTH Slicing.
- Resampling (Right-labeled).
- Loading & Normalization.
"""

import pandas as pd
import logging
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


def test_rth_validation_logs_warning(caplog):
    """Ensure the system screams if we feed it incomplete data."""
    # Create a dummy dataframe with 10 rows (Standard day needs 390)
    dates = pd.date_range("2024-01-01 09:30", periods=10, freq="1min")
    df = pd.DataFrame({"close": 100}, index=dates)

    # Capture logs
    with caplog.at_level(logging.WARNING):
        validate_rth_completeness(df)

    # Assert we got the warning
    assert "Data Integrity Warning" in caplog.text
    assert "2024-01-01" in caplog.text
