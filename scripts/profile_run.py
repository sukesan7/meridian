"""
Script: Performance Profiler
Purpose: Wraps any Meridian CLI command with cProfile to identify latency bottlenecks.

Description:
    Executes the target command (backtest/walkforward) with instrumentation enabled.
    Outputs a binary '.prof' file (visualizable with SnakeViz) and a text summary
    of the top N most expensive function calls.

Usage:
    python scripts/profile_run.py --out outputs/profiles/bt.prof --top 50 -- \
        backtest --config configs/base.yaml ...

Arguments:
    --out  : Path to save the binary profile.
    --top  : Number of rows to print in the text summary.
    --     : Separator. All arguments after '--' are passed to the Meridian CLI.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import time
from pathlib import Path

from s3a_backtester.cli import main as cli_main


def run_profile(argv: list[str], out_prof: Path, *, top: int, sort: str) -> float:
    out_prof.parent.mkdir(parents=True, exist_ok=True)

    pr = cProfile.Profile()
    t0 = time.perf_counter()

    pr.enable()
    cli_main(argv)
    pr.disable()

    dt = time.perf_counter() - t0

    # 1) Save binary stats for future inspection
    pr.dump_stats(str(out_prof))

    # 2) Save summary
    s = io.StringIO()
    stats = pstats.Stats(pr, stream=s).strip_dirs().sort_stats(sort)
    stats.print_stats(top)

    out_txt = out_prof.with_suffix(".txt")
    out_txt.write_text(s.getvalue(), encoding="utf-8")

    # 3) Save timing metadata
    out_meta = out_prof.with_suffix(".timing.json")
    out_meta.write_text(
        json.dumps({"seconds": dt, "argv": argv}, indent=2),
        encoding="utf-8",
    )

    return dt


def main() -> None:
    p = argparse.ArgumentParser(description="Profile Meridian CLI via cProfile.")
    p.add_argument(
        "--out",
        required=True,
        help="Output .prof path (e.g. outputs/profiles/run.prof)",
    )
    p.add_argument("--top", type=int, default=50, help="Top N functions in profile.txt")
    p.add_argument(
        "--sort",
        default="cumtime",
        choices=["cumtime", "tottime", "calls", "ncalls"],
        help="Sort key for profile output",
    )
    p.add_argument(
        "remainder",
        nargs=argparse.REMAINDER,
        help="Pass CLI args after -- (e.g. -- backtest --config ...)",
    )

    args = p.parse_args()
    if not args.remainder or args.remainder[0] != "--":
        raise SystemExit(
            "Expected CLI args after '--'. Example: python scripts/profile_run.py --out x.prof -- backtest ..."
        )

    argv = args.remainder[1:]  # drop the leading "--"
    out_prof = Path(args.out)

    dt = run_profile(argv, out_prof, top=args.top, sort=args.sort)
    print(f"[PROFILE] wrote: {out_prof} (+ .txt/.timing.json)  wall={dt:.3f}s")


if __name__ == "__main__":
    main()
