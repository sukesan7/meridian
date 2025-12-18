# Test Management Session

from __future__ import annotations

import pandas as pd
import numpy as np
import pytest

from s3a_backtester.engine import simulate_trades
from s3a_backtester.config import MgmtCfg, TimeStopCfg


def _make_session(start: str = "2025-01-01 09:30", n: int = 10) -> pd.DataFrame:
    """
    Build a simple 1-minute OHLC frame we can mutate per-test.
    """
    idx = pd.date_range(start=start, periods=n, freq="1min")
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


class DummyInstrument:
    def __init__(self, tick_size: float = 1.0) -> None:
        self.tick_size = tick_size


class DummyConfig:
    """
    Minimal config object exposing the attributes engine.simulate_trades expects:
      - instrument.tick_size OR tick_size
      - management: MgmtCfg
      - time_stop: TimeStopCfg
    """

    def __init__(
        self, mgmt_cfg: MgmtCfg, ts_cfg: TimeStopCfg, tick_size: float = 1.0
    ) -> None:
        self.instrument = DummyInstrument(tick_size=tick_size)
        self.management = mgmt_cfg
        self.time_stop = ts_cfg
        self.tick_size = tick_size


def test_management_session_long_tp1_then_tp2(monkeypatch):
    """
    End-to-end: long trade where TP1 hits first, then TP2.
    We expect:
      - TP1 at +1R,
      - TP2 at +2R,
      - scale_at_tp1 = 0.5, so total R = 0.5*1R + 0.5*2R = 1.5R.
    """
    # Build 10-bar session, 1-minute bars from 09:30
    bars = _make_session(n=10)
    idx = bars.index

    # Real prices:
    # entry at t1 (09:31) at 100, stop at 99 -> risk_per_unit = 1
    #   TP1 at 101 (hit at t2),
    #   TP2 at 102 (hit at t3).
    bars.loc[idx[1], ["open", "high", "low", "close"]] = [100.0, 100.0, 99.8, 100.0]
    bars.loc[idx[2], ["open", "high", "low", "close"]] = [
        100.2,
        101.2,
        100.1,
        101.0,
    ]  # TP1
    bars.loc[idx[3], ["open", "high", "low", "close"]] = [
        101.0,
        102.2,
        100.9,
        102.0,
    ]  # TP2

    # Construct "signals" DataFrame as engine expects:
    signals = bars.copy()
    signals["direction"] = 0
    signals["trigger_ok"] = False
    signals["riskcap_ok"] = True
    signals["time_window_ok"] = True
    signals["disqualified_2sigma"] = False
    signals["stop_price"] = np.nan
    signals["or_high"] = 102.0
    signals["or_low"] = 100.0
    signals["vwap"] = 100.0
    signals["vwap_1u"] = 101.0
    signals["vwap_1d"] = 99.0
    signals["micro_break_dir"] = 0
    signals["engulf_dir"] = 0
    signals["pdh"] = np.nan
    signals["pdl"] = np.nan

    entry_ts = idx[1]
    signals.loc[entry_ts, "direction"] = 1  # long
    signals.loc[entry_ts, "trigger_ok"] = True
    signals.loc[entry_ts, "stop_price"] = 99.0  # 1R

    # Management and time-stop config:
    mgmt_cfg = MgmtCfg(
        tp1_R=1.0,
        tp2_R=2.0,
        scale_at_tp1=0.5,
        move_to_BE_on_tp1=True,
    )
    # Disable time-stop for this test to isolate TP logic.
    ts_cfg = TimeStopCfg(
        mode="none",
        tp1_timeout_min=15,
        max_holding_min=45,
        allow_extension=True,
    )
    cfg = DummyConfig(mgmt_cfg=mgmt_cfg, ts_cfg=ts_cfg, tick_size=1.0)

    # Monkeypatch slippage to be zero so entry_price == raw close.
    def _no_slip(side: str, ts, price: float, cfg_obj):
        return price

    monkeypatch.setattr("s3a_backtester.engine.apply_slippage", _no_slip)

    trades = simulate_trades(df1=bars, signals=signals, cfg=cfg)
    assert len(trades) == 1

    trade = trades.iloc[0]

    # Entry / exit times
    assert trade["entry_time"] == entry_ts
    assert trade["exit_time"] == idx[3]  # TP2 bar

    # TP levels
    assert trade["tp1"] == pytest.approx(101.0, rel=1e-6)
    assert trade["tp2"] == pytest.approx(102.0, rel=1e-6)

    # TP1 occurs 1 minute after entry (t1 -> t2)
    assert trade["t_to_tp1_min"] == pytest.approx(1.0, rel=1e-6)

    # Realized R: 0.5 * 1R + 0.5 * 2R = 1.5R
    assert trade["realized_R"] == pytest.approx(1.5, rel=1e-6)
    assert trade["time_stop"] == "none"


