# 3A Backtester – VWAP Trend Pullback (NQ/ES)

Deterministic, test-driven backtester for **Strategy 3A** – a VWAP trend-pullback intraday strategy on **NQ/ES** during US regular trading hours (RTH).

The goal of this project is to produce a **reproducible research harness** that can answer:

- Does 3A have a real edge across regimes?
- How does it behave by OR size, day-of-week, month, etc.?
- What is realistic MaxDD and CAGR under Monte Carlo?

This repo is structured like a small production quant project: clean package, CLI, tests, CI, and documentation.

---

## Current Status (end of Week 3)

- **Week 1 – Data & metrics**
  - 1-minute loader + RTH slice + 5m/30m resample (no look-ahead).
  - Session refs: OR / PDH / PDL, VWAP ±σ bands, ATR15.
  - Core metrics: summary stats, equity curve in R, MaxDD (R), SQN, grouped stats by arbitrary column.
  - Data contract + dev vs prod split (QQQ vs NQ/ES) documented in `docs/data-notes.md`.

- **Week 2 – Structure & engine scaffolding**
  - 5-minute trend labeling (HH/HL vs LH/LL + VWAP filter).
  - 1-minute swing markers (swing highs/lows).
  - Engine unlock & structure:
    - OR break unlock,
    - ±2σ disqualifier,
    - first valid trading zone per day.
  - Databento NQ/ES futures CSV→Parquet normalization script; IO / RTH / resample behavior covered by tests.

- **Week 3 – Triggers, risk, entry-side trade simulation**
  - Micro-structure trigger:
    - 1-minute micro-swing break + body engulf pattern,
    - combined into a direction signal and wired into `trigger_ok`.
  - Risk logic:
    - Stop = 1 tick beyond invalidation swing.
    - Risk-cap: reject trades if stop distance > 1.25 × OR height.
  - Trade simulation:
    - `simulate_trades` implemented for **entry-side** simulation:
      - slippage-aware entries using time-of-day model,
      - computes per-trade risk distance in ticks and R,
      - fills a normalized trade log schema with TP1/TP2 placeholders and metadata (OR height, slippage, trigger type, etc.).
  - Slippage:
    - Time-of-day slippage model (normal vs “hot” windows) implemented and tested.
  - Tests & docs:
    - Dedicated tests for structure (trend + micro-swing/engulf), slippage, signal generation, and trade simulation (`test_engine_week3.py`).
    - `docs/week3-notes.md` captures trigger, risk-cap, slippage, and trade-log design.
  - **Not yet implemented (targeted for Weeks 4–6):**
    - Management (TP1/TP2, time-stop),
    - walk-forward,
    - Monte Carlo.

See `docs/week*-notes.md` for full notes.

---

## Strategy 3A

3A is a **VWAP trend pullback** strategy on NQ/ES:

- Session: US RTH 09:30–16:00 ET; entries only 09:35–11:00.
- Opening Range (OR): 09:30–09:35 high/low; trend “unlock” when price closes beyond ORH/ORL and aligns with 5-min structure.
- Trend filter: price vs session VWAP + 5-min HH/HL (bull) or LH/LL (bear).
- Location: first pullback into VWAP or ±1σ in trend direction, disqualified if price closes beyond the opposite ±2σ beforehand.
- Trigger: 1-minute engulf or micro-swing break out of the pullback.
- Risk: stop 1 tick beyond invalidation swing; reject if stop > 1.25×OR height.
- Management (design target for Week 4+): scale at +1R, runner to BE, TP2 at PDH/PDL / OR measured move / +2R, plus time-stop logic.

The backtester’s job is to encode these rules exactly and test them over 12–24 months of continuous NQ/ES data.

---

## Repository Layout

