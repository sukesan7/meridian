# 3A Backtester – VWAP Trend Pullback (NQ/ES)

Deterministic, test-driven backtester for **Strategy 3A** – a VWAP trend-pullback intraday strategy on **NQ/ES** during US regular trading hours (RTH).

The goal of this project is to produce a **reproducible research harness** that can answer:

- Does 3A have a real edge across regimes?
- How does it behave by OR size, day-of-week, month, etc.?
- What is realistic MaxDD and CAGR under Monte Carlo?

This repo is structured like a small production quant project: clean package, CLI, tests, CI, and documentation.

---

## Current Status (Week 1)

**Focus:** data foundation + deterministic scaffolding.

✅ Implemented

- Python package `s3a_backtester` with CLI entrypoint.
- Data I/O:
  - `load_minute_df` – strict 1-minute OHLCV loader.
  - `slice_rth` – RTH filter (`09:30–16:00` ET, tz-aware, DST-safe).
  - `resample(rule="5min"|"30min")` – right-labeled, right-closed, no look-ahead.
- Session features:
  - `compute_session_refs` – OR (09:30–09:35), `or_high`, `or_low`, `or_height`, PDH/PDL placeholders.
  - `compute_session_vwap_bands` – session-anchored VWAP with ±1σ/±2σ bands.
  - `compute_atr15` – 15-minute ATR over the 1-minute series.
- Tests:
  - I/O + RTH slicing.
  - 5-min and 30-min resample alignment (no peek).
  - OR/VWAP/bands.
  - ATR15.
  - Synthetic DST regression (RTH behavior across the DST switch).
- Docs:
  - `docs/data-notes.md` – data contract (schema, tz/DST, RTH, resampling, dev vs prod data).
- CI:
  - GitHub Actions matrix (Python 3.10/3.11) running pre-commit (ruff/black) + pytest on every push/PR.
  - Protected `main`: changes go through feature branches and PRs.

🚧 Not implemented yet (Week 2+)

- 3A signal generation (trend unlock, pullback zone, triggers).
- Trade simulation & portfolio accounting.
- Walk-forward IS/OOS evaluation.
- Monte Carlo on trade series.

The current code is a **solid data/feature layer** ready for strategy logic.

---

## Strategy 3A – one-paragraph snapshot

3A is a **VWAP trend pullback** strategy on NQ/ES:

- Session: US RTH 09:30–16:00 ET; entries only 09:35–11:00.
- Opening Range (OR): 09:30–09:35 high/low; trend “unlock” when price closes beyond ORH/ORL and aligns with 5-min structure.
- Trend filter: price vs session VWAP + 5-min HH/HL (bull) or LH/LL (bear).
- Location: first pullback into VWAP or ±1σ in trend direction, disqualified if price closes beyond the opposite ±2σ beforehand.
- Trigger: 1-minute engulf or micro swing break out of the pullback.
- Risk: stop 1 tick beyond invalidation swing; reject if stop > 1.25×OR height.
- Management: scale at +1R, runner to BE, TP2 at PDH/PDL / OR measured move / +2R, plus time-stop logic.

The backtester’s job is to encode these rules exactly and test them over 12–24 months of continuous NQ/ES data.

---

## Repository layout

```text
3a-backtester/
  .github/workflows/ci.yml      # CI: pre-commit + pytest (3.10/3.11)
  configs/
    base.yaml                   # Default config (instrument, RTH window, risk params, etc.)
  data/
    .gitkeep                    # Local data only (QQQ/NQ/ES 1-min) – not tracked
  docs/
    data-notes.md               # Data schema, tz/DST, RTH, resampling, dev vs prod data
  notebooks/
    README.md                   # Placeholder for future analysis notebooks
  outputs/
    .gitkeep                    # Backtest outputs (trades, summaries) – not tracked
  s3a_backtester/
    __init__.py
    cli.py                      # CLI entrypoint (run-backtest / walkforward / mc)
    config.py                   # Config dataclasses + YAML loader
    data_io.py                  # CSV/Parquet loader, tz handling, RTH slice, resample
    features.py                 # OR/PDH/PDL, VWAP bands, ATR15, swing helpers
    structure.py                # 5-min trend and micro-structure (stubs in Week 1)
    engine.py                   # Signal generation & trade engine (stubs in Week 1)
    slippage.py                 # Slippage models (stub)
    portfolio.py                # R-based sizing & PnL (stub)
    metrics.py                  # Summary stats, equity curve, SQN
    walkforward.py              # Rolling IS/OOS splits (stub)
    monte_carlo.py              # MC simulator on trade series (stub)
  tests/
    test_io_rth_resample.py     # I/O, RTH slicing, 5/30-min resample, DST
    test_refs_vwap.py           # OR, VWAP ±σ bands
    test_metrics.py             # Metrics empty-safety, basic behaviour
  pyproject.toml                # Build metadata, deps, CLI script `threea-run`
  .pre-commit-config.yaml       # ruff, ruff-format, black, EOF/trailing whitespace
  .editorconfig                 # Consistent editor settings
  .gitattributes                # Text normalization (LF)
  README.md                     # You are here
```
---

