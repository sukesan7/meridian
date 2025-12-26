"""
Walk-Forward Engine
-------------------
Implements rolling window analysis (In-Sample / Out-of-Sample).
Ensures zero data leakage between training and testing periods.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

import pandas as pd

from .metrics import summary as metrics_summary


class BacktestFn(Protocol):
    def __call__(
        self,
        df1: pd.DataFrame,
        df5: pd.DataFrame | None,
        cfg: Any | None,
        *,
        params: dict[str, Any] | None,
        regime: str,
        window_id: int,
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class WFWindow:
    window_id: int
    is_sessions: pd.DatetimeIndex
    oos_sessions: pd.DatetimeIndex


def _normalize_sessions_from_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    if df is None or len(df) == 0:
        return pd.DatetimeIndex([])
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("walkforward requires df.index to be a DatetimeIndex")

    idx = df.index
    idx = idx.sort_values()
    sessions = pd.to_datetime(idx).normalize()
    uniq = pd.Index(pd.unique(sessions))
    return pd.DatetimeIndex(uniq)


def _slice_by_sessions(
    df: pd.DataFrame | None, sessions: pd.DatetimeIndex
) -> pd.DataFrame | None:
    if df is None or len(sessions) == 0:
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("walkforward requires df.index to be a DatetimeIndex")
    sess = pd.to_datetime(df.index).normalize()
    mask = sess.isin(sessions)
    return df.loc[mask]


def iter_rolling_windows(
    sessions: pd.DatetimeIndex,
    *,
    is_days: int,
    oos_days: int,
    step: int | None = None,
) -> list[WFWindow]:
    if is_days <= 0 or oos_days <= 0:
        raise ValueError("is_days and oos_days must be > 0")

    n = len(sessions)
    if n == 0:
        return []

    if step is None:
        step = oos_days
    if step <= 0:
        raise ValueError("step must be > 0")

    out: list[WFWindow] = []
    i = 0
    wid = 0
    while i + is_days + oos_days <= n:
        is_s = sessions[i : i + is_days]
        oos_s = sessions[i + is_days : i + is_days + oos_days]
        out.append(WFWindow(window_id=wid, is_sessions=is_s, oos_sessions=oos_s))
        i += step
        wid += 1
    return out


def _timestamp_col(trades: pd.DataFrame) -> str:
    if "exit_time" in trades.columns:
        return "exit_time"
    if "entry_time" in trades.columns:
        return "entry_time"
    return ""


def rolling_walkforward_frames(
    df1: pd.DataFrame,
    df5: pd.DataFrame | None,
    cfg: Any | None,
    *,
    is_days: int = 63,
    oos_days: int = 21,
    step: int | None = None,
    run_backtest_fn: BacktestFn,
    tune_fn: (
        Callable[
            [pd.DataFrame, pd.DataFrame | None, pd.DataFrame, Any | None, int],
            dict[str, Any] | None,
        ]
        | None
    ) = None,
) -> dict[str, pd.DataFrame]:
    if run_backtest_fn is None:
        raise ValueError("run_backtest_fn is required")

    df1 = df1.sort_index()
    sessions = _normalize_sessions_from_index(df1)
    windows = iter_rolling_windows(
        sessions, is_days=is_days, oos_days=oos_days, step=step
    )

    is_rows: list[dict[str, Any]] = []
    oos_rows: list[dict[str, Any]] = []
    is_trades_all: list[pd.DataFrame] = []
    oos_trades_all: list[pd.DataFrame] = []
    equity_parts: list[pd.DataFrame] = []

    for w in windows:
        is_df1 = _slice_by_sessions(df1, w.is_sessions)
        oos_df1 = _slice_by_sessions(df1, w.oos_sessions)

        is_df5 = _slice_by_sessions(df5, w.is_sessions) if df5 is not None else None
        oos_df5 = _slice_by_sessions(df5, w.oos_sessions) if df5 is not None else None

        if is_df1 is not None:
            is_trades = run_backtest_fn(
                is_df1,
                is_df5,
                cfg,
                params=None,
                regime="IS",
                window_id=w.window_id,
            )
            is_trades = is_trades.copy()
            is_trades["window_id"] = w.window_id
            is_trades["regime"] = "IS"
            is_trades_all.append(is_trades)

            frozen_params = None
            if tune_fn is not None:
                frozen_params = tune_fn(is_df1, is_df5, is_trades, cfg, w.window_id)

        if oos_df1 is not None:
            oos_trades = run_backtest_fn(
                oos_df1,
                oos_df5,
                cfg,
                params=frozen_params if "frozen_params" in locals() else None,
                regime="OOS",
                window_id=w.window_id,
            )
            oos_trades = oos_trades.copy()
            oos_trades["window_id"] = w.window_id
            oos_trades["regime"] = "OOS"
            oos_trades_all.append(oos_trades)

            oos_s = metrics_summary(oos_trades)
            oos_s.update(
                {
                    "window_id": w.window_id,
                    "is_start": (
                        str(w.is_sessions.min().date()) if len(w.is_sessions) else ""
                    ),
                    "is_end": (
                        str(w.is_sessions.max().date()) if len(w.is_sessions) else ""
                    ),
                    "oos_start": (
                        str(w.oos_sessions.min().date()) if len(w.oos_sessions) else ""
                    ),
                    "oos_end": (
                        str(w.oos_sessions.max().date()) if len(w.oos_sessions) else ""
                    ),
                }
            )
            oos_rows.append(oos_s)

            if len(oos_trades) > 0 and "realized_R" in oos_trades.columns:
                ts_col = _timestamp_col(oos_trades)
                if ts_col:
                    t = pd.to_datetime(oos_trades[ts_col], errors="coerce")
                else:
                    t = pd.Series([pd.NaT] * len(oos_trades))

                r = pd.to_numeric(oos_trades["realized_R"], errors="coerce").fillna(0.0)
                eq = r.cumsum()

                part = pd.DataFrame(
                    {
                        "timestamp": t,
                        "equity_R": eq,
                        "window_id": w.window_id,
                        "regime": "OOS",
                    }
                )
                equity_parts.append(part)

        if is_df1 is not None and "is_trades" in locals():
            is_s = metrics_summary(is_trades)
            is_s.update(
                {
                    "window_id": w.window_id,
                    "is_start": (
                        str(w.is_sessions.min().date()) if len(w.is_sessions) else ""
                    ),
                    "is_end": (
                        str(w.is_sessions.max().date()) if len(w.is_sessions) else ""
                    ),
                    "oos_start": (
                        str(w.oos_sessions.min().date()) if len(w.oos_sessions) else ""
                    ),
                    "oos_end": (
                        str(w.oos_sessions.max().date()) if len(w.oos_sessions) else ""
                    ),
                }
            )
            is_rows.append(is_s)

    is_summary = pd.DataFrame(is_rows)
    oos_summary = pd.DataFrame(oos_rows)

    wf_equity = pd.DataFrame(columns=["timestamp", "equity_R", "window_id", "regime"])
    if equity_parts:
        wf_equity = pd.concat(equity_parts, ignore_index=True)
        wf_equity = wf_equity.sort_values(
            ["timestamp", "window_id"], kind="mergesort"
        ).reset_index(drop=True)

    is_trades_df = (
        pd.concat(is_trades_all, ignore_index=True) if is_trades_all else pd.DataFrame()
    )
    oos_trades_df = (
        pd.concat(oos_trades_all, ignore_index=True)
        if oos_trades_all
        else pd.DataFrame()
    )

    return {
        "is_summary": is_summary,
        "oos_summary": oos_summary,
        "wf_equity": wf_equity,
        "is_trades": is_trades_df,
        "oos_trades": oos_trades_df,
    }
