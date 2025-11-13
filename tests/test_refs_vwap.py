from s3a_backtester.data_io import load_minute_df
from s3a_backtester.features import compute_session_refs, compute_session_vwap_bands


def test_refs_and_vwap():
    p = r"data/QQQ_1min_2025-04_to_2025-10.csv"
    df = load_minute_df(p, tz="America/New_York")
    refs = compute_session_refs(df)
    assert {"or_high", "or_low", "or_height", "pdh", "pdl"} <= set(refs.columns)
    bands = compute_session_vwap_bands(df)
    assert {"vwap", "band_p1", "band_m1", "band_p2", "band_m2"} <= set(bands.columns)
    # band ordering wherever defined
    sample = bands.dropna().head(20)
    if not sample.empty:
        assert (sample["band_p2"] >= sample["band_p1"]).all()
        assert (sample["band_p1"] >= sample["vwap"]).all()
        assert (sample["vwap"] >= sample["band_m1"]).all()
        assert (sample["band_m1"] >= sample["band_m2"]).all()
