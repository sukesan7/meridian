# Meridian — Deterministic Futures Backtester (Strategy 3A)

Meridian is a **deterministic, research‑grade backtesting engine** for intraday futures execution logic (Strategy 3A: *VWAP Trend Pullback*). It consumes **1‑minute OHLCV** (Databento continuous futures), builds session features (Opening Range, anchored VWAP + bands, structure), generates signals (unlock → zone touch → trigger), and simulates trades using a rule‑driven management lifecycle (TP1/TP2/time‑stop + slippage).

---

## What problem this solves

Backtesting intraday futures strategies reliably is hard because small implementation details dominate outcomes:

- session boundaries and timezone handling (UTC vs ET, DST behavior)
- realistic execution assumptions (slippage, time stops, partial scale outs)
- stateful, multi‑stage signals (unlock → pullback → trigger)
- reproducibility (same data + config should produce the same outputs)

Meridian is built to make these assumptions **explicit**, **testable**, and **repeatable**.

---

## How it works (high level)

### 1) Data → normalized session bars
1. Fetch 1‑minute continuous futures OHLCV from Databento (e.g., `NQ.v.0`, `ES.v.0`).
2. Normalize to a clean `vendor_parquet` schema and slice to **RTH** (09:30–16:00 ET).
3. Load into the engine with a tz‑aware ET index (strategy logic runs in **America/New_York**).

### 2) Feature build (`features.py`, `structure.py`)
Per session/day, features are computed deterministically:
- Opening Range (OR) stats
- Anchored VWAP and σ bands (used for “zone” logic)
- Lightweight structure/trend helpers (e.g., swing context) used by filters/triggers

### 3) Signal engine (`engine.py`)
Meridian uses an explicit session state machine:
- **Unlock:** OR break in the trend direction
- **Zone touch:** first pullback into VWAP +-1σ after unlock (configurable close-only vs range-overlap)
- **Trigger:** breakout / micro‑break within a configurable lookback window
- **Risk:** stop distance capped by an OR multiple (`risk.max_stop_or_mult`)

### 4) Trade simulation (`management.py`, `time_stop_conditions.py`, `slippage.py`)
Given entries/exits, the simulator applies:
- slippage (normal + “hot minute” rules)
- TP1/TP2 targets in R
- scale‑out at TP1 + optional move‑to‑breakeven
- time‑stop (TP1 timeout, max holding, optional extension)

### 5) Evaluation + robustness
- `metrics.summary(...)` produces standardized run metrics in R space.
- `walkforward.rolling_walkforward(...)` runs rolling **IS → OOS** windows with no parameter bleed.
- `monte_carlo.mc_simulate_R(...)` bootstraps the trade R‑series (IID or block) to estimate drawdown/CAGR distributions.

---

## Repo Layout

```
.
├── .github/workflows/ci.yml              # CI: tests + lint gates
├── configs/
│   └── base.yaml                         # primary YAML config (strategy + execution)
├── docs/
│   ├── week1-notes.md
│   ├── week2-notes.md
│   ├── week3-notes.md
│   ├── week4-notes.md
│   ├── week5-notes.md
│   └── data/
│       ├── data-notes.md
│       └── data-pipeline.md
├── s3a_backtester/
│   ├── cli.py                            # `threea-run` / `meridian-run`
│   ├── config.py                         # dataclass schema + YAML loader
│   ├── data_io.py                        # parquet/csv loader + tz normalization
│   ├── engine.py                         # unlock → zone → trigger logic
│   ├── features.py                       # OR/VWAP/bands + session features
│   ├── filters.py                        # session filter mask
│   ├── management.py                     # TP1/TP2/BE + lifecycle
│   ├── metrics.py                        # summary + grouped_summary (OR quartile / DOW / month)
│   ├── monte_carlo.py                    # bootstrap MC on trade R series
│   ├── portfolio.py                      # equity/DD helpers used by MC/metrics
│   ├── slippage.py                       # simple slippage model
│   ├── structure.py                      # 5min trend direction
│   ├── time_stop_conditions.py
│   └── walkforward.py                    # rolling IS/OOS runner
├── tests/                                # unit tests for core invariants
├── scripts/
│   ├── dev/
│   │   └── debug_signals_qqq.py          # dev script for testing IO on QQQ
│   ├── legacy/
│   │   └── convert_databento_to_parquet.py  # legacy script for databento web portal data
│   ├── databento_fetch_continuous.py     # Databento API fetch → raw parquet
│   ├── normalize_continuous_to_vendor_parquet.py  # raw → vendor_parquet (RTH + by_day + combined)
│   └── data_inventory.py                 # coverage/schema sanity checks
├── pyproject.toml                        # deps + CLI entrypoints
└── README.md
```

---

## Environment & dependencies

- Python **3.10+**
- Core: `pandas`, `numpy`, `pyarrow`, `pyyaml`, `scipy`
- Dev: `pytest`, `ruff`, `black`, `pre-commit`

Install (recommended):
```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip setuptools wheel
python -m pip install -e ".[dev]"
```

---

## Configuration (YAML + dataclass schema)

Primary config: `configs/base.yaml`

The loader (`s3a_backtester/config.py`) maps YAML into typed dataclasses. The config surface covers:
- instrument + timezone
- entry window
- risk (`risk.max_stop_or_mult`)
- slippage rules (including “hot minutes”)
- filters (tiny OR, ATR regime, news blackout)
- signal policies (zone touch mode, trigger lookback, disqualify timing)
- management (TP1/TP2/scale‑out/BE + time stop)

