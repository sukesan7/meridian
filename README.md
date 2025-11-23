# 3A Backtester – VWAP Trend Pullback (NQ/ES)

Deterministic, test-driven backtester for **Strategy 3A** – a VWAP trend-pullback intraday strategy on **NQ/ES** during US regular trading hours (RTH).

The goal of this project is to produce a **reproducible research harness** that can answer:

- Does 3A have a real edge across regimes?
- How does it behave by OR size, day-of-week, month, etc.?
- What is realistic MaxDD and CAGR under Monte Carlo?

This repo is structured like a small production quant project: clean package, CLI, tests, CI, and documentation.
---

## Current Status

- **Week 1** – Data & metrics:
  - 1m loader + RTH slice + 5m/30m resample (no look-ahead),
  - OR / VWAP ±σ / ATR15 features,
  - Basic metrics (summary, equity curve, MaxDD, SQN),
  - QQQ dev data pipeline documented.
- **Week 2** – Structure & engine:
  - 5m trend labelling (HH/HL vs LH/LL + VWAP),
  - 1m micro swings,
  - Engine unlock + 2σ disqualifier + first zone per day,
  - Databento NQ/ES futures CSV→Parquet pipeline.

See `docs/week*-notes.md` for full notes.
---

## Strategy 3A

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
    base.yaml                   # Default config (instrument, entry window, risk, filters)
  data/
    .gitkeep                    # Local data only (QQQ/NQ/ES 1-min) – not tracked
    raw/
        databento/
            NQ/                 # Raw Databento CSVs (zstd-decompressed)
            ES/                 # Raw Databento CSVs (zstd-decompressed)
    vendor_parquet/
        NQ/                     # Normalized Parquet for NQ (1-min, ET)
        ES/                     # Normalized Parquet for ES
  docs/
    data-notes.md               # Data schema, tz/DST, RTH, resampling, dev vs prod data
    week1-notes.md              # Notes regarding Week 1 progress
    week2-notes.md              # Notes regarding Week 2 progress
  notebooks/
    README.md                   # Placeholder for future analysis notebooks
  outputs/
    .gitkeep                    # Backtest outputs (trades, summaries) – not tracked
  scripts/
    convert_databento_to_parquet.py     # Helper to normalize vendor CSVs to Parquet
  s3a_backtester/
    __init__.py
    cli.py                      # CLI entrypoint (run-backtest / walkforward / mc)
    config.py                   # Config dataclasses + YAML loader
    data_io.py                  # CSV/Parquet loader, tz handling, RTH slice, resample
    features.py                 # OR/PDH/PDL, VWAP bands, ATR15, 1m swing markers
    structure.py                # 5-min trend labeling (HH/HL vs LH/LL + VWAP)
    engine.py                   # Signal generation: unlock, 2σ disqualifier, zones; trade stub
    slippage.py                 # Slippage models (stub)
    portfolio.py                # R-based sizing & PnL (stub)
    metrics.py                  # Summary stats, equity curve, MaxDD, SQN, group stats
    walkforward.py              # Rolling IS/OOS splits (stub)
    monte_carlo.py              # Monte Carlo simulator on trade series (stub)
  tests/
    test_features.py            # Session refs, VWAP/bands, ATR15, 1m swings
    test_engine.py              # Unlock, zone, 2σ disqualifier, signal schema
    test_metrics.py             # Metrics & equity curve empty-safety and basics
  pyproject.toml                # Build metadata, deps, CLI script `threea-run`
  .pre-commit-config.yaml       # ruff, ruff-format, black, EOF/trailing whitespace
  .editorconfig                 # Consistent editor settings
  .gitattributes                # Text normalization (LF)
  .gitignore                    # Ignore virtualenv, data, outputs, build artifacts
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
