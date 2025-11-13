from s3a_backtester.data_io import load_minute_df, slice_rth, resample
from .conftest import make_minute_ohlcv


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
