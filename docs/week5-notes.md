## Week 5 — Metrics, Walk-forward, Monte Carlo, CLI (Meridian)

✅ Implemented (core Week 5 scope)

---

### 0. Context (Week 4 → Week 5 transition)

Week 4 delivered the managed trade lifecycle + session filters + Databento continuous futures pipeline (NQ/ES) and an end-to-end runnable backtest harness.

Week 5 focuses on: **metrics/reporting**, **rolling walk-forward**, **Monte Carlo robustness**, and a **real CLI workflow** with run-scoped artifacts.

---

### 1. Metrics Suite (`metrics.py`)

Week 5 formalizes a single metrics API for consistent reporting across:

- backtest
- walk-forward
- Monte Carlo summaries

#### 1.1 `metrics.summary(...)`
A single function that returns standardized keys:

- `trades`
- `win_rate`
- `avg_R`
- `expectancy_R`
- `avg_win_R`, `avg_loss_R`
- `sum_R`
- `maxDD_R`
- `SQN`
- `trades_per_month`

Notes:
- Summary is computed directly from the trade-level `realized_R` series.
- Keys are stable so CLI can print JSON consistently and downstream plotting/reporting doesn’t drift.

#### 1.2 `metrics.grouped_summary(...)`
Grouped aggregations for slicing robustness by:

- **OR quartile**
- **day-of-week**
- **month**

Goal:
- “Does this only work on specific regimes / days / seasonal clusters?”

Output:
- a clean summary table per group with the same standardized keys as `summary(...)`.

#### 1.3 Bug fix: MaxDD anchoring
A correctness issue surfaced during walk-forward:

- If a window starts with a losing trade, a naive drawdown calculation on the cumulative series can report **MaxDD = 0** (because the “peak” is negative).
- Fix: **anchor equity curve at 0** before drawdown computation so drawdown is measured from starting equity.

Result:
- OOS window drawdowns now correctly report `maxDD_R = 1.0` when the first trade is a -1R.

---

### 2. Walk-forward Engine (`walkforward.py`)

#### 2.1 Rolling windows
Implemented rolling walk-forward with:

- **IS** = 63 sessions (~3 months)
- **OOS** = 21 sessions (~1 month)
- **step** = configurable (set to 21 right now)

Each window produces:
- IS summary stats
- OOS summary stats
- OOS trades (for MC)
- optional labeled equity curve / window metadata

#### 2.2 No parameter bleed
Key rule enforced:
- OOS evaluation uses only parameters fixed before the OOS period begins.

In the current implementation:
- No grid-search tuning was required to satisfy “no bleed” (parameters are frozen).
- (Optional Week 6+: add a minimal IS-only tuning hook that writes `window_params.json` per window.)

#### 2.3 Important operational note
Walk-forward requires enough sessions to form at least one IS+OOS window.

Example:
- 63 + 21 = **84 sessions minimum**
- If you only run ~3 months of data, you must reduce `is_days/oos_days/step` to get any windows.

---

### 3. Monte Carlo Bootstrap (`monte_carlo.py`)

#### 3.1 What is simulated
Monte Carlo operates on the **trade R-series** (`realized_R`) and simulates equity paths via bootstrapping:

- Base: IID bootstrap (resample trades with replacement)
- Optional: **block bootstrap** (`block_size`) to preserve clustering/serial dependence

#### 3.2 Outputs
Per MC run, the CLI writes:
- `summary.json` (headline stats)
- `mc_samples.parquet` (full path samples for later plotting)

Reported stats include:
- `n_trades`, `n_paths`, `risk_per_trade`, `block_size`
- `years` inferred from trade timestamps (used for CAGR)
- `median_cagr`
- MaxDD distribution percentiles: `maxDD_pct_p05`, `p50`, `p95`
- `blowup_rate` (simple survival metric if implemented)

#### 3.3 Common pitfall caught during integration
If you accidentally pass a **CSV summary** instead of a **trades parquet**, MC will load zero trades and output all zeros.

Mitigation:
- Always use `--trades-file .../trades.parquet` or `.../oos_trades.parquet` (not `oos_summary.csv`).

---

### 4. CLI Workflow (`threea-run`)

Week 5 turns “scripts” into a real CLI workflow that:

- prints compact JSON summaries to stdout
- writes deterministic artifacts under `outputs/<cmd>/<run_id>/`

