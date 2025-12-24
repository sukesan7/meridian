# Meridian — Architecture

## Pipeline
1) Data IO
- Load vendor 1m OHLCV (UTC) and normalize to America/New_York RTH session.

2) Features (1m + 5m frames)
- Session references: OR, anchored VWAP, VWAP bands.
- Structure/trend features from 5m aggregation.

3) Signal engine (`generate_signals`)
- OR break unlock
- Pullback zone touch (configurable: close vs range)
- Trigger logic (micro-break / engulf) with lookback window
- Disqualifiers (e.g., 2σ opposite side) with `disqualify_after_unlock` gating

4) Execution simulator (`simulate_trades`)
- Slippage model (normal vs hot minutes)
- Trade management (TP1 scale, BE moves, time-stop)

5) Analytics
- metrics: summary + grouped summaries
- walkforward: rolling IS/OOS windows, no parameter bleed
- monte-carlo: IID/block bootstrap on realized_R → drawdown/CAGR distributions

## Reproducibility & artifacts
- Every run writes:
  - run_meta.json (inputs, ranges, seed, knobs)
  - summary.json (headline stats)
  - artifacts (signals/trades/wf equity/mc samples)

## Quality gates
- Unit tests cover unlock/zone/trigger + gating switches
- Integration smoke tests validate artifact contracts
- CI runs pre-commit + pytest on push/PR
