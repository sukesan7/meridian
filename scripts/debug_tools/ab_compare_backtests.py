"""
AB Compare Backtests
-------------------
Compares two Meridian backtest artifacts (Run A vs Run B) and answers:

- How many trades overlap vs are unique?
- Did common trades change entry/exit/R materially?
- Are the "new-only" trades low quality (avg R / win-rate)?

Usage:
  python scripts/debug_tools/ab_compare_backtests.py ^
    --a outputs/backtest/v1_0_5_backtest_baseline ^
    --b outputs/backtest/v1_0_6_backtest_baseline ^
    --out outputs/ab_compare/v1_0_5_vs_v1_0_6

You can also pass trades files directly:
  --a path/to/trades.parquet --b path/to/trades.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

# ---------------- IO helpers ----------------


def _read_json(p: Path) -> dict[str, Any] | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _resolve_trades_path(p: Path) -> Path:
    """
    Accept either:
      - a run directory containing trades.parquet or trades.csv
      - a direct file path to trades.parquet/csv
    """
    if p.is_file():
        return p

    if not p.exists():
        raise FileNotFoundError(str(p))

    # directory
    cand_parq = p / "trades.parquet"
    cand_csv = p / "trades.csv"
    if cand_parq.exists():
        return cand_parq
    if cand_csv.exists():
        return cand_csv

    raise FileNotFoundError(f"No trades.parquet or trades.csv found under: {p}")


def _read_trades(p: Path) -> pd.DataFrame:
    suf = p.suffix.lower()
    if suf == ".parquet":
        return pd.read_parquet(p)
    if suf == ".csv":
        # CSVs may lose dtypes; we normalize below
        return pd.read_csv(p)
    raise ValueError(f"Unsupported trades file type: {suf}")


# ---------------- Normalization ----------------

_TIME_COL_CANDIDATES = [
    "signal_time",
    "entry_time",
    "exit_time",
    "fill_time",
    "ts_signal",
    "ts_entry",
    "ts_exit",
]

_R_COL_CANDIDATES = ["realized_R", "R", "r", "pnl_R", "pnl_r"]

_SIDE_COL_CANDIDATES = ["side", "direction", "dir", "side_lit"]


def _pick_first_existing(cols: Iterable[str], df_cols: Iterable[str]) -> str | None:
    s = set(df_cols)
    for c in cols:
        if c in s:
            return c
    return None


def _coerce_dt(s: pd.Series) -> pd.Series:
    # robust datetime parsing; works with tz-aware and tz-naive strings
    return pd.to_datetime(s, errors="coerce", utc=False)


def _normalize_trades(df: pd.DataFrame) -> tuple[pd.DataFrame, str, str, str]:
    """
    Returns:
      (normalized_df, time_key_col, r_col, side_col)
    Normalization goals:
      - ensure the key time column is datetime64[ns] (tz-aware okay)
      - ensure R column is float
      - ensure side is a stable string ("long"/"short"/"flat")
    """
    if df is None or df.empty:
        raise ValueError("Trades DF is empty")

    time_key_col = _pick_first_existing(_TIME_COL_CANDIDATES, df.columns)
    if time_key_col is None:
        raise KeyError(
            f"Could not find a time column in trades. Tried: {_TIME_COL_CANDIDATES}"
        )

    r_col = _pick_first_existing(_R_COL_CANDIDATES, df.columns)
    if r_col is None:
        raise KeyError(
            f"Could not find an R column in trades. Tried: {_R_COL_CANDIDATES}"
        )

    side_col = _pick_first_existing(_SIDE_COL_CANDIDATES, df.columns)
    if side_col is None:
        raise KeyError(
            f"Could not find a side/direction column. Tried: {_SIDE_COL_CANDIDATES}"
        )

    out = df.copy()

    # Datetime normalize
    out[time_key_col] = _coerce_dt(out[time_key_col])
    if out[time_key_col].isna().any():
        # keep rows but warn later; for joining we need non-null keys
        pass

    # R normalize
    out[r_col] = pd.to_numeric(out[r_col], errors="coerce").astype(float)

    # Side normalize
    if side_col == "direction" or side_col == "dir":
        # numeric direction: >0 long, <0 short, 0 flat
        d = pd.to_numeric(out[side_col], errors="coerce").fillna(0.0)
        out["_side"] = d.apply(
            lambda x: "long" if x > 0 else ("short" if x < 0 else "flat")
        )
    else:
        s = out[side_col].astype(str).str.lower()
        # accept "long"/"short" or similar tokens
        out["_side"] = s.apply(
            lambda x: "long" if "long" in x else ("short" if "short" in x else x)
        )

    return out, time_key_col, r_col, "_side"


def _make_key(df: pd.DataFrame, time_col: str, side_col: str) -> pd.Series:
    # Use ISO-like string to avoid tz comparison pitfalls across versions.
    t = df[time_col]
    t_str = t.dt.strftime("%Y-%m-%d %H:%M:%S%z").fillna("NA_TIME")
    return t_str + "|" + df[side_col].astype(str)


# ---------------- Metrics ----------------


def _basic_metrics(df: pd.DataFrame, r_col: str) -> dict[str, Any]:
    if df.empty:
        return {"n": 0, "win_rate": None, "avg_R": None, "sum_R": 0.0}

    r = df[r_col].astype(float)
    wins = (r > 0).sum()
    n = len(df)
    return {
        "n": n,
        "win_rate": float(wins / n),
        "avg_R": float(r.mean()),
        "median_R": float(r.median()),
        "sum_R": float(r.sum()),
        "p25_R": float(r.quantile(0.25)),
        "p75_R": float(r.quantile(0.75)),
    }


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "NA"
    return f"{100.0 * x:.2f}%"


def _fmt_num(x: float | None) -> str:
    if x is None:
        return "NA"
    return f"{x:.4f}"


def _print_block(title: str, m: dict[str, Any]) -> None:
    print(f"\n== {title} ==")
    print(f"n        : {m.get('n')}")
    print(f"win_rate : {_fmt_pct(m.get('win_rate'))}")
    print(f"avg_R    : {_fmt_num(m.get('avg_R'))}")
    print(f"median_R : {_fmt_num(m.get('median_R'))}")
    print(f"sum_R    : {_fmt_num(m.get('sum_R'))}")
    print(f"p25/p75  : {_fmt_num(m.get('p25_R'))} / {_fmt_num(m.get('p75_R'))}")


# ---------------- Main compare ----------------


def compare(a_path: Path, b_path: Path, out_dir: Path | None, key_col_name: str) -> int:
    a_trades_path = _resolve_trades_path(a_path)
    b_trades_path = _resolve_trades_path(b_path)

    # If user passed run directories, try to read meta
    a_run_dir = a_path if a_path.is_dir() else a_trades_path.parent
    b_run_dir = b_path if b_path.is_dir() else b_trades_path.parent

    a_meta = _read_json(a_run_dir / "run_meta.json")
    b_meta = _read_json(b_run_dir / "run_meta.json")

    print("AB Compare:")
    print(f"  A trades: {a_trades_path}")
    print(f"  B trades: {b_trades_path}")
    if a_meta:
        print(f"  A run_id: {a_meta.get('run_id', 'NA')}")
        print(f"  A git   : {a_meta.get('git_sha', a_meta.get('git', 'NA'))}")
    if b_meta:
        print(f"  B run_id: {b_meta.get('run_id', 'NA')}")
        print(f"  B git   : {b_meta.get('git_sha', b_meta.get('git', 'NA'))}")

    a_raw = _read_trades(a_trades_path)
    b_raw = _read_trades(b_trades_path)

    a_df, a_time_col, a_r_col, a_side_col = _normalize_trades(a_raw)
    b_df, b_time_col, b_r_col, b_side_col = _normalize_trades(b_raw)

    # Choose which time column to key on (signal_time vs entry_time etc.)
    # If key_col_name not present, fall back to the detected time column.
    if key_col_name in a_df.columns:
        a_time = key_col_name
    else:
        a_time = a_time_col

    if key_col_name in b_df.columns:
        b_time = key_col_name
    else:
        b_time = b_time_col

    a_df["_key"] = _make_key(a_df, a_time, a_side_col)
    b_df["_key"] = _make_key(b_df, b_time, b_side_col)

    # Drop rows with NA time keys; they can't be reliably joined
    a_df = a_df[a_df["_key"].str.startswith("NA_TIME").eq(False)].copy()
    b_df = b_df[b_df["_key"].str.startswith("NA_TIME").eq(False)].copy()

    a_keys = set(a_df["_key"].tolist())
    b_keys = set(b_df["_key"].tolist())

    common = sorted(a_keys & b_keys)
    only_a = sorted(a_keys - b_keys)
    only_b = sorted(b_keys - a_keys)

    a_only_df = a_df[a_df["_key"].isin(only_a)].copy()
    b_only_df = b_df[b_df["_key"].isin(only_b)].copy()

    # Metrics
    _print_block("A (overall)", _basic_metrics(a_df, a_r_col))
    _print_block("B (overall)", _basic_metrics(b_df, b_r_col))
    _print_block(
        "Common trades (A subset)",
        _basic_metrics(a_df[a_df["_key"].isin(common)], a_r_col),
    )
    _print_block(
        "Common trades (B subset)",
        _basic_metrics(b_df[b_df["_key"].isin(common)], b_r_col),
    )
    _print_block("Only-A trades", _basic_metrics(a_only_df, a_r_col))
    _print_block("Only-B trades", _basic_metrics(b_only_df, b_r_col))

    # Join common trades for delta analysis
    a_common = a_df[a_df["_key"].isin(common)].copy()
    b_common = b_df[b_df["_key"].isin(common)].copy()

    # Keep a small set of comparable columns if present
    def _keep_cols(df: pd.DataFrame) -> list[str]:
        base = ["_key", a_r_col if df is a_common else b_r_col]
        for c in [
            "signal_time",
            "entry_time",
            "exit_time",
            "entry_price",
            "exit_price",
            "stop_price",
        ]:
            if c in df.columns:
                base.append(c)
        return list(dict.fromkeys(base))

    a_common_small = a_common[_keep_cols(a_common)].rename(
        columns={a_r_col: "A_realized_R"}
    )
    b_common_small = b_common[_keep_cols(b_common)].rename(
        columns={b_r_col: "B_realized_R"}
    )

    common_join = a_common_small.merge(
        b_common_small, on="_key", how="inner", suffixes=("_A", "_B")
    )
    common_join["delta_R"] = common_join["B_realized_R"].astype(float) - common_join[
        "A_realized_R"
    ].astype(float)

    print("\nOverlap summary:")
    print(f"  common : {len(common)}")
    print(f"  only A : {len(only_a)}")
    print(f"  only B : {len(only_b)}")

    # Write outputs
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        a_only_df.to_csv(out_dir / "only_A.csv", index=False)
        b_only_df.to_csv(out_dir / "only_B.csv", index=False)
        common_join.sort_values("delta_R").to_csv(
            out_dir / "common_delta.csv", index=False
        )

        # also dump a compact json summary
        summary = {
            "a_trades_path": str(a_trades_path),
            "b_trades_path": str(b_trades_path),
            "counts": {
                "common": len(common),
                "only_a": len(only_a),
                "only_b": len(only_b),
            },
            "metrics": {
                "A": _basic_metrics(a_df, a_r_col),
                "B": _basic_metrics(b_df, b_r_col),
                "only_A": _basic_metrics(a_only_df, a_r_col),
                "only_B": _basic_metrics(b_only_df, b_r_col),
            },
        }
        (out_dir / "ab_summary.json").write_text(json.dumps(summary, indent=2))

        print("\nWrote:")
        print(f"  {out_dir / 'only_A.csv'}")
        print(f"  {out_dir / 'only_B.csv'}")
        print(f"  {out_dir / 'common_delta.csv'}")
        print(f"  {out_dir / 'ab_summary.json'}")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="Run A dir or trades.(parquet|csv)")
    ap.add_argument("--b", required=True, help="Run B dir or trades.(parquet|csv)")
    ap.add_argument(
        "--key",
        default="signal_time",
        help="Which timestamp column to key on (default: signal_time). If missing, auto-falls back.",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="Output directory to write only_A/only_B/common_delta CSVs + json summary",
    )
    args = ap.parse_args()

    out_dir = Path(args.out) if args.out else None
    return compare(Path(args.a), Path(args.b), out_dir, args.key)


if __name__ == "__main__":
    raise SystemExit(main())
