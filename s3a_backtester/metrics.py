# Metrics for 3A
from __future__ import annotations

from typing import Any

import pandas as pd
import numpy as np


# ----------------------------
# Core helpers
# ----------------------------
def _realized_r(trades: pd.DataFrame) -> pd.Series:
    """Return realized_R as a clean float series (NaNs -> 0)."""
    if trades is None or len(trades) == 0 or "realized_R" not in trades.columns:
        return pd.Series(dtype=float)
    r = pd.to_numeric(trades["realized_R"], errors="coerce").fillna(0.0)
    return r


def _to_dt(trades: pd.DataFrame, col: str) -> pd.Series:
    """Best-effort datetime parsing for a column."""
    if trades is None or col not in trades.columns or len(trades) == 0:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(trades[col], errors="coerce")


# ----------------------------
# Equity + DD in R-space
# ----------------------------
def equity_curve_R(trades: pd.DataFrame) -> pd.Series:
    """Cumulative R equity curve (trade-by-trade)."""
    r = _realized_r(trades)
    return r.cumsum()


def max_drawdown_R(curve: pd.Series) -> float:
    """Max drawdown of an equity curve in R units, anchored at 0."""
    if curve is None or len(curve) == 0:
        return 0.0

    values = pd.to_numeric(curve, errors="coerce").fillna(0.0).to_numpy()
    values = np.concatenate(([0.0], values))  # anchor at 0

    roll_max = np.maximum.accumulate(values)
    dd = roll_max - values
    return float(dd.max()) if dd.size else 0.0


def sqn(trades: pd.DataFrame) -> float:
    """System Quality Number (Van Tharp): mean(R)/std(R) * sqrt(n)."""
    r = _realized_r(trades)
    if len(r) < 2 or r.std(ddof=0) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=0) * (len(r) ** 0.5))


# ----------------------------
# Summary API
# ----------------------------
def trades_per_month(trades: pd.DataFrame) -> float:
    """Average trades/month over months that actually have trades."""
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
    """
    Single-run summary stats from a normalized trade log.
    """
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
        "expectancy_R": avg_R,  # explicit alias: expectancy in R
        "avg_win_R": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_R": float(losses.mean()) if len(losses) else 0.0,  # negative
        "sum_R": float(r.sum()),
        "maxDD_R": float(mdd),
        "SQN": float(sqn(trades)),
        "trades_per_month": float(trades_per_month(trades)),
    }


# Backwards-compatability: Week 1-4 code uses compute_summary()
def compute_summary(trades: pd.DataFrame) -> dict[str, Any]:
    return summary(trades)


# ----------------------------
# Grouped summaries
# ----------------------------
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
    """Compute per-group summary(trades) for a grouping key."""
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


# Legacy function kept, still useful for quick aggregations
def group_stats(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    """Legacy simple aggregation: count/mean/sum of realized_R."""
    if trades is None or by not in trades.columns or len(trades) == 0:
        return pd.DataFrame(columns=["trades", "avg_R", "sum_R"])
    r = _realized_r(trades)
    df = trades.copy()
    df["realized_R"] = r
    out = df.groupby(by)["realized_R"].agg(["count", "mean", "sum"])
    return out.rename(columns={"count": "trades", "mean": "avg_R", "sum": "sum_R"})
