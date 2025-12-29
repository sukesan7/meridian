"""
Tests for s3a_backtester.engine.simulate_trades
-----------------------------------------------
Coverage:
- Entry Logic (Trade Creation).
- Stop Loss Calculation.
- Slippage Application on Entry.
- Filtering (Risk Cap, Session Filters).
"""

import pandas as pd
from s3a_backtester.engine import generate_signals, simulate_trades
from s3a_backtester.config import Config, SlippageCfg


class MockCfg:
    tick_size = 1.0
    entry_window = type("EW", (), {"start": "09:35", "end": "11:00"})()
    risk = type("R", (), {"max_stop_or_mult": 1.5})()


def test_simulate_valid_long_trade():
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

    sig = generate_signals(df, cfg=MockCfg)

    sig["last_swing_low_price"] = 100.0
    sig["last_swing_high_price"] = 120.0

    trades = simulate_trades(df, sig, cfg=MockCfg)

    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["side"] == "long"
    assert t["stop"] == 99.0
    assert t["trigger_type"] == "swingbreak"


def test_simulate_risk_cap_block():
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

    # Stop is at 80 (Risk 30). Cap is 1.5 * 2 = 3.
    df["stop_price"] = 80.0
    df["trigger_ok"] = True
    df["time_window_ok"] = True
    df["direction"] = 1

    sig = generate_signals(df, cfg=MockCfg)

    trades = simulate_trades(df, sig, cfg=MockCfg)
    assert len(trades) == 0


def test_next_open_execution_logic():
    """
    Critical Test: Verify that 'next_open' mode actually fills at the
    OPEN of the NEXT bar (i+1), not the close of the current bar (i).
    """
    # Setup Data: 3 bars
    # Bar 0: Signal generated here. Close = 100.
    # Bar 1: Execution should happen here. Open = 105.
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

    # Setup Signal: Buy at Bar 0
    signals = df.copy()
    signals["direction"] = 0
    signals.iloc[0, signals.columns.get_loc("direction")] = 1  # Long signal at Bar 0

    # Mock required columns to bypass other checks
    signals["trigger_ok"] = True
    signals["riskcap_ok"] = True
    signals["time_window_ok"] = True
    signals["disqualified_2sigma"] = False
    signals["stop_price"] = 90.0

    # Case A: Configure for 'next_open' (Realistic)
    cfg_next = Config(slippage=SlippageCfg(mode="next_open", tick_size=0.0))
    trades_next = simulate_trades(df, signals, cfg_next)

    # Case B: Configure for 'close' (Optimistic/Legacy)
    cfg_close = Config(slippage=SlippageCfg(mode="close", tick_size=0.0))
    trades_close = simulate_trades(df, signals, cfg_close)

    # Assertions
    assert len(trades_next) == 1
    assert len(trades_close) == 1

    # The 'next_open' trade should fill at Bar 1 Open (105.0)
    assert (
        trades_next.iloc[0]["entry"] == 105.0
    ), "Failed: next_open mode did not look ahead!"

    # The 'close' trade should fill at Bar 0 Close (100.0)
    assert (
        trades_close.iloc[0]["entry"] == 100.0
    ), "Failed: close mode did not fill at signal bar!"
