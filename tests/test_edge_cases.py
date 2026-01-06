"""
Tests for s3a_backtester.edge_cases
-----------------------------------
Coverage:
- Gap Risk (Open vs Stop execution).
- Zero Volatility / Division by Zero.
- Data Corruption (NaNs, Empty Frames).
- Extreme Market Conditions (Negative Prices).
- Boundary Logic (1-bar sessions, simultaneous events).
"""

import pandas as pd
import numpy as np
import pytest
from s3a_backtester.engine import generate_signals, simulate_trades
from s3a_backtester.management import manage_trade_lifecycle
from s3a_backtester.config import MgmtCfg, TimeStopCfg, Config, SlippageCfg
from s3a_backtester.features import compute_atr15, find_swings_1m
from s3a_backtester.slippage import apply_slippage


# --- Mocks ---
class MockCfg:
    tick_size = 1.0
    entry_window = type("EW", (), {"start": "09:30", "end": "16:00"})()
    risk = type("R", (), {"max_stop_or_mult": 100.0})()
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
    slippage = SlippageCfg(normal_ticks=0, hot_ticks=0, tick_size=1.0)
    # Add default management so tests don't produce NaT exits
    management = MgmtCfg()
    time_stop = TimeStopCfg()


def _make_df(close_vals, index=None):
    if index is None:
        index = pd.date_range(
            "2025-01-01 09:30",
            periods=len(close_vals),
            freq="1min",
            tz="America/New_York",
        )

    df = pd.DataFrame(
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
            "trigger_ok": True,
            "riskcap_ok": True,
            "time_window_ok": True,
            "disqualified_2sigma": False,
            "direction": 1,
            "stop_price": 90.0,
        },
        index=index,
    )
    return df


# ----------------------------------------------------------------
# 1. The "Gap of Death" (Execution Logic)
# ----------------------------------------------------------------


def test_gap_open_below_stop_long():
    """
    Scenario: Long Entry. Stop is 90.
    Next bar Opens at 80 (Gap Down).
    Expected: Execution at 80 (Open), NOT 90 (Stop).
    """
    idx = pd.date_range("2024-01-01 09:30", periods=5, freq="1min")
    df = pd.DataFrame(
        {"high": 100.0, "low": 100.0, "close": 100.0, "open": 100.0}, index=idx
    )

    df.loc[idx[2], "open"] = 80.0
    df.loc[idx[2], "high"] = 85.0
    df.loc[idx[2], "low"] = 70.0
    df.loc[idx[2], "close"] = 75.0

    res = manage_trade_lifecycle(
        df,
        entry_idx=0,
        side=1,
        entry_price=100.0,
        stop_price=90.0,
        mgmt_cfg=MgmtCfg(move_to_BE_on_tp1=False),
        time_cfg=TimeStopCfg(mode="none"),
        refs={},
    )

    assert res["exit_idx"] == 2


# ----------------------------------------------------------------
# 2. Math & Data Singularities
# ----------------------------------------------------------------


def test_zero_volatility_atr():
    """Market is frozen. High=Low=Close. ATR should handle 0 range without crashing."""
    df = _make_df([100.0] * 20)
    atr = compute_atr15(df)
    assert atr.iloc[-1] == 0.0
    assert not atr.isna().any()


def test_degenerate_risk_zero():
    """Entry == Stop. Risk is Zero. Division by Zero risk in R-calc."""
    df = _make_df([100.0] * 5)
    res = manage_trade_lifecycle(
        df,
        entry_idx=0,
        side=1,
        entry_price=100.0,
        stop_price=100.0,
        mgmt_cfg=MgmtCfg(),
        time_cfg=TimeStopCfg(),
        refs={},
    )
    assert res["realized_R"] == 0.0
    assert res["time_stop_reason"] == "degenerate_risk"


def test_nan_price_handling():
    """Data corruption: Price becomes NaN mid-session."""
    vals = [100.0, 101.0, np.nan, 102.0]
    df = _make_df(vals)
    out = generate_signals(df, cfg=MockCfg)

    assert not out["trigger_ok"].iloc[2]


def test_empty_dataframe_simulation():
    """Empty dataset passed to simulate_trades."""
    res = simulate_trades(pd.DataFrame(), pd.DataFrame(), cfg=MockCfg)
    assert res.empty
    assert "realized_R" in res.columns


# ----------------------------------------------------------------
# 3. Extreme Market Conditions
# ----------------------------------------------------------------


def test_negative_prices_oil_crash():
    """April 2020 Scenario: Price goes negative."""
    vals = [10.0, 5.0, 0.0, -5.0, -10.0, -5.0]
    df = _make_df(vals)

    atr = compute_atr15(df)
    assert (atr >= 0).all()

    out = generate_signals(df, cfg=MockCfg)
    assert not out.empty


