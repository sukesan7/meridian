# Phase 5: Evaluation Framework & Reporting

**Status:** Complete

**Focus:** Walk-Forward Optimization (WFO), Monte Carlo, Reproducibility

## 1. Objectives
* Implement rigorous validation methods to detect overfitting.
* Generate auditor-grade reports (Tearsheets).
* Verify system determinism (The "Bit-Perfect" Gate).

## 2. Implementation Details

### A. Walk-Forward Analysis
* **Method:** Sliding Window (Train/Test).
* **Configuration:** 63 Days In-Sample (IS) / 21 Days Out-of-Sample (OOS).
* **Goal:** Verify that OOS performance does not degrade significantly compared to IS performance.

### B. Monte Carlo Simulation
* **Method:** Block Bootstrap resampling of realized trade returns.
* **Iterations:** 2,500 paths.
* **Goal:** Estimate `Max Drawdown (95% CI)` and `Risk of Ruin`.

### C. Determinism Gate
We implemented a strict regression test in CI.
* **Procedure:** Run Backtest A $\to$ Run Backtest B (same seed).
* **Check:** SHA-256 hash of `trades.parquet` must be identical.

## 3. Proof & Verification

### Verified Contracts
* **Determinism:** CI fails if artifacts differ by even 1 byte.
* **Robustness:** See [`docs/system/STRATEGY_RESULTS.md`](../system/STRATEGY_RESULTS.md) for the latest generated metrics.

### Artifacts
* **Performance Report:** `assets/performance.png`
* **Run Metadata:** `outputs/.../run_meta.json` (Contains Config + Seed).

### Test Coverage
| Invariant | Test ID |
| :--- | :--- |
| **Determinism** | `scripts/verify_determinism.py` (Run in CI) |
| **WFO Window Logic** | `tests/test_optimization.py::test_wfo_window_generation` |
| **Monte Carlo Seed** | `tests/test_reporting.py::test_monte_carlo_reproducibility` |

## 4. Known Limitations
1.  **Trade Scarcity:** Strategy 3A is low-frequency. Confidence intervals on Expectancy are wide.
2.  **Partial Days:** Holidays are treated as normal sessions; reduced liquidity on these days is not modeled.
3.  **Execution Model:** We assume full liquidity at the touch (no order book queue modeling).

## 5. Definition of Done
- WFO Engine Implemented
- Monte Carlo Engine Implemented
- Determinism Script in CI
- Final Documentation Audited
