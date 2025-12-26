"""
Script: Strategy Report Generator
Purpose: Compiles raw run artifacts into a professional Markdown report.

Description:
    Ingests `run_meta.json` and `summary.json` from Backtest, Walk-Forward, or
    Monte Carlo runs. Generates a 'STRATEGY_RESULTS.md' file suitable for
    documentation or stakeholder review.

Usage:
    python scripts/make_report.py --run outputs/backtest/run_01 --out docs/system/STRATEGY_RESULTS.md
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class RunKind:
    name: str


BACKTEST = RunKind("backtest")
WALKFORWARD = RunKind("walkforward")
MONTE_CARLO = RunKind("monte-carlo")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def detect_run_kind(run_dir: Path) -> RunKind:
    if (run_dir / "wf_equity.parquet").exists() or (
        run_dir / "oos_summary.csv"
    ).exists():
        return WALKFORWARD
    if (run_dir / "mc_samples.parquet").exists() or (
        run_dir / "mc_samples.csv"
    ).exists():
        return MONTE_CARLO
    if (run_dir / "trades.parquet").exists() or (run_dir / "trades.csv").exists():
        return BACKTEST
    # Fallback/Default to Backtest if mostly empty (smoke test)
    return BACKTEST


def _make_md_table(
    data: Dict[str, Any], headers: list[str] = ["Metric", "Value", "Notes"]
) -> str:
    """Creates a clean Markdown table from a dictionary of metrics."""
    lines = []
    lines.append(f"| {' | '.join(headers)} |")
    lines.append(f"| {' | '.join(['---'] * len(headers))} |")

    for k, v in data.items():
        if isinstance(v, float):
            val_str = f"`{v:.4g}`"
        else:
            val_str = f"`{v}`"

        # Simple heuristic for notes
        note = ""
        if k == "win_rate":
            note = "Target > 40%"
        if k == "SQN":
            note = "System Quality Number"
        if k == "expectancy_R":
            note = "Risk-adjusted return"

        lines.append(f"| **{k}** | {val_str} | {note} |")

    return "\n".join(lines)


def _headline_stats_dict(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts only high-level KPIs for the table."""
    # Priority keys for the table
    wanted = [
        "trades",
        "win_rate",
        "expectancy_R",
        "avg_R",
        "maxDD_R",
        "SQN",
        "sharpe",
        "sortino",
    ]
    return {k: summary[k] for k in wanted if k in summary}


def _mc_stats_dict(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts Monte Carlo specific stats."""
    wanted = [
        "n_paths",
        "risk_per_trade",
        "blowup_rate",
        "median_cagr",
        "maxDD_pct_p95",
        "maxDD_pct_p50",
    ]
    return {k: summary[k] for k in wanted if k in summary}


def write_report(run_dir: Path, out_path: Path) -> None:
    kind = detect_run_kind(run_dir)

    meta_path = run_dir / "run_meta.json"
    sum_path = run_dir / "summary.json"

    # Graceful handling if files missing (e.g. crashed run)
    if not meta_path.exists() or not sum_path.exists():
        print(f"[WARN] Missing meta/summary in {run_dir}. Generating skeleton report.")
        meta = {}
        summary = {}
    else:
        meta = _read_json(meta_path)
        summary = _read_json(sum_path)

    run_id = meta.get("run_id") or run_dir.name

    # Detect "Smoke Test" status (0 trades)
    is_smoke_test = summary.get("trades", 0) == 0

    md = []
    md.append("# Meridian — Strategy Validation Results\n")

    # 1. Executive Summary
    md.append("## 1. Executive Summary (Representative Run)\n")
    md.append(
        "This document serves as the **Integrity Validation Report** for the Meridian execution engine."
    )

    if is_smoke_test:
        md.append(
            "The current run represents a **Technical Verification (Smoke Test)** using synthetic or limited data to confirm pipeline stability, event processing, and reporting artifacts.\n"
        )
    else:
        md.append(
            "The current run represents a **Strategy Performance Validation** cycle evaluating the core logic against historical market data.\n"
        )

    md.append(f"* **Run Label**: `{run_id}`")
    md.append(
        f"* **Date Range**: `{meta.get('date_from', 'N/A')}` → `{meta.get('date_to', 'N/A')}`"
    )
    md.append(f"* **Data Source**: `{meta.get('data', 'N/A')}`")
    md.append("")

    # 2. Headline Stats
    md.append("## 2. Headline Performance Stats (Backtest)\n")
    if is_smoke_test:
        md.append(
            "> *Note: Zero values are expected for synthetic smoke tests or uncalibrated parameters.*\n"
        )

    stats = _headline_stats_dict(summary)
    if stats:
        md.append(_make_md_table(stats))
    else:
        md.append("_(No headline stats found in summary.json)_")
    md.append("")

    # 3. Walk-Forward (Conditional)
    if kind is WALKFORWARD:
        md.append("## 3. Walk-Forward Analysis (OOS)\n")
        md.append(
            "The Walk-Forward engine prevents overfitting by enforcing a strict separation between In-Sample (IS) optimization and Out-of-Sample (OOS) verification.\n"
        )

        oos_stats = {
            k: v for k, v in summary.items() if "oos_" in k or "expected_" in k
        }
        if oos_stats:
            md.append(_make_md_table(oos_stats))
        else:
            md.append("_(No OOS stats found)_")
        md.append("")

    # 4. Monte Carlo (Conditional)
    if kind is MONTE_CARLO:
        md.append("## 4. Monte Carlo Simulation (Bootstrap)\n")
        md.append(
            "To stress-test the system against sequence risk, we employ a block-bootstrap resampling method on realized R-multiples.\n"
        )
        mc_stats = _mc_stats_dict(summary)
        md.append(_make_md_table(mc_stats))
        md.append("")

    # 5. Reproducibility
    md.append("## 5. Reproducibility Contract\n")
    md.append(
        "Meridian guarantees full reproducibility of any result via the following artifacts:\n"
    )
    md.append("* **Config Snapshot**: stored in `run_meta.json`.")
    md.append(
        f"* **Deterministic Seeding**: Seed `{meta.get('seed', 'N/A')}` used for randomization."
    )
    md.append(f"* **Artifact Location**: `outputs/{kind.name}/{run_id}`")
    md.append("")

    md.append("---\n")
    md.append(
        "> **Disclaimer:** These results are generated programmatically. Past performance is not indicative of future results."
    )

    _safe_mkdir(out_path.parent)
    out_path.write_text("\n".join(md).strip() + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate a Professional Strategy Report from run outputs."
    )
    ap.add_argument(
        "--run",
        required=True,
        help="Path to a run folder, e.g. outputs/backtest/<run_id>",
    )
    # UPDATED DEFAULT: Points to the new System Documentation standard
    ap.add_argument(
        "--out",
        default="docs/system/STRATEGY_RESULTS.md",
        help="Output markdown path. Defaults to 'docs/system/STRATEGY_RESULTS.md'.",
    )
    args = ap.parse_args()

    run_dir = Path(args.run).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()

    write_report(run_dir, out_path)
    print(f"[SUCCESS] Strategy Report generated at: {out_path}")


if __name__ == "__main__":
    main()
