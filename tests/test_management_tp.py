# Test management for TP1 and TP2

import pandas as pd

from s3a_backtester.management import apply_tp1, compute_tp2_target
from s3a_backtester.config import MgmtCfg


def _make_session(num_bars: int = 10, start="2025-01-01 09:30") -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=num_bars, freq="1min")
    # simple monotonic prices; you can override in individual tests
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


def test_apply_tp1_long_hit_and_be_move():
    df = _make_session(10)
    # Construct prices so TP1 is hit on bar 5
    # entry at 100, stop at 99 -> risk_per_unit = 1, tp1_R=1 -> tp1_price = 101
    df.loc[df.index[3], ["open", "high", "low", "close"]] = [100.0, 100.5, 99.8, 100.2]
    df.loc[df.index[4], ["open", "high", "low", "close"]] = [100.2, 100.8, 100.0, 100.6]
    df.loc[df.index[5], ["open", "high", "low", "close"]] = [100.6, 101.2, 100.5, 101.0]

    entry_idx = 2
    entry_price = 100.0
    stop_price = 99.0
    side = 1

    cfg = MgmtCfg(tp1_R=1.0, tp2_R=2.0, scale_at_tp1=0.5, move_to_BE_on_tp1=True)
    res = apply_tp1(df, entry_idx, side, entry_price, stop_price, cfg)

    assert res.hit is True
    assert res.idx == 5
    assert res.time == df.index[5]
    assert res.price == entry_price + 1.0 * (entry_price - stop_price)
    assert res.stop_after_tp1 == entry_price
    # 3 minutes from bar 2 -> bar 5
    assert abs(res.t_to_tp1_min - 3.0) < 1e-6


def test_apply_tp1_short_no_hit_no_be_move():
    df = _make_session(10)
    # entry at 100, stop at 101 -> risk_per_unit = 1, tp1_R=1 -> tp1_price = 99
    # We never trade low below 99, so TP1 should not hit.
    df.loc[:, ["open", "high", "low", "close"]] = [100.0, 100.5, 99.5, 100.0]

    entry_idx = 1
    entry_price = 100.0
    stop_price = 101.0
    side = -1

    cfg = MgmtCfg(tp1_R=1.0, tp2_R=2.0, scale_at_tp1=0.5, move_to_BE_on_tp1=False)
    res = apply_tp1(df, entry_idx, side, entry_price, stop_price, cfg)

    assert res.hit is False
    assert res.idx is None
    assert res.time is None
    assert res.t_to_tp1_min is None
    # stop unchanged because we never moved to BE
    assert res.stop_after_tp1 == stop_price


def test_compute_tp2_target_priority_and_earliest():
    df = _make_session(10)
    # entry at 100, stop at 99 -> risk_per_unit=1
    # We'll arrange:
    #   - measured move at 102, hit on bar 7
    #   - +2R target at 102, hit on bar 6
    #   - PDH at 101.5, hit earliest on bar 5
    # The function should pick PDH (earliest; PDH priority).
    df.loc[df.index[4], ["high", "low"]] = [101.0, 100.2]
    df.loc[df.index[5], ["high", "low"]] = [101.6, 100.5]  # PDH hit here
    df.loc[df.index[6], ["high", "low"]] = [102.1, 101.0]  # +2R hit here
    df.loc[df.index[7], ["high", "low"]] = [102.2, 101.5]  # measured move also hit

    entry_idx = 2
    entry_price = 100.0
    stop_price = 99.0
    side = 1

    cfg = MgmtCfg(tp1_R=1.0, tp2_R=2.0, scale_at_tp1=0.5, move_to_BE_on_tp1=True)
    refs = {
        "pdh": 101.5,
        "pdl": None,
        "or_height": 2.0,
    }

    res = compute_tp2_target(df, entry_idx, side, entry_price, stop_price, cfg, refs)

    assert res.hit is True
    assert res.label == "pdh_pdl"
    assert res.idx == 5
    assert res.time == df.index[5]
    assert abs(res.price - 101.5) < 1e-6
