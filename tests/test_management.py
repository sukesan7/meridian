"""
Tests for s3a_backtester.management
-----------------------------------
Coverage:
- TP1 Logic (Hit, Scale-out, BE Move).
- TP2 Logic (Priority targets).
- Time Stop Logic (Timeout, Extensions).
- Full Lifecycle Integration.
"""

import pandas as pd
import pytest
from s3a_backtester.management import (
    apply_tp1,
    compute_tp2_target,
    run_time_stop,
    manage_trade_lifecycle,
)
from s3a_backtester.config import MgmtCfg, TimeStopCfg


@pytest.fixture
def session_df():
    idx = pd.date_range("2024-01-01 09:30", periods=60, freq="1min")
    return pd.DataFrame({"high": 100.0, "low": 100.0, "close": 100.0}, index=idx)


def test_apply_tp1_hit_and_be_move(session_df):
    session_df.loc[session_df.index[5], "high"] = 101.5
    cfg = MgmtCfg(tp1_R=1.0, move_to_BE_on_tp1=True)
    res = apply_tp1(
        session_df,
        entry_idx=2,
        side=1,
        entry_price=100.0,
        stop_price=99.0,
        mgmt_cfg=cfg,
    )
    assert res.hit
    assert res.idx == 5
    assert res.stop_after_tp1 == 100.0


def test_apply_tp1_miss(session_df):
    cfg = MgmtCfg(tp1_R=1.0)
    res = apply_tp1(
        session_df,
        entry_idx=2,
        side=1,
        entry_price=100.0,
        stop_price=99.0,
        mgmt_cfg=cfg,
    )
    assert not res.hit


def test_tp2_priority_pdh_over_r(session_df):
    session_df.loc[session_df.index[5], "high"] = 104.0
    refs = {"pdh": 102.0, "pdl": 90.0, "or_height": 5.0}
    cfg = MgmtCfg(tp2_R=3.0)
    res = compute_tp2_target(
        session_df,
        entry_idx=2,
        side=1,
        entry_price=100.0,
        stop_price=99.0,
        mgmt_cfg=cfg,
        refs=refs,
    )
    assert res.hit
    assert res.label == "pdh_pdl"
    assert res.price == 102.0


def test_tp2_measured_move(session_df):
    session_df.loc[session_df.index[10], "high"] = 106.0
    refs = {"pdh": None, "pdl": None, "or_height": 5.0}
    cfg = MgmtCfg(tp2_R=10.0)
    res = compute_tp2_target(
        session_df,
        entry_idx=2,
        side=1,
        entry_price=100.0,
        stop_price=99.0,
        mgmt_cfg=cfg,
        refs=refs,
    )
    assert res.hit
    assert res.label == "measured_move"
    assert res.price == 105.0


def test_time_stop_no_tp1_exit(session_df):
    cfg = TimeStopCfg(mode="15m", tp1_timeout_min=15)
    res = run_time_stop(
        session_df,
        entry_idx=0,
        tp1_idx=None,
        side=1,
        entry_price=100,
        stop_price=99,
        time_cfg=cfg,
    )
    assert res.reason == "no_tp1_15m"
    assert res.idx == 15


def test_time_stop_extension_break(session_df):
    trend_ok = pd.Series(True, index=session_df.index)
    trend_ok.iloc[20] = False
    cfg = TimeStopCfg(mode="15m", allow_extension=True)
    res = run_time_stop(
        session_df,
        entry_idx=0,
        tp1_idx=5,
        side=1,
        entry_price=100,
        stop_price=99,
        time_cfg=cfg,
        trend_ok=trend_ok,
    )
    assert res.reason == "extension_break"
    assert res.idx == 20


def test_time_stop_max_hold(session_df):
    # If using extension logic, it exits the minute AFTER deadline
    cfg = TimeStopCfg(mode="15m", max_holding_min=45, allow_extension=True)
    res = run_time_stop(
        session_df,
        entry_idx=0,
        tp1_idx=5,
        side=1,
        entry_price=100,
        stop_price=99,
        time_cfg=cfg,
    )
    assert res.reason == "max_hold"
    # 09:30 + 45 = 10:15 (Index 45). Logic > deadline implies 10:16 (Index 46).
    assert res.idx == 46


def test_lifecycle_runner_stopped_at_be(session_df):
    # Entry @ 2. TP1 @ 5. Stop moves to BE (100).
    # IMPORTANT: Keep prices > 100 between TP1 and Stop Hit to prevent early exit.
    session_df["low"] = 100.5
    session_df["high"] = 100.5
    session_df["close"] = 100.5

    session_df.loc[session_df.index[5], "high"] = 101.5  # TP1 Hit
    session_df.loc[session_df.index[10], "low"] = 99.5  # Stop Hit

    m_cfg = MgmtCfg(tp1_R=1.0, scale_at_tp1=0.5, move_to_BE_on_tp1=True)
    t_cfg = TimeStopCfg(mode="none")

    res = manage_trade_lifecycle(
        session_df,
        entry_idx=2,
        side=1,
        entry_price=100,
        stop_price=99,
        mgmt_cfg=m_cfg,
        time_cfg=t_cfg,
        refs={},
        vwap_side_ok=None,
        trend_ok=None,
        sigma_ok=None,
        dd_ok=None,
    )

    assert res["realized_R"] == pytest.approx(0.5)
    assert res["exit_idx"] == 10