Implemented commands:

#### 4.1 Backtest
```bash
threea-run backtest --config configs/base.yaml --data <PATH_TO_1M.parquet> --from YYYY-MM-DD --to YYYY-MM-DD --run-id <run_id>
```

Artifacts (expected):
- `outputs/backtest/<run_id>/summary.json`
- `outputs/backtest/<run_id>/trades.parquet`
- (optional) `run_meta.json` and other diagnostic outputs

#### 4.2 Walk-forward
```bash
threea-run walkforward --config configs/base.yaml --data <PATH_TO_1M.parquet> --from YYYY-MM-DD --to YYYY-MM-DD --is-days 63 --oos-days 21 --step 21 --run-id <run_id>
```

Artifacts (expected):
- `outputs/walkforward/<run_id>/is_summary.csv`
- `outputs/walkforward/<run_id>/oos_summary.csv`
- `outputs/walkforward/<run_id>/oos_trades.parquet`
- (optional) labeled equity curve / per-window metadata

#### 4.3 Monte Carlo
```bash
threea-run monte-carlo --config configs/base.yaml --trades-file outputs/walkforward/<wf_run_id>/oos_trades.parquet --n-paths 2000 --risk-per-trade 0.01 --block-size 5 --run-id <run_id>
```

Artifacts (expected):
- `outputs/monte-carlo/<run_id>/summary.json`
- `outputs/monte-carlo/<run_id>/mc_samples.parquet`

---

### 5. Data & Timezone QA

A major Week 5 investigation was validating “low trade count” was not caused by broken time logic.

#### 5.1 Dataset is UTC
The vendor parquet timestamps are tz-aware UTC (e.g., `2024-12-02 14:30:00+00:00`).

Correct handling:
- Convert to **America/New_York** at load time for any session logic anchored at 09:30 ET.

#### 5.2 Loader verification
`load_minute_df(..., tz="America/New_York")` produces:
- tz-aware NY index
- 256 RTH sessions in the 12-month file
- 390 bars/session
- OR window 09:30–09:59 has exactly 30 bars/session

Diagnostic command used:
```powershell
python - << 'PY'
import pandas as pd
from s3a_backtester.data import load_minute_df

path = r"data\vendor_parquet\NQ\NQ.v.0_2024-12-01_2025-11-30_RTH.parquet"
df = load_minute_df(path, tz="America/New_York")

print("index tz:", df.index.tz)
print("range:", df.index.min(), "->", df.index.max())
print("sessions:", df.index.normalize().nunique())
print("rows:", len(df))

hm = df.index.strftime("%H:%M")
or_mask = (hm >= "09:30") & (hm <= "09:59")
print("OR bars total:", int(or_mask.sum()), "expected approx:", df.index.normalize().nunique() * 30)
PY
```

Result: data + OR window are correct; strategy frequency is governed by strategy logic/filters, not data loss.

---

### 6. Config Schema Fix (prevent “silent misconfig”)

A key Week 5 fix: YAML keys were previously being silently ignored if not present in the dataclass.

#### 6.1 Added nested config objects
- `RiskCfg(max_stop_or_mult)`
- `SignalsCfg(disqualify_after_unlock, zone_touch_mode, trigger_lookback_bars)`

#### 6.2 Confirmed config loads correctly
Proof command:
```bash
python -c "from s3a_backtester.config import load_config; import pprint; pprint.pp(load_config('configs/base.yaml'))"
```

Result:
- `risk=RiskCfg(...)` and `signals=SignalsCfg(...)` appear in the printed config.

---

### 7. Databento: 12-month continuous futures dataset (credit-safe)

#### 7.1 Constraint
The fetch script enforces a date-range guard (≤ ~120 days per request) to protect credits.

#### 7.2 Fetch in chunks (example: 12 months)
```bash
python scripts/databento_fetch_continuous.py --symbol NQ.v.0 --start 2024-12-01 --end 2025-03-30
python scripts/databento_fetch_continuous.py --symbol NQ.v.0 --start 2025-03-31 --end 2025-07-28
python scripts/databento_fetch_continuous.py --symbol NQ.v.0 --start 2025-07-29 --end 2025-11-25
python scripts/databento_fetch_continuous.py --symbol NQ.v.0 --start 2025-11-26 --end 2025-11-30
```

