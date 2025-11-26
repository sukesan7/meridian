# Tests for the 3A Engine
from s3a_backtester.engine import generate_signals, simulate_trades
import pandas as pd


# --------------------------------------------
# Test engine stubs
# --------------------------------------------
def test_engine_stubs_run():
    idx = pd.date_range(
        "2024-01-02 09:30", periods=10, freq="1min", tz="America/New_York"
    )
    df1 = pd.DataFrame(
        {
            "open": [1] * 10,
            "high": [1] * 10,
            "low": [1] * 10,
            "close": [1] * 10,
            "volume": [1] * 10,
        },
        index=idx,
    )
    df5 = (
        df1.resample("5min", label="right", closed="right")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )

    class _Cfg:  # minimal shim
        entry_window = type("EW", (), {"start": "09:35", "end": "11:00"})()

    sig = generate_signals(df1, df5, _Cfg)
    assert {
        "time_window_ok",
        "or_break_unlock",
        "in_zone",
        "trigger_ok",
        "disqualified_±2σ",
        "riskcap_ok",
    } <= set(sig.columns)
    trades = simulate_trades(df1, sig, _Cfg)
    assert list(trades.columns)  # has schema


def _make_simple_day_index():
    return pd.date_range(
        "2024-01-02 09:30",
        periods=16,
        freq="1min",
        tz="America/New_York",
    )


# --------------------------------------------
# Test unlock and zone long trend
# --------------------------------------------
def test_generate_signals_unlock_and_zone_long():
    idx = _make_simple_day_index()

    # Design prices:
    # 09:30-09:34: inside OR
    # 09:35: first close > ORH -> unlock
    # 09:37: pullback into [VWAP, +1σ] -> zone
    close = [
        100.0,
        101.0,
        102.0,
        103.0,
        104.0,  # 09:30-09:34
        111.0,  # 09:35 unlock (ORH=110)
        112.0,  # 09:36
        108.0,  # 09:37 zone: between VWAP=105 and +1σ=110
    ] + [108.0] * (len(idx) - 8)

    df = pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1,
            # OR levels flat for the day
            "or_high": 110.0,
            "or_low": 90.0,
            # VWAP bands flat as well
            "vwap": 105.0,
            "vwap_1u": 110.0,
            "vwap_1d": 100.0,
            "vwap_2u": 115.0,
            "vwap_2d": 95.0,
            # Uptrend all day
            "trend_5m": 1,
        },
        index=idx,
    )

    out = generate_signals(df)

    unlock_ts = idx[5]  # 09:35
    zone_ts = idx[7]  # 09:37

    # Exactly one unlock bar at 09:35
    unlock_rows = out[out["or_break_unlock"]]
    assert list(unlock_rows.index) == [unlock_ts]
    assert out.loc[unlock_ts, "direction"] == 1

    # Exactly one zone bar at 09:37
    zone_rows = out[out["in_zone"]]
    assert list(zone_rows.index) == [zone_ts]

    # No 2σ disqualifier in this toy example
    assert not bool(out["disqualified_2sigma"].any())

    # Bars in RTH should be time_window_ok == True
    assert out["time_window_ok"].all()


# --------------------------------------------
# Test 2sigma disqualifers
# --------------------------------------------
def test_generate_signals_disqualified_long_if_opposite_2sigma_hit_first():
    idx = _make_simple_day_index()

    close = [95.0]  # 09:30: already below VWAP-2σ -> disqualifier

    # Fill the rest so that unlock would *otherwise* occur at 09:35
    close += [100.0, 102.0, 103.0, 104.0]  # 09:31-09:34 inside OR
    close += [111.0]  # 09:35 > ORH => unlock candidate
    close += [108.0] * (len(idx) - len(close))

    df = pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1,
            "or_high": 110.0,
            "or_low": 90.0,
            "vwap": 105.0,
            "vwap_1u": 110.0,
            "vwap_1d": 100.0,
            "vwap_2u": 115.0,
            "vwap_2d": 95.0,
            "trend_5m": 1,
        },
        index=idx,
    )

    out = generate_signals(df)
    unlock_ts = idx[5]

    # Unlock still identified…
    assert out.loc[unlock_ts, "or_break_unlock"]
    # …but flagged as disqualified by pre-existing 2σ breach
    assert out.loc[unlock_ts, "disqualified_2sigma"]


# --------------------------------------------
# Test if zone requires an unlock
# --------------------------------------------
def test_generate_signals_zone_requires_unlock():
    """No unlock => no zone, even if price sits in the VWAP±1σ band."""
    idx = _make_simple_day_index()

    # Always trade inside OR, never break ORH/ORL
    close = [105.0] * len(idx)  # inside [vwap_1d, vwap_1u]

    df = pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1,
            "or_high": 110.0,
            "or_low": 90.0,
            "vwap": 105.0,
            "vwap_1u": 110.0,
            "vwap_1d": 100.0,
            "vwap_2u": 115.0,
            "vwap_2d": 95.0,
            "trend_5m": 1,  # uptrend
        },
        index=idx,
    )

    out = generate_signals(df)

    assert not bool(out["or_break_unlock"].any())
    assert not bool(out["in_zone"].any())


