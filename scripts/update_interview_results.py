from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _fmt(summary: Dict[str, Any], keys: list[str]) -> str:
    lines = []
    for k in keys:
        if k not in summary:
            continue
        v = summary[k]
        if isinstance(v, float):
            lines.append(f"- **{k}**: `{v:.6g}`")
        else:
            lines.append(f"- **{k}**: `{v}`")
    return "\n".join(lines) if lines else "_(no keys found)_"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest-run", required=True, help="outputs/backtest/<run_id>")
    ap.add_argument(
        "--walkforward-run", required=True, help="outputs/walkforward/<run_id>"
    )
    ap.add_argument("--mc-run", required=True, help="outputs/monte-carlo/<run_id>")
    ap.add_argument("--out", default="docs/interview/RESULTS.md")
    ap.add_argument(
        "--label",
        default="Quickstart (synthetic 3-day)",
        help="Label for this representative run",
    )
    args = ap.parse_args()

    bt = Path(args.backtest_run).resolve()
    wf = Path(args.walkforward_run).resolve()
    mc = Path(args.mc_run).resolve()
    out = Path(args.out).resolve()

    bt_meta = _read_json(bt / "run_meta.json")
    bt_sum = _read_json(bt / "summary.json")

    wf_meta = _read_json(wf / "run_meta.json")
    wf_sum = _read_json(wf / "summary.json")

    mc_meta = _read_json(mc / "run_meta.json")
    mc_sum = _read_json(mc / "summary.json")

    md = []
    md.append("# Meridian — Results (1-pager)\n")
    md.append("## Representative run\n")
    md.append(f"- **Label**: `{args.label}`")
    md.append(f"- **Config**: `{bt_meta.get('config')}`")
    md.append(f"- **Data**: `{bt_meta.get('data', '<n/a>')}`")
    md.append(
        f"- **Date range**: `{bt_meta.get('date_from')}` → `{bt_meta.get('date_to')}`"
    )
    md.append("- **Run IDs**:")
    md.append(f"  - Backtest: `{bt_meta.get('run_id', bt.name)}`")
    md.append(f"  - Walkforward: `{wf_meta.get('run_id', wf.name)}`")
    md.append(f"  - Monte Carlo: `{mc_meta.get('run_id', mc.name)}`")
    md.append("")

    md.append("## Headline stats (Backtest)\n")
    md.append(
        _fmt(
            bt_sum,
            [
                "trades",
                "win_rate",
                "expectancy_R",
                "avg_R",
                "maxDD_R",
                "SQN",
                "trades_per_month",
                "sum_R",
            ],
        )
    )
    md.append("")

    md.append("## Walk-forward (OOS overall)\n")
    md.append(
        _fmt(
            wf_sum,
            [
                "trades",
                "win_rate",
                "expectancy_R",
                "avg_R",
                "maxDD_R",
                "SQN",
                "trades_per_month",
                "sum_R",
            ],
        )
    )
    md.append("")

    md.append("## Monte Carlo (bootstrap on realized_R)\n")
    md.append(
        _fmt(
            mc_sum,
            [
                "n_trades",
                "n_paths",
                "block_size",
                "risk_per_trade",
                "years",
                "blowup_rate",
                "median_cagr",
                "maxDD_pct_p05",
                "maxDD_pct_p50",
                "maxDD_pct_p95",
            ],
        )
    )
    md.append("")

    md.append("## Reproducibility\n")
    md.append("- Deterministic seeds recorded in `run_meta.json`.")
    md.append(
        "- Outputs contract: `outputs/<cmd>/<run_id>/` contains `run_meta.json`, `summary.json`, and artifacts."
    )
    md.append("")

    md.append("## Notes / caveats\n")
    md.append(
        "- This 1-pager is a *representative run summary*, not a guarantee of future performance."
    )
    md.append(
        "- Walk-forward freezes IS parameters before OOS evaluation (no parameter bleed)."
    )
    md.append(
        "- Monte Carlo reflects bootstrap assumptions (IID/block). Interpret distributions, not point estimates."
    )
    md.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
