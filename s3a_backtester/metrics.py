# s3a_backtester/metrics.py
from __future__ import annotations
import pandas as pd


def compute_summary(trades: pd.DataFrame) -> dict:
    """
    Return a light summary so the CLI runs.
    Expects a 'realized_R' column when trades exist; handles empty input.
    """
    if trades is None or len(trades) == 0:
        return {"trades": 0, "win_rate": 0.0, "avg_R": 0.0, "maxDD_R": 0.0, "SQN": 0.0}
    r = pd.to_numeric(trades.get("realized_R"), errors="coerce").fillna(0.0)
    wr = float((r > 0).mean()) if len(r) else 0.0
    avg_R = float(r.mean()) if len(r) else 0.0
    curve = equity_curve_R(trades)
    mdd = max_drawdown_R(curve)
    sqn_val = sqn(trades)
    return {
        "trades": int(len(trades)),
        "win_rate": wr,
        "avg_R": avg_R,
        "maxDD_R": mdd,
        "SQN": sqn_val,
    }


def equity_curve_R(trades: pd.DataFrame) -> pd.Series:
    """Cumulative R curve from 'realized_R'. Empty-safe."""
    r = pd.to_numeric(trades.get("realized_R"), errors="coerce").fillna(0.0)
    return r.cumsum()


def max_drawdown_R(curve: pd.Series) -> float:
    """Max drawdown over a cumulative R series."""
    if curve is None or len(curve) == 0:
        return 0.0
    roll_max = curve.cummax()
    dd = roll_max - curve
    return float(dd.max()) if len(dd) else 0.0


def sqn(trades: pd.DataFrame) -> float:
    """Van Tharp SQN (mean/STD * sqrt(N)) over realized_R. Empty-safe."""
    r = pd.to_numeric(trades.get("realized_R"), errors="coerce").dropna()
    if len(r) < 2 or r.std(ddof=0) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=0) * (len(r) ** 0.5))


def group_stats(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    """Simple grouped stats; returns empty DF if key missing."""
    if trades is None or by not in trades.columns or len(trades) == 0:
        return pd.DataFrame(columns=["trades", "avg_R", "sum_R"])
    r = pd.to_numeric(trades.get("realized_R"), errors="coerce").fillna(0.0)
    df = trades.copy()
    df["realized_R"] = r
    out = df.groupby(by)["realized_R"].agg(["count", "mean", "sum"])
    return out.rename(columns={"count": "trades", "mean": "avg_R", "sum": "sum_R"})
