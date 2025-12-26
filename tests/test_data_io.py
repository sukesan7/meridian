"""
Tests for s3a_backtester.data_io
--------------------------------
Coverage:
- RTH Slicing.
- Resampling (Right-labeled).
- Loading & Normalization.
"""

from s3a_backtester.data_io import load_minute_df, slice_rth, resample


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
