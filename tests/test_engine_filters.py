from __future__ import annotations

import numpy as np
import pandas as pd

from s3a_backtester.filters import build_session_filter_mask
from s3a_backtester.engine import simulate_trades
from s3a_backtester.config import MgmtCfg, TimeStopCfg


class DummyFiltersCfg:
    def __init__(
        self,
        enable_tiny_or: bool = True,
        tiny_or_mult: float = 0.25,
        enable_low_atr: bool = True,
        low_atr_percentile: float = 20.0,
        enable_news_blackout: bool = True,
        enable_dom_filter: bool = True,
    ) -> None:
        self.enable_tiny_or = enable_tiny_or
        self.tiny_or_mult = tiny_or_mult
        self.enable_low_atr = enable_low_atr
        self.low_atr_percentile = low_atr_percentile
        self.enable_news_blackout = enable_news_blackout
        self.enable_dom_filter = enable_dom_filter


class DummyInstrument:
    def __init__(self, tick_size: float = 1.0) -> None:
        self.tick_size = tick_size


class DummyConfig:
    """
    Minimal config object that exposes what simulate_trades needs:
      - instrument.tick_size
      - tick_size
      - management (MgmtCfg)
      - time_stop (TimeStopCfg)
      - filters (filters cfg)
    """

    def __init__(
        self,
        mgmt_cfg: MgmtCfg,
        ts_cfg: TimeStopCfg,
        filters_cfg: DummyFiltersCfg,
        tick_size: float = 1.0,
    ) -> None:
        self.instrument = DummyInstrument(tick_size=tick_size)
        self.tick_size = tick_size
        self.management = mgmt_cfg
        self.time_stop = ts_cfg
        self.filters = filters_cfg


def _make_daily_index(start: str, days: int) -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=days, freq="1D")


def test_session_filter_no_cfg_all_allowed():
    idx = _make_daily_index("2025-01-01", 5)
    df = pd.DataFrame(
        {"or_high": 10.0, "or_low": 0.0, "atr15": 5.0},
        index=idx,
    )

    mask = build_session_filter_mask(df, filters_cfg=None)
    assert mask.index.equals(df.index)
    assert mask.dtype == bool
    assert mask.all()  # everything allowed


def test_tiny_or_day_is_blocked():
    """
    Tiny-day rule: OR < median(15d) * tiny_or_mult.

    Build 20 sessions:
      - first 19 have OR height 10
      - last day has OR height 1

    With tiny_or_mult=0.25:
      median(15d) for the last day (based on prior 15 sessions) ~ 10,
      so threshold ~ 2.5; OR=1 < 2.5 => day 20 should be skipped.
    """
    days = 20
    idx = _make_daily_index("2025-01-01", days)

    # Default OR: high=10, low=0 => height=10
    df = pd.DataFrame(
        {"or_high": 10.0, "or_low": 0.0, "atr15": 5.0},
        index=idx,
    )

    # Make last day a "tiny" OR = 1
    df.loc[idx[-1], "or_high"] = 1.0
    df.loc[idx[-1], "or_low"] = 0.0

    cfg = DummyFiltersCfg(
        enable_tiny_or=True,
        tiny_or_mult=0.25,
        enable_low_atr=False,  # isolate OR condition
    )

    mask = build_session_filter_mask(df, filters_cfg=cfg)

    # All previous days allowed, last day blocked
    assert mask[:-1].all()
    assert not mask.iloc[-1]


def test_low_atr_day_is_blocked():
    """
    Low-ATR rule: atr15 in bottom X% of last 60 sessions.

    Build 60 sessions:
      - first 59 days atr15 = 10
      - last day atr15 = 1 (very low)

    For last day, rolling(60).quantile(0.2).shift(1) uses the previous 59 values (all 10),
    so the 20th percentile is 10; 1 < 10 => low ATR day => blocked.
    """
    days = 60
    idx = _make_daily_index("2025-01-01", days)

    df = pd.DataFrame(
        {
            "or_high": 10.0,
            "or_low": 0.0,
            "atr15": 10.0,
        },
        index=idx,
    )

    # Last day has very low ATR
    df.loc[idx[-1], "atr15"] = 1.0

    cfg = DummyFiltersCfg(
        enable_tiny_or=False,  # ignore OR
        enable_low_atr=True,
        low_atr_percentile=20.0,  # bottom 20%
    )

    mask = build_session_filter_mask(df, filters_cfg=cfg)

    # Before we have enough history / last low-ATR day, everything allowed
    assert mask[:-1].all()
    # Last day blocked because it's unusually low ATR
    assert not mask.iloc[-1]


