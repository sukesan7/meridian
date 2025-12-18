# Test Management Time-Stop

import pandas as pd

from s3a_backtester.management import run_time_stop
from s3a_backtester.config import TimeStopCfg


def _make_session(num_bars: int, start: str = "2025-01-01 09:30") -> pd.DataFrame:
    """Simple 1-minute session frame with dummy prices."""
    idx = pd.date_range(start=start, periods=num_bars, freq="1min")
    df = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
        },
        index=idx,
    )
    return df


def test_time_stop_no_tp1_hits_exit_at_15_min():
    """
    If TP1 never hits, we should exit at the first bar at/after entry_time + 15 minutes.
    """
    bars = _make_session(20)  # 09:30 .. 09:49
    entry_idx = 0
    tp1_idx = None
    side = 1

    cfg = TimeStopCfg(
        mode="15m",
        tp1_timeout_min=15,
        max_holding_min=45,
        allow_extension=True,
    )

    res = run_time_stop(
        bars=bars,
        entry_idx=entry_idx,
        tp1_idx=tp1_idx,
        side=side,
        entry_price=100.0,
        stop_price=99.0,
        time_cfg=cfg,
    )

    # 15 minutes after 09:30 is 09:45, which is iloc 15
    expected_idx = 15
    assert res.idx == expected_idx
    assert res.time == bars.index[expected_idx]
    assert res.reason == "no_tp1_15m"


def test_time_stop_tp1_hit_with_extension_breaks_on_condition():
    """
    TP1 hits, extension is allowed. We break as soon as one of the extension
    conditions fails, before the hard max-holding deadline.
    """
    bars = _make_session(30)  # 09:30 .. 09:59
    entry_idx = 0
    tp1_idx = 5  # TP1 hit at 09:35
    side = 1

    cfg = TimeStopCfg(
        mode="15m",
        tp1_timeout_min=15,
        max_holding_min=45,
        allow_extension=True,
    )

    # All conditions True initially
    vwap_side_ok = pd.Series(True, index=bars.index)
    trend_ok = pd.Series(True, index=bars.index)
    sigma_ok = pd.Series(True, index=bars.index)
    dd_ok = pd.Series(True, index=bars.index)

    # Force a break at bar 10 (09:40) by flipping one condition to False
    break_idx = 10
    vwap_side_ok.iloc[break_idx] = False

    res = run_time_stop(
        bars=bars,
        entry_idx=entry_idx,
        tp1_idx=tp1_idx,
        side=side,
        entry_price=100.0,
        stop_price=99.0,
        time_cfg=cfg,
        vwap_side_ok=vwap_side_ok,
        trend_ok=trend_ok,
        sigma_ok=sigma_ok,
        dd_ok=dd_ok,
    )

    # We start checking from tp1_idx+1 = 6, so the first failing bar is 10.
    assert res.idx == break_idx
    assert res.time == bars.index[break_idx]
    assert res.reason == "extension_break"


def test_time_stop_tp1_hit_no_extension_uses_hard_max_hold():
    """
    If extension is disabled, we ignore the VWAP/trend/sigma/DD conditions and
    simply exit at the first bar at/after the hard max-holding deadline.
    """
    # 60 bars: 09:30 .. 10:29
    bars = _make_session(60)
    entry_idx = 0
    tp1_idx = 5
    side = 1

    cfg = TimeStopCfg(
        mode="15m",
        tp1_timeout_min=15,
        max_holding_min=45,  # 45m after 09:30 -> 10:15
        allow_extension=False,
    )

    res = run_time_stop(
        bars=bars,
        entry_idx=entry_idx,
        tp1_idx=tp1_idx,
        side=side,
        entry_price=100.0,
        stop_price=99.0,
        time_cfg=cfg,
    )

    # 09:30 + 45 minutes = 10:15, which is iloc 45 in a 1-min series starting 09:30
    expected_idx = 45
    assert res.idx == expected_idx
    assert res.time == bars.index[expected_idx]
    assert res.reason == "max_hold"


def test_time_stop_disabled_mode_none():
    """
    If mode is 'none', time-stop logic should not produce any forced exit.
    """
    bars = _make_session(20)
    entry_idx = 0
    tp1_idx = None
    side = 1

    cfg = TimeStopCfg(
        mode="none", tp1_timeout_min=15, max_holding_min=45, allow_extension=True
    )

    res = run_time_stop(
        bars=bars,
        entry_idx=entry_idx,
        tp1_idx=tp1_idx,
        side=side,
        entry_price=100.0,
        stop_price=99.0,
        time_cfg=cfg,
    )

    assert res.idx is None
    assert res.time is None
    assert res.reason is None


def test_time_stop_tp1_hit_after_15_counts_as_no_tp1():
    bars = _make_session(30)  # 09:30 .. 09:59
    entry_idx = 0
    tp1_idx = 20  # 09:50 (after 15m deadline)
    side = 1

    cfg = TimeStopCfg(
        mode="15m",
        tp1_timeout_min=15,
        max_holding_min=45,
        allow_extension=True,
    )

    res = run_time_stop(
        bars=bars,
        entry_idx=entry_idx,
        tp1_idx=tp1_idx,
        side=side,
        entry_price=100.0,
        stop_price=99.0,
        time_cfg=cfg,
    )

    # Exit at 09:45 (idx 15), not at tp1_idx
    assert res.idx == 15
    assert res.time == bars.index[15]
    assert res.reason == "no_tp1_15m"
