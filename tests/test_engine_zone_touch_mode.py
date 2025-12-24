from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from s3a_backtester.engine import generate_signals


def _cfg(*, zone_touch_mode: str) -> SimpleNamespace:
    return SimpleNamespace(
        entry_window=SimpleNamespace(start="09:35", end="11:00"),
        signals=SimpleNamespace(
            zone_touch_mode=zone_touch_mode,
            disqualify_after_unlock=False,
            trigger_lookback_bars=2,
        ),
    )


def _base_df(idx: pd.DatetimeIndex) -> pd.DataFrame:
    # Required FULL-mode columns per generate_signals
    df = pd.DataFrame(index=idx)
    df["or_high"] = 105.0
    df["or_low"] = 95.0

    df["vwap"] = 100.0
    df["vwap_1u"] = 101.0
    df["vwap_1d"] = 99.0
    df["vwap_2u"] = 102.0
    df["vwap_2d"] = 98.0

    df["trend_5m"] = 1.0  # long day
    df["close"] = 100.0

    # range-mode requires these:
    df["high"] = df["close"]
    df["low"] = df["close"]
    return df


def test_zone_touch_close_vs_range() -> None:
    """
    Validate zone_touch_mode switch:

    - close mode: long zone touch requires vwap <= close <= vwap_1u
    - range mode: long zone touch allows overlap: low <= vwap_1u AND high >= vwap

    We craft a bar where:
      close is OUTSIDE the zone (above vwap_1u),
      but the bar range overlaps the zone.
    """
    idx = pd.date_range(
        "2025-01-06 09:35", periods=2, freq="1min", tz="America/New_York"
    )
    # 09:35 unlock bar, 09:36 candidate zone bar
    df = _base_df(idx)

    # Unlock at 09:35: close > OR high and >= VWAP
    df.loc[idx[0], "close"] = 106.0
    df.loc[idx[0], "high"] = 106.2
    df.loc[idx[0], "low"] = 105.8

    # 09:36: close above +1σ (so close-mode should NOT count as zone),
    # but range overlaps VWAP..+1σ (so range-mode SHOULD count as zone).
    df.loc[idx[1], "close"] = 101.8  # > vwap_1u (=101.0)
    df.loc[idx[1], "high"] = 102.2  # >= vwap
    df.loc[idx[1], "low"] = 100.6  # <= vwap_1u

    out_close = generate_signals(df, None, _cfg(zone_touch_mode="close"))
    out_range = generate_signals(df, None, _cfg(zone_touch_mode="range"))

    # sanity: unlock event on first bar
    assert bool(out_close.loc[idx[0], "or_break_unlock"])
    assert bool(out_range.loc[idx[0], "or_break_unlock"])

    # close mode: not in_zone on 09:36 because close outside band
    assert not bool(out_close.loc[idx[1], "in_zone"])

    # range mode: in_zone on 09:36 because bar range overlaps band
    assert bool(out_range.loc[idx[1], "in_zone"])
