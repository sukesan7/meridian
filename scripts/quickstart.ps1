<#
.SYNOPSIS
    Windows Quickstart & Smoke Test.

.DESCRIPTION
    1. Installs the package in editable mode.
    2. Generates synthetic data (no API key required).
    3. Runs a short backtest to verify system stability.
    4. Generates a 'STRATEGY_RESULTS.md' report.

.EXAMPLE
    .\quickstart.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "[1/4] Installing dependencies..."
python -m pip install -e ".[dev]" --no-build-isolation | Out-Null

Write-Host "[2/4] Generating synthetic data..."
$SAMPLE = "data/sample/synth_3d_RTH.parquet"
python scripts/make_synth_parquet.py --out $SAMPLE --days 3 --seed 123

Write-Host "[3/4] Running Smoke Test (Backtest)..."
$RID = "quickstart_bt"
meridian-run backtest --config configs/base.yaml --data $SAMPLE --from 2025-01-06 --to 2025-01-08 --run-id $RID --seed 123 | Out-Null

Write-Host "[4/4] Generating Report..."
$REPORT_PATH = "docs/reports/$RID.md"
python scripts/make_report.py --run "outputs/backtest/$RID" --out $REPORT_PATH

Write-Host "---------------------------------------------------"
Write-Host "SUCCESS! Quickstart complete."
Write-Host "Report generated at: $REPORT_PATH"
Write-Host "---------------------------------------------------"
