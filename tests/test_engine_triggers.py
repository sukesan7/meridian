from __future__ import annotations

import numpy as np
import pandas as pd

from s3a_backtester.engine import generate_signals


def _make_fullmode_df(
    start: str = "2025-01-02 09:30", minutes: int = 15
) -> pd.DataFrame:
    """
    Minimal 1-session 1m dataframe that forces generate_signals FULL mode.
    We control unlock, zone touch, and micro-break timing.
    """
    idx = pd.date_range(start, periods=minutes, freq="1min", tz="America/New_York")

    close = np.full(minutes, 100.0, dtype=float)  # <= ORH so no early unlock
    df = pd.DataFrame(
        {
            "open": close.copy(),
            "high": close.copy() + 0.25,
            "low": close.copy() - 0.25,
            "close": close.copy(),
            "volume": 100,
        },
        index=idx,
    )

    # FULL-mode required columns
    df["or_high"] = 100.5
    df["or_low"] = 99.5
    df["vwap"] = 100.0
    df["vwap_1u"] = 100.75
    df["vwap_1d"] = 99.25
    df["vwap_2u"] = 101.50
    df["vwap_2d"] = 98.50
    df["trend_5m"] = 1.0  # long direction

    # Other columns referenced downstream
    df["stop_price"] = 99.0
    df["riskcap_ok"] = True
    df["disqualified_2sigma"] = False

    # Trigger input
    df["micro_break_dir"] = 0

    return df


def _set_bar(df: pd.DataFrame, ts: pd.Timestamp, close: float) -> None:
    df.loc[ts, "open"] = close
    df.loc[ts, "close"] = close
    df.loc[ts, "high"] = close + 0.25
    df.loc[ts, "low"] = close - 0.25


def _assert_single_zone_bar(out: pd.DataFrame) -> pd.Timestamp:
    zone_idx = out.index[out["in_zone"].astype(bool)]
    assert (
        len(zone_idx) == 1
    ), f"Expected exactly 1 in_zone bar, got {len(zone_idx)} at {list(zone_idx)}"
    return zone_idx[0]


def test_trigger_ok_fires_on_breakout_after_zone_touch() -> None:
    """
    Unlock -> FIRST zone touch -> breakout micro-break.
    Trigger should fire on the breakout bar even if that bar is not in-zone.
    """
    df = _make_fullmode_df()

    # Choose bars comfortably after 09:35 (but cfg=None => time_ok all True anyway)
    unlock_ts = df.index[6]  # 09:36
    after_unlock_ts = df.index[
        7
    ]  # 09:37  (force OUT of zone so zone doesn't happen here)
    zone_ts = df.index[8]  # 09:38  (first in-zone after unlock)
    breakout_ts = df.index[9]  # 09:39  (micro break)

    # 1) Unlock (close > ORH and above VWAP)
    _set_bar(df, unlock_ts, close=101.00)

    # 2) Immediately after unlock, force OUT of zone so engine doesn't pick this as zone_ts.
    # For long-zone definition: [vwap, vwap_1u] = [100.0, 100.75]. Use 101.00.
    _set_bar(df, after_unlock_ts, close=101.00)

    # 3) First zone touch AFTER unlock
    _set_bar(df, zone_ts, close=100.50)  # inside [vwap, vwap_1u]

    # 4) Breakout bar: outside zone, micro-break long
    _set_bar(df, breakout_ts, close=101.25)
    df.loc[breakout_ts, "micro_break_dir"] = 1

    out = generate_signals(df, cfg=None)

    assert bool(out.loc[unlock_ts, "or_break_unlock"]) is True

    found_zone_ts = _assert_single_zone_bar(out)
    assert found_zone_ts == zone_ts

    assert bool(out.loc[breakout_ts, "trigger_ok"]) is True


def test_trigger_ok_blocked_without_any_zone_touch() -> None:
    """
    If we never touch the zone AFTER unlock, triggers must not fire even if micro_break_dir exists.
    """
    df = _make_fullmode_df()

    unlock_ts = df.index[6]
    breakout_ts = df.index[9]

    # Unlock
    _set_bar(df, unlock_ts, close=101.00)

    # Force ALL bars after unlock out-of-zone (close > vwap_1u)
    for ts in df.index[df.index > unlock_ts]:
        _set_bar(df, ts, close=101.00)

    df.loc[breakout_ts, "micro_break_dir"] = 1

    out = generate_signals(df, cfg=None)

    assert bool(out.loc[unlock_ts, "or_break_unlock"]) is True
    assert int(out["in_zone"].astype(bool).sum()) == 0
    assert int(out["trigger_ok"].astype(bool).sum()) == 0


def test_trigger_ok_requires_pattern_direction_match() -> None:
    """
    If direction is long but micro_break_dir is short, trigger_ok must remain False.
    """
    df = _make_fullmode_df()

    unlock_ts = df.index[6]
    after_unlock_ts = df.index[7]
    zone_ts = df.index[8]
    trigger_ts = df.index[9]

    _set_bar(df, unlock_ts, close=101.00)
    _set_bar(df, after_unlock_ts, close=101.00)  # out-of-zone so zone occurs at zone_ts
    _set_bar(df, zone_ts, close=100.50)  # in-zone
    _set_bar(df, trigger_ts, close=101.25)  # breakout

    df.loc[trigger_ts, "micro_break_dir"] = -1  # opposite direction

    out = generate_signals(df, cfg=None)

    assert bool(out.loc[unlock_ts, "or_break_unlock"]) is True
    found_zone_ts = _assert_single_zone_bar(out)
    assert found_zone_ts == zone_ts
    assert bool(out.loc[trigger_ts, "trigger_ok"]) is False


def test_zone_seen_resets_each_session_date() -> None:
    """
    Zone touch on day1 must not arm day2.
    """
    d1 = _make_fullmode_df(start="2025-01-02 09:30", minutes=15)
    d2 = _make_fullmode_df(start="2025-01-03 09:30", minutes=15)

    # Day 1: unlock, force out-of-zone next bar, then zone touch
    _set_bar(d1, d1.index[6], close=101.00)  # unlock
    _set_bar(d1, d1.index[7], close=101.00)  # out-of-zone
    _set_bar(d1, d1.index[8], close=100.50)  # zone

    # Day 2: unlock + micro-break, but NEVER touch zone after unlock
    _set_bar(d2, d2.index[6], close=101.00)  # unlock
    for ts in d2.index[d2.index > d2.index[6]]:
        _set_bar(d2, ts, close=101.00)  # out-of-zone all post-unlock bars
    d2.loc[d2.index[9], "micro_break_dir"] = 1

    df = pd.concat([d1, d2]).sort_index()
    out = generate_signals(df, cfg=None)

    # Day1 has exactly one zone bar
    zone_idx = out.index[out["in_zone"].astype(bool)]
    assert len(zone_idx) == 1
    assert zone_idx[0].date() == pd.Timestamp("2025-01-02").date()

    # Day2 breakout must not trigger (no zone on day2)
    assert bool(out.loc[d2.index[9], "trigger_ok"]) is False