```text
3a-backtester/
  .github/workflows/ci.yml      # CI: pre-commit + pytest (3.10/3.11)

  configs/
    base.yaml                   # Default config (instrument, entry window, risk-cap, filters, slippage, mgmt)

  data/
    .gitkeep                    # Local data only (QQQ/NQ/ES 1-min) – not tracked
    raw/
      databento/
        NQ/                     # Raw Databento CSVs (zstd-decompressed)
        ES/                     # Raw Databento CSVs (zstd-decompressed)
    vendor_parquet/
      NQ/                       # Normalized 1-min Parquet for NQ (ET)
      ES/                       # Normalized 1-min Parquet for ES (ET)

  docs/
    data-notes.md               # Data schema, tz/DST, RTH, resampling, dev vs prod data
    week1-notes.md              # Notes regarding Week 1 progress (data, metrics)
    week2-notes.md              # Notes regarding Week 2 progress (structure, engine scaffolding)
    week3-notes.md              # Notes regarding Week 3 progress (triggers, risk-cap, entry sim, slippage)

  notebooks/
    README.md                   # Placeholder for future analysis notebooks

  outputs/
    .gitkeep                    # Backtest outputs (trades, summaries) – not tracked

  s3a_backtester/
    __init__.py
    cli.py                      # CLI entrypoint (run-backtest / run-walkforward / run-mc)
    config.py                   # Config dataclasses + YAML loader (entry window, filters, mgmt, etc.)
    data_io.py                  # CSV/Parquet loader, tz handling, RTH slice, resample
    features.py                 # OR/PDH/PDL, VWAP bands, ATR15, 1m swing markers
    structure.py                # 5-min trend labeling + micro-swing/engulf structure
    engine.py                   # Signal generation + entry-side trade simulation (Week 3)
    slippage.py                 # Time-of-day slippage model (normal vs hot windows)
    portfolio.py                # R-based sizing & PnL (stub for later weeks)
    metrics.py                  # Summary stats, equity curve, MaxDD, SQN, grouped stats
    walkforward.py              # Rolling IS/OOS splits (stub for Week 5)
    monte_carlo.py              # Monte Carlo simulator on trade series (stub for Week 5)

  scripts/
    convert_databento_to_parquet.py  # Databento CSV→Parquet normalizer
    debug_signals_qqq.py        # Dev plotting/debug script for QQQ

  tests/
    __init__.py
    utils.py                    # Shared helpers for tests (random OHLCV generators, etc.)
    test_io_rth_resample.py     # Data IO, RTH slicing, 5m/30m resampling behavior
    test_features.py            # Session refs, VWAP/bands, ATR15, 1m swing markers
    test_refs_vwap.py           # VWAP/bands reference checks
    test_structure.py           # 5m trend + micro-swing/engulf structure
    test_slippage.py            # Slippage model (normal vs hot tick behavior)
    test_engine.py              # Signal generation: unlock, zones, disqualifiers, signal schema
    test_engine_week3.py        # Trade simulation (entry-side) + risk-cap + slippage
    test_metrics.py             # Metrics & equity curve empty-safety and basics

  pyproject.toml                # Build metadata, deps, CLI script `threea-run`
  .pre-commit-config.yaml       # ruff, ruff-format, black, EOF/trailing whitespace
  .editorconfig                 # Consistent editor settings
  .gitattributes                # Text normalization (LF)
  .gitignore                    # Ignore virtualenv, data, outputs, build artifacts
  README.md                     # You are here
```

---

# Installation & Setup

## Requirements

- Python 3.10 or 3.11 (3.11 recommended).
- Git, virtualenv support.
- `pandas`, `numpy`, `pyyaml`, `pyarrow`, `scipy` etc. are installed via `pyproject.toml`.

### 1. Clone the repo

```bash
git clone https://github.com/sukesan7/3a-backtester.git
cd 3a-backtester
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. Install in editable mode (with dev tools)

```bash
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

This installs the package, CLI script `threea-run`, and dev tooling (pytest, ruff, black, pre-commit).

---

# Quickstart

With your environment activated and dev/fixture data in `data/`:

```bash
# Using the installed script
threea-run run-backtest --config configs/base.yaml --data data/QQQ_1min_2025-04_to_2025-10.csv

# Or equivalently:
python -m s3a_backtester.cli run-backtest --config configs/base.yaml --data data/QQQ_1min_2025-04_to_2025-10.csv
```

- For **dev**, you can point `--data` at any 1-minute CSV/Parquet in the expected schema (see `docs/data-notes.md`), e.g. QQQ.
- For **futures**, you typically generate 1-minute Parquet via `scripts/convert_databento_to_parquet.py` and then pass the resulting file path into `--data`.

The CLI will:

1. Load data and slice RTH.
2. Compute OR/refs, VWAP ±σ, ATR15, swings, micro-structure.
3. Generate 3A signals and simulate trades (entry-side, with slippage).
4. Print a summary to stdout and (in later weeks) write trades/metrics under `outputs/`.

---

# Running Tests & Linting

All core guarantees implemented through **Week 3** (data contract, refs, structure, slippage, signal generation, entry-side trade simulation, metrics) are enforced by tests and pre-commit hooks.

From the project root (with virtual environment active):

```bash
# Run linters/formatters on all files
pre-commit run --all-files

# Run all tests
pytest -q
```

CI runs these checks on every push and pull request for Python 3.10 and 3.11.

---

# Development Workflow

The repo is developed via **feature branches + pull requests**:

1. Sync `main`:

   ```bash
   git switch main
   git pull --ff-only
   ```

2. Create a feature branch:

   ```bash
   git switch -c feat/<short-feature-name>
   ```

3. Work on the code, run:

   ```bash
   pre-commit run --all-files
   pytest -q
   ```

4. Commit and push:

   ```bash
   git add -A
   git commit -m "feat: short description"
   git push -u origin feat/<short-feature-name>
   ```

5. Open a PR on GitHub.
   CI must be green before merging. `main` is protected. Merges are done via **“Squash and Merge”** to keep history clean.

---

# License

This project is licensed under the MIT License. See `LICENSE` for details.
