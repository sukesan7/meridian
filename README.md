# Meridian

[![CI](https://img.shields.io/github/actions/workflow/status/sukesan7/meridian/ci.yml?branch=main&label=CI&logo=github)](https://github.com/sukesan7/meridian/actions)
[![Coverage](https://img.shields.io/codecov/c/github/sukesan7/meridian?token=TOKEN&logo=codecov)](https://codecov.io/gh/sukesan7/meridian)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: Mypy](https://img.shields.io/badge/type_checked-mypy-blue.svg)](https://mypy-lang.org/)

**Meridian** is a deterministic, event-driven backtesting engine designed for the simulation of intraday futures strategies. It prioritizes correctness, reproducibility, and strict session handling over raw execution speed, serving as a rapid prototyping environment for **Strategy 3A** (VWAP Trend Pullback) logic.

---

## 1. Core Philosophy

Quantitative infrastructure often suffers from lookahead bias, implicit assumptions, and irreproducibility. Meridian addresses these by enforcing a strict **State Machine** architecture for signal generation and trade management.

* **Deterministic Execution:** Identical data, configuration, and seeds guarantee bit-perfect identical artifacts.
* **No Lookahead:** Signal logic is causally strictly enforced; future bars are inaccessible during the decision phase.
* **Session-Aware:** Native handling of exchange timezones (America/New_York) and RTH/ETH boundaries.
* **Realistic Simulation:** Models execution friction including spread, slippage (time-variant), and time-based forced exits.
* **Stateful Logic:** Supports multi-stage signal progression (`Unlock` $\to$ `Zone` $\to$ `Trigger`) rather than simple vector cross-overs.

---

## 2. System Architecture

The engine operates as a unidirectional pipeline, transforming raw vendor data into auditable trade artifacts.

### Data Flow
1.  **Ingestion:** Raw 1-minute OHLCV is normalized to a strict parquet schema.
2.  **Feature Engineering:** Session-scoped indicators (Opening Range, Anchored VWAP, ATR) are computed.
3.  **Signal Generation:** A vectorized state machine identifies valid setups based on market structure.
4.  **Execution Simulation:** An event loop processes signals, applying risk rules, slippage models, and lifecycle management (TP/SL).
5.  **Robustness Analysis:** Walk-Forward Optimization (WFO) and Monte Carlo methods validate parameter stability.

### Repository Layout
```text
.
├── .github/workflows/                 # CI/CD pipeline definition
├── configs/                           # Strategy execution parameters
├── data/                              # Data lake (excluded from git)
│   ├── raw/                           # Immutable source data
│   └── vendor_parquet/                # Normalized, RTH-sliced schema
├── docs/                              # System documentation & engineering logs
├── notebooks/                         # Research & prototyping environment
├── s3a_backtester/                    # Core package source
│   ├── cli.py                         # Entrypoint (backtest / walkforward / mc)
│   ├── engine.py                      # Signal state machine & event loop
│   ├── management.py                  # Trade lifecycle (TP/SL/Time-stops)
│   ├── walkforward.py                 # Rolling IS/OOS validation engine
│   ├── monte_carlo.py                 # Bootstrap resampling engine
│   └── ...                            # Helper modules (features, slippage, etc.)
├── scripts/                           # Utility scripts (ETL, Reporting)
│   ├── databento_fetch_continuous.py
│   ├── normalize_continuous_to_vendor_parquet.py
│   ├── make_report.py
│   └── quickstart.ps1                 # One-click demo runner
├── tests/                             # Unit & Integration suite (pytest)
├── pyproject.toml                     # Dependency management
└── README.md
```

---

## 3. Quick Start

### Prerequisites
* Python 3.10+
* Dependencies: `pandas`, `numpy`, `pyarrow`, `scipy`, `pyyaml`

### Installation
```bash
# Clone the repository
git clone [https://github.com/sukesan7/meridian.git](https://github.com/sukesan7/meridian.git)
cd meridian

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install strictly pinned dependencies
pip install -e ".[dev]"
```

### Running a Demo Simulation
To validate the installation without requiring proprietary data, run the test suite which generates synthetic market data on the fly:

```bash
# Run full test suite with verbose output
pytest -v
```

---

## 4. Operational Workflow

Meridian exposes a CLI entrypoint `meridian-run` (or `threea-run`) for all simulation modes.

### A. Standard Backtest
Runs a single simulation over a fixed period.

```bash
meridian-run backtest \
  --config configs/base.yaml \
  --data data/vendor_parquet/NQ/NQ_2024_RTH.parquet \
  --run-id nq_research_01
```
* **Artifacts:** `summary.json`, `trades.parquet`, `signals.parquet`

### B. Walk-Forward Analysis (WFO)
Performs rolling window validation (e.g., 3-month In-Sample, 1-month Out-of-Sample) to test parameter stationarity.

```bash
meridian-run walkforward \
  --config configs/base.yaml \
  --data data/vendor_parquet/NQ/NQ_2024_RTH.parquet \
  --is-days 63 --oos-days 21 \
  --run-id nq_wfo_01
```
* **Artifacts:** `is_summary.csv`, `oos_summary.csv`, `oos_trades.parquet`

### C. Monte Carlo Simulation
Applies bootstrap resampling (IID or Block) to the trade distribution to estimate tail risks.

```bash
meridian-run monte-carlo \
  --config configs/base.yaml \
  --trades-file outputs/backtest/nq_research_01/trades.parquet \
  --n-paths 2000 --risk-per-trade 0.01 \
  --run-id nq_mc_01
```
* **Artifacts:** `mc_samples.parquet`, `summary.json` (Drawdown & CAGR distributions)

---

## 5. Engineering Standards & Quality Gates

This project enforces strict software engineering standards suitable for production environments.

* **Static Typing:** Fully typed codebase verified by `mypy --strict`. No `Any` types allowed in core logic.
* **Linting & Formatting:** Enforced via `ruff` (replaces Flake8/Black/Isort) for consistent style.
* **CI/CD Pipeline:** GitHub Actions automatically runs the test suite and type checkers on every push/PR.
* **Pre-Commit Hooks:** Local guardrails prevent committing failing code or large data files.

To run the quality suite locally:
```bash
pre-commit run --all-files
```

---

## 6. Data Contract

Meridian requires 1-minute OHLCV data normalized to the `vendor_parquet` schema.

**Expected Columns:**
* `timestamp` (DatetimeTZ, UTC)
* `open`, `high`, `low`, `close` (Float64)
* `volume` (Float64/Int64)

**Pipeline Note:**
The engine internally converts UTC timestamps to `America/New_York` to align with US Equity Futures session timings (RTH 09:30 - 16:00 ET).

---

## 7. Roadmap (v2.0.0)
* **Performance:** Migration of `engine.py` from Pandas/NumPy to **Polars** (Rust) for improved vectorization performance and lower memory footprint.
* **Multi-Asset Support:** Architecture upgrades to support execution logic on ES (S&P 500), Equities, and ETFs.
* **Optimization:** Integration of a genetic optimizer for parameter tuning.

---

## Disclaimer

**Educational & Research Use Only.**
Meridian is a software tool for quantitative analysis. It does not constitute financial advice. Past performance in simulation is not indicative of future results in live trading. Execution models are approximations and cannot fully replicate live market microstructure (latency, queue position, impact).
