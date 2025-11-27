# Test file specifically for 3A's trade simulations
import pandas as pd
import pytest
from s3a_backtester.engine import generate_signals, simulate_trades


def _make_idx():
    return pd.date_range(
        "2024-01-02 09:30",
        periods=16,
        freq="1min",
        tz="America/New_York",
    )


class _Cfg:
    # 1-point tick so math is easy
    tick_size = 1.0
    risk_cap_multiple = 1.25
    entry_window = type("EW", (), {"start": "09:35", "end": "11:00"})()


def _make_long_day_df(first_low: float) -> pd.DataFrame:
    """
    Synthetic 1-day series:

    - OR: 90–110
    - VWAP bands: vwap=105, [vwap_1d, vwap_1u] = [100, 110]
    - Uptrend all day (trend_5m = 1)
    - 09:35: first break above ORH -> unlock long
    - 09:37: pullback into [VWAP, +1σ] -> zone
    - micro_break_dir = +1 at 09:37 (trigger bar)
    - swing_low at first bar, with configurable low price.
    """
    idx = _make_idx()

    close = [
        100.0,
        101.0,
        102.0,
        103.0,
        104.0,  # 09:30–09:34 inside OR
        111.0,  # 09:35 unlock (> ORH=110)
        112.0,  # 09:36
        108.0,  # 09:37: in zone [105, 110]
    ] + [108.0] * (len(idx) - 8)

    # highs/lows: flat except configurable first-bar low
    high = close.copy()
    low = close.copy()
    low[0] = first_low

    df = pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1.0,
            "or_high": 110.0,
            "or_low": 90.0,
            "vwap": 105.0,
            "vwap_1u": 110.0,
            "vwap_1d": 100.0,
            "vwap_2u": 115.0,
            "vwap_2d": 95.0,
            "trend_5m": 1.0,  # uptrend (long bias)
        },
        index=idx,
    )

    # Swings: one swing low at first bar, no swing highs.
    df["swing_low"] = [True] + [False] * (len(idx) - 1)
    df["swing_high"] = [False] * len(idx)

    # Pattern: micro-swing break up at 09:37
    df["micro_break_dir"] = 0
    df["engulf_dir"] = 0
    df.loc[idx[7], "micro_break_dir"] = 1

    return df


def test_engine_week3_long_trade_basic():
    """
    Full pipeline: generate_signals + simulate_trades.

    We expect exactly one long trade at the first zone/trigger bar,
    with stop 1 tick below the last swing low and sensible R math.
    """
    df = _make_long_day_df(first_low=100.0)
    idx = df.index

    sig = generate_signals(df, cfg=_Cfg)
    trades = simulate_trades(df, sig, _Cfg)

    # Exactly one trade
    assert len(trades) == 1

    trade = trades.iloc[0]

    # Entry should be at the trigger/zone bar (09:37)
    assert trade["entry_time"] == idx[7]
    assert trade["side"] == "long"

    # Stop = last swing low - 1 tick (tick_size = 1.0) -> 100 - 1 = 99
    assert trade["stop"] == pytest.approx(99.0)

    # OR height recorded correctly (110 - 90 = 20)
    assert trade["or_height"] == pytest.approx(20.0)

    # Risk per unit and ticks are consistent
    risk_per_unit = abs(trade["entry"] - trade["stop"])
    assert trade["sl_ticks"] == pytest.approx(risk_per_unit / _Cfg.tick_size)

    # Planned R is fixed at 1.0 for now
    assert trade["risk_R"] == pytest.approx(1.0)

    # Trigger classification should come from micro_break_dir
    assert trade["trigger_type"] == "swingbreak"


def test_engine_week3_riskcap_blocks_trade_when_stop_too_far():
    """
    Same price path, but with a much deeper swing low.

    That pushes the stop far enough away that riskcap_ok should reject
    the entry, so simulate_trades must return no trades.
    """
    df = _make_long_day_df(first_low=70.0)  # deep earlier swing low
    idx = df.index

    sig = generate_signals(df, cfg=_Cfg)

    # At the trigger bar we still have a valid trigger…
    trigger_bar = idx[7]
    assert sig.loc[trigger_bar, "trigger_ok"]

    # …but the stop should be beyond the 1.25 * OR_height cap, so riskcap_ok is False
    assert not sig.loc[trigger_bar, "riskcap_ok"]

    trades = simulate_trades(df, sig, _Cfg)
    # No trades should be taken if riskcap_ok is false.
    assert len(trades) == 0
