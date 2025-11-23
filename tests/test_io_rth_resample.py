# Tests for Input / Output and Regular Trading Hours Resampling
from s3a_backtester.data_io import load_minute_df, slice_rth, resample
from tests.utils import make_minute_ohlcv
import pandas as pd


def test_io_rth_resample_smoke(tmp_path):
    _, csv_df = make_minute_ohlcv()
    p = tmp_path / "toy.csv"
    csv_df.to_csv(p, index=False)

    df = load_minute_df(str(p), tz="America/New_York")
    assert str(df.index.tz) == "America/New_York"
    assert all(c in df.columns for c in ("open", "high", "low", "close", "volume"))

    # first couple of days: check RTH count is >0 and sane
    rth = slice_rth(df)
    assert len(rth) > 0

    df5 = resample(rth, "5min")
    assert len(df5) > 0
    # right-labeled bars align to :00/:05 etc.
    assert df5.index[0].minute % 5 == 0


def test_resample_30min_alignment_no_peek():
    """30min resample should align to clock and not peek into future bars.

    We build a synthetic 1min series with strictly increasing prices so that
    the 30min OHLC is easy to reason about. If resample used look-ahead or
    misaligned windows, the high/close values would not match the last minute
    inside each 30min block.
    """
    idx = pd.date_range(
        "2024-01-02 09:31",
        periods=60,
        freq="1min",
        tz="America/New_York",
    )

    # Monotonically increasing prices: 0, 1, 2, ..., 59
    values = pd.Series(range(len(idx)), index=idx, dtype="float64")
    df1 = pd.DataFrame(
        {
            "open": values,
            "high": values,
            "low": values,
            "close": values,
            "volume": 1.0,
        },
        index=idx,
    )

    df30 = resample(df1, rule="30min")

    # We expect two full 30min bars:
    # (09:30, 10:00] -> timestamp 10:00
    # (10:00, 10:30] -> timestamp 10:30
    assert len(df30) == 2
    assert [t.hour for t in df30.index] == [10, 10]
    assert [t.minute for t in df30.index] == [0, 30]

    # Each 30min window should only use data up to its close:
    # first bar covers values 0..29, second 30..59
    assert df30["high"].iloc[0] == 29
    assert df30["close"].iloc[0] == 29

    assert df30["high"].iloc[1] == 59
    assert df30["close"].iloc[1] == 59

    # Sanity: highs are non-decreasing with our synthetic monotonic data
    assert df30["high"].is_monotonic_increasing


def test_slice_rth_consistent_across_dst(tmp_path):
    """
    RTH slice (09:30–16:00 ET) should give 391 bars both before and after
    a DST transition when timestamps come in as UTC and are converted to ET.
    """
    # Build a 1-min ET index spanning a DST change weekend (US/Eastern).
    # DST in 2024 starts Sunday 2024-03-10, so:
    # - 2024-03-08 is a Friday (Standard Time)
    # - 2024-03-11 is a Monday (Daylight Time)
    idx_et = pd.date_range(
        "2024-03-08 00:00",
        "2024-03-12 23:59",
        freq="1min",
        tz="America/New_York",
    )

    # Simple constant OHLCV; we only care about the index.
    df_et = pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1.0,
        },
        index=idx_et,
    )

    # Emulate real feed: store timestamps as UTC in a 'datetime' column.
    csv_df = df_et.copy()
    csv_df.insert(0, "datetime", csv_df.index.tz_convert("UTC"))

    path = tmp_path / "dst_test.csv"
    csv_df.to_csv(path, index=False)

    # Load via our real loader (UTC -> ET) and slice RTH via our real function.
    df = load_minute_df(str(path), tz="America/New_York")
    assert str(df.index.tz) == "America/New_York"

    for day_str in ("2024-03-08", "2024-03-11"):
        daydf = df.loc[day_str]
        rth = slice_rth(daydf)

        # Full RTH 09:30–16:00 inclusive = 391 bars.
        assert len(rth) == 391, f"Unexpected RTH length for {day_str}"

        first = rth.index[0]
        last = rth.index[-1]
        assert (first.hour, first.minute) == (9, 30)
        assert (last.hour, last.minute) == (16, 0)
