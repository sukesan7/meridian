# Meridian — Deterministic Futures Backtester (Strategy 3A)

Meridian is a **deterministic, research-grade backtesting engine** for intraday futures execution logic (Strategy 3A: *VWAP Trend Pullback*). It consumes **1-minute OHLCV** (Databento continuous futures), computes session features (OR, VWAP bands, structure), generates signals (unlock → zone → trigger), and simulates trades with a rule-driven management lifecycle (TP1/TP2/time-stop).

> **Current status (end of Week 4):** end-to-end pipeline is working on real Databento continuous data, management + time-stop conditions are wired, session filters exist, CLI runs, tests pass, and Week 4 docs are written. Remaining work is largely **signal richness** (engulf, swing hi/lo, better structure) to increase trade frequency / realism.

---

## Why this exists

Most student “backtesters” are:
- nondeterministic (hidden state, lookahead bias),
- hand-wavy about execution (fills, slippage, session resets),
- impossible to reproduce (no data contract, no config contract, no tests).

Meridian is the opposite:
- **deterministic**: same input data + config ⇒ same outputs
- **explicit contracts**: data schema + config schema + state machine
- **test-first**: unit + integration coverage for critical Week 1–4 rules
- **research workflow**: CLI, artifacts, documented weekly milestones

---

## Key capabilities

### Engine
- Session-scoped state machine:
  - **Unlock** (OR break in trend direction)
  - **Zone** (first pullback into VWAP±1σ after unlock)
  - **Trigger** (micro-break / engulf after zone touch; breakout bar allowed)
  - **Risk-cap + stop** (OR-multiple cap + swing-based stop)
- Trade simulation with:
  - entry/exit timestamps
  - realized R-multiples
  - TP1 scaling + BE move
  - TP2 arbitration (R-target / levels where implemented)
  - time-stop (15m + conditional extension rules)

### Data pipeline (Week 4)
- Databento API **continuous symbol** fetch (e.g., `NQ.v.0`, `ES.v.0`)
- Normalization to a clean **vendor_parquet** format suitable for Meridian
- RTH slicing to match strategy assumptions (09:30–16:00 ET)
- Inventory tooling to verify coverage and schema

### Tooling & reproducibility
- CLI entrypoint (`meridian-run`) for repeatable runs
- YAML configuration (`configs/base.yaml`)
- `pytest` test suite validating core rule logic

---

## Repo layout

```
.
├── configs/
│   └── base.yaml
├── docs/
│   ├── week1-notes.md
│   ├── week2-notes.md
│   ├── week3-notes.md
│   ├── week4-notes.md
│   └── data/
│       ├── data-notes.md
│       └── data-pipeline.md
├── scripts/
│   ├── databento_fetch_continuous.py
│   ├── normalize_continuous_to_vendor_parquet.py
│   ├── data_inventory.py
│   ├── dev/
│   │   └── debug_signals_qqq.py          # dev-only (legacy I/O smoke)
│   └── legacy/
│       └── convert_databento_to_parquet.py # portal-download legacy path
├── s3a_backtester/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── data_io.py
│   ├── engine.py
│   ├── features.py
│   ├── filters.py
│   ├── management.py
│   ├── metrics.py
│   ├── monte_carlo.py
│   ├── portfolio.py
│   ├── slippage.py
│   ├── structure.py
│   ├── time_stop_conditions.py
│   └── walkforward.py
├── tests/
│   ├── test_engine.py
│   ├── test_engine_triggers.py
│   ├── test_engine_week3.py
│   ├── test_filters.py
│   ├── test_io_rth_resample.py
│   ├── test_management_session.py
│   ├── test_management_time.py
│   ├── test_management_tp.py
│   ├── test_metrics.py
│   └── test_refs_vwap.py
├── pyproject.toml
└── README.md
```

---

## Environment & dependencies

- Python: **3.10+** (developed on Windows / VSCode / PowerShell)
- Core deps: `pandas`, `numpy`, `pyarrow`, `pyyaml`, `scipy`
- Dev deps: `pytest`, `ruff`, `black`, `pre-commit`

Install (recommended):
```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip setuptools wheel
python -m pip install -e ".[dev]"
```

### If editable install (`pip install -e .`) fails on Windows
Some Windows/Python setups can hit distutils/setuptools conflicts. If that happens, you can still run Meridian without editable mode:

```powershell
python -m pip install ".[dev]"   # non-editable
python -m s3a_backtester.cli --help
```

(Editable install is convenience, not a blocker for the project.)

---

## Configuration

Primary config file:
- `configs/base.yaml`

It defines:
- instrument + timezone
- entry window
- risk cap (OR multiple)
- filters (tiny OR, ATR, news)
- signal policy switches (zone touch mode, lookbacks)
- management parameters (TP1/TP2, time-stop mode)
- slippage rules

Example (trimmed):
```yaml
instrument: "NQ"
tz: "America/New_York"

entry_window: { start: "09:35", end: "11:00" }
time_stop: { mode: "15min", conditional_30m: true }
risk_cap_or_mult: 1.25

slippage:
  normal_ticks: 1
  hot_ticks: 2
  hot_minutes: ["09:30-09:40", "10:00-10:02"]

filters:
  skip_tiny_or: true
  tiny_or_mult: 0.25
  low_atr_percentile: 0.2
  news_blackout: false

management:
  tp1_R: 1.0
  tp2_R: 2.0
  scale_at_tp1: 0.5
  move_to_BE_on_tp1: true
```

---

## Data contract (vendor_parquet)

Meridian expects 1-minute OHLCV with a timestamp:

