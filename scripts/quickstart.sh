#!/usr/bin/env bash
#
# Script: Linux/Mac Quickstart & Smoke Test
# Purpose: One-click environment validation for CI/CD or new developers.
#
# Description:
#   1. Installs package dependencies.
#   2. Generates synthetic Brownian Motion data.
#   3. Executes a 3-day backtest (Smoke Test).
#   4. Compiles results into a Markdown report.
#
# Usage:
#   ./quickstart.sh
#
set -euo pipefail

echo "[1/4] Installing dependencies..."
python -m pip install -e ".[dev]" --no-build-isolation > /dev/null 2>&1

echo "[2/4] Generating synthetic data..."
SAMPLE="data/sample/synth_3d_RTH.parquet"
python scripts/make_synth_parquet.py --out "$SAMPLE" --days 3 --seed 123

echo "[3/4] Running Smoke Test (Backtest)..."
RID="quickstart_bt"
meridian-run backtest --config configs/base.yaml --data "$SAMPLE" --from 2025-01-06 --to 2025-01-08 --run-id "$RID" --seed 123 > /dev/null

echo "[4/4] Generating Report..."
REPORT_PATH="docs/reports/${RID}.md"
python scripts/make_report.py --run "outputs/backtest/$RID" --out "$REPORT_PATH"

echo "---------------------------------------------------"
echo "SUCCESS! Quickstart complete."
echo "Report generated at: $REPORT_PATH"
echo "---------------------------------------------------"
