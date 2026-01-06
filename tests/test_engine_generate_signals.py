"""
Tests for s3a_backtester.engine.generate_signals
------------------------------------------------
Coverage:
- Signal State Machine (Unlock -> Zone -> Trigger).
- Time Window gating.
- Disqualification logic.
- Configuration toggles.
"""

import pandas as pd

from s3a_backtester.engine import generate_signals


# Mock Config to enforce time window checks
class MockWindowCfg:
    entry_window = type("EW", (), {"start": "09:35", "end": "11:00"})()
    signals = type(
        "S",
        (),
        {
            "trigger_lookback_bars": 5,
            "disqualify_after_unlock": False,
            "zone_touch_mode": "close",
        },
    )()
    instrument = type("I", (), {"tick_size": 1.0})()
    risk = type("R", (), {"max_stop_or_mult": 1.5})()


def _make_df(close_vals):
    idx = pd.date_range(
        "2025-01-01 09:30", periods=len(close_vals), freq="1min", tz="America/New_York"
    )
    return pd.DataFrame(
        {
            "open": close_vals,
            "high": close_vals,
            "low": close_vals,
            "close": close_vals,
            "volume": 100,
            "or_high": 110.0,
            "or_low": 100.0,
            "vwap": 105.0,
            "vwap_1u": 110.0,
            "vwap_1d": 100.0,
            "vwap_2u": 115.0,
            "vwap_2d": 95.0,
            "trend_5m": 1,
            "micro_break_dir": 0,
            "engulf_dir": 0,
        },
        index=idx,
    )


def test_unlock_event_long():
    vals = [105.0] * 5 + [111.0] + [105.0] * 4
    df = _make_df(vals)
    out = generate_signals(df, cfg=MockWindowCfg)
    assert out["or_break_unlock"].iloc[5]
    assert out["unlocked"].iloc[6]


def test_unlock_blocked_before_window():
    vals = [105.0, 105.0, 111.0, 105.0, 105.0]
    df = _make_df(vals)
    out = generate_signals(df, cfg=MockWindowCfg)
    assert not out["or_break_unlock"].iloc[2]


def test_zone_requires_unlock():
    vals = [105.0] * 5 + [108.0]
    df = _make_df(vals)
    out = generate_signals(df, cfg=MockWindowCfg)
    assert not out["or_break_unlock"].any()
    assert not out["in_zone"].any()


def test_zone_identification_long():
    vals = [105.0] * 5 + [111.0, 108.0]
    df = _make_df(vals)
    out = generate_signals(df, cfg=MockWindowCfg)
    assert out["in_zone"].iloc[6]


def test_trigger_fires_on_pattern():
    vals = [105.0] * 5 + [111.0, 108.0, 109.0]
    df = _make_df(vals)
    df.loc[df.index[7], "micro_break_dir"] = 1
    out = generate_signals(df, cfg=MockWindowCfg)
    assert out["trigger_ok"].iloc[7]


def test_disqualify_2sigma_breach():
    vals = [94.0] + [105.0] * 4 + [111.0]
    df = _make_df(vals)
    out = generate_signals(df, cfg=MockWindowCfg)
    assert out["disqualified_2sigma"].any()
    assert not out["trigger_ok"].any()


def test_config_zone_touch_mode_range():
    # Setup: Zone is VWAP (105.0) to VWAP_1u (110.0).
    # We need a bar where Close is > 110 (OUTSIDE) but Low is < 110 (INSIDE).
    # 09:35 (Idx 5) = Unlock (111.0).
    # 09:36 (Idx 6) = Zone candidate.
    vals = [105.0] * 5 + [111.0, 112.0]  # Close 112 is > 110 (Outside)
    df = _make_df(vals)

    # Force overlap: High=112, Low=109. Range [109, 112] overlaps [105, 110].
    df.loc[df.index[6], "low"] = 109.0
    df.loc[df.index[6], "high"] = 112.0

    class RangeCfg(MockWindowCfg):
        signals = type(
            "S",
            (),
            {
                "trigger_lookback_bars": 5,
                "disqualify_after_unlock": False,
                "zone_touch_mode": "range",
            },
        )()

    out = generate_signals(df, cfg=RangeCfg)
    assert out["in_zone"].iloc[6]


