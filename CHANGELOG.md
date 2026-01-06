# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v1.0.6] - 2026-01-06
### Fixed
- **Data Integrity (No Look-Ahead):** Corrected 1m→5m aggregation alignment to enforce “closed bars only” semantics at decision time (prevents higher-timeframe session leakage).
- **Execution Integrity (No Execution Leak):** Enforced market data as the single source of truth for fills and lifecycle bars (next-bar-open execution and management now reference the market tape, not the signals frame).
- **CI / Typing:** Resolved mypy regressions introduced by timestamp/index handling changes during the causality patch.

### Added
- **Provenance / Auditability:** End-to-end SHA256 hashing recorded in `run_meta.json` (config + artifact hashes; optional input-data hashing) to make runs tamper-evident and reviewer-auditable.
- **Regression Harness:** A/B trade-ledger diff workflow to quantify behavioral deltas after integrity patches and catch future causality regressions.

### Changed
- **Engine Contracts:** Formalized “next-open causality” and “market-frame source-of-truth” invariants via targeted tests to prevent reintroducing look-ahead or execution leakage.

## [v1.0.5] - 2026-01-04
### Fixed
- **Core Engine:** Removed non-ASCII characters (`±`, `σ`) from column names in `engine.py` to satisfy Linux/Windows cross-platform audit requirements.
- **CI/CD:** Hardened GitHub Actions pipeline:
  - Upgraded runner to `ubuntu-24.04`.
  - Added `PYTHONHASHSEED: "0"` for strict hash determinism.
  - Enforced `pip install --no-deps -r requirements.lock` to prevent dependency drift.
- **Developer Experience:** Updated VS Code configuration (`settings.json`, `extensions.json`) to enforce Ruff formatting and handle Line Endings (LF) automatically on Windows.

### Documentation
- **Synchronized:** Updated `ARCHITECTURE`, `PERFORMANCE`, and `STRATEGY_SPEC` to match the actual v1.0.5 codebase.
- **Benchmarks:** Updated performance stats with real profiling data (Backtest: ~13.3s, Monte Carlo: ~0.49s).
- **Engineering Logs:** Converted `docs/engineering_log/` from a dev diary into a verifiable Audit Trail with strict invariant references.
- **Visuals:** Updated `assets/` with new Equity Curve and Strategy Logic proofs showing v1.0.5 behavior.

### Changed
- **Tearsheet:** Upgraded `generate_tearsheet.py` to produce higher-grade reports (Rolling Win Rate, Drawdown Duration, Monthly Returns).

## [v1.0.4] - 2026-01-02
### Fixed
- **Time Contract:** Standardized internal timestamps to "Bar-Start" convention (Model A). Logic at `09:30:00` uses `09:30` bar data; execution occurs at `09:31` (Next Open).
- **Risk Decoupling:** Removed risk checks from `generate_signals` to prevent execution logic from leaking into the signal layer. Risk is now enforced exclusively in `simulate_trades`.
- **Schema:** Added `signal_time` to the `trades.parquet` schema to prove causal separation between Signal and Entry.

### Changed
- **Determinism:** Renamed "Bit-Perfect Identity" to **"Semantic Determinism"** in all verify scripts and CI steps to accurately reflect float tolerance handling.
- **Data Pipeline:** Standardized naming convention to `NQ.v.0_{START}_{END}_RTH.parquet` and added strict session boundary checks (No cross-session forward-fill).

## [v1.0.3] - 2025-12-30
### Critical Integrity Patch
This release establishes the "Verified Baseline" for Strategy 3A, addressing critical look-ahead bias and execution gating issues identified during the initial code audit. It also introduces strict dependency locking and performance visualization.

### Fixed
- **Look-Ahead Bias in `filters.py`:** The ATR volatility filter previously used EOD data to gate intraday trades. Fixed by explicitly lagging the regime calculation by one session (`.shift(1)`).
- **Gap Risk Gating in `engine.py`:** The Risk Cap check previously used the signal price instead of the true fill price. Logic updated to calculate `risk_per_unit` *after* applying the open/gap fill price, rejecting trades that gap beyond the 1.25x limit.
- **Slippage Timestamp:** `slippage.py` now receives the timestamp of the *fill* (Bar `i+1`) rather than the *signal* (Bar `i`), ensuring correct "Hot Window" penalties are applied.
- **Metadata Provenance:** `run_meta.py` now hashes the `st_mtime` (modification time) of input data files instead of the execution timestamp, ensuring reproducible data versioning.

### Added
- **Dependency Locking:** Added `requirements.lock` generation and verification in `run_meta.py` metadata artifacts.
- **Performance Verification:** Added `assets/v1_0_3_performance.png` demonstrating the realistic equity curve with regime-dependent drawdowns.
- **Data Audit:** Added `assets/nq_session_density.png` and `assets/nq_volatility_regime.png` to validate input data integrity.

### Changed
- **README Claims:** Downgraded claims from "Bit-perfect reproducibility" to "Semantic Determinism" to better reflect cross-platform floating-point realities.
- **Typing Strictness:** Updated documentation to reflect CI-enforced `mypy` typing without promising "No Any" absolutes.

---

## [v1.0.2] - 2025-12-29
### Logic Hardening
Refinement of the core Finite State Machine (FSM) following the initial v1.0.0 release.

### Fixed
- **FSM State Transitions:** Corrected edge cases in the "Unlock -> Zone -> Trigger" sequence where state could bleed across session boundaries.
- **Signal Forward-Filling:** Fixed issue where trend direction was not correctly propagated through the session.

---