#### 7.3 Normalize each chunk to vendor parquet (RTH)
```bash
python scripts/normalize_continuous_to_vendor_parquet.py --raw-parquet <RAW.parquet> --symbol NQ.v.0 --product NQ --start <start> --end <end>
```

#### 7.4 Combine chunk RTH files into a single 12-month parquet
(Example one-liner used during integration)
```bash
python -c "import pandas as pd; from pathlib import Path; files=[
r'data/vendor_parquet/NQ/NQ.v.0_2024-12-01_2025-03-30_RTH.parquet',
r'data/vendor_parquet/NQ/NQ.v.0_2025-03-31_2025-07-28_RTH.parquet',
r'data/vendor_parquet/NQ/NQ.v.0_2025-07-29_2025-11-25_RTH.parquet',
r'data/vendor_parquet/NQ/NQ.v.0_2025-11-26_2025-11-30_RTH.parquet'
]; df=pd.concat([pd.read_parquet(f) for f in files], ignore_index=True); df=df.sort_values('timestamp'); df=df.drop_duplicates(subset=['timestamp'], keep='last'); out=r'data/vendor_parquet/NQ/NQ.v.0_2024-12-01_2025-11-30_RTH.parquet'; Path(out).parent.mkdir(parents=True, exist_ok=True); df.to_parquet(out, index=False); print('WROTE', out, 'rows', len(df))"
```

Final dataset used for the Week 5 gate:
- `data/vendor_parquet/NQ/NQ.v.0_2024-12-01_2025-11-30_RTH.parquet`

---

### 8. Week 5 Gate Run (12-month NQ)

Goal: prove the full research loop works end-to-end on real data.

#### 8.1 Backtest (12 months)
```bash
threea-run backtest --config configs/base.yaml --data data/vendor_parquet/NQ/NQ.v.0_2024-12-01_2025-11-30_RTH.parquet --from 2024-12-01 --to 2025-11-30 --run-id nq_12m_bt
```

Observed summary (headline):
- trades: 43
- expectancy_R: ~0.426
- sum_R: ~18.31R
- maxDD_R: ~2.16R

#### 8.2 Walk-forward (63/21 rolling)
```bash
threea-run walkforward --config configs/base.yaml --data data/vendor_parquet/NQ/NQ.v.0_2024-12-01_2025-11-30_RTH.parquet --from 2024-12-01 --to 2025-11-30 --is-days 63 --oos-days 21 --step 21 --run-id nq_12m_wf
```

Observed summary (headline):
- trades: 41
- expectancy_R: ~0.388
- sum_R: ~15.92R
- maxDD_R: ~2.16R

Interpretation:
- modest OOS decay vs backtest (expected)
- results did not collapse (pipeline + logic appear consistent)

#### 8.3 Monte Carlo on OOS trades (block bootstrap)
```bash
threea-run monte-carlo --config configs/base.yaml --trades-file outputs/walkforward/nq_12m_wf/oos_trades.parquet --n-paths 2000 --risk-per-trade 0.01 --block-size 5 --run-id nq_12m_wf_mc
```

Observed MC summary (headline):
- median CAGR ~ 0.244 (annualized over inferred trade span)
- MaxDD% distribution (risk=1%/trade):
  - p50 ~ 2.14%
  - p95 ~ 3.25%

Note:
- CAGR is sensitive to the inferred `years` computed from trade timestamps; interpret as a comparative signal.

---

### 9. Tests / Tooling (Week 5)

- Unit tests added/extended for:
  - metrics summary keys + grouped summaries
  - walk-forward window slicing correctness on synthetic data
  - Monte Carlo bootstrap determinism (seeded) + output shapes
- Tooling hygiene:
  - ruff/pre-commit issues resolved (auto-fix conflicts avoided by keeping working tree clean)

Proof commands:
- `pytest -q`
- `pre-commit run --all-files`

---

### 10. Not implemented yet (Week 6+)

- Standardized `run_meta.json` + naming consistency across **backtest / walkforward / monte-carlo**.
- Dedicated “combine chunks” script (replace one-liner with `scripts/combine_vendor_parquet.py`).
- ES cross-validation (run the same WF/MC pipeline on ES).
- Multi-year regime coverage (5-year NQ and/or NQ+ES), plus sensitivity variants.
- Optional IS-only tuning hook with explicit `window_params.json` per window.