# --------------------------------------------
# Test there can only be one zone per day (first unlock)
# --------------------------------------------
def test_generate_signals_only_first_zone_per_day():
    """After unlock, only the first pullback into the zone is marked."""
    idx = _make_simple_day_index()

    # 09:30-09:34 inside OR
    close = [100.0, 101.0, 102.0, 103.0, 104.0]

    # 09:35 unlock (ORH = 110)
    close.append(111.0)  # idx[5]

    # 09:36 not in zone
    close.append(112.0)  # idx[6]

    # 09:37 zone candidate #1
    close.append(108.0)  # idx[7]

    # 09:38 zone candidate #2 – also inside zone band
    close.append(107.0)  # idx[8]

    # Rest of the day flat
    close += [107.0] * (len(idx) - len(close))

    df = pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1,
            "or_high": 110.0,
            "or_low": 90.0,
            "vwap": 105.0,
            "vwap_1u": 110.0,
            "vwap_1d": 100.0,
            "vwap_2u": 115.0,
            "vwap_2d": 95.0,
            "trend_5m": 1,
        },
        index=idx,
    )

    out = generate_signals(df)

    zone_indices = list(out.index[out["in_zone"]])
    # Only the first zone (09:37) should be marked
    assert zone_indices == [idx[7]]


# --------------------------------------------
# Test disqualified zone block
# --------------------------------------------
def test_generate_signals_zone_blocked_if_disqualified():
    """
    If the opposite 2σ band is breached before unlock, we still unlock,
    but we must never mark a zone for that session.
    """
    idx = _make_simple_day_index()

    close = []

    # 09:30 - big breach below vwap_2d (opposite 2σ for a long)
    close.append(94.0)  # < vwap_2d=95.0

    # Fill so that unlock would otherwise happen at 09:35
    close += [100.0, 102.0, 103.0, 104.0]  # 09:31-09:34 inside OR
    close.append(111.0)  # 09:35 unlock (> ORH=110)
    close.append(112.0)  # 09:36
    close.append(108.0)  # 09:37 would be in-zone if not disqualified

    close += [108.0] * (len(idx) - len(close))

    df = pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1,
            "or_high": 110.0,
            "or_low": 90.0,
            "vwap": 105.0,
            "vwap_1u": 110.0,
            "vwap_1d": 100.0,
            "vwap_2u": 115.0,
            "vwap_2d": 95.0,
            "trend_5m": 1,
        },
        index=idx,
    )

    out = generate_signals(df)

    unlock_ts = idx[5]  # 09:35

    # Unlock still happens…
    assert out.loc[unlock_ts, "or_break_unlock"]

    # …but 2σ disqualifier is active for the session
    assert bool(out["disqualified_2sigma"].any())

    # Therefore no zone should be marked
    assert not bool(out["in_zone"].any())


# --------------------------------------------
# Test trigger
# --------------------------------------------
def _make_simple_day_index():
    return pd.date_range(
        "2024-01-02 09:30", periods=16, freq="1min", tz="America/New_York"
    )


def test_trigger_ok_long_micro_break_inside_zone():
    idx = _make_simple_day_index()

    # Prices: OR 100–110, VWAP 105, zone [105, 110]
    close = [104.0] * len(idx)
    close[5] = 111.0  # 09:35 unlock (close > ORH)
    close[7] = 108.0  # 09:37: in zone and micro-break up

    df = pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1,
            "or_high": 110.0,
            "or_low": 100.0,
            "vwap": 105.0,
            "vwap_1u": 110.0,
            "vwap_1d": 100.0,
            "vwap_2u": 115.0,
            "vwap_2d": 95.0,
            "trend_5m": 1,
            # micro_swing_break output: mark a +1 break at 09:37
            "micro_break_dir": [0] * len(idx),
            "engulf_dir": [0] * len(idx),
        },
        index=idx,
    )
    df.loc[idx[7], "micro_break_dir"] = 1

    out = generate_signals(df)

    trig_rows = out[out["trigger_ok"]]
    assert list(trig_rows.index) == [idx[7]]
    assert out.loc[idx[7], "direction"] == 1


# --------------------------------------------
# Test riskcap
# --------------------------------------------
def _make_idx():
    return pd.date_range(
        "2024-01-02 09:30", periods=5, freq="1min", tz="America/New_York"
    )


class _Cfg:
    # 1-point tick so the math is easy in tests
    tick_size = 1.0
    risk_cap_multiple = 1.25
    entry_window = type("EW", (), {"start": "09:35", "end": "11:00"})()


def _base_df(or_high, or_low, close, lows):
    idx = _make_idx()
    return pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": lows,
            "close": close,
            "volume": 1,
            "or_high": or_high,
            "or_low": or_low,
            "vwap": 100.0,
            "vwap_1u": 110.0,
            "vwap_1d": 90.0,
            "vwap_2u": 120.0,
            "vwap_2d": 80.0,
            "trend_5m": 1.0,  # uptrend (long)
            "swing_high": [False] * 5,
            "swing_low": [True] + [False] * 4,  # swing low at first bar
        },
        index=idx,
    )


def test_riskcap_ok_when_stop_within_cap():
    # OR height = 10 → cap = 1.25 * 10 = 12.5
    # close = 110, swing low = 100, tick_size = 1 → stop = 99 → SL = 11 <= 12.5
    df = _base_df(or_high=110.0, or_low=100.0, close=[110.0] * 5, lows=[100.0] * 5)
    out = generate_signals(df, cfg=_Cfg)
    assert out["riskcap_ok"].all()


def test_riskcap_rejects_when_stop_too_far():
    # OR height = 10 → cap = 12.5
    # close = 110, swing low = 90, tick_size = 1 → stop = 89 → SL = 21 > 12.5
    df = _base_df(or_high=110.0, or_low=100.0, close=[110.0] * 5, lows=[90.0] * 5)
    out = generate_signals(df, cfg=_Cfg)
    # At least one bar (the ones with valid swings) should be rejected.
    assert not out["riskcap_ok"].all()