def test_news_and_dom_flags_block_entire_day():
    """
    If a day has either news_blackout or dom_bad set, the whole day should be blocked
    when the corresponding filters are enabled.
    """
    idx = _make_daily_index("2025-01-01", 3)

    df = pd.DataFrame(
        {
            "or_high": [10.0, 10.0, 10.0],
            "or_low": [0.0, 0.0, 0.0],
            "atr15": [5.0, 5.0, 5.0],
            "news_blackout": [False, True, False],
            "dom_bad": [False, False, True],
        },
        index=idx,
    )

    cfg = DummyFiltersCfg(
        enable_tiny_or=False,
        enable_low_atr=False,
        enable_news_blackout=True,
        enable_dom_filter=True,
    )

    mask = build_session_filter_mask(df, filters_cfg=cfg)

    # Day 1: no news, no dom -> allowed
    # Day 2: news_blackout=True -> blocked
    # Day 3: dom_bad=True -> blocked
    assert mask.iloc[0]
    assert not mask.iloc[1]
    assert not mask.iloc[2]


def test_simulate_trades_respects_session_filters(monkeypatch):
    """
    End-to-end check: one session is clean, one is flagged by news_blackout.
    We create valid entry signals on both days, and expect trades only on the
    unflagged day when filters are enabled.
    """
    idx = pd.to_datetime(
        [
            "2025-01-01 09:30",
            "2025-01-01 09:31",
            "2025-01-02 09:30",
            "2025-01-02 09:31",
        ]
    )

    # Base OHLC
    bars = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.5, 100.5, 100.5, 100.5],
            "low": [99.5, 99.5, 99.5, 99.5],
            "close": [100.0, 100.0, 100.0, 100.0],
        },
        index=idx,
    )

    signals = bars.copy()
    # Core signal columns
    signals["direction"] = 0
    signals["trigger_ok"] = False
    signals["riskcap_ok"] = True
    signals["time_window_ok"] = True
    signals["disqualified_2sigma"] = False
    signals["stop_price"] = np.nan

    # OR / ATR / refs
    signals["or_high"] = 102.0
    signals["or_low"] = 100.0
    signals["atr15"] = 5.0
    signals["vwap"] = 100.0
    signals["vwap_1u"] = 101.0
    signals["vwap_1d"] = 99.0
    signals["micro_break_dir"] = 0
    signals["engulf_dir"] = 0
    signals["pdh"] = np.nan
    signals["pdl"] = np.nan

    # News/DOM flags: second day is news_blackout=True
    signals["news_blackout"] = [False, False, True, True]
    signals["dom_bad"] = [False, False, False, False]

    # Valid entries on both days (one per day)
    entry_ts_day1 = idx[1]  # 2025-01-01 09:31
    entry_ts_day2 = idx[3]  # 2025-01-02 09:31
    for ts in [entry_ts_day1, entry_ts_day2]:
        signals.loc[ts, "direction"] = 1
        signals.loc[ts, "trigger_ok"] = True
        signals.loc[ts, "stop_price"] = 99.0

    mgmt_cfg = MgmtCfg(
        tp1_R=1.0,
        tp2_R=2.0,
        scale_at_tp1=0.5,
        move_to_BE_on_tp1=True,
    )
    # Disable time-stop to keep behaviour simple; we only care if trades appear or not.
    ts_cfg = TimeStopCfg(
        mode="none",
        tp1_timeout_min=15,
        max_holding_min=45,
        allow_extension=True,
    )
    filters_cfg = DummyFiltersCfg(
        enable_tiny_or=False,
        enable_low_atr=False,
        enable_news_blackout=True,
        enable_dom_filter=True,
    )
    cfg = DummyConfig(
        mgmt_cfg=mgmt_cfg, ts_cfg=ts_cfg, filters_cfg=filters_cfg, tick_size=1.0
    )

    # No slippage so entry_price == close
    def _no_slip(side: str, ts, price: float, cfg_obj):
        return price

    monkeypatch.setattr("s3a_backtester.engine.apply_slippage", _no_slip)

    trades = simulate_trades(df1=bars, signals=signals, cfg=cfg)

    # We should get exactly one trade: day 1 allowed, day 2 blocked by news filter.
    assert len(trades) == 1
    assert trades["date"].iloc[0] == entry_ts_day1.date()
