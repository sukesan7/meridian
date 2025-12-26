# Meridian — Strategy Validation Results

## 1. Summary (Representative Run)

This document serves as the **Integrity Validation Report** for the Meridian execution engine. The current run represents a **Technical Verification (Smoke Test)** using synthetic data to confirm pipeline stability, event processing, and reporting artifacts.

* **Run Label**: `Quickstart (Synthetic 3-Day)`
* **Data Source**: Synthetic RTH Generator (Brownian Motion with Drift)
* **Objective**: Confirm end-to-end execution without crashes; validate artifact generation.

## 2. Headline Performance Stats (Backtest)

*Note: Zero values are expected for synthetic smoke tests with uncalibrated parameters.*

| Metric               | Value | Description                               |
| :------------------- | :---- | :---------------------------------------- |
| **Total Trades**     | `0`   | No signals triggered in synthetic sample. |
| **Win Rate**         | `0%`  | N/A                                       |
| **Expectancy (R)**   | `0`   | Risk-adjusted return per trade.           |
| **Max Drawdown (R)** | `0`   | Maximum peak-to-valley decline.           |
| **SQN**              | `0`   | System Quality Number (Signal-to-Noise).  |

## 3. Walk-Forward Analysis (OOS)

The Walk-Forward engine prevents overfitting by enforcing a strict separation between In-Sample (IS) optimization and Out-of-Sample (OOS) verification.

| Metric                  | Value | Notes                                 |
| :---------------------- | :---- | :------------------------------------ |
| **OOS Trades**          | `0`   |                                       |
| **OOS Win Rate**        | `0%`  |                                       |
| **Parameter Stability** | N/A   | Parameters frozen prior to OOS entry. |

## 4. Monte Carlo Simulation (Bootstrap)

To stress-test the system against sequence risk, we employ a block-bootstrap resampling method on realized R-multiples.

* **Iterations**: `500` paths
* **Block Size**: `3` trades (preserves short-term serial correlation)
* **Risk Per Trade**: `1.0%`

| Risk Metric         | Value | Interpretation                      |
| :------------------ | :---- | :---------------------------------- |
| **Risk of Ruin**    | `0%`  | Probability of account hitting 0.   |
| **Median CAGR**     | `0%`  | Expected annual growth rate.        |
| **Max DD (95th %)** | `0%`  | Worst-case scenario (5% tail risk). |

## 5. Reproducibility Contract

Meridian guarantees full reproducibility of any result via the following artifacts:

* **Config Snapshot**: stored in `run_meta.json`.
* **Deterministic Seeding**: Random seed `123` used for synthetic data generation and Monte Carlo paths.
* **Artifact Location**: `outputs/backtest/qs_bt_20251225_192408`

> **Disclaimer:** These results are generated from a technical verification run and do not represent live trading performance.