def test_config_disqualify_after_unlock_true():
    vals = [94.0] + [105.0] * 4 + [111.0, 108.0]
    df = _make_df(vals)

    class DisqCfg(MockWindowCfg):
        signals = type(
            "S",
            (),
            {
                "trigger_lookback_bars": 5,
                "disqualify_after_unlock": True,
                "zone_touch_mode": "close",
            },
        )()

    out = generate_signals(df, cfg=DisqCfg)
    assert not out["disqualified_2sigma"].iloc[0]
    assert out["in_zone"].iloc[6]


def test_signals_do_not_prefilter_risk():
    """
    Verifies that generate_signals returns 'trigger_ok' even if the stop width
    looks huge relative to 'close'. The execution layer handles the rejection.
    """
    # 1. Setup Data: A valid setup pattern
    dates = pd.date_range("2024-01-01 09:30", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "close": [100.0] * 5,
            "high": [105.0] * 5,
            "low": [95.0] * 5,
            "open": [100.0] * 5,
            "or_high": [101.0] * 5,  # OR Height = 2.0
            "or_low": [99.0] * 5,
            "vwap": [100.0] * 5,
            "vwap_1u": [102.0] * 5,
            "vwap_1d": [98.0] * 5,
            "trend_5m": [1] * 5,  # Long Trend
        },
        index=dates,
    )

    # 2. Force a valid pattern logic manually to isolate risk check
    # We fake the internal columns that usually trigger a signal
    df["direction"] = 1
    df["in_zone"] = True
    df["trigger_ok"] = True  # The pattern is valid
    df["time_window_ok"] = True
    df["stop_price"] = 90.0  # Wide stop (Risk=10).
    # If OR=2.0 and max_mult=1.5, MaxRisk=3.0.
    # This WOULD be rejected if risk logic existed here.

    # 3. Run Signal Gen
    signals = generate_signals(df)

    # 4. Assert
    # It should STILL be OK because we deleted the risk check from this function
    assert signals.iloc[0]["trigger_ok"], (
        "generate_signals should not filter based on risk; that is the engine's job."
    )


def test_trigger_does_not_peek_forward_for_pattern():
    """
    Regression: trigger_ok at time T must not become True because a pattern appears at T+1.
    """
    vals = [105.0] * 5 + [111.0, 108.0, 109.0, 109.0]  # unlock at 5, zone at 6
    df = _make_df(vals)

    # Put the pattern at a later bar (T+1), not at the candidate trigger bar.
    df.loc[df.index[8], "micro_break_dir"] = 1

    out = generate_signals(df, cfg=MockWindowCfg)

    # Ensure bar 7 didn't fire early due to a future pattern at bar 8
    assert not out["trigger_ok"].iloc[7]
    # And bar 8 can fire normally (allowed) if other gates are satisfied
    assert out["trigger_ok"].iloc[8]


def test_trend_5m_shift_prevents_lookahead():
    idx = pd.date_range(
        "2024-01-02 09:30", periods=10, freq="1min", tz="America/New_York"
    )
    df1 = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 100,
            "or_high": 110.0,
            "or_low": 90.0,
            "vwap": 100.0,
            "vwap_1u": 105.0,
            "vwap_1d": 95.0,
            "vwap_2u": 110.0,
            "vwap_2d": 90.0,
        },
        index=idx,
    )

    df5_idx = pd.date_range(
        "2024-01-02 09:30", periods=2, freq="5min", tz="America/New_York"
    )
    df5 = pd.DataFrame({"trend_5m": [1, -1]}, index=df5_idx)

    out = generate_signals(df1, df5, cfg=None)

    # 09:30-09:34 should not see the 09:30-09:34 bar's trend yet.
    assert (out.loc[idx[:5], "trend_5m"] == 0).all()
    # 09:35-09:39 should see the completed 09:30-09:34 bar trend.
    assert (out.loc[idx[5:], "trend_5m"] == 1).all()
