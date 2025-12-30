# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
