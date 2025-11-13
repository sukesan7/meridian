import numpy as np
import pandas as pd


def make_minute_ohlcv(
    start="2024-06-03 09:20",
    end="2024-06-05 16:10",
    tz="America/New_York",
    seed=7,
):
    idx = pd.date_range(start=start, end=end, freq="1min", tz=tz)
    rng = np.random.default_rng(seed)
    close = 100 + rng.standard_normal(len(idx)).cumsum() / 20
    high = close + rng.uniform(0.02, 0.12, len(idx))
    low = close - rng.uniform(0.02, 0.12, len(idx))
    open_ = close + rng.uniform(-0.05, 0.05, len(idx))
    vol = rng.integers(50, 200, len(idx))
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )
    csv_df = df.copy()
    csv_df.insert(0, "datetime", csv_df.index.tz_convert("UTC"))
    return df, csv_df
