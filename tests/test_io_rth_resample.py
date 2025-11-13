from s3a_backtester.data_io import load_minute_df, slice_rth, resample


def test_io_rth_resample_smoke():
    p = r"data/QQQ_1min_2025-04_to_2025-10.csv"
    df = load_minute_df(p, tz="America/New_York")
    assert str(df.index.tz) == "America/New_York"
    assert all(c in df.columns for c in ("open", "high", "low", "close", "volume"))
    rth = slice_rth(df)
    assert len(rth) > 0
    df5 = resample(rth, "5min")
    # right-labeled: first bar of a normal day should end on :35
    first = df5.index[0]
    assert first.minute % 5 == 0
