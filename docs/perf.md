# Performance Notes (Week 6)

This doc records profiling results and only optimizes confirmed bottlenecks.

## How to profile

### Backtest
Compute-only (recommended first: avoid IO noise like writing huge signals):
- Use CLI flags to disable signals/trades writing if implemented (e.g. `--no-write-signals`, `--no-write-trades`).

```powershell
python scripts\profile_run.py --out outputs\profiles\nq_12m_backtest.prof --top 60 -- `
  backtest `
  --config configs\base.yaml `
  --data data\vendor_parquet\NQ\NQ.v.0_2024-12-01_2025-11-30_RTH.parquet `
  --from 2024-12-01 `
  --to 2025-11-30 `
  --run-id prof_nq_12m_bt
```

### Walk-forward
```powershell
python scripts\profile_run.py --out outputs\profiles\nq_12m_walkforward.prof --top 60 -- `
  walkforward `
  --config configs\base.yaml `
  --data data\vendor_parquet\NQ\NQ.v.0_2024-12-01_2025-11-30_RTH.parquet `
  --from 2024-12-01 `
  --to 2025-11-30 `
  --is-days 63 `
  --oos-days 21 `
  --step 21 `
  --run-id prof_nq_12m_wf
```

## Viewing results

Quick view (built-in):
```powershell
python -m pstats outputs\profiles\nq_12m_backtest.prof
```

Inside pstats:
- `sort cumtime`
- `stats 40`

Optional (nicer UI):
- `pip install snakeviz`
- `snakeviz outputs\profiles\nq_12m_backtest.prof`

## Baseline results (2025-12-22)

- Dataset: NQ 1m RTH, 12m, 256 sessions
- Backtest wall time: 14.56 s
- Function calls: ~15.6M

Top hotspots (cumulative time):
1. cli.py:209(build_feature_frames) ~12.77s
2. structure.py:90(trend_5m) ~5.20s (per-day trend calc)
3. data_io.py:11(load_minute_df) ~2.93s (tz_convert ~2.65s)
4. features.py:143(find_swings_1m) ~2.25s
5. engine.py:41(simulate_trades) ~1.36s

Notes:
- Major overhead from pandas indexing operations (heavy slicing / list-like indexing). Considering Polars.
- Timezone conversion is unexpectedly expensive due to zoneinfo resource loading.
