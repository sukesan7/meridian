# Phase 3: Signal Generation & Risk Controls

**Status:** Complete

**Focus:** Strategy Logic, State Gating, Risk Invariants

## 1. Objectives
* Implement Strategy 3A logic (Unlock $\to$ Zone $\to$ Trigger) as defined in [`docs/system/STRATEGY_SPEC.md`](../system/STRATEGY_SPEC.md).
* Enforce hard Risk Caps (Max R per trade).
* Implement "Disqualification" logic (2-Sigma Band touches).

## 2. Implementation Details

### A. The Signal Pipeline
Signals are generated via a vectorized pass over the feature frame.
1.  **Unlock:** Check if `Close > OR_High` (Long) or `Close < OR_Low` (Short).
2.  **Zone:** Check for pullbacks into `[VWAP, Band]`.
3.  **Trigger:** Check for Micro-Structure Break (BOS).

### B. Risk Invariants
To prevent execution errors, the signal generator enforces strict data validation *before* passing orders to the engine.
* **Tick Rounding:** All `stop_price` and `entry_price` values are rounded to the nearest instrument tick (0.25 for NQ).
* **Minimum Risk:** If `|Entry - Stop| < 4 ticks`, the trade is rejected (Noise).
* **Maximum Risk:** If `|Entry - Stop| > 1.25 * OR_Height`, the trade is rejected (Volatility Cap).

### C. State Gating
* **2-Sigma Rule:** If price touches the *opposing* 2-sigma band, the session is flagged `disqualified_2sigma = True`. No further signals are generated for that session.

## 3. Proof & Verification

### Verified Contracts
* **Gating:** Verified that no signals exist after a 2-sigma violation.
* **Risk Cap:** Verified that no trades exceed the defined R-risk max width.

### Test Coverage
| Invariant | Test ID |
| :--- | :--- |
| **Signal Logic** | `tests/test_engine_generate_signals.py::test_long_entry_logic` |
| **Risk Cap** | `tests/test_engine_generate_signals.py::test_risk_cap_rejection` |
| **Disqualification** | `tests/test_engine_generate_signals.py::test_2sigma_disqualification` |
| **Tick Rounding** | `tests/test_engine_generate_signals.py::test_price_rounding` |

## 4. Definition of Done
- Strategy Logic Implemented (`s3a_backtester/logic.py`)
- Risk Invariants Defined and Enforced
- Configuration Schema Validated
- CI Tests Green
