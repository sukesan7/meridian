from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import pandas as pd


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
    raise FileNotFoundError(
        f"Could not detect run type in {run_dir}. Expected backtest/walkforward/monte-carlo artifacts."
    )


def _fmt_kv(d: Dict[str, Any], keys: list[str]) -> str:
    out = []
    for k in keys:
        if k in d and d[k] is not None:
            out.append(f"- **{k}**: `{d[k]}`")
    return "\n".join(out) if out else "_(none)_"


def _headline_stats_block(summary: Dict[str, Any]) -> str:
    # Common keys across commands
    keys = [
        "trades",
        "win_rate",
        "avg_R",
        "expectancy_R",
        "avg_win_R",
        "avg_loss_R",
        "sum_R",
        "maxDD_R",
        "SQN",
        "trades_per_month",
        # MC keys (if present)
        "n_trades",
        "n_paths",
        "risk_per_trade",
        "block_size",
        "years",
        "blowup_rate",
        "median_cagr",
        "maxDD_pct_p05",
        "maxDD_pct_p50",
        "maxDD_pct_p95",
    ]
    present = {k: summary.get(k) for k in keys if k in summary}
    if not present:
        return "_(no summary keys found)_"

    lines = []
    for k, v in present.items():
        # Keep JSON-ish scalars clean
        if isinstance(v, float):
            lines.append(f"- **{k}**: `{v:.6g}`")
        else:
            lines.append(f"- **{k}**: `{v}`")
    return "\n".join(lines)


def _repro_cmd(kind: RunKind, meta: Dict[str, Any], run_dir: Path) -> str:
    # If you store argv, that’s the best source of truth
    argv = meta.get("argv")
    if isinstance(argv, list) and argv:
        # show as "threea-run <argv...>" and keep quoted
        pieces = ["threea-run"] + [str(x) for x in argv]
        return "```bash\n" + " ".join(pieces) + "\n```"

    # Fallbacks: reconstruct from meta
    if kind is BACKTEST:
        cfg = meta.get("config", "configs/base.yaml")
        data = meta.get("data", "<PATH_TO_PARQUET>")
        date_from = meta.get("date_from")
        date_to = meta.get("date_to")
        seed = meta.get("seed")
        parts = [
            "threea-run backtest",
            f'--config "{cfg}"',
            f'--data "{data}"',
        ]
        if date_from:
            parts.append(f"--from {date_from}")
        if date_to:
            parts.append(f"--to {date_to}")
        if seed is not None:
            parts.append(f"--seed {seed}")
        return "```bash\n" + " ".join(parts) + "\n```"

    if kind is WALKFORWARD:
        cfg = meta.get("config", "configs/base.yaml")
        data = meta.get("data", "<PATH_TO_PARQUET>")
        date_from = meta.get("date_from")
        date_to = meta.get("date_to")
        seed = meta.get("seed")
        is_days = meta.get("is_days", 63)
        oos_days = meta.get("oos_days", 21)
        step = meta.get("step")
        parts = [
            "threea-run walkforward",
            f'--config "{cfg}"',
            f'--data "{data}"',
            f"--is-days {is_days}",
            f"--oos-days {oos_days}",
        ]
        if step is not None:
            parts.append(f"--step {step}")
        if date_from:
            parts.append(f"--from {date_from}")
        if date_to:
            parts.append(f"--to {date_to}")
        if seed is not None:
            parts.append(f"--seed {seed}")
        return "```bash\n" + " ".join(parts) + "\n```"

    # MONTE_CARLO
    cfg = meta.get("config", "configs/base.yaml")
    trades_file = (
        meta.get("trades_file") or meta.get("trades_path") or "<PATH_TO_TRADES_PARQUET>"
    )
    n_paths = meta.get("n_paths", 1000)
    risk = meta.get("risk_per_trade", 0.01)
    block = meta.get("block_size")
    years = meta.get("years")
    seed = meta.get("seed")
    parts = [
        "threea-run monte-carlo",
        f'--config "{cfg}"',
        f'--trades-file "{trades_file}"',
        f"--n-paths {n_paths}",
        f"--risk-per-trade {risk}",
    ]
    if block is not None:
        parts.append(f"--block-size {block}")
    if years is not None:
        parts.append(f"--years {years}")
    if seed is not None:
        parts.append(f"--seed {seed}")
    return "```bash\n" + " ".join(parts) + "\n```"


