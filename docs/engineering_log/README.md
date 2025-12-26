# Engineering Development Log

## Overview
This directory contains the chronological technical logs documenting the construction of the **Meridian Backtesting Engine** from **October 2025 to Present**.

As this project was engineered from first principles (without a pre-existing commercial codebase), these logs serve as an audit trail of:
1.  **Architectural Decisions:** The evolution from simple scripts to an Event-Driven System.
2.  **Trade-offs:** Latency vs. Accuracy discussions (e.g., Vectorized Features vs. Iterative Execution).
3.  **Debugging:** Records of race conditions resolved, look-ahead bias eliminated, and logic hardened.

## Log Index

* **[Phase 1: Data Foundation](01_foundation_and_data_contract.md)**
    * Establishing the Data Contract, Timezone/DST invariants, and CI/CD pipelines.
* **[Phase 2: Market Structure & Pipeline](02_market_structure_and_pipeline.md)**
    * Implementing Trend logic, Unlock/Zone state machines, and the Databento ETL pipeline.
* **[Phase 3: Signal & Risk](03_signal_generation_and_risk_controls.md)**
    * Wiring micro-structure triggers and implementing pre-trade Risk Caps (OR-based).
* **[Phase 4: Execution Lifecycle](04_execution_lifecycle_and_management.md)**
    * Building the `TradeManager` for complex exits (TP1 scaling, Auto-BE, Time Stops).
* **[Phase 5: Evaluation Framework](05_evaluation_framework_and_reporting.md)**
    * Developing the Research Harness: Walk-Forward Analysis, Monte Carlo robustness, and standardized Reporting.
