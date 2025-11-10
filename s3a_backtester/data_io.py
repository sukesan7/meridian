from __future__ import annotations
import pandas as pd


def load_minute_df(path: str, tz: str = "America/New_York") -> pd.DataFrame:
    """Load 1-min OHLCV, parse UTC timestamps, return tz-aware ET index."""
    df = (
        pd.read_parquet(path)
        if path.lower().endswith(".parquet")
        else pd.read_csv(path)
    )

    # find timestamp column
    ts = None
    for cand in ("timestamp", "datetime", "time", "date"):
        if cand in df.columns:
            ts = pd.to_datetime(df[cand], utc=True, errors="coerce")
            df = df.drop(columns=[cand])
            break
    if ts is None:
        ts = pd.to_datetime(df.iloc[:, 0], utc=True, errors="coerce")
        df = df.iloc[:, 1:]

    if ts.isna().any():
        bad = int(ts.isna().sum())
        raise ValueError(f"{bad} rows have invalid timestamps; check file schema.")

    # convert on a DatetimeIndex (not a Series)
    idx = pd.DatetimeIndex(ts).tz_convert(tz)
    df.index = idx

    # enforce schema
    expected = ["open", "high", "low", "close", "volume"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    return df.sort_index()


def slice_rth(df: pd.DataFrame) -> pd.DataFrame:
    """Keep US RTH 09:30–16:00 ET (inclusive on both ends)."""
    return df.between_time("09:30", "16:00", inclusive="both")


def resample(df1: pd.DataFrame, rule: str = "5min") -> pd.DataFrame:
    """Resample to higher TF without peeking (label/closed = right)."""
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    return df1.resample(rule, label="right", closed="right").agg(agg).dropna(how="all")
