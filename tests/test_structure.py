# Tests for the structure
import pandas as pd

from s3a_backtester.structure import trend_5m, Trend5mConfig, micro_swing_break


# --------- create day test ------------
def _make_simple_day(direction: str = "up") -> pd.DataFrame:
    idx = pd.date_range(
        "2024-01-02 09:30",
        periods=10,
        freq="5min",
        tz="America/New_York",
    )

    if direction == "up":
        highs = range(1, 11)
        lows = range(0, 10)
    else:
        highs = range(11, 1, -1)
        lows = range(10, 0, -1)

    df = pd.DataFrame(
        {
            "open": list(highs),
            "high": list(highs),
            "low": list(lows),
            "close": list(highs),
        },
        index=idx,
    )
    # simple flat VWAP in the middle so VWAP-side check is deterministic
    df["vwap"] = 5.0
    return df


# --------- 5-minute trend------------
def test_trend_5m_uptrend_basic():
    df = _make_simple_day("up")
    cfg = Trend5mConfig(lookback=3)
    out = trend_5m(df, cfg)

    assert "trend_5m" in out.columns
    assert "trend_vwap_ok" in out.columns

    # After a few bars the trend should lock in as +1
    assert out["trend_5m"].iloc[-1] == 1
    # In this synthetic series all closes are above VWAP=5 after the early bars
    assert out["trend_vwap_ok"].iloc[-1]


def test_trend_5m_downtrend_basic():
    df = _make_simple_day("down")
    cfg = Trend5mConfig(lookback=3)
    out = trend_5m(df, cfg)

    # Trend should end as -1
    assert out["trend_5m"].iloc[-1] == -1
    # Closes are below VWAP=5 for most of the series → last bar OK for downtrend
    assert out["trend_vwap_ok"].iloc[-1]


# --------- 1-minute micro swing break ------------
def _make_1min_index(n: int = 10) -> pd.DatetimeIndex:
    return pd.date_range(
        "2024-01-02 09:30",
        periods=n,
        freq="1min",
        tz="America/New_York",
    )


def test_micro_swing_break_upside_break():
    """Marks +1 when price breaks the most recent swing high."""
    idx = _make_1min_index(10)

    # Swing high at bar 2, broken at bar 4.
    high = [100, 105, 110, 109, 112, 111, 110, 109, 108, 107]
    low = [95, 96, 100, 101, 102, 103, 104, 105, 106, 107]

    df = pd.DataFrame(
        {
            "open": high,
            "high": high,
            "low": low,
            "close": high,
            "volume": 1,
            "swing_high": [
                False,
                False,
                True,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
            ],
            "swing_low": [False] * 10,
        },
        index=idx,
    )

    out = micro_swing_break(df)
    # Only one break, at bar 4
    assert out["micro_break_dir"].sum() == 1
    assert out["micro_break_dir"].iloc[4] == 1


def test_micro_swing_break_downside_break():
    """Marks -1 when price breaks the most recent swing low."""
    idx = _make_1min_index(10)

    # Swing low at bar 2, broken at bar 4.
    high = [110, 109, 108, 107, 106, 105, 104, 103, 102, 101]
    low = [100, 99, 95, 96, 94, 95, 96, 97, 98, 99]

    df = pd.DataFrame(
        {
            "open": low,
            "high": high,
            "low": low,
            "close": low,
            "volume": 1,
            "swing_high": [False] * 10,
            "swing_low": [
                False,
                False,
                True,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
            ],
        },
        index=idx,
    )

    out = micro_swing_break(df)
    # Only one break, at bar 4
    assert out["micro_break_dir"].sum() == -1  # one -1
    assert out["micro_break_dir"].iloc[4] == -1


def test_micro_swing_break_engulf_dir():
    """Engulf detection returns +1 for bullish and -1 for bearish engulfing bars."""
    idx = _make_1min_index(4)

    # Bar 0: red
    # Bar 1: bullish engulf of bar 0
    # Bar 2: bearish engulf of bar 1
    # Bar 3: nothing
    df = pd.DataFrame(
        {
            "open": [100.0, 98.0, 102.0, 101.0],
            "high": [101.0, 103.0, 103.0, 102.0],
            "low": [99.0, 97.0, 97.0, 100.0],
            "close": [99.0, 101.0, 97.0, 101.0],
            "volume": 1,
            "swing_high": [False] * 4,
            "swing_low": [False] * 4,
        },
        index=idx,
    )

    out = micro_swing_break(df)
    engulf = out["engulf_dir"]

    assert engulf.tolist() == [0, 1, -1, 0]
