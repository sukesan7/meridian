# Phase 3: Signal Generation & Risk Controls

## 1. Objective
Wire the structural components into a cohesive `SignalGenerator` and implement entry-level risk controls (Risk Caps) to reject invalid setups before execution.

## 2. Key Implementations

### 2.1 Trigger Logic (`trigger_ok`)
* **Micro-Structure Triggers**:
    * Implemented `micro_swing_break`: Detects price breaking the most recent 1-minute swing high/low.
    * **Causality Check:** Verified that logic does not "peek" at swings formed in the future.
* **Zone Proximity Filters**:
    * Added "No Chase" logic: Triggers are valid only if price is within 1 tick of the VWAP band.

### 2.2 Risk Management (Pre-Trade)
* **Risk Cap Enforcement**:
    * Defined `Max SL Distance` as a function of OR Height (e.g., `1.25 * OR_Height`).
    * **Rejection Logic:** If `(Entry - Stop) > Max_Risk`, the signal is invalidated immediately.
* **Stop Placement**:
    * Dynamic Stop Loss placement based on the most recent invalidation swing.

### 2.3 Entry Simulation
* **Slippage Model (`slippage.py`)**:
    * Implemented regime-based slippage (Normal vs. High Volatility).
    * Default assumption: 1 tick adverse slippage on entry.
* **Trade Logging**:
    * Structured the `simulate_trades` output schema (`entry_price`, `stop_price`, `risk_R`, `or_height`).

## 3. Testing & Verification
* **Scenario Testing**: Created "Golden Day" synthetic data to verify that:
    1.  Valid signals trigger exactly one trade.
    2.  Signals with stops exceeding the Risk Cap are silently rejected (0 trades).
* **Smoke Test**: Validated end-to-end flow on QQQ development data.