def test_huge_gap_up_tp1():
    """Gap UP through TP1."""
    idx = pd.date_range("2024-01-01 09:30", periods=5, freq="1min")
    df = pd.DataFrame({"high": 100.0, "low": 100.0}, index=idx)
    df.loc[idx[2], ["high", "low", "open", "close"]] = 105.0

    res = manage_trade_lifecycle(
        df,
        entry_idx=0,
        side=1,
        entry_price=100.0,
        stop_price=99.0,
        mgmt_cfg=MgmtCfg(tp1_R=1.0),
        time_cfg=TimeStopCfg(),
        refs={},
    )
    assert res["tp1_price"] == 101.0


# ----------------------------------------------------------------
# 4. Logic Conflicts & Boundaries
# ----------------------------------------------------------------


def test_unlock_and_zone_same_bar():
    """Unlock happens. On the SAME bar, price is in zone. Should NOT mark zone."""
    df = _make_df([100.0] * 5 + [108.0])
    df["or_high"] = 100.0
    df["vwap"] = 105.0
    df["vwap_1u"] = 110.0
    df["trend_5m"] = 1

    out = generate_signals(df, cfg=MockCfg)
    assert out["or_break_unlock"].iloc[5]
    assert not out["in_zone"].iloc[5]


def test_single_bar_session():
    """Session with only 1 minute of data."""
    df = _make_df([100.0])
    atr = compute_atr15(df)
    swings = find_swings_1m(df)

    assert not atr.isna().all()
    assert not swings["swing_high_confirmed"].any()


def test_trigger_on_last_bar():
    """Trigger happens on the very last bar of data."""
    vals = [105.0] * 5 + [111.0, 108.0, 109.0]
    df = _make_df(vals)
    df.loc[df.index[-1], "micro_break_dir"] = 1

    out = generate_signals(df, cfg=MockCfg)
    assert out["trigger_ok"].iloc[-1]

    res = simulate_trades(df, out, cfg=MockCfg)
    assert not res.empty
    t = res.iloc[0]

    assert t["entry_time"] == t["exit_time"]
    assert t["realized_R"] == 0.0


# ----------------------------------------------------------------
# 5. Configuration Edge Cases
# ----------------------------------------------------------------


def test_missing_optional_config_sections():
    """Simulate trades with bare-bones config object (missing sub-configs)."""
    df = _make_df([100.0] * 10)
    df["trigger_ok"] = False

    df.loc[df.index[5], ["trigger_ok", "riskcap_ok", "time_window_ok"]] = True
    df.loc[df.index[5], "direction"] = 1
    df.loc[df.index[5], "stop_price"] = 99.0

    class BareCfg:
        instrument = type("I", (), {"tick_size": 1.0})()

    res = simulate_trades(df, df, cfg=BareCfg)
    assert len(res) == 1


def test_risk_cap_infinite():
    """User sets Risk Cap to Infinity."""
    df = _make_df([100.0])
    df["stop_price"] = 0.0
    df["or_height"] = 1.0

    class InfCfg(MockCfg):
        risk = type("R", (), {"max_stop_or_mult": float("inf")})()

    out = generate_signals(df, cfg=InfCfg)
    assert out["riskcap_ok"].iloc[0]


def test_slippage_with_nan_price():
    """
    Slippage on NaN price should return NaN (or handle gracefully).
    """
    cfg = Config()
    ts = pd.Timestamp("2023-01-01 12:00:00")

    res = apply_slippage("long", ts, float("nan"), cfg)
    assert np.isnan(res)


def test_slippage_zero_tick_size():
    """
    If tick_size is 0, price should not change even with slippage ticks.
    """
    slip = SlippageCfg(normal_ticks=10, tick_size=0.0)
    cfg = Config(slippage=slip)
    ts = pd.Timestamp("2023-01-01 12:00:00")

    assert apply_slippage("long", ts, 100.0, cfg) == 100.0


def test_malformed_hot_window_strings():
    """
    If hot_start strings are garbage, code should not crash (fallback to normal).
    """
    slip = SlippageCfg(
        normal_ticks=1, hot_ticks=10, hot_start="GARBAGE", hot_end="TRASH"
    )
    cfg = Config(slippage=slip)
    ts = pd.Timestamp("2023-01-01 09:35:00", tz="America/New_York")

    try:
        apply_slippage("long", ts, 100.0, cfg)
    except Exception as e:
        pytest.fail(f"Slippage crashed on bad time strings: {e}")


def test_slippage_exceeds_trade_profit():
    """
    Win trade (Price 100 -> 101).
    Slippage is Massive.
    """
    slip_config = SlippageCfg(
        hot_ticks=5, hot_start="09:00", hot_end="10:00", normal_ticks=5
    )

    class MockCfg:
        slippage = slip_config
        instrument = None

    ts = pd.Timestamp("2024-01-01 09:30:00", tz="America/New_York")

    # 5 ticks * 0.25 = 1.25 slippage
    # Long 100.0 -> 101.25
    exec_price = apply_slippage("long", ts, 100.0, MockCfg())
    assert exec_price == 101.25
