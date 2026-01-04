# Phase 2: Market Structure & Feature Pipeline

**Status:** Complete

**Focus:** Vectorized Feature Engineering, Swing Detection Causality

## 1. Objectives
* Build a high-performance `FeatureEngineer` class.
* Implement **Causal Swing Detection** (identifying pivots without looking ahead).
* Calculate core indicators: VWAP, Opening Range (OR), and 5m Trends.

## 2. Implementation Details

### A. Vectorized Calculation
To meet performance targets (<15s backtest), we utilize Pandas/NumPy vectorization.
* **Resampling:** `trend_5m` logic aggregates 1m bars into 5m blocks using `label='right', closed='right'`.

### B. Swing Detection & Causality
We use a **Fractal Swing** definition (High of Highs).
* **Algorithm:** `find_swings_1m` looks for a peak surrounded by lower highs.
* **The Lookahead Trap:** A peak at time $t$ is mathematically unknowable until time $t + k$ (where $k$ is the confirmation window).
* **Causality Semantics:**
    * **Swing Time:** The timestamp of the pivot itself ($t$).
    * **Confirmation Time:** The timestamp when the pattern completes ($t + k$).
    * **Usage Rule:** Signals generated at time $\tau$ can ONLY reference swings where $Confirmation Time \le \tau$.

### C. Indicator Invariants
* **VWAP:** Anchored to 09:30 ET. Reset daily.
* **Opening Range:** Defined strictly as 09:30–09:35. `or_high` and `or_low` are forward-filled for the remainder of the session.

## 3. Proof & Verification

### Verified Contracts
* **No Peeking:** Verified that `last_swing_high` for a given bar corresponds to a swing confirmed *before* that bar's close.
* **Resampling:** Verified that a 5m bar labeled 10:00 contains data from 09:55:01–10:00:00.

### Test Coverage
| Invariant | Test ID |
| :--- | :--- |
| **Swing Causality** | `tests/test_features.py::test_swing_detection_no_lookahead` |
| **OR Logic** | `tests/test_features.py::test_opening_range_calculation` |
| **Resampling Bounds** | `tests/test_features.py::test_resample_right_edge_labeling` |
| **VWAP Reset** | `tests/test_features.py::test_vwap_daily_reset` |

## 4. Definition of Done
- Feature Engine Implemented (`s3a_backtester/features.py`)
- Swing Detection Causality Verified
- Performance Benchmarks Met (< 200ms for feature gen)
- Unit Tests Green