Example (trimmed):
```yaml
instrument: "NQ"
tz: "America/New_York"

entry_window:
  start: "09:35"
  end: "11:00"

risk:
  max_stop_or_mult: 1.25

signals:
  disqualify_after_unlock: true
  zone_touch_mode: "range"
  trigger_lookback_bars: 5

trend:
  require_vwap_side: true
  swing_lookback_5m: 2

management:
  tp1_R: 1.0
  tp2_R: 2.0
  scale_at_tp1: 0.5
  move_to_BE_on_tp1: true
```

Config sanity check:
```bash
python -c "from s3a_backtester.config import load_config; import pprint; pprint.pp(load_config('configs/base.yaml'))"
```

---

## Data contract (`vendor_parquet`)

Meridian expects 1‑minute OHLCV with a timestamp column (UTC, tz‑aware):

- `timestamp` (UTC, tz‑aware)
- `open`, `high`, `low`, `close`, `volume`
- optional `symbol`

Normalization script output (typical):
- `data/vendor_parquet/<PRODUCT>/<SYMBOL>_<start>_<end>_RTH.parquet`
- plus an optional `by_day/` layout for convenient inspection.

Important:
- Strategy logic is defined in **ET**. The loader converts timestamps to `America/New_York` internally before computing OR/VWAP/session features.

---

## Databento pipeline (continuous futures → vendor_parquet)

### 1) Fetch raw continuous OHLCV (API)
Requires `DATABENTO_API_KEY`:
```powershell
$env:DATABENTO_API_KEY="YOUR_KEY_HERE"
```

Fetch (example):
```powershell
python scripts/databento_fetch_continuous.py --symbol NQ.v.0 --start 2025-09-01 --end 2025-11-30
```

### 2) Normalize to `vendor_parquet` (RTH + clean schema)
```powershell
python scripts/normalize_continuous_to_vendor_parquet.py `
  --raw-parquet data/raw/databento_api/GLBX.MDP3_ohlcv-1m_NQ.v.0_2025-09-01_2025-11-30.parquet `
  --symbol  NQ.v.0 `
  --product NQ `
  --start   2025-09-01 `
  --end     2025-11-30
```

### 3) Inventory / sanity check coverage
```powershell
python scripts/data_inventory.py --parquet-dir data/vendor_parquet/NQ --out outputs/data_inventory_nq.csv
```

Notes:
- Databento requests are typically chunked (e.g., ≤ ~120 days per fetch) for credit‑control and API limits.
- For multi‑chunk datasets, normalize each chunk and then combine the resulting `*_RTH.parquet` files into a single run file (Meridian’s CLI expects a **single parquet path**).

---

## Running the engine (CLI)

The package exposes two equivalent entrypoints:
- `threea-run`
- `meridian-run`

All commands:
- print a compact JSON summary to stdout
- write artifacts under `outputs/<cmd>/<run_id>/`

### Backtest
```powershell
threea-run backtest `
  --config configs/base.yaml `
  --data   data/vendor_parquet/NQ/NQ.v.0_2024-12-01_2025-11-30_RTH.parquet `
  --from   2024-12-01 `
  --to     2025-11-30 `
  --run-id nq_12m_bt
```

Expected artifacts:
- `outputs/backtest/<run_id>/summary.json`
- `outputs/backtest/<run_id>/trades.parquet`

### Walk-forward (rolling IS → OOS)
```powershell
threea-run walkforward `
  --config  configs/base.yaml `
  --data    data/vendor_parquet/NQ/NQ.v.0_2024-12-01_2025-11-30_RTH.parquet `
  --from    2024-12-01 `
  --to      2025-11-30 `
  --is-days  63 `
  --oos-days 21 `
  --step     21 `
  --run-id   nq_12m_wf
```

Expected artifacts:
- `outputs/walkforward/<run_id>/is_summary.csv`
- `outputs/walkforward/<run_id>/oos_summary.csv`
- `outputs/walkforward/<run_id>/oos_trades.parquet`
- (optional) labeled equity curve / per-window metadata (if enabled)

### Monte Carlo (bootstrap on trade R series)
```powershell
threea-run monte-carlo `
  --config          configs/base.yaml `
  --trades-file     outputs/walkforward/nq_12m_wf/oos_trades.parquet `
  --n-paths         2000 `
  --risk-per-trade  0.01 `
  --block-size      5 `
  --run-id          nq_12m_wf_mc
```

Expected artifacts:
- `outputs/monte-carlo/<run_id>/summary.json`
- `outputs/monte-carlo/<run_id>/mc_samples.parquet`

Common mistake:
- Do **not** pass `oos_summary.csv` to Monte Carlo. Use the trade file (`*_trades.parquet`).

---

## Outputs & artifacts

Meridian is built around **auditable research artifacts**. Each run produces:
- machine-readable summaries (`summary.json` / `*_summary.csv`)
- trade tables (`trades.parquet` / `oos_trades.parquet`)
- Monte Carlo samples (`mc_samples.parquet`)

Recommended workflow:
- Treat `outputs/` as a run ledger: one run ID per experiment.
- Record run IDs + commands.

---

## Testing & quality gates

Run unit tests:
```powershell
pytest -q
```

Run pre-commit (lint/format):
```powershell
pre-commit run --all-files
```

CI:
- GitHub Actions runs the same gates on PRs (see `.github/workflows/ci.yml`).


---

## Disclaimer

Meridian is a **research tool**. Results depend on data quality, session definitions, and execution assumptions. Nothing in this repository is financial advice.
