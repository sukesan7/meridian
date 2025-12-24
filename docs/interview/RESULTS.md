# Meridian — Results

## Representative run
- Instrument:
- Date range:
- Config:
- Run IDs:
  - Backtest:
  - Walkforward (OOS):
  - Monte Carlo:

## Headline stats (Backtest)
- trades:
- win_rate:
- expectancy_R:
- maxDD_R:
- SQN:
- trades_per_month:

## Walk-forward (OOS)
- trades:
- expectancy_R:
- maxDD_R:
- SQN:

## Monte Carlo (bootstrap on realized_R)
- n_paths:
- block_size:
- median_cagr:
- maxDD pctiles (p05 / p50 / p95):

## Reproducibility
- Deterministic seeds: yes (recorded in run_meta.json)
- Outputs contract: outputs/<cmd>/<run_id>/ with run_meta.json + summary.json + artifacts

## Notes / caveats
- Strategy is event-driven; trade counts can be low depending on filters/market regime.
- Monte Carlo reflects bootstrap assumptions (IID/block); interpret distributions, not point estimates.
