from s3a_backtester.data_io import load_minute_df
from s3a_backtester.features import compute_session_refs, compute_session_vwap_bands
from tests.utils import make_minute_ohlcv


def test_refs_and_vwap(tmp_path):
    _, csv_df = make_minute_ohlcv()
    p = tmp_path / "toy.csv"
    csv_df.to_csv(p, index=False)

    df = load_minute_df(str(p), tz="America/New_York")

    refs = compute_session_refs(df)
    assert {"or_high", "or_low", "or_height", "pdh", "pdl"} <= set(refs.columns)

    bands = compute_session_vwap_bands(df)
    # Only assert ordering where defined
    b = bands.dropna().head(50)
    if not b.empty:
        assert (b["band_p2"] >= b["band_p1"]).all()
        assert (b["band_p1"] >= b["vwap"]).all()
        assert (b["vwap"] >= b["band_m1"]).all()
        assert (b["band_m1"] >= b["band_m2"]).all()
