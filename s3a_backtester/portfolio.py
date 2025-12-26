"""
Portfolio Utilities
-------------------
Calculates equity curves, compounding growth (CAGR), and drawdowns
from a series of trade returns (R).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PathStats:
    maxdd_pct: float
    cagr: float
    final_equity: float
    blew_up: bool


def equity_curve_from_r(
    r: np.ndarray,
    *,
    risk_per_trade: float,
    start_equity: float = 1.0,
) -> np.ndarray:
    """
    Computes an equity curve using fixed fractional position sizing.
    Formula: Equity_{t+1} = Equity_t * (1 + risk * R_t)
    """
    r = np.asarray(r, dtype=float)
    n = int(r.size)

    eq = np.empty(n + 1, dtype=float)
    eq[0] = float(start_equity)

    for i in range(n):
        mult = 1.0 + float(risk_per_trade) * float(r[i])
        if mult <= 0.0:
            eq[i + 1 :] = 0.0
            break
        eq[i + 1] = eq[i] * mult

    return eq


def max_drawdown_pct(equity: np.ndarray) -> float:
    """Calculates the maximum percentage drawdown from peak equity."""
    equity = np.asarray(equity, dtype=float)
    if equity.size <= 1:
        return 0.0

    peak = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0.0, (peak - equity) / peak, 0.0)

    mdd = float(np.nanmax(dd)) if dd.size else 0.0
    if not np.isfinite(mdd):
        return 0.0
    return max(0.0, min(1.0, mdd))


def cagr_from_equity(
    start_equity: float,
    end_equity: float,
    *,
    years: float,
) -> float:
    """Calculates Compound Annual Growth Rate."""
    if years <= 0.0:
        raise ValueError("years must be > 0")
    if end_equity <= 0.0:
        return -1.0
    if start_equity <= 0.0:
        raise ValueError("start_equity must be > 0")

    return float((end_equity / start_equity) ** (1.0 / years) - 1.0)


def path_stats_from_r(
    r: np.ndarray,
    *,
    risk_per_trade: float,
    years: float,
    start_equity: float = 1.0,
) -> PathStats:
    """Aggregates portfolio stats for a single simulation path."""
    eq = equity_curve_from_r(
        r, risk_per_trade=risk_per_trade, start_equity=start_equity
    )
    mdd = max_drawdown_pct(eq)
    final_eq = float(eq[-1])
    blew_up = final_eq <= 0.0
    cagr = cagr_from_equity(start_equity, final_eq, years=years)
    return PathStats(maxdd_pct=mdd, cagr=cagr, final_equity=final_eq, blew_up=blew_up)
