# Phase 4: Execution Lifecycle & Trade Management

## 1. Objective
Implement the full lifecycle state machine for trade execution, including partial take-profits (TP1), break-even moves, and time-based exits.

## 2. Key Implementations

### 2.1 Trade Lifecycle Module (`management.py`)
* **TP1 & Break-Even**:
    * Implemented scaling logic: Close 50% of position at +1R.
    * **Auto-BE:** Move Stop Loss to Entry Price immediately upon hitting TP1.
* **TP2 Arbitration**:
    * Defined a deterministic hierarchy for targets: `PDH/PDL` > `Measured Move` > `Fixed 2R`.
* **Time-Based Exits**:
    * **Stalemate Rule:** If TP1 is not hit within 15 minutes, exit at market.
    * **Extension Logic:** Allow holding up to 45 minutes *if and only if* structure remains intact (Price > VWAP, Trend OK).

### 2.2 Session Filters
* **Regime Gating**:
    * **Tiny Day Filter:** Reject entries if OR Height is in the bottom percentile (low volatility).
    * **News Blackout:** Added hooks to filter specific time windows (e.g., FOMC releases).

### 2.3 System Hardening
* **Date Leaks**: Audit confirmed no multi-day state bleeding (variables reset strictly on `df.groupby('date')`).
* **API Rate Limiting**: Added chunking logic to the Databento fetcher to prevent credit overages on large historical requests.

## 3. Milestone Delivery
* **3-Month Gate**: Successfully ran a full backtest on 3 months of continuous NQ futures.
* **Docs**: Published `data-pipeline.md` detailing the production data workflow.