## [v1.0.0] - 2025-12-26
### Initial Production Release
First "Production-Grade" release of the Meridian Engine. Validated end-to-end execution of Strategy 3A on Nasdaq-100 futures data.

### Added
- **Unified CLI:** `meridian-run` entrypoint supporting `backtest`, `walkforward`, and `monte-carlo` modes.
- **Metrics Engine:** Standardized reporting of Expectancy, SQN, and MaxDD via `metrics.py`.
- **Walk-Forward Analysis:** Rolling IS/OOS validation engine to detect overfitting.
- **Monte Carlo:** Block-bootstrap simulation to estimate tail risks.
- **Data Pipeline:** Full integration with Databento parquet schema (`NQ.v.0`).

---

## [v0.5.0] - 2025-12-21
### Validation & Reporting
Focused on statistical validation tools and reporting infrastructure.

### Added
- `metrics.summary()`: Standardized JSON output for trade logs.
- `walkforward.py`: Implementation of 63-day Train / 21-day Test rolling windows.
- `monte_carlo.py`: Bootstrapping engine for equity curve simulation.
- **Timezone QA:** Strict enforcement of `America/New_York` conversion at load time.

### Fixed
- **MaxDD Anchoring:** Corrected drawdown calculation to anchor equity curves at 0, preventing "0 Drawdown" reports on losing start sequences.

---

## [v0.4.0] - 2025-12-18
### Management & Filters
Introduction of the full trade lifecycle and session-level gating.

### Changed
- **Project Rename:** Renamed internal project identifier to **Meridian**.

### Added
- **Trade Management:** `management.py` implementing TP1 scaling, Break-Even stops, and TP2 arbitration.
- **Time-Based Exits:** Logic to force exit after `n` minutes if targets aren't met.
- **Session Filters:** `filters.py` to gate trading on "Tiny Range" days or News Blackouts.
- **Continuous Futures:** Added `scripts/databento_fetch_continuous.py` for credit-safe data ingestion.

---
## [1.0.5] - 2026-01-04
### Fixed
- **Core Engine:** Removed non-ASCII characters (`±`, `σ`) from column names in `engine.py` to satisfy Linux/Windows cross-platform audit requirements.
- **CI/CD:** Hardened GitHub Actions pipeline:
  - Upgraded runner to `ubuntu-24.04`.
  - Added `PYTHONHASHSEED: "0"` for strict hash determinism.
  - Enforced `pip install --no-deps -r requirements.lock` to prevent dependency drift.
- **Developer Experience:** Updated VS Code configuration (`settings.json`, `extensions.json`) to enforce Ruff formatting and handle Line Endings (LF) automatically on Windows.

### Documentation
- **Synchronized:** Updated `ARCHITECTURE`, `PERFORMANCE`, and `STRATEGY_SPEC` to match the actual v1.0.5 codebase.
- **Benchmarks:** Updated performance stats with real profiling data (Backtest: ~13.3s, Monte Carlo: ~0.49s).
- **Engineering Logs:** Converted `docs/engineering_log/` from a dev diary into a verifiable Audit Trail with strict invariant references.
- **Visuals:** Updated `assets/` with new Equity Curve and Strategy Logic proofs showing v1.0.5 behavior.

### Changed
- **Tearsheet:** Upgraded `generate_tearsheet.py` to produce institutional-grade reports (Rolling Win Rate, Drawdown Duration, Monthly Returns).

## [1.0.4] - 2026-01-04
### Fixed
- **Time Contract:** Standardized internal timestamps to "Bar-Start" convention (Model A). Logic at `09:30:00` uses `09:30` bar data; execution occurs at `09:31` (Next Open).
- **Risk Decoupling:** Removed risk checks from `generate_signals` to prevent execution logic from leaking into the signal layer. Risk is now enforced exclusively in `simulate_trades`.
- **Schema:** Added `signal_time` to the `trades.parquet` schema to prove causal separation between Signal and Entry.

### Changed
- **Determinism:** Renamed "Bit-Perfect Identity" to **"Semantic Determinism"** in all verify scripts and CI steps to accurately reflect float tolerance handling.
- **Data Pipeline:** Standardized naming convention to `NQ.v.0_{START}_{END}_RTH.parquet` and added strict session boundary checks (No cross-session forward-fill).


## [v0.3.0] - 2025-11-27
### Triggers & Risk
Implementation of the entry execution logic.

### Added
- **Micro-Structure Trigger:** `structure.micro_swing_break()` to identify fractal entries.
- **Risk Gating:** Logic to calculate Stop Loss distance based on prior swing lows.
- **Risk Cap:** Hard rejection of trades where Stop Distance > 1.25x Opening Range.
- **Slippage Model:** `slippage.py` with configurable "Hot Window" friction.

---

## [v0.2.0] - 2025-11-22
### Structure & State
Development of the core price action structure and state machine foundation.

### Added
- **Trend Logic:** `structure.trend_5m()` for higher-timeframe alignment.
- **Swing Detection:** `features.find_swings_1m()` for pivot identification.
- **State Machine Stubs:** Initial implementation of `generate_signals` (Unlock/Zone logic).
- **Parquet Normalization:** Scripts to convert raw vendor CSVs to strict Arrow schema.

---

## [v0.1.0] - 2025-11-16
### Data Foundation
Initial scaffolding of the data IO and feature engineering layer.

### Added
- **Data IO:** `load_minute_df` with strict schema validation.
- **RTH Slicing:** Filtering logic for 09:30–16:00 ET sessions.
- **Session Features:** `compute_session_refs` (OR High/Low) and `compute_atr15`.
- **CI/CD:** Initial GitHub Actions workflow for linting (Ruff) and testing (Pytest).
