"""
Script: Strategy Report Generator (Consolidated)
Purpose: Compiles Backtest + Walkforward + Monte Carlo + Profile artifacts
         into a professional Markdown report.

Inputs:
  - Backtest run dir: must contain run_meta.json + summary.json (and typically trades.parquet)
  - Walkforward run dir: run_meta.json + summary.json; optionally oos_summary.csv
  - Monte Carlo run dir: run_meta.json + summary.json
  - Profile timing JSON(s): produced by scripts/profile_run.py (*.timing.json)

Output:
  - docs/system/STRATEGY_RESULTS.md (default)

Example:
  python scripts/make_report.py
    --label v1_0_6_baseline
    --backtest outputs/backtest/v1_0_6_backtest_baseline
    --walkforward outputs/walkforward/v1_0_6_walkforward_baseline
    --monte-carlo outputs/monte-carlo/v1_0_6_montecarlo_baseline
    --profile outputs/profiles/v1_0_6_baseline/backtest.timing.json
    --profile outputs/profiles/v1_0_6_baseline/walkforward.timing.json
    --profile outputs/profiles/v1_0_6_baseline/monte_carlo.timing.json
    --out docs/system/STRATEGY_RESULTS.md
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

# ----------------------------
# Helpers
# ----------------------------

JSONDict = Dict[str, Any]


def _read_json(path: Path) -> JSONDict:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _rel(p: Path) -> str:
    """
    Try to print a nice repo-relative path, but fall back to absolute.
    """
    try:
        return p.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except Exception:
        return p.resolve().as_posix()


def _fmt(v: Any) -> str:
    if v is None:
        return "`N/A`"
    if isinstance(v, float):
        # stable, compact formatting
        return f"`{v:.4g}`"
    return f"`{v}`"


def _make_md_table(rows: Iterable[tuple[str, Any, str]], headers: list[str]) -> str:
    lines: list[str] = []
    lines.append(f"| {' | '.join(headers)} |")
    lines.append(f"| {' | '.join(['---'] * len(headers))} |")
    for metric, value, note in rows:
        lines.append(f"| **{metric}** | {_fmt(value)} | {note} |")
    return "\n".join(lines)


def _get_any(d: JSONDict, keys: list[str], default: Any = None) -> Any:
    for k in keys:
        if k in d:
            return d[k]
    return default


def _read_run_artifacts(run_dir: Path) -> tuple[JSONDict, JSONDict]:
    meta_path = run_dir / "run_meta.json"
    sum_path = run_dir / "summary.json"
    meta = _read_json(meta_path) if meta_path.exists() else {}
    summary = _read_json(sum_path) if sum_path.exists() else {}
    return meta, summary


def _read_oos_summary_csv(run_dir: Path) -> JSONDict:
    """
    Optional: parse oos_summary.csv into a dict (first row).
    We keep this intentionally simple and robust.
    """
    p = run_dir / "oos_summary.csv"
    if not p.exists():
        return {}

    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader, None)
        if row is None:
            return {}

    out: JSONDict = {}
    for k, v in row.items():
        if v is None or v == "":
            continue
        # attempt numeric coercion
        try:
            if "." in v or "e" in v.lower():
                out[k] = float(v)
            else:
                out[k] = int(v)
        except Exception:
            out[k] = v
    return out


# ----------------------------
# Metric extraction
# ----------------------------


@dataclass(frozen=True)
class BacktestMetrics:
    total_trades: Any
    win_rate: Any
    expectancy_r: Any
    avg_r: Any
    avg_win_r: Any
    avg_loss_r: Any
    maxdd_r: Any
    sqn: Any
    sharpe: Any
    sortino: Any


def _extract_backtest_metrics(summary: JSONDict) -> BacktestMetrics:
    return BacktestMetrics(
        total_trades=_get_any(summary, ["trades", "total_trades", "n_trades"], 0),
        win_rate=_get_any(summary, ["win_rate"], None),
        expectancy_r=_get_any(summary, ["expectancy_R", "expectancy_r"], None),
        avg_r=_get_any(summary, ["avg_R", "avg_r"], None),
        avg_win_r=_get_any(summary, ["avg_win_R", "avg_win_r", "avg_win"], None),
        avg_loss_r=_get_any(summary, ["avg_loss_R", "avg_loss_r", "avg_loss"], None),
        maxdd_r=_get_any(summary, ["maxDD_R", "max_dd_R", "max_drawdown_R"], None),
        sqn=_get_any(summary, ["SQN", "sqn"], None),
        sharpe=_get_any(summary, ["sharpe"], None),
        sortino=_get_any(summary, ["sortino"], None),
    )


def _extract_wfo_metrics(summary: JSONDict, oos_csv: JSONDict) -> JSONDict:
    """
    Prefer explicit OOS keys in summary.json.
    If not present, fall back to oos_summary.csv.
    """
    oos = {k: v for k, v in summary.items() if k.lower().startswith("oos_")}
    if oos:
        return oos
    # fallback: try CSV fields
    return oos_csv


def _extract_mc_metrics(summary: JSONDict) -> JSONDict:
    wanted = [
        "n_paths",
        "risk_per_trade",
        "blowup_rate",
        "median_cagr",
        "maxDD_pct_p95",
        "maxDD_pct_p50",
    ]
    out: JSONDict = {}
    for k in wanted:
        if k in summary:
            out[k] = summary[k]
    # allow common alternates
    alt_map = {
        "n_paths": ["paths", "iterations"],
        "median_cagr": ["cagr_median"],
        "blowup_rate": ["risk_of_ruin", "ruin_rate"],
        "maxDD_pct_p95": ["max_dd_pct_p95", "maxdd_pct_p95"],
        "maxDD_pct_p50": ["max_dd_pct_p50", "maxdd_pct_p50"],
    }
    for std_k, alts in alt_map.items():
        if std_k not in out:
            v = _get_any(summary, alts, None)
            if v is not None:
                out[std_k] = v
    return out


def _read_profile_timing(path: Path) -> Optional[JSONDict]:
    if not path.exists():
        return None
    try:
        j = _read_json(path)
    except Exception:
        return None
    if "seconds" not in j:
        return None
    return j


# ----------------------------
# Report writer
# ----------------------------


def write_report(
    *,
    label: str,
    out_path: Path,
    backtest_dir: Optional[Path],
    walkforward_dir: Optional[Path],
    monte_carlo_dir: Optional[Path],
    profile_timings: list[Path],
) -> None:
    md: list[str] = []
    md.append("# Meridian — Strategy Validation Results\n")

    # 1) Summary
    md.append(f"## 1. Summary ({label})\n")
    md.append(
        "This document contains the **Audited Performance Report** for the Meridian execution engine.\n"
        "It is generated programmatically from run artifacts (`run_meta.json`, `summary.json`) and optional profiler timing outputs.\n"
    )

    # Backtest meta as the “representative” metadata source
    rep_meta: JSONDict = {}
    rep_sum: JSONDict = {}
    if backtest_dir is not None:
        rep_meta, rep_sum = _read_run_artifacts(backtest_dir)

    run_label = _get_any(rep_meta, ["run_id"], label)
    data_src = _get_any(rep_meta, ["data", "data_path", "dataset"], "N/A")
    integrity = _get_any(rep_meta, ["integrity_status"], "N/A")
    seed = _get_any(rep_meta, ["seed"], "N/A")

    md.append(f"* **Run Label**: `{run_label}`")
    md.append(f"* **Data Source**: `{data_src}`")
    if integrity != "N/A":
        md.append(f"* **Integrity Status**: **{integrity}**")
    md.append("")

    # 2) Backtest stats
    md.append("## 2. Headline Performance Stats (Backtest)\n")

    if backtest_dir is None:
        md.append("_(Backtest run not provided.)_\n")
    else:
        _, bt_summary = _read_run_artifacts(backtest_dir)
        bt = _extract_backtest_metrics(bt_summary)

        rows = [
            ("Total Trades", bt.total_trades, ""),
            ("Win Rate", bt.win_rate, "Target > 40%"),
            ("Expectancy (R)", bt.expectancy_r, "Risk-adjusted return per trade"),
            ("Avg R", bt.avg_r, ""),
            ("Avg Win", bt.avg_win_r, ""),
            ("Avg Loss", bt.avg_loss_r, ""),
            ("Max Drawdown (R)", bt.maxdd_r, ""),
            ("SQN", bt.sqn, "System Quality Number"),
        ]

        # optional rows if present
        if bt.sharpe is not None:
            rows.append(("Sharpe", bt.sharpe, "Optional (interpret cautiously)"))
        if bt.sortino is not None:
            rows.append(("Sortino", bt.sortino, "Optional (interpret cautiously)"))

        md.append(_make_md_table(rows, headers=["Metric", "Value", "Description"]))
        md.append("")

    # 3) Walk-forward
    md.append("## 3. Walk-Forward Analysis (Robustness)\n")
    md.append(
        "The Walk-Forward engine prevents overfitting by enforcing a strict separation between "
        "In-Sample (IS) calibration and Out-of-Sample (OOS) verification.\n"
    )

    if walkforward_dir is None:
        md.append("_(Walk-forward run not provided.)_\n")
    else:
        wf_meta, wf_summary = _read_run_artifacts(walkforward_dir)
        oos_csv = _read_oos_summary_csv(walkforward_dir)
        oos = _extract_wfo_metrics(wf_summary, oos_csv)

        is_days = _get_any(wf_meta, ["is_days"], "N/A")
        oos_days = _get_any(wf_meta, ["oos_days"], "N/A")
        if is_days != "N/A" or oos_days != "N/A":
            md.append(f"* **Window**: `{is_days}` Days IS / `{oos_days}` Days OOS.\n")

        if not oos:
            md.append("_(No OOS stats found in summary.json or oos_summary.csv.)_\n")
        else:
            rows = []
            for k in sorted(oos.keys()):
                rows.append((k, oos[k], ""))
            md.append(
                _make_md_table(rows, headers=["Metric", "Value", "Interpretation"])
            )
            md.append("")

    # 4) Monte Carlo
    md.append("## 4. Monte Carlo Simulation (Risk Assessment)\n")
    md.append(
        "Stress-testing sequence risk using block-bootstrap resampling on realized R-multiples.\n"
    )

    if monte_carlo_dir is None:
        md.append("_(Monte Carlo run not provided.)_\n")
    else:
        mc_meta, mc_summary = _read_run_artifacts(monte_carlo_dir)
        mc = _extract_mc_metrics(mc_summary)

        n_paths = _get_any(mc_summary, ["n_paths", "paths", "iterations"], "N/A")
        risk_pt = _get_any(mc_summary, ["risk_per_trade"], "N/A")
        mc_seed = _get_any(mc_meta, ["seed"], seed)

        md.append(f"* **Iterations**: `{n_paths}` paths")
        md.append(f"* **Seed**: `{mc_seed}`")
        md.append(f"* **Risk Per Trade**: `{risk_pt}`")
        md.append("")

        if not mc:
            md.append("_(No MC stats found in summary.json.)_\n")
        else:
            rows = []
            for k in mc.keys():
                rows.append((k, mc[k], ""))
            md.append(
                _make_md_table(rows, headers=["Risk Metric", "Value", "Interpretation"])
            )
            md.append("")

    # 4.5) Performance profile
    if profile_timings:
        md.append("## 4.5 Performance Profile (Reference Machine)\n")
        rows = []
        for p in profile_timings:
            j = _read_profile_timing(p)
            if not j:
                continue
            argv = j.get("argv", [])
            cmd = " ".join(str(x) for x in argv[:6]) + (" ..." if len(argv) > 6 else "")
            rows.append((_rel(p), float(j["seconds"]), cmd))

        if rows:
            md.append(
                _make_md_table(
                    rows, headers=["Timing File", "Seconds", "Command (truncated)"]
                )
            )
            md.append("")
        else:
            md.append("_(No valid *.timing.json files found.)_\n")

    # 5) Reproducibility
    md.append("## 5. Reproducibility Contract\n")
    md.append(
        "Meridian guarantees reproducibility of reported results via immutable inputs and recorded metadata:\n"
    )
    md.append("* **Config Snapshot**: stored in `run_meta.json`.")
    md.append(
        f"* **Deterministic Seeding**: Seed `{seed}` for baseline runs (unless overridden per module)."
    )

    if backtest_dir is not None:
        md.append(f"* **Backtest Artifacts**: `{_rel(backtest_dir)}`")
    if walkforward_dir is not None:
        md.append(f"* **Walkforward Artifacts**: `{_rel(walkforward_dir)}`")
    if monte_carlo_dir is not None:
        md.append(f"* **Monte Carlo Artifacts**: `{_rel(monte_carlo_dir)}`")

    md.append("")
    md.append(
        "> **Disclaimer:** Past performance is not indicative of future results.\n"
    )

    _safe_mkdir(out_path.parent)
    out_path.write_text("\n".join(md).strip() + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate consolidated strategy report from run outputs."
    )
    ap.add_argument(
        "--label",
        required=True,
        help="Human label for the baseline (e.g., v1_0_5_baseline)",
    )
    ap.add_argument(
        "--backtest",
        help="Path to backtest run dir (contains run_meta.json, summary.json)",
    )
    ap.add_argument(
        "--walkforward",
        help="Path to walkforward run dir (contains run_meta.json, summary.json)",
    )
    ap.add_argument(
        "--monte-carlo",
        dest="monte_carlo",
        help="Path to monte-carlo run dir (contains run_meta.json, summary.json)",
    )
    ap.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Path to *.timing.json from profile_run.py (repeatable)",
    )
    ap.add_argument(
        "--out", default="docs/system/STRATEGY_RESULTS.md", help="Output markdown path"
    )
    args = ap.parse_args()

    out_path = Path(args.out).expanduser().resolve()
    bt = Path(args.backtest).expanduser().resolve() if args.backtest else None
    wf = Path(args.walkforward).expanduser().resolve() if args.walkforward else None
    mc = Path(args.monte_carlo).expanduser().resolve() if args.monte_carlo else None
    profs = [Path(p).expanduser().resolve() for p in args.profile]

    write_report(
        label=args.label,
        out_path=out_path,
        backtest_dir=bt,
        walkforward_dir=wf,
        monte_carlo_dir=mc,
        profile_timings=profs,
    )
    print(f"[SUCCESS] Strategy Report generated at: {out_path}")


if __name__ == "__main__":
    main()
