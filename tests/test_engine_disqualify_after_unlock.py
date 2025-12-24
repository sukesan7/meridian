from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from s3a_backtester.engine import generate_signals


def _cfg(*, disqualify_after_unlock: bool) -> SimpleNamespace:
    return SimpleNamespace(
        entry_window=SimpleNamespace(start="09:35", end="11:00"),
        signals=SimpleNamespace(
            disqualify_after_unlock=disqualify_after_unlock,
            zone_touch_mode="close",
            trigger_lookback_bars=2,
        ),
    )


def _base_df(idx: pd.DatetimeIndex) -> pd.DataFrame:
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
    return df


def test_disqualify_after_unlock_controls_preunlock_poisoning() -> None:
    """
    Engine behavior:

    hit_opp_long = (trend>0) & (close <= vwap_2d)
    disq = cummax(hit_for_disq) per day
      where hit_for_disq = hit_opp            if disqualify_after_unlock=False
                         = hit_opp & unlocked if disqualify_after_unlock=True

    We create:
      09:35: close <= v2d -> hit_opp BEFORE unlock
      09:36: unlock happens
      09:37: zone touch bar

    Expectation:
      - disqualify_after_unlock=False -> disqualified already True and zone blocked
      - disqualify_after_unlock=True  -> pre-unlock hit_opp ignored; zone allowed
    """
    idx = pd.date_range(
        "2025-01-06 09:35", periods=3, freq="1min", tz="America/New_York"
    )
    # times: 09:35, 09:36, 09:37
    df = _base_df(idx)

    # 09:35: pre-unlock opposite 2σ hit (long day: close <= v2d=98)
    df.loc[idx[0], "close"] = 97.0

    # 09:36: unlock (close > OR high and >= VWAP)
    df.loc[idx[1], "close"] = 106.0

    # 09:37: zone touch (close inside VWAP..+1σ)
    df.loc[idx[2], "close"] = 100.5

    out_pre = generate_signals(df, None, _cfg(disqualify_after_unlock=False))
    out_post = generate_signals(df, None, _cfg(disqualify_after_unlock=True))

    # Pre-unlock disqualifier behavior differs
    assert bool(out_pre.loc[idx[0], "disqualified_2sigma"])
    assert not bool(out_post.loc[idx[0], "disqualified_2sigma"])

    # Unlock still occurs either way
    assert bool(out_pre.loc[idx[1], "or_break_unlock"])
    assert bool(out_post.loc[idx[1], "or_break_unlock"])

    # Zone is blocked if pre-poisoned, allowed otherwise
    assert not bool(out_pre.loc[idx[2], "in_zone"])
    assert bool(out_post.loc[idx[2], "in_zone"])
