"""
Tests for s3a_backtester.slippage
---------------------------------
Verifies:
- Normal hours slippage.
- Hot window slippage (Opening Range).
- Tick size math.
"""

import pandas as pd
from s3a_backtester.slippage import apply_slippage
from s3a_backtester.config import Config, SlippageCfg


def test_slippage_normal_hours():
    """
    Test standard slippage outside the hot window.
    """
    # Setup: 1 tick normal, 5 ticks hot, tick_size=1.0
    slip_cfg = SlippageCfg(normal_ticks=1, hot_ticks=5, tick_size=1.0)
    cfg = Config(slippage=slip_cfg)

    # 12:00 PM (Normal)
    ts = pd.Timestamp("2023-01-01 12:00:00", tz="America/New_York")

    # Long: Price + 1 tick
    assert apply_slippage("long", ts, 100.0, cfg) == 101.0
    # Short: Price - 1 tick
    assert apply_slippage("short", ts, 100.0, cfg) == 99.0


def test_slippage_hot_window():
    """
    Test increased slippage during the market open (09:30-09:40).
    """
    slip_cfg = SlippageCfg(normal_ticks=1, hot_ticks=10, tick_size=0.25)
    cfg = Config(slippage=slip_cfg)

    # 09:30:05 (Hot)
    ts = pd.Timestamp("2023-01-01 09:30:05", tz="America/New_York")

    # Long: 100 + (10 * 0.25) = 102.5
    assert apply_slippage("long", ts, 100.0, cfg) == 102.5
    # Short: 100 - (10 * 0.25) = 97.5
    assert apply_slippage("short", ts, 100.0, cfg) == 97.5


def test_no_config_defaults():
    """
    If config is None, slippage should be 0 (or default safe behavior).
    """
    ts = pd.Timestamp("2023-01-01 12:00:00", tz="America/New_York")
    # Default Config() has normal_ticks=1, tick_size=0.25
    # So we expect 100.25 for long

    # Case 1: Absolutely None -> 0 slippage (safe fallback)
    assert apply_slippage("long", ts, 100.0, None) == 100.0

    # Case 2: Default Config object
    cfg = Config()
    assert apply_slippage("long", ts, 100.0, cfg) == 100.25
