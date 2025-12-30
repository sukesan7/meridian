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


# use for test cases prior to v1.0.3
class MockFilterCfg:
    enable_tiny_or = True
    tiny_or_mult = 0.5
    enable_low_atr = False
    enable_news_blackout = True


# use for test case v1.0.3 (lookahead fix)
class MockFiltersConfig:
    def __init__(self) -> None:
        self.enable_low_atr = True
        self.low_atr_percentile = 20.0
        self.skip_tiny_or = False
        self.tiny_or_mult = 0.25
        self.news_blackout = False
        self.enable_dom_filter = False


def test_filter_tiny_or_blocks_day() -> None:
    idx = pd.date_range("2024-01-01", periods=20, freq="D")
    df = pd.DataFrame({"or_high": 10.0, "or_low": 0.0, "atr15": 5.0}, index=idx)
    # Make last day tiny (Height 1.0 vs Median 10.0)
    df.loc[idx[-1], "or_high"] = 1.0

    mask = build_session_filter_mask(df, filters_cfg=MockFilterCfg)

    assert mask.iloc[0]  # Normal day should be True
    assert not mask.iloc[-1]  # Tiny day should be False (Blocked)


def test_filter_news_blackout() -> None:
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


def test_atr_lookahead_bias() -> None:
    """
    CRITICAL TEST: Verifies that the Session Filter does NOT use today's EOD ATR
    to filter today's trades. It must use Yesterday's ATR.
    """
    # 1. Setup: Create 40 days of data (enough for min_periods=20 rolling window)
    dates = pd.date_range("2024-01-01", periods=40, freq="D")
    df = pd.DataFrame(index=dates)

    # Fill with "Normal" High Volatility (ATR = 100.0)
    df["atr15"] = 100.0

    # 2. Set the Trap
    # Day 38 (Yesterday): Extremely Low Volatility (ATR = 0.1)
    # Day 39 (Today):     Normal High Volatility (ATR = 100.0)
    idx_yesterday = 38
    idx_today = 39

    df.loc[dates[idx_yesterday], "atr15"] = 0.1
    df.loc[dates[idx_today], "atr15"] = 100.0

    # 3. Run Filter
    cfg = MockFiltersConfig()
    mask = build_session_filter_mask(df, cfg)

    # 4. Verify Causality
    # The rolling 20th percentile threshold will be somewhere between 0.1 and 100.
    # Since Day 38 was 0.1, it is definitely "Low Regime".

    # IF BUGGY: The code checks Day 39's ATR (100.0). 100 > Threshold. Result = True (Keep).
    # IF FIXED: The code checks Day 38's ATR (0.1).   0.1 < Threshold. Result = False (Skip).

    is_today_allowed = mask.iloc[idx_today]

    assert not is_today_allowed, (
        "LOOK-AHEAD BIAS DETECTED: The filter allowed trading on Day 39 despite Day 38 "
        "having essentially zero volatility. It likely used Day 39's EOD data to make the decision."
    )

    print(
        "\n[PASSED] ATR Causality Test: Filter correctly used yesterday's data to skip today."
    )


if __name__ == "__main__":
    test_atr_lookahead_bias()
