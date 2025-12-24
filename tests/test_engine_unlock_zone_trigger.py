from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from s3a_backtester.engine import generate_signals


def _cfg(
    *,
    start: str = "09:35",
    end: str = "11:00",
    trigger_lookback_bars: int = 2,
    zone_touch_mode: str = "close",
    disqualify_after_unlock: bool = False,
):
    # Minimal config object with the exact attributes generate_signals reads.
    return SimpleNamespace(
        entry_window=SimpleNamespace(start=start, end=end),
        signals=SimpleNamespace(
            trigger_lookback_bars=trigger_lookback_bars,
            zone_touch_mode=zone_touch_mode,
            disqualify_after_unlock=disqualify_after_unlock,
        ),
        instrument=SimpleNamespace(tick_size=1.0),
        risk=SimpleNamespace(max_stop_or_mult=1.25),
    )


def _base_df(index: pd.DatetimeIndex) -> pd.DataFrame:
    # Required FULL-mode columns:
    # close, or_high, or_low, vwap, vwap_1u, vwap_1d, vwap_2u, vwap_2d, trend_5m
    df = pd.DataFrame(index=index)
    df["or_high"] = 105.0
    df["or_low"] = 95.0
    df["vwap"] = 100.0
    df["vwap_1u"] = 101.0
    df["vwap_1d"] = 99.0
    df["vwap_2u"] = 102.0
    df["vwap_2d"] = 98.0
    df["trend_5m"] = 1.0  # long trend
    df["close"] = 100.0  # will override per test scenario
    return df


def test_unlock_event_and_state_transition() -> None:
    """
    Rule validated:
    - unlock_raw requires: trend>0 AND close>or_high AND close>=vwap AND time_window_ok
    - or_break_unlock is the *event* (True only on first unlock bar of the day)
    - unlocked is session-scoped cummax state after the first unlock
    """
    idx = pd.date_range(
        "2025-01-06 09:30", periods=10, freq="1min", tz="America/New_York"
    )
    df = _base_df(idx)

    # Before entry window: even if price breaks, unlock must be blocked by time_window_ok
    # Entry window starts at 09:35.
    df.loc[idx[0:5], "close"] = (
        106.0  # would break OR, but time_window_ok should be False
    )

    # First eligible bar at 09:35: unlock happens here
    df.loc[idx[5], "close"] = 106.0  # 09:35

    # After unlock: drop back below OR high so unlock_raw is not repeatedly true
    df.loc[idx[6:], "close"] = 104.0

    out = generate_signals(df, None, _cfg(start="09:35", end="11:00"))

    # time_window_ok: 09:30-09:34 False, 09:35+ True
    assert bool(out.loc[idx[4], "time_window_ok"]) is False
    assert bool(out.loc[idx[5], "time_window_ok"]) is True

    # Event only on the first unlock bar
    assert bool(out.loc[idx[5], "or_break_unlock"]) is True
    assert bool(out.loc[idx[6], "or_break_unlock"]) is False

    # State flips on unlock and stays True afterward (for the day)
    assert bool(out.loc[idx[4], "unlocked"]) is False
    assert bool(out.loc[idx[5], "unlocked"]) is True
    assert bool(out.loc[idx[9], "unlocked"]) is True

    # Direction should be long (trend_5m>0)
    assert int(out.loc[idx[5], "direction"]) == 1


def test_zone_touch_is_after_unlock_and_one_per_day() -> None:
    """
    Rule validated:
    - Zone can only occur AFTER unlock bar (zone_candidate requires ~unlock_event)
    - Zone touch (default close-mode) for long: vwap <= close <= vwap_1u
    - Exactly one in_zone event per session/day (first True only)
    """
    idx = pd.date_range(
        "2025-01-06 09:34", periods=6, freq="1min", tz="America/New_York"
    )
    # times: 09:34, 09:35, 09:36, 09:37, 09:38, 09:39
    df = _base_df(idx)

    # Unlock at 09:35
    df.loc[idx[1], "close"] = 106.0  # > or_high and >= vwap

    # First pullback touch in zone at 09:36 (between vwap and vwap_1u)
    df.loc[idx[2], "close"] = 100.5

    # Still in zone at 09:37, but should NOT produce another in_zone event
    df.loc[idx[3], "close"] = 100.3

    # Outside zone afterwards
    df.loc[idx[4:], "close"] = 103.0

    out = generate_signals(df, None, _cfg(start="09:35", end="11:00"))

    # Sanity: unlock event at 09:35
    assert bool(out.loc[idx[1], "or_break_unlock"]) is True
    assert bool(out.loc[idx[1], "unlocked"]) is True

    # Zone must not occur on unlock bar even if it "touches" (it doesn't here, but rule enforced anyway)
    assert bool(out.loc[idx[1], "in_zone"]) is False

    # First zone event only
    assert bool(out.loc[idx[2], "in_zone"]) is True  # first zone touch after unlock
    assert (
        bool(out.loc[idx[3], "in_zone"]) is False
    )  # subsequent zone touches do NOT re-fire


def test_trigger_within_lookback_only() -> None:
    """
    Rule validated:
    - trigger_ok requires:
        direction != 0
        zone_seen True (a zone happened earlier that day)
        zone_recent True (zone within last N bars, default N=2 here)
        micro_break_dir or engulf_dir matches direction
        time_window_ok True
        not disqualified_2sigma
    - Trigger should fire within lookback and fail outside it.
    """
    idx = pd.date_range(
        "2025-01-06 09:35", periods=5, freq="1min", tz="America/New_York"
    )
    # times: 09:35, 09:36, 09:37, 09:38, 09:39
    df = _base_df(idx)

    # Unlock at 09:35
    df.loc[idx[0], "close"] = 106.0

    # Zone at 09:36
    df.loc[idx[1], "close"] = 100.5

    # Pattern columns (only one should be set per bar)
    df["micro_break_dir"] = 0
    df["engulf_dir"] = 0

    # Valid trigger at 09:38 (two bars after zone, within lookback=2)
    df.loc[idx[3], "micro_break_dir"] = 1

    # Also set a pattern at 09:39 (three bars after zone) — should NOT trigger with lookback=2
    df.loc[idx[4], "micro_break_dir"] = 1

    out = generate_signals(
        df, None, _cfg(start="09:35", end="11:00", trigger_lookback_bars=2)
    )

    # Zone occurred at 09:36
    assert bool(out.loc[idx[1], "in_zone"]) is True

    # 09:38 should trigger (zone_recent includes shift2 from 09:36)
    assert bool(out.loc[idx[3], "trigger_ok"]) is True

    # 09:39 should NOT trigger (outside lookback window)
    assert bool(out.loc[idx[4], "trigger_ok"]) is False