**Combined RTH files** (typical):
- `data/vendor_parquet/NQ/NQ.v.0_YYYY-MM-DD_YYYY-MM-DD_RTH.parquet`
- `data/vendor_parquet/ES/ES.v.0_YYYY-MM-DD_YYYY-MM-DD_RTH.parquet`

Schema:
- `timestamp` (UTC, tz-aware)
- `open, high, low, close, volume`
- optional `symbol`

Meridian then converts timestamps to ET internally and applies the strategy logic in ET.

---

## Data pipeline (Databento continuous → vendor_parquet)

### 1) Fetch raw Databento continuous OHLCV (API)
```powershell
python scripts\databento_fetch_continuous.py `
  --symbol NQ.v.0 `
  --start 2025-09-01 `
  --end   2025-11-30
```

### 2) Normalize to Meridian vendor_parquet (RTH + clean schema)
```powershell
python scripts\normalize_continuous_to_vendor_parquet.py `
  --raw-parquet data\raw\databento_api\GLBX.MDP3_ohlcv-1m_NQ.v.0_2025-09-01_2025-11-30.parquet `
  --symbol  NQ.v.0 `
  --product NQ `
  --start   2025-09-01 `
  --end     2025-11-30
```

### 3) Inventory / sanity check coverage
```powershell
python scripts\data_inventory.py --parquet-dir data\vendor_parquet\NQ --out outputs\data_inventory_nq.csv
python scripts\data_inventory.py --parquet-dir data\vendor_parquet\ES --out outputs\data_inventory_es.csv
```

> Notes on legacy scripts:
> - `scripts/legacy/convert_databento_to_parquet.py` is the **portal-download path** (parent product → many instruments). Kept for reference but not the current pipeline.
> - `scripts/dev/debug_signals_qqq.py` is dev-only.

---

## Running backtests

### CLI entrypoint

`pyproject.toml` exposes:
- `meridian-run` (preferred)
- `threea-run` (legacy alias)

### Describe data file
```powershell
meridian-run describe-data --data data\vendor_parquet\NQ\NQ.v.0_2025-09-01_2025-11-30_RTH.parquet
```

### Run backtest (prints a summary + optional debug counters)
```powershell
meridian-run run-backtest `
  --config configs\base.yaml `
  --data   data\vendor_parquet\NQ\NQ.v.0_2025-09-01_2025-11-30_RTH.parquet `
  --debug-signals
```

Output:
- a run summary dict (trades, win_rate, avg_R, maxDD_R, SQN)
- optional signal coverage counters (unlock/zone/trigger/disqualifiers)

---

## Testing & quality gates

### Unit tests
```powershell
pytest -q
```

### Lint/format (if configured via pre-commit)
```powershell
pre-commit run --all-files
```

Meridian’s Week 1–4 gates are enforced by tests:
- IO/RTH slicing correctness (including DST behavior)
- session refs + VWAP bands
- unlock/zone/trigger invariants
- risk-cap/stop correctness
- management lifecycle + time-stop scenarios
- engine/management integration

---

## Outputs & artifacts

Meridian is designed to emit **auditable artifacts** for research:
- debug counters (coverage)
- trade table (entry/exit, R, flags)
- run summaries

Week 4’s “artifacts” concept is documented in `docs/week4-notes.md` (and related docs). If you want persistent files per run, the next natural step is adding:
- `--out outputs/backtest/<run_id>/`
- `trades.parquet` / `trades.csv`
- `summary.json`
- `sampled_trades.csv` for audit

(That wiring is straightforward and belongs in Week 5 if not already implemented.)

---

## Current limitations (honest status)

Right now, low trade counts are expected because:
- `engulf_dir` is not implemented/available in the real-data feature set yet
- `swing_hi/swing_lo` are not fully wired as first-class features on live data
- triggers are conservative by design (zone gating + direction match + disqualifiers)

This is not a “strategy conclusion” yet — it’s a **feature completeness** issue.

---

## Next steps (Week 5 direction)

1) **Feature completeness (signal richness)**
   - implement `engulf_dir`
   - implement robust `swing_hi/swing_lo` + micro-structure signals on 5m/1m
   - ensure feature parity between synthetic tests and real continuous data

2) **Research ergonomics**
   - persistent run artifacts (`--out`, trades parquet/csv, summary json)
   - deterministic sampling tooling for audits
   - structured logging (instead of print)

3) **Evaluation tooling**
   - parameter sweeps
   - walk-forward + Monte Carlo gating (skeleton exists)

4) **Packaging hygiene**
   - rename package metadata (`project.name`) to `meridian` when ready
   - optional: remove `threea-run` alias after transition

---

## Disclaimer

Meridian is a **research tool**, not a production trading system. Backtests are sensitive to data quality, session definitions, and execution assumptions. This repo does not constitute financial advice.

---

## Quick “Day-1” workflow (PowerShell)

```powershell
# 1) Setup
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip setuptools wheel
python -m pip install -e ".[dev]"

# 2) Tests
pytest -q

# 3) Fetch + normalize 3 months (NQ)
python scripts\databento_fetch_continuous.py --symbol NQ.v.0 --start 2025-09-01 --end 2025-11-30
python scripts\normalize_continuous_to_vendor_parquet.py --raw-parquet data\raw\databento_api\GLBX.MDP3_ohlcv-1m_NQ.v.0_2025-09-01_2025-11-30.parquet --symbol NQ.v.0 --product NQ --start 2025-09-01 --end 2025-11-30

# 4) Run backtest
meridian-run run-backtest --config configs\base.yaml --data data\vendor_parquet\NQ\NQ.v.0_2025-09-01_2025-11-30_RTH.parquet --debug-signals
```

---
