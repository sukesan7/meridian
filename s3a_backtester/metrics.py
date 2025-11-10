from __future__ import annotations
import pandas as pd


def _realized_r(trades: pd.DataFrame) -> pd.Series:
    if trades is None or len(trades) == 0 or "realized_R" not in trades.columns:
        return pd.Series(dtype=float)
    r = pd.to_numeric(trades["realized_R"], errors="coerce").fillna(0.0)
    return r


def compute_summary(trades: pd.DataFrame) -> dict:
    r = _realized_r(trades)
    n = int(len(r))
    wr = float((r > 0).mean()) if n else 0.0
    avg_R = float(r.mean()) if n else 0.0
    curve = equity_curve_R(trades)
    mdd = max_drawdown_R(curve)
    sqn_val = sqn(trades)
    return {"trades": n, "win_rate": wr, "avg_R": avg_R, "maxDD_R": mdd, "SQN": sqn_val}


def equity_curve_R(trades: pd.DataFrame) -> pd.Series:
    r = _realized_r(trades)
    return r.cumsum()


def max_drawdown_R(curve: pd.Series) -> float:
    if curve is None or len(curve) == 0:
        return 0.0
    roll_max = curve.cummax()
    dd = roll_max - curve
    return float(dd.max()) if len(dd) else 0.0


def sqn(trades: pd.DataFrame) -> float:
    r = _realized_r(trades)
    if len(r) < 2 or r.std(ddof=0) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=0) * (len(r) ** 0.5))


def group_stats(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    if trades is None or by not in trades.columns or len(trades) == 0:
        return pd.DataFrame(columns=["trades", "avg_R", "sum_R"])
    r = _realized_r(trades)
    df = trades.copy()
    df["realized_R"] = r
    out = df.groupby(by)["realized_R"].agg(["count", "mean", "sum"])
    return out.rename(columns={"count": "trades", "mean": "avg_R", "sum": "sum_R"})
