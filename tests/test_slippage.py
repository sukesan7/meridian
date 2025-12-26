"""
Tests for s3a_backtester.slippage
---------------------------------
Coverage:
- Normal Window Slippage.
- Hot Window Slippage.
- Side logic (Long vs Short).
"""

import pandas as pd
from s3a_backtester.slippage import apply_slippage, SlippageConfig


class MockCfg:
    slippage = SlippageConfig(
        normal_ticks=1, hot_ticks=2, hot_start="09:30", hot_end="09:35"
    )
    instrument = type("I", (), {"tick_size": 0.25})


def test_slippage_long_normal():
    ts = pd.Timestamp("2024-01-01 09:40", tz="America/New_York")
    # 1 tick adverse
    p = apply_slippage("long", ts, 100.0, MockCfg)
    assert p == 100.25


def test_slippage_short_hot():
    ts = pd.Timestamp("2024-01-01 09:31", tz="America/New_York")
    # 2 ticks adverse
    p = apply_slippage("short", ts, 100.0, MockCfg)
    assert p == 99.50
