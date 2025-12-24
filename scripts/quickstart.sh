#!/usr/bin/env bash
set -euo pipefail

python -m pip install -e ".[dev]" --no-build-isolation

SAMPLE="data/sample/synth_3d_RTH.parquet"
python scripts/make_synth_parquet.py --out "$SAMPLE" --days 3 --seed 123

RID="quickstart_bt"
meridian-run backtest --config configs/base.yaml --data "$SAMPLE" --from 2025-01-06 --to 2025-01-08 --run-id "$RID" --seed 123

python scripts/make_report.py --run "outputs/backtest/$RID" --out "docs/reports/$RID.md"

echo "Report: docs/reports/$RID.md"
