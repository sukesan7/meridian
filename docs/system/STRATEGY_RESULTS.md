# Meridian — Strategy Validation Results

## 1. Summary (v1.0.1 Baseline)

This document contains the **Audited Performance Report** for the Meridian execution engine (v1.0.1).

* **Run Label**: `v1_0_1_baseline`
* **Data Source**: `NQ.v.0 (2024-12-01 to 2025-11-30)`
* **Integrity Status**: **PASS**

## 2. Headline Performance Stats (Backtest)

*Performance derived from a 12-month In-Sample (IS) run on NQ.*

| Metric             | Value     | Description                              |
| :----------------- | :-------- | :--------------------------------------- |
| **Total Trades**   | `59`      | Filtered for high-probability setups.    |
| **Win Rate**       | `61.0%`   | High win-rate trend following logic.     |
| **Expectancy (R)** | `0.24`    | Realized risk-adjusted return per trade. |
| **Avg Win**        | `0.93 R`  | Captures ~1R per successful trade.       |
| **Avg Loss**       | `-0.85 R` | Controlled losses near -1R (Stop Loss).  |
| **SQN**            | `1.91`    | "Average" system quality (Tradeable).    |

## 3. Walk-Forward Analysis (Robustness)

The Walk-Forward engine prevents overfitting by enforcing a strict separation between In-Sample (IS) optimization and Out-of-Sample (OOS) verification.

* **Window**: 63 Days IS / 21 Days OOS.

| Metric             | Value    | Interpretation                      |
| :----------------- | :------- | :---------------------------------- |
| **OOS Trades**     | `54`     | Slight drop in frequency OOS.       |
| **OOS Win Rate**   | `48%`    | Expected degradation from IS (61%). |
| **OOS Expectancy** | `0.09 R` | Strategy remains profitable OOS.    |
| **Max Drawdown**   | `4.21 R` | Comparable to IS Drawdown (3.88 R). |

## 4. Monte Carlo Simulation (Risk Assessment)

Stress-testing the system against sequence risk using block-bootstrap resampling on the v1.0.1 trade list.

* **Iterations**: `2500` paths
* **Seed**: `7`
* **Risk Per Trade**: `1.0%`

| Risk Metric         | Value   | Interpretation                    |
| :------------------ | :------ | :-------------------------------- |
| **Risk of Ruin**    | `0.0%`  | Probability of account hitting 0. |
| **Median CAGR**     | `14.9%` | Expected annual growth rate.      |
| **Max DD (95th %)** | `7.9%`  | Worst-case scenario (Tail Risk).  |
| **Max DD (50th %)** | `4.0%`  | Expected Drawdown.                |

## 5. Reproducibility Contract

Meridian guarantees full reproducibility of these results via the following artifacts:

* **Config Snapshot**: stored in `run_meta.json`.
* **Deterministic Seeding**: Random seed `42` (Backtest) and `7` (Monte Carlo).
* **Artifact Location**: `outputs/backtest/v1_0_1_baseline`

> **Disclaimer:** Past performance is not indicative of future results.
