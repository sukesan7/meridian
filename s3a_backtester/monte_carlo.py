# Monte Carlo Simulation
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .portfolio import path_stats_from_r


def _realized_r(trades: pd.DataFrame) -> np.ndarray:
    if trades is None or len(trades) == 0 or "realized_R" not in trades.columns:
        return np.array([], dtype=float)
    r = pd.to_numeric(trades["realized_R"], errors="coerce").fillna(0.0)
    return r.to_numpy(dtype=float)


def _infer_years_from_trades(trades: pd.DataFrame) -> float | None:
    """
    Infer a calendar time span (years) from trade timestamps.

    Prefers [min(entry_time), max(exit_time)] if available. Falls back to entry_time only.
    Returns None if timestamps are missing/unparseable.
    """
    if trades is None or len(trades) == 0:
        return None

    cols = [c for c in ["entry_time", "exit_time"] if c in trades.columns]
    if not cols:
        return None

    # Use the earliest entry and latest exit if possible
    empty_dt = pd.Series(dtype="datetime64[ns]")
    entry = pd.to_datetime(
        trades.get("entry_time", empty_dt), errors="coerce", utc=True
    )
    exit_ = pd.to_datetime(trades.get("exit_time", empty_dt), errors="coerce", utc=True)

    start = entry.min() if not entry.empty else pd.NaT
    end = exit_.max() if not exit_.empty else pd.NaT

    if pd.isna(start) and not exit_.empty:
        start = exit_.min()
    if pd.isna(end) and not entry.empty:
        end = entry.max()

    if pd.isna(start) or pd.isna(end) or end <= start:
        return None

    days = (end - start).total_seconds() / 86400.0
    years = days / 365.25
    return float(years) if years > 0 else None


def _iid_bootstrap_indices(rng: np.random.Generator, n: int) -> np.ndarray:
    return rng.integers(0, n, size=n, dtype=np.int64)


def _block_bootstrap_indices(
    rng: np.random.Generator, n: int, block_size: int
) -> np.ndarray:
    """
    Circular block bootstrap:
      - pick random block starts
      - take `block_size` consecutive indices (wrapping with modulo)
      - repeat until length n
    """
    if block_size <= 0:
        raise ValueError("block_size must be > 0")

    out: list[int] = []
    while len(out) < n:
        start = int(rng.integers(0, n))
        for k in range(block_size):
            out.append((start + k) % n)
            if len(out) >= n:
                break
    return np.asarray(out, dtype=np.int64)


def mc_simulate_R(
    trades: pd.DataFrame,
    *,
    n_paths: int = 1000,
    risk_per_trade: float = 0.01,
    block_size: int | None = None,
    seed: int | None = None,
    years: float | None = None,
    keep_equity_paths: bool = False,
    require_seed: bool = True,
) -> dict[str, Any]:
    """
    Monte Carlo simulation on a trade R-series.

    - Base mode: IID bootstrap sampling of realized_R
    - Optional: block bootstrap via block_size (captures clustering)

    Returns:
      {
        "summary": {...},
        "samples": DataFrame[path_id, maxDD_pct, cagr, final_equity, blew_up],
        "equity_paths": DataFrame[path_id, step, equity] OR None,
      }
    """
    r = _realized_r(trades)
    n = int(r.size)

    if require_seed and seed is None:
        raise ValueError(
            "seed is required for deterministic Monte Carlo (pass --seed)."
        )
    rng = np.random.default_rng(seed)

    if n_paths <= 0:
        raise ValueError("n_paths must be > 0")
    if n == 0:
        return {
            "summary": {
                "n_trades": 0,
                "n_paths": n_paths,
                "risk_per_trade": float(risk_per_trade),
                "block_size": block_size,
                "years": years,
                "blowup_rate": 0.0,
                "median_cagr": 0.0,
                "maxDD_pct_p05": 0.0,
                "maxDD_pct_p50": 0.0,
                "maxDD_pct_p95": 0.0,
            },
            "samples": pd.DataFrame(
                columns=["path_id", "maxDD_pct", "cagr", "final_equity", "blew_up"]
            ),
            "equity_paths": None,
        }

    if years is None:
        years = _infer_years_from_trades(trades)
    if years is None:
        raise ValueError(
            "Could not infer years from trades; pass years= explicitly (or include entry_time/exit_time)."
        )
    if years <= 0.0:
        raise ValueError("years must be > 0")

    rows: list[dict[str, Any]] = []
    equity_paths = []  # list[DataFrame] only if keep_equity_paths

    for pid in range(n_paths):
        if block_size is None:
            idx = _iid_bootstrap_indices(rng, n)
        else:
            idx = _block_bootstrap_indices(rng, n, int(block_size))

        r_path = r[idx]
        stats = path_stats_from_r(r_path, risk_per_trade=risk_per_trade, years=years)

        rows.append(
            {
                "path_id": pid,
                "maxDD_pct": stats.maxdd_pct,
                "cagr": stats.cagr,
                "final_equity": stats.final_equity,
                "blew_up": stats.blew_up,
            }
        )

        if keep_equity_paths:
            # store full equity curve for plotting later
            # (equity length = n_trades + 1)
            from .portfolio import (
                equity_curve_from_r,
            )  # local import to keep module tidy

            eq = equity_curve_from_r(r_path, risk_per_trade=risk_per_trade)
            equity_paths.append(
                pd.DataFrame(
                    {
                        "path_id": pid,
                        "step": np.arange(eq.size, dtype=int),
                        "equity": eq,
                    }
                )
            )

    samples = pd.DataFrame(rows)

    dd = samples["maxDD_pct"]
    cagr_s = samples["cagr"]
    blowup_rate = float(samples["blew_up"].mean()) if len(samples) else 0.0

    summary = {
        "n_trades": n,
        "n_paths": int(n_paths),
        "risk_per_trade": float(risk_per_trade),
        "block_size": block_size,
        "seed": seed,
        "years": float(years),
        "blowup_rate": blowup_rate,
        "median_cagr": float(cagr_s.quantile(0.50, interpolation="linear")),
        "maxDD_pct_p05": float(dd.quantile(0.05, interpolation="linear")),
        "maxDD_pct_p50": float(dd.quantile(0.50, interpolation="linear")),
        "maxDD_pct_p95": float(dd.quantile(0.95, interpolation="linear")),
    }

    eq_df = None
    if keep_equity_paths and equity_paths:
        eq_df = pd.concat(equity_paths, ignore_index=True)

    return {"summary": summary, "samples": samples, "equity_paths": eq_df}