def test_management_session_stop_before_tp1(monkeypatch):
    """
    End-to-end: long trade where the original stop is hit before TP1.
    We expect:
      - no TP1 hit,
      - full position exits at -1R,
      - realized_R = -1.0.
    """
    bars = _make_session(n=10)
    idx = bars.index

    # entry at t1 at 100, stop at 99 -> risk_per_unit = 1
    # low goes to 98.8 at t2 => stop hit before any TP1.
    bars.loc[idx[1], ["open", "high", "low", "close"]] = [100.0, 100.0, 99.2, 100.0]
    bars.loc[idx[2], ["open", "high", "low", "close"]] = [
        100.0,
        100.2,
        98.8,
        99.0,
    ]  # stop

    signals = bars.copy()
    signals["direction"] = 0
    signals["trigger_ok"] = False
    signals["riskcap_ok"] = True
    signals["time_window_ok"] = True
    signals["disqualified_2sigma"] = False
    signals["stop_price"] = np.nan
    signals["or_high"] = 102.0
    signals["or_low"] = 100.0
    signals["vwap"] = 100.0
    signals["vwap_1u"] = 101.0
    signals["vwap_1d"] = 99.0
    signals["micro_break_dir"] = 0
    signals["engulf_dir"] = 0
    signals["pdh"] = np.nan
    signals["pdl"] = np.nan

    entry_ts = idx[1]
    signals.loc[entry_ts, "direction"] = 1
    signals.loc[entry_ts, "trigger_ok"] = True
    signals.loc[entry_ts, "stop_price"] = 99.0

    mgmt_cfg = MgmtCfg(
        tp1_R=1.0,
        tp2_R=2.0,
        scale_at_tp1=0.5,
        move_to_BE_on_tp1=True,
    )
    ts_cfg = TimeStopCfg(
        mode="none",
        tp1_timeout_min=15,
        max_holding_min=45,
        allow_extension=True,
    )
    cfg = DummyConfig(mgmt_cfg=mgmt_cfg, ts_cfg=ts_cfg, tick_size=1.0)

    def _no_slip(side: str, ts, price: float, cfg_obj):
        return price

    monkeypatch.setattr("s3a_backtester.engine.apply_slippage", _no_slip)

    trades = simulate_trades(df1=bars, signals=signals, cfg=cfg)
    assert len(trades) == 1

    trade = trades.iloc[0]

    # Exit should be at stop on t2
    assert trade["entry_time"] == entry_ts
    assert trade["exit_time"] == idx[2]
    # -1R
    assert trade["realized_R"] == pytest.approx(-1.0, rel=1e-6)
    # TP1 never really "hit" before stop; implementation will still have a TP1 price,
    # but t_to_tp1_min should be NaN.
    assert np.isnan(trade["t_to_tp1_min"])
    assert trade["time_stop"] == "none"


def test_time_stop_extension_breaks_on_sigma_ok(monkeypatch):
    """
    Entry -> TP1 hits quickly, no TP2, no stop.
    Extension should break when close drops below vwap_1d (long).
    This test validates engine wiring of sigma_ok into run_time_stop.
    """
    idx = pd.date_range("2025-01-01 09:30", periods=50, freq="1min")
    bars = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.2,
            "low": 99.8,
            "close": 100.0,
        },
        index=idx,
    )

    entry_ts = idx[1]  # 09:31
    stop_price = 97.0  # risk = 3.0
    entry_price = 100.0
    tp1_price = entry_price + (entry_price - stop_price) * 1.0  # 103.0

    # Entry at 09:31, TP1 at 09:32
    bars.loc[idx[2], ["high", "low", "close"]] = [
        103.2,
        99.8,
        103.0,
    ]

    # Later, violate sigma_ok
    bars.loc[idx[20], ["high", "low", "close"]] = [
        100.2,
        98.9,
        98.9,
    ]

    signals = bars.copy()
    signals["direction"] = 0
    signals["trigger_ok"] = False
    signals["riskcap_ok"] = True
    signals["time_window_ok"] = True
    signals["disqualified_2sigma"] = False
    signals["stop_price"] = np.nan

    # Required refs/features
    signals["or_high"] = 110.0
    signals["or_low"] = 100.0
    signals["atr15"] = 5.0
    signals["vwap"] = 0.0
    signals["vwap_1u"] = 101.0
    signals["vwap_1d"] = 99.0
    signals["micro_break_dir"] = 0
    signals["engulf_dir"] = 0
    signals["pdh"] = np.nan
    signals["pdl"] = np.nan
    signals["trend_dir_5m"] = 1

    signals.loc[entry_ts, "direction"] = 1
    signals.loc[entry_ts, "trigger_ok"] = True
    signals.loc[entry_ts, "stop_price"] = stop_price

    mgmt_cfg = MgmtCfg(tp1_R=1.0, tp2_R=10.0, scale_at_tp1=0.5, move_to_BE_on_tp1=False)
    ts_cfg = TimeStopCfg(
        mode="15m", tp1_timeout_min=15, max_holding_min=45, allow_extension=True
    )
    cfg = DummyConfig(mgmt_cfg=mgmt_cfg, ts_cfg=ts_cfg, tick_size=1.0)

    def _no_slip(side: str, ts, price: float, cfg_obj):
        return price

    monkeypatch.setattr("s3a_backtester.engine.apply_slippage", _no_slip)

    trades = simulate_trades(df1=bars, signals=signals, cfg=cfg)
    assert len(trades) == 1
    trade = trades.iloc[0]

    # Expect exit at the sigma-break bar
    assert trade["tp1"] == pytest.approx(tp1_price)
    assert trade["exit_time"] == idx[20]
    assert trade["time_stop"] != "none"
