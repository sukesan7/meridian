import pandas as pd

from s3a_backtester.slippage import apply_slippage, SlippageConfig


def _make_ts(time_str: str) -> pd.Timestamp:
    # Single toy date; time-of-day is what matters here.
    return pd.Timestamp(f"2024-01-02 {time_str}", tz="America/New_York")


class _Cfg:
    """Tiny shim config for tests."""

    class instrument:
        tick_size = 0.25

    slippage = SlippageConfig(
        normal_ticks=1,
        hot_ticks=2,
        hot_start="09:30",
        hot_end="09:35",
        tick_size=0.25,
    )


def test_apply_slippage_no_cfg_is_noop():
    ts = _make_ts("09:32")
    price = 100.0
    slipped = apply_slippage("long", ts, price, cfg=None)
    assert slipped == price


def test_apply_slippage_normal_window_long():
    ts = _make_ts("09:40")  # outside hot window
    price = 100.0
    slipped = apply_slippage("long", ts, price, cfg=_Cfg())
    # +1 tick of 0.25
    assert slipped == 100.25


def test_apply_slippage_hot_window_short():
    ts = _make_ts("09:31")  # inside hot window [09:30, 09:35)
    price = 100.0
    slipped = apply_slippage("short", ts, price, cfg=_Cfg())
    # -2 ticks of 0.25
    assert slipped == 100.0 - 2 * 0.25


def test_apply_slippage_unknown_side_noop():
    ts = _make_ts("09:32")
    price = 100.0
    slipped = apply_slippage("flat", ts, price, cfg=_Cfg())
    assert slipped == price
