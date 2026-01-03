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
from s3a_backtester.config import Config, SlippageCfg, RiskCfg, EntryWindow


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

    assert (
        trades_next.iloc[0]["entry"] == 105.0
    ), "Failed: next_open mode did not look ahead!"

    assert (
        trades_close.iloc[0]["entry"] == 100.0
    ), "Failed: close mode did not fill at signal bar!"


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
