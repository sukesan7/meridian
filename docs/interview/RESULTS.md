# Meridian — Results (1-pager)

## Representative run

- **Label**: `Quickstart (synthetic 3-day)`
- **Config**: `None`
- **Data**: `<n/a>`
- **Date range**: `2025-01-06` → `2025-01-08`
- **Run IDs**:
  - Backtest: `qs_bt_20251225_192408`
  - Walkforward: `qs_bt_20251225_192408_wf`
  - Monte Carlo: `qs_bt_20251225_192408_mc`

## Headline stats (Backtest)

- **trades**: `0`
- **win_rate**: `0`
- **expectancy_R**: `0`
- **avg_R**: `0`
- **maxDD_R**: `0`
- **SQN**: `0`
- **trades_per_month**: `0`
- **sum_R**: `0`

## Walk-forward (OOS overall)

- **trades**: `0`
- **win_rate**: `0`
- **expectancy_R**: `0`
- **avg_R**: `0`
- **maxDD_R**: `0`
- **SQN**: `0`
- **trades_per_month**: `0`
- **sum_R**: `0`

## Monte Carlo (bootstrap on realized_R)

- **n_trades**: `0`
- **n_paths**: `500`
- **block_size**: `3`
- **risk_per_trade**: `0.01`
- **years**: `1`
- **blowup_rate**: `0`
- **median_cagr**: `0`
- **maxDD_pct_p05**: `0`
- **maxDD_pct_p50**: `0`
- **maxDD_pct_p95**: `0`

## Reproducibility

- Deterministic seeds recorded in `run_meta.json`.
- Outputs contract: `outputs/<cmd>/<run_id>/` contains `run_meta.json`, `summary.json`, and artifacts.

## Notes / caveats

- This 1-pager is a *representative run summary*, not a guarantee of future performance.
- Walk-forward freezes IS parameters before OOS evaluation (no parameter bleed).
- Monte Carlo reflects bootstrap assumptions (IID/block). Interpret distributions, not point estimates.
