"""
Tests for s3a_backtester.engine.simulate_trades
-----------------------------------------------
Coverage:
- Entry Logic (Trade Creation).
- Stop Loss Calculation.
- Slippage Application on Entry.
- Filtering (Risk Cap, Session Filters).
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

import s3a_backtester.engine as eng
from s3a_backtester.config import Config, EntryWindow, RiskCfg, SlippageCfg
from s3a_backtester.engine import generate_signals, simulate_trades


def test_simulate_valid_long_trade() -> None:
    idx = pd.date_range(
        "2024-01-02 09:30", periods=15, freq="1min", tz="America/New_York"
    )
    df = pd.DataFrame(
        {
            "open": 105.0,
            "high": 105.0,
            "low": 105.0,
            "close": 105.0,
            "volume": 100,
            "or_high": 110.0,
            "or_low": 100.0,
            "trend_5m": 1,
            "vwap": 105.0,
            "vwap_1u": 110.0,
            "vwap_1d": 100.0,
            "vwap_2u": 115.0,
            "vwap_2d": 95.0,
        },
        index=idx,
    )

    df.loc[idx[5], "close"] = 111.0
    df.loc[idx[6], "close"] = 108.0
    df.loc[idx[7], ["micro_break_dir", "close"]] = [1, 109.0]

    df["last_swing_low_price"] = 100.0
    df["last_swing_high_price"] = 120.0

    cfg = Config(
        entry_window=EntryWindow(start="09:35", end="11:00"),
        risk=RiskCfg(max_stop_or_mult=1.25),
    )

    sig = generate_signals(df, cfg=cfg)

    sig["last_swing_low_price"] = 100.0
    sig["last_swing_high_price"] = 120.0

    trades = simulate_trades(df, sig, cfg=cfg)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["side"] == "long"
    assert t["stop"] == 99.75
    assert t["trigger_type"] == "swingbreak"


def test_simulate_risk_cap_block() -> None:
    idx = pd.date_range(
        "2024-01-02 09:30", periods=10, freq="1min", tz="America/New_York"
    )
    df = pd.DataFrame(
        {
            "close": 110.0,
            "or_high": 110.0,
            "or_low": 108.0,
            "trend_5m": 1,
            "vwap": 100,
            "vwap_1u": 110,
            "vwap_1d": 90,
            "vwap_2u": 120,
            "vwap_2d": 80,
        },
        index=idx,
    )

    # Stop is at 80 (Risk 30). Cap is 1.25 * 2 = 2.5.
    df["stop_price"] = 80.0
    df["trigger_ok"] = True
    df["time_window_ok"] = True
    df["direction"] = 1

    cfg = Config(
        entry_window=EntryWindow(start="09:35", end="11:00"),
        risk=RiskCfg(max_stop_or_mult=1.25),
    )

    sig = generate_signals(df, cfg=cfg)

    trades = simulate_trades(df, sig, cfg=cfg)
    assert len(trades) == 0


def test_next_open_execution_logic() -> None:
    """
    Critical Test: Verify that 'next_open' mode actually fills at the
    OPEN of the NEXT bar (i+1), not the close of the current bar (i).
    """
    dates = pd.date_range("2024-01-01 09:30", periods=3, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100, 105, 110],
            "close": [100, 105, 110],
            "high": [100, 105, 110],
            "low": [100, 105, 110],
        },
        index=dates,
    )

    signals = df.copy()
    signals["direction"] = 0
    signals.loc[dates[0], "direction"] = 1  # Long signal at Bar 0

    signals["trigger_ok"] = True
    signals["riskcap_ok"] = True
    signals["time_window_ok"] = True
    signals["disqualified_2sigma"] = False
    signals["stop_price"] = 90.0

    # Case A: Configure for 'next_open'
    cfg_next = Config(slippage=SlippageCfg(mode="next_open", tick_size=0.0))
    trades_next = simulate_trades(df, signals, cfg_next)

    # Case B: Configure for 'close'
    cfg_close = Config(slippage=SlippageCfg(mode="close", tick_size=0.0))
    trades_close = simulate_trades(df, signals, cfg_close)

    assert len(trades_next) == 1
    assert len(trades_close) == 1

    assert trades_next.iloc[0]["entry"] == 105.0, (
        "Failed: next_open mode did not look ahead!"
    )

    assert trades_close.iloc[0]["entry"] == 100.0, (
        "Failed: close mode did not fill at signal bar!"
    )


def test_simulate_gap_risk_rejection() -> None:
    """
    CRITICAL TEST (v1.0.3): Verify that the engine REJECTS a trade if the GAP
    at the open causes the risk to exceed the cap, even if it looked valid at the signal close.
    """
    dates = pd.date_range("2024-01-01 09:30", periods=3, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100, 105, 110],  # Bar 1 Gap up to 105
            "close": [100, 105, 110],
            "high": [100, 105, 110],
            "low": [100, 105, 110],
        },
        index=dates,
    )

    signals = df.copy()
    signals["direction"] = 0
    signals.loc[dates[0], "direction"] = 1  # Long

    signals["trigger_ok"] = True
    signals["riskcap_ok"] = True
    signals["time_window_ok"] = True
    signals["disqualified_2sigma"] = False

    signals["stop_price"] = 95.0
    signals["or_high"] = 104.0
    signals["or_low"] = 100.0  # OR Height = 4.0

    cfg = Config(
        slippage=SlippageCfg(mode="next_open", tick_size=0.0),
        risk=RiskCfg(max_stop_or_mult=1.25),
    )

    trades = simulate_trades(df, signals, cfg)

    assert len(trades) == 0, (
        f"GAP RISK FAILURE: Engine accepted a trade with risk {trades.iloc[0]['risk_R'] if not trades.empty else 'N/A'} "
        "despite it exceeding the cap due to a market gap."
    )

    print("\n[PASSED] Gap Risk Rejection: Engine correctly identified unsafe gap.")


def test_next_open_causality_contract() -> None:
    """
    Regression Test:
    Verifies that a signal at T results in an entry_time at T+1 (or fill time),
    and that the trade record reflects this causality.
    """
    # 1. Setup Data: 09:30 signal, 09:31 fill
    dates = pd.date_range("2025-01-01 09:30", periods=5, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104],
            "high": [100, 101, 102, 103, 104],
            "low": [100, 101, 102, 103, 104],
            "close": [100, 101, 102, 103, 104],
            "volume": 1000,
        },
        index=dates,
    )

    # 2. Force a Signal at 09:30 (Index 0)
    signals = df.copy()
    signals["direction"] = 0
    signals.loc[dates[0], "direction"] = 1

    # Enable all filters
    signals["trigger_ok"] = True
    signals["riskcap_ok"] = True
    signals["time_window_ok"] = True
    signals["disqualified_2sigma"] = False
    signals["stop_price"] = 90.0

    # 3. Configure for Next Open
    cfg = Config(slippage=SlippageCfg(mode="next_open", tick_size=0.0))

    # 4. Run
    trades = simulate_trades(df, signals, cfg)

    # 5. Assertions
    assert len(trades) == 1
    t = trades.iloc[0]

    # Signal was at 09:30
    # Entry MUST be 09:31
    assert t["entry_time"] == dates[1], f"Entry Time {t['entry_time']} != 09:31"
    assert t["entry"] == 101.0

    # Date must match the entry
    assert t["date"] == dates[1].date()


def test_engine_rejects_gap_risk_at_fill():
    """
    Verifies that simulate_trades rejects a trade if the 'next_open'
    gaps such that risk > max_risk_cap.
    """
    # 1. Setup Config with strict risk limits
    cfg_mock = MagicMock()
    cfg_mock.risk.max_stop_or_mult = 1.0
    cfg_mock.instrument.tick_size = 0.25
    cfg_mock.slippage.mode = "next_open"  # Crucial: fill at next bar

    # 2. Setup Data
    dates = pd.date_range("2024-01-01 09:30", periods=2, freq="1min")
    signals = pd.DataFrame(
        {
            "close": [100.0, 105.0],  # 09:30 close is 100
            "open": [100.0, 105.0],  # 09:31 OPEN GAPS TO 105!
            "high": [100.0, 105.0],
            "low": [100.0, 105.0],
            "trigger_ok": [True, False],
            "direction": [1, 0],
            "stop_price": [99.0, 99.0],  # Stop at 99.0
            "or_high": [100.5, 100.5],
            "or_low": [99.5, 99.5],  # OR Height = 1.0
            "time_window_ok": [True, True],
            "disqualified_2sigma": [False, False],
        },
        index=dates,
    )

    # 3. Calculation:
    # Signal at 09:30.
    # Fill at 09:31 Open = 105.0.
    # Risk = 105.0 - 99.0 = 6.0.
    # Max Cap = OR(1.0) * Mult(1.0) = 1.0.
    # 6.0 > 1.0 -> REJECT.

    # 4. Run Simulation
    trades = simulate_trades(signals, signals, cfg_mock)

    # 5. Assert
    assert trades.empty, "Trade should have been rejected due to gap risk violation."


def test_engine_accepts_valid_risk_at_fill():
    """
    Control test: proves the trade works if the gap is small.
    """
    cfg_mock = MagicMock()
    cfg_mock.risk.max_stop_or_mult = 1.5
    cfg_mock.instrument.tick_size = 0.25
    cfg_mock.slippage.mode = "next_open"
    cfg_mock.time_stop.tp1_timeout_min = 60
    cfg_mock.time_stop.entry_timeout_min = 120
    cfg_mock.time_stop.max_holding_min = 240
    cfg_mock.time_stop.timer_start_on_tp1 = False

    dates = pd.date_range("2024-01-01 09:30", periods=2, freq="1min")
    signals = pd.DataFrame(
        {
            "close": [100.0, 100.0],
            "open": [100.0, 100.0],  # 09:31 Open is 100 (No Gap)
            "high": [100.0, 100.0],
            "low": [100.0, 100.0],
            "trigger_ok": [True, False],
            "direction": [1, 0],
            "stop_price": [99.0, 99.0],  # Risk = 1.0
            "or_high": [100.5, 100.5],
            "or_low": [99.5, 99.5],  # OR Height = 1.0. Max Risk = 1.0.
            "time_window_ok": [True, True],
            "disqualified_2sigma": [False, False],
        },
        index=dates,
    )

    # Risk (1.0) <= Cap (1.0) -> ACCEPT.
    trades = simulate_trades(signals, signals, cfg_mock)

    assert len(trades) == 1, "Trade should be accepted when risk is within limits."


def test_next_open_uses_market_df_not_signals_df() -> None:
    dates = pd.date_range("2024-01-01 09:30", periods=3, freq="1min")

    df1 = pd.DataFrame(
        {
            "open": [100.0, 105.0, 110.0],
            "high": [100.0, 105.0, 110.0],
            "low": [100.0, 105.0, 110.0],
            "close": [100.0, 105.0, 110.0],
            "volume": [100, 100, 100],
            # Make OR height large so risk cap won't reject
            "or_high": [140.0, 140.0, 140.0],
            "or_low": [100.0, 100.0, 100.0],
        },
        index=dates,
    )

    signals = df1.copy()
    signals["open"] = [100.0, 999.0, 999.0]  # poison signals OHLC
    signals["direction"] = 0
    signals.loc[dates[0], "direction"] = 1
    signals["trigger_ok"] = True
    signals["time_window_ok"] = True
    signals["disqualified_2sigma"] = False
    signals["stop_price"] = 90.0

    # Ensure slippage doesn't move the entry
    cfg = Config(
        slippage=SlippageCfg(
            mode="next_open", normal_ticks=0, hot_ticks=0, tick_size=0.25
        )
    )

    trades = simulate_trades(df1, signals, cfg)

    assert len(trades) == 1
    assert trades.iloc[0]["entry"] == 105.0


def test_simulate_trades_rejects_index_mismatch() -> None:
    """
    Contract test: df1 and signals must be aligned (same timestamps).
    If they diverge, simulate_trades must fail fast.
    """
    idx1 = pd.date_range("2024-01-01 09:30", periods=3, freq="1min")
    idx2 = pd.date_range("2024-01-01 09:31", periods=3, freq="1min")  # shifted

    df1 = pd.DataFrame(
        {
            "open": [100, 101, 102],
            "high": [100, 101, 102],
            "low": [100, 101, 102],
            "close": [100, 101, 102],
        },
        index=idx1,
    )
    signals = pd.DataFrame(
        {
            "direction": [1, 0, 0],
            "trigger_ok": [True, False, False],
            "time_window_ok": [True, True, True],
            "disqualified_2sigma": [False, False, False],
            "stop_price": [90.0, 90.0, 90.0],
        },
        index=idx2,
    )

    cfg = Config(slippage=SlippageCfg(mode="next_open", tick_size=0.0))

    with pytest.raises(ValueError):
        simulate_trades(df1, signals, cfg)


def test_lifecycle_bars_source_market_not_signals(monkeypatch) -> None:
    """
    Regression: When management is enabled, the bars passed to manage_trade_lifecycle
    must be sourced from df1 (market tape), not from signals.

    We monkeypatch manage_trade_lifecycle to assert the OHLC it receives equals df1.
    """
    dates = pd.date_range("2024-01-01 09:30", periods=2, freq="1min")

    df1 = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [100.0, 101.0],
            "low": [100.0, 101.0],
            "close": [100.0, 101.0],
            "volume": [100, 100],
            "or_high": [101.0, 101.0],
            "or_low": [99.0, 99.0],
        },
        index=dates,
    )

    # Poison signals OHLC
    signals = df1.copy()
    signals["open"] = [0.0, 0.0]
    signals["high"] = [0.0, 0.0]
    signals["low"] = [0.0, 0.0]
    signals["close"] = [0.0, 0.0]

    # Minimal signal fields
    signals["direction"] = [1, 0]
    signals["trigger_ok"] = [True, False]
    signals["time_window_ok"] = [True, True]
    signals["disqualified_2sigma"] = [False, False]
    signals["stop_price"] = [99.0, 99.0]
    signals["vwap"] = [100.0, 100.0]
    signals["vwap_1u"] = [101.0, 101.0]
    signals["vwap_1d"] = [99.0, 99.0]

    # Force management path without depending on your real mgmt/time_stop cfg classes
    cfg = MagicMock()
    cfg.slippage.mode = "next_open"
    cfg.instrument.tick_size = 0.25
    cfg.risk.max_stop_or_mult = 10.0
    cfg.management = object()  # non-None
    cfg.time_stop = object()  # non-None

    class DummyConds:
        vwap_side_ok = True
        trend_ok = True
        sigma_ok = True
        dd_ok = True

    def stub_build_time_stop_condition_series(**kwargs):
        return DummyConds()

    def stub_manage_trade_lifecycle(
        *,
        bars,
        entry_idx,
        side,
        entry_price,
        stop_price,
        mgmt_cfg,
        time_cfg,
        refs,
        vwap_side_ok,
        trend_ok,
        sigma_ok,
        dd_ok,
    ):
        # ASSERT: OHLC comes from df1, not signals
        assert float(bars["open"].iloc[0]) == 100.0
        assert float(bars["open"].iloc[1]) == 101.0
        assert float(bars["close"].iloc[0]) == 100.0
        assert float(bars["close"].iloc[1]) == 101.0

        return {
            "exit_time": bars.index[entry_idx],
            "realized_R": 0.0,
            "tp1_price": float(entry_price),
            "tp2_price": float(entry_price),
            "t_to_tp1_min": None,
            "time_stop_reason": "none",
        }

    # Patch in the engine module (simulate_trades uses these imported symbols)
    monkeypatch.setattr(
        eng, "build_time_stop_condition_series", stub_build_time_stop_condition_series
    )
    monkeypatch.setattr(eng, "manage_trade_lifecycle", stub_manage_trade_lifecycle)

    trades = eng.simulate_trades(df1, signals, cfg)
    assert len(trades) == 1
