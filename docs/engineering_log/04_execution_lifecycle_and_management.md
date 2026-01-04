# Phase 4: Execution Lifecycle & Management

**Status:** Complete

**Focus:** Event-Driven Simulation, Order State Machine, Slippage

## 1. Objectives
* Simulate a realistic exchange matching engine.
* Manage trade lifecycle: Entry $\to$ TP1 (Scale) $\to$ TP2 (Exit) or Stop.
* Enforce RTH boundary exits (Time Stop).

## 2. Implementation Details

### A. The Event Loop
The `simulate_trades` function iterates bar-by-bar.
* **Fill Logic:** "Next Open" execution. A signal at bar $i$ fills at $Open_{i+1}$.
* **Slippage:** Deterministic penalty applied to every fill.
    * Entry: `Price + 1 tick`
    * Stop: `Price - 1 tick`

### B. Execution Invariants
To ensure simulation integrity, the engine adheres to strict ordering rules within a single bar:
1.  **Check Open:** Gap fills (Stop/TP triggered on Open).
2.  **Check High/Low:** Intra-bar fills.
    * *Conflict Resolution:* If a bar hits both Stop and TP, the Stop is assumed to hit first (Conservative/Pessimistic assumption).
3.  **Check Time:** If `timestamp == 15:59`, force exit.

### C. Position Management
* **Breakeven:** Moved to Entry Price once TP1 is hit.
* **Partials:** TP1 exits 50% of the position. Realized R is calculated on the closed portion immediately.

## 3. Proof & Verification

### Verified Contracts
* **Pessimistic Fills:** Verified that in a "Stop & TP in same bar" scenario, the result is a Loss.
* **RTH Enforcement:** Verified no positions remain open after 16:00 ET.
* **No Multi-Day Bleed:** Verified that position state is flushed at EOD.

### Artifacts
* **Trade Log:** `outputs/backtest/.../trades.parquet` (Contains `exit_reason` column).

### Test Coverage
| Invariant | Test ID |
| :--- | :--- |
| **Next Open Fill** | `tests/test_engine_simulate_trades.py::test_fill_on_next_open` |
| **Stop vs TP Priority** | `tests/test_engine_simulate_trades.py::test_conflict_resolution_stop_first` |
| **Time Stop** | `tests/test_engine_simulate_trades.py::test_eod_forced_exit` |
| **Breakeven Logic** | `tests/test_engine_simulate_trades.py::test_move_to_breakeven` |

## 4. Definition of Done
- Execution Engine Implemented (`s3a_backtester/engine.py`)
- Slippage Model Configured
- Trade Lifecycle Tests Verified
- CI Tests Green
