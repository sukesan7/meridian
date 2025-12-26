"""
Performance Metrics
-------------------
Calculates standardized trading metrics (R-multiples, SQN, Drawdown).
Includes grouping helpers for slicing performance by time or market regime.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import numpy as np


def _realized_r(trades: pd.DataFrame | None) -> pd.Series:
    """Extracts realized_R as a float Series, handling missing values."""
    if trades is None or len(trades) == 0 or "realized_R" not in trades.columns:
        return pd.Series(dtype=float)
    r = pd.to_numeric(trades["realized_R"], errors="coerce").fillna(0.0)
    return r


def _to_dt(trades: pd.DataFrame | None, col: str) -> pd.Series:
    """Parses a column to datetime, returning empty series on failure."""
    if trades is None or col not in trades.columns or len(trades) == 0:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(trades[col], errors="coerce")


def equity_curve_R(trades: pd.DataFrame) -> pd.Series:
    """Computes the cumulative equity curve in R-units."""
    r = _realized_r(trades)
    return r.cumsum()


def max_drawdown_R(curve: pd.Series | None) -> float:
    """Calculates the maximum drawdown of an R-unit equity curve."""
    if curve is None or len(curve) == 0:
        return 0.0

    values = pd.to_numeric(curve, errors="coerce").fillna(0.0).to_numpy()
    values = np.concatenate(([0.0], values))

    roll_max = np.maximum.accumulate(values)
    dd = roll_max - values
    return float(dd.max()) if dd.size else 0.0


def sqn(trades: pd.DataFrame) -> float:
    """Calculates System Quality Number (Van Tharp)."""
    r = _realized_r(trades)
    if len(r) < 2 or r.std(ddof=0) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=0) * (len(r) ** 0.5))


def trades_per_month(trades: pd.DataFrame) -> float:
    """Calculates average trade frequency per active month."""
    dt = _to_dt(trades, "entry_time")
    if len(dt) == 0:
        return 0.0
    dt = dt.dropna()
    if dt.empty:
        return 0.0
    months = dt.dt.to_period("M")
    n_months = int(months.nunique())
    return float(len(dt) / n_months) if n_months else 0.0


def summary(trades: pd.DataFrame) -> dict[str, Any]:
    """Generates a comprehensive statistical summary of the trade log."""
    r = _realized_r(trades)
    n = int(len(r))

    if n == 0:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg_R": 0.0,
            "expectancy_R": 0.0,
            "avg_win_R": 0.0,
            "avg_loss_R": 0.0,
            "sum_R": 0.0,
            "maxDD_R": 0.0,
            "SQN": 0.0,
            "trades_per_month": 0.0,
        }

    wins = r[r > 0]
    losses = r[r < 0]

    avg_R = float(r.mean())
    wr = float((r > 0).mean())

    curve = equity_curve_R(trades)
    mdd = max_drawdown_R(curve)

    return {
        "trades": n,
        "win_rate": wr,
        "avg_R": avg_R,
        "expectancy_R": avg_R,
        "avg_win_R": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_R": float(losses.mean()) if len(losses) else 0.0,
        "sum_R": float(r.sum()),
        "maxDD_R": float(mdd),
        "SQN": float(sqn(trades)),
        "trades_per_month": float(trades_per_month(trades)),
    }


def compute_summary(trades: pd.DataFrame) -> dict[str, Any]:
    """Alias for summary() to maintain compatibility."""
    return summary(trades)


def _add_time_parts(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return df
    out = df.copy()
    dt = _to_dt(out, "entry_time")
    if len(dt):
        out["day_of_week"] = dt.dt.day_name()
        out["month"] = dt.dt.to_period("M").astype(str)
    return out


def _add_or_quartile(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return df
    out = df.copy()

    if "or_height" not in out.columns:
        out["or_quartile"] = pd.Series(dtype="object")
        return out

    x = pd.to_numeric(out["or_height"], errors="coerce")
    if x.notna().sum() < 4:
        out["or_quartile"] = pd.Series(["Q?"] * len(out), index=out.index)
        return out

    try:
        q = pd.qcut(x, 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
        out["or_quartile"] = q.astype(str)
    except ValueError:
        out["or_quartile"] = pd.Series(["Q?"] * len(out), index=out.index)
    return out


def grouped_summary(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    """Computes summary statistics grouped by a specific column."""
    if trades is None or len(trades) == 0:
        return pd.DataFrame()

    df = trades.copy()
    df = _add_time_parts(df)
    df = _add_or_quartile(df)

    if by not in df.columns:
        raise ValueError(f"Grouping column '{by}' not present/derivable")

    rows: list[dict[str, Any]] = []
    for key, g in df.groupby(by, dropna=False):
        s = summary(g)
        s[by] = str(key)
        rows.append(s)

    out = pd.DataFrame(rows).set_index(by)
    return out.sort_index()
