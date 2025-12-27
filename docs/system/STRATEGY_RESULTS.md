# Meridian — Strategy Validation Results

## 1. Summary (v1.0.1 Baseline)

This document contains the **Audited Performance Report** for the Meridian execution engine (v1.0.1). This baseline establishes the "Honest PnL" after the removal of look-ahead bias and the correct alignment of news day filtering.

* **Run Label**: `v1_0_1_baseline`
* **Data Source**: `NQ.v.0 (2024-12-01 to 2025-11-30)`
* **Integrity Status**: **PASS** (Delayed signal confirmation enforced).

## 2. Headline Performance Stats (Backtest)

*Performance derived from a 12-month In-Sample (IS) run on NQ.*

| Metric             | Value     | Description                                     |
| :----------------- | :-------- | :---------------------------------------------- |
| **Total Trades**   | `61`      | Increased slightly due to news trading enabled. |
| **Win Rate**       | `59.0%`   | Solid trend following win-rate.                 |
| **Expectancy (R)** | `0.20`    | Realized risk-adjusted return per trade.        |
| **Avg Win**        | `0.92 R`  | Captures ~0.9R per successful trade.            |
| **Avg Loss**       | `-0.83 R` | Controlled losses near -0.83R (Stop Loss).      |
| **SQN**            | `1.69`    | "Average" system quality (Tradeable).           |

## 3. Walk-Forward Analysis (Robustness)

The Walk-Forward engine prevents overfitting by enforcing a strict separation between In-Sample (IS) optimization and Out-of-Sample (OOS) verification.

* **Window**: 63 Days IS / 21 Days OOS.

| Metric             | Value    | Interpretation                      |
| :----------------- | :------- | :---------------------------------- |
| **OOS Trades**     | `55`     | Consistent frequency OOS.           |
| **OOS Win Rate**   | `47%`    | Expected degradation from IS (59%). |
| **OOS Expectancy** | `0.09 R` | Strategy remains profitable OOS.    |
| **Max Drawdown**   | `4.26 R` | Comparable to IS Drawdown (3.88 R). |

## 4. Monte Carlo Simulation (Risk Assessment)

Stress-testing the system against sequence risk using block-bootstrap resampling on the v1.0.1 trade list.

* **Iterations**: `2500` paths
* **Seed**: `7`
* **Risk Per Trade**: `1.0%`

| Risk Metric         | Value   | Interpretation                    |
| :------------------ | :------ | :-------------------------------- |
| **Risk of Ruin**    | `0.0%`  | Probability of account hitting 0. |
| **Median CAGR**     | `13.2%` | Expected annual growth rate.      |
| **Max DD (95th %)** | `8.5%`  | Worst-case scenario (Tail Risk).  |
| **Max DD (50th %)** | `4.4%`  | Expected Drawdown.                |

## 5. Reproducibility Contract

Meridian guarantees full reproducibility of these results via the following artifacts:

* **Config Snapshot**: stored in `run_meta.json`.
* **Deterministic Seeding**: Random seed `42` (Backtest) and `7` (Monte Carlo).
* **Artifact Location**: `outputs/backtest/v1_0_1_baseline`

> **Disclaimer:** Past performance is not indicative of future results.