# Installation & Setup:

## Requirements:

- Python 3.10 or 3.11 (3.11 recommended).
- Git, virtualenv support
- Pandas / numpty etc. are installed via `pyproject.yaml`.

## 1. Clone the Repo
```bash
git clone https://github.com/sukesan7/3a-backtester.git
```

## 2. Create and Activate a Virtual Environment

**Windows (powershell):**
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

## 3. Install in editable mode (with dev tools)
```bash
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

This installs the package, CLI script `threea-run`, and dev tooling (pytest, ruff, black, pre-commit).

---

# Dev Data (Week 1: QQQ 1-minute)

For Week 1, the engine is being developed against **QQQ 1-minute RTH data** as a stand-in for the NQ/ES futures data.

**1.** Drop a CSV or Parquet file under `data/`, eg:
```text
data/QQQ_1min_2025-04_to_2025-10.csv
```

**2.** Expected columns (see `docs/data-notes.md`):
- `datetime` (UTC or ET, parseable),
- `open`, `high`, `low`, `close`, `volume`,
- optional `symbol`.

**3.** The loader will:
- parse timestamps,
- convert to `America/New_York` (tz-aware),
- sort by time,
- later functions apply RTH slicing and resampling.

Final production runs will use continuous, back-adjusted NQ/ES 1-minute data from a vendor such as Kibot, Barchart, or IQFeed; this is documented but not yet wired.

---
# Quickstart

With your environment activated and dev data in `data/`:
```bash
# Using the installed script
threea-run run-backtest --config configs/base.yaml --data data/QQQ_1min_2025-04_to_2025-10.csv

# Or equivalently:
python -m s3a_backtester.cli run-backtest --config configs/base.yaml --data data/QQQ_1min_2025-04_to_2025-10.csv
```

In Week 1, the "backtest" is essentially a pipeline smoke test:
- load 1-minute data,
- RTH slice,
- resample,
- compute OR/VWAP/bands/ATR,
- run a stub engine,
- print a summary (currently zero trades, stats in R).

Once the engine is implemented (Week 2+), this command will produce a full `trades.csv` and summary under `outputs/`.

---

# Running Tests & Linting

All core guarantees in Week 1 are enforced by tests and pre-commit hooks.

From the project root (with virtual environment active):
```bash
# Run linters/formatters on all files
pre-commit run --all-files

# Run all tests
pytest -q
```

Useful focused test runs:
```bash
pytest -q -k resample     # I/O + 5/30-min resample + no-peek alignment
pytest -q -k refs         # OR, VWAP, bands
pytest -q -k atr15        # ATR15 feature
pytest -q -k dst          # DST regression (RTH window across clock change)
```

CI runs these checks on every push and pull request for Python 3.10 and 3.11.

---

# Development Workflow

The repo is developed via **feature branches + pull requests:**

**1.** Sync `main`:
```bash
git switch main
git pull --ff-only
```

**2.** Create a feature branch:
```bash
git switch -c feat/<short-feature-name>
```

**3.** Work on the code, run:
```bash
pre-commit run --all-files
pytest -q
```

**4.** Commit and push:
```bash
git add -A
git commit -m "feat: short description"
git push -u origin feat/<short-feature-name>
```

**5.** Open a PR on GitHub.
    CI must be green before merging. `main` is protected. Merges are done via **"Squash and Merge"** to keep history clean.

---

# License

This project is licensed under the MIT License. See `LICENSE` for details.
