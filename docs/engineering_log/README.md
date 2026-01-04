# Engineering Log & Audit Trail

This directory contains the chronological engineering record for the **Meridian High-Frequency Backtesting Engine**. It documents the iterative development, architectural decisions, and verification steps for each system phase.

## Purpose
Unlike a standard changelog, this log serves as an **Audit Trail** proving that the system meets its strict determinism and causality contracts. Each phase includes:
* **Objectives:** What was built.
* **Implementation Details:** How strict invariants were enforced.
* **Proof:** Specific tests (`tests/*.py`) and artifacts that verify the claims.

## Phase Index

| Phase | Component | Focus | Status |
| :--- | :--- | :--- | :--- |
| **01** | [Foundation & Data Contract](01_foundation_and_data_contract.md) | Schema, Timezones, RTH Completeness |  Audited |
| **02** | [Market Structure & Pipeline](02_market_structure_and_pipeline.md) | Feature Engineering, Swing Causality |  Audited |
| **03** | [Signal Gen & Risk Controls](03_signal_generation_and_risk_controls.md) | Event Logic, Risk Caps, Gating |  Audited |
| **04** | [Execution Lifecycle](04_execution_lifecycle_and_management.md) | State Machine, Slippage, TPs/SLs |  Audited |
| **05** | [Evaluation & Reporting](05_evaluation_framework_and_reporting.md) | WFO, Monte Carlo, Determinism Gates |  Audited |

## Documentation Standards
All references within these logs adhere to the canonical documentation tree:
* **System Architecture:** [`docs/system/ARCHITECTURE.md`](../system/ARCHITECTURE.md)
* **Performance Benchmarks:** [`docs/system/PERFORMANCE.md`](../system/PERFORMANCE.md)
* **Strategy Specifications:** [`docs/system/STRATEGY_SPEC.md`](../system/STRATEGY_SPEC.md)
* **Data Contracts:** [`docs/data/data-specification.md`](../data/data-specification.md)
* **Pipelines:** [`docs/data/data-pipeline.md`](../data/data-pipeline.md)

## Definition of Done (Global)
* **Strict Determinism:** Identical inputs $\to$ Identical artifacts (SHA-256 verified).
* **Causality:** Zero look-ahead in feature generation or execution.
* **Completeness:** All RTH sessions account for 390 minutes (or explicit exception).
