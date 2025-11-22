from s3a_backtester.engine import generate_signals, simulate_trades
import pandas as pd


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
