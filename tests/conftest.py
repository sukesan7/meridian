from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import pytest


def make_synth_rth_1m(
    start_date: str, n_days: int = 3, tz: str = "America/New_York"
) -> pd.DataFrame:
    """
    Create a minimal RTH 1m OHLCV dataset with a tz-aware timestamp column.
    - 09:30 to 15:59 = 390 bars/session.
    - Simple trend + noise to allow unlock/zone/trigger events to occur sometimes.
    """
    start = pd.Timestamp(start_date, tz=tz)

    frames = []
    price = 100.0
    rng = np.random.default_rng(123)

    for d in range(n_days):
        day = (start + pd.Timedelta(days=d)).normalize()
        # skip weekends automatically, for now assume tests use weekdays
        idx = pd.date_range(
            day + pd.Timedelta(hours=9, minutes=30),
            day + pd.Timedelta(hours=15, minutes=59),
            freq="1min",
            tz=tz,
        )

        # deterministic-ish intraday drift + small noise
        drift = np.linspace(0, 1.5, len(idx))
        noise = rng.normal(0, 0.05, size=len(idx))
        close = price + drift + noise
        open_ = np.r_[close[0], close[:-1]]
        high = np.maximum(open_, close) + 0.02
        low = np.minimum(open_, close) - 0.02
        vol = rng.integers(50, 200, size=len(idx))

        df = pd.DataFrame(
            {
                "timestamp": idx.tz_convert("UTC"),  # store UTC like vendor files
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": vol,
            }
        )
        frames.append(df)

        price = float(close[-1] + 0.25)  # carry forward baseline

    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def synth_parquet(tmp_path: Path) -> Path:
    df = make_synth_rth_1m("2025-01-06", n_days=3)  # Monday start
    p = tmp_path / "synth_3d_RTH.parquet"
    df.to_parquet(p, index=False)
    return p
