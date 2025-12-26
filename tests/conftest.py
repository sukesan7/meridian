"""
Pytest Fixtures
---------------
Shared resources for testing.
- sample_minute_df: Basic deterministic OHLCV data.
- synth_parquet: Integrated synthetic dataset for CLI/Pipeline tests.
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_minute_df():
    """
    Creates a basic valid 1-minute OHLCV DataFrame for unit tests.
    390 bars (standard RTH session).
    """
    idx = pd.date_range(
        "2024-01-02 09:30", periods=390, freq="1min", tz="America/New_York"
    )
    rng = np.random.default_rng(42)
    close = 100 + rng.standard_normal(len(idx)).cumsum() / 10.0

    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 1000,
        },
        index=idx,
    )
    return df


@pytest.fixture
def synth_parquet(tmp_path: Path) -> Path:
    """
    Creates a synthetic parquet file for integration/CLI tests.
    Contains 3 days of RTH data with deterministic timestamps.
    """
    start = pd.Timestamp("2025-01-06", tz="America/New_York")
    frames = []
    price = 100.0
    rng = np.random.default_rng(123)

    for d in range(3):
        day = (start + pd.Timedelta(days=d)).normalize()
        idx = pd.date_range(
            day + pd.Timedelta(hours=9, minutes=30),
            day + pd.Timedelta(hours=15, minutes=59),
            freq="1min",
            tz="America/New_York",
        )
        noise = rng.normal(0, 0.05, size=len(idx))
        close = price + np.linspace(0, 1.0, len(idx)) + noise

        df = pd.DataFrame(
            {
                "timestamp": idx.tz_convert("UTC"),
                "open": close,
                "high": close + 0.05,
                "low": close - 0.05,
                "close": close,
                "volume": 100,
            }
        )
        frames.append(df)
        price = close[-1]

    df = pd.concat(frames, ignore_index=True)
    p = tmp_path / "synth_3d_RTH.parquet"
    df.to_parquet(p, index=False)
    return p