def _artifacts_list(kind: RunKind) -> list[str]:
    if kind is BACKTEST:
        return [
            "run_meta.json",
            "summary.json",
            "signals.parquet",
            "trades.parquet",
            "trades.csv",
        ]
    if kind is WALKFORWARD:
        return [
            "run_meta.json",
            "summary.json",
            "is_summary.csv",
            "oos_summary.csv",
            "is_trades.parquet",
            "oos_trades.parquet",
            "wf_equity.parquet",
        ]
    return ["run_meta.json", "summary.json", "mc_samples.parquet", "mc_samples.csv"]


def _maybe_embed_walkforward_table(run_dir: Path, max_rows: int = 12) -> str:
    p = run_dir / "oos_summary.csv"
    if not p.exists():
        return ""
    df = pd.read_csv(p)
    if df.empty:
        return ""
    # Keep it small
    df_small = df.head(max_rows)
    return (
        "\n\n## OOS window summary (head)\n\n"
        + df_small.to_markdown(index=False)
        + ("\n\n_(truncated)_\n" if len(df) > max_rows else "\n")
    )


def write_report(run_dir: Path, out_path: Path) -> None:
    kind = detect_run_kind(run_dir)

    meta_path = run_dir / "run_meta.json"
    sum_path = run_dir / "summary.json"
    if not meta_path.exists() or not sum_path.exists():
        raise FileNotFoundError(f"Missing run_meta.json or summary.json in {run_dir}")

    meta = _read_json(meta_path)
    summary = _read_json(sum_path)

    run_id = meta.get("run_id") or run_dir.name

    title = f"Meridian Report — {kind.name} — {run_id}"

    artifacts = _artifacts_list(kind)
    artifacts_existing = [a for a in artifacts if (run_dir / a).exists()]

    md = []
    md.append(f"# {title}\n")
    md.append("## What this is\n")
    md.append(
        "This report summarizes a single Meridian run (inputs, configuration, and headline results) and provides a reproduction command.\n"
    )

    md.append("## Run metadata\n")
    md.append(
        _fmt_kv(
            meta,
            [
                "cmd",
                "run_id",
                "config",
                "data",
                "trades_file",
                "date_from",
                "date_to",
                "seed",
            ],
        )
    )
    md.append("\n## Headline stats\n")
    md.append(_headline_stats_block(summary))

    if kind is WALKFORWARD:
        md.append(_maybe_embed_walkforward_table(run_dir))

    md.append("\n## Artifacts\n")
    for a in artifacts_existing:
        md.append(f"- `{(run_dir / a).name}`")
    md.append("")

    md.append("## Reproduce\n")
    md.append(_repro_cmd(kind, meta, run_dir))

    md.append("\n## Notes / caveats\n")
    md.append(
        "- Results depend on data quality, session definition (RTH), and configuration.\n"
        "- Walk-forward avoids parameter bleed by freezing IS parameters before evaluating OOS.\n"
        "- Monte Carlo uses bootstrap assumptions (IID or block); interpret distributions, not point estimates.\n"
    )

    _safe_mkdir(out_path.parent)
    out_path.write_text("\n".join(md).strip() + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate a Markdown report from an outputs/<cmd>/<run_id> folder."
    )
    ap.add_argument(
        "--run",
        required=True,
        help="Path to a run folder, e.g. outputs/backtest/<run_id>",
    )
    ap.add_argument(
        "--out",
        required=True,
        help="Output markdown path, e.g. docs/reports/<run_id>.md",
    )
    args = ap.parse_args()

    run_dir = Path(args.run).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()

    write_report(run_dir, out_path)
    print(str(out_path))


if __name__ == "__main__":
    main()
