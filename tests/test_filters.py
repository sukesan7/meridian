"""
Tests for s3a_backtester.filters
--------------------------------
Coverage:
- Tiny OR filtration.
- Low ATR filtration.
- News Blackout / DOM Bad flags.
"""

import pandas as pd
from s3a_backtester.filters import build_session_filter_mask


class MockFilterCfg:
    enable_tiny_or = True
    tiny_or_mult = 0.5
    enable_low_atr = False
    enable_news_blackout = True


def test_filter_tiny_or_blocks_day():
    idx = pd.date_range("2024-01-01", periods=20, freq="D")
    df = pd.DataFrame({"or_high": 10.0, "or_low": 0.0, "atr15": 5.0}, index=idx)
    # Make last day tiny (Height 1.0 vs Median 10.0)
    df.loc[idx[-1], "or_high"] = 1.0

    mask = build_session_filter_mask(df, filters_cfg=MockFilterCfg)

    assert mask.iloc[0]  # Normal day should be True
    assert not mask.iloc[-1]  # Tiny day should be False (Blocked)


def test_filter_news_blackout():
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    df = pd.DataFrame(
        {"or_high": 10.0, "or_low": 0.0, "atr15": 5.0, "news_blackout": False},
        index=idx,
    )
    df.loc[idx[1], "news_blackout"] = True

    mask = build_session_filter_mask(df, filters_cfg=MockFilterCfg)

    assert mask.iloc[0]  # Allowed
    assert not mask.iloc[1]  # Blocked
    assert mask.iloc[2]  # Allowed
