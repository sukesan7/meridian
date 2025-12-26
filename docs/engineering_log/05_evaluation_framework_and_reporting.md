# Phase 5: Evaluation Framework & Reporting

## 1. Objective
Build the "Research Harness" to rigorously evaluate strategy performance. This includes standardized metrics, Walk-Forward Analysis (WFA) to prevent overfitting, and Monte Carlo simulations for robustness testing.

## 2. Key Implementations

### 2.1 Metrics Suite (`metrics.py`)
* **Standardization**: Unified calculation of `Expectancy (R)`, `SQN`, `Win Rate`, and `Max Drawdown` across all report types.
* **Grouping**: Added regime analysis (metrics grouped by Day of Week, OR Quartile).

### 2.2 Walk-Forward Engine (`walkforward.py`)
* **Rolling Window Validation**:
    * Implemented `In-Sample (IS)` optimization windows (63 days) followed by `Out-of-Sample (OOS)` verification windows (21 days).
    * **Constraint:** Strict parameter freezing to ensure "No Bleed" from future data.

### 2.3 Monte Carlo Engine (`monte_carlo.py`)
* **Bootstrap Method**: Implemented "Block Bootstrap" (block size = 5 trades) to preserve short-term serial correlation in trade results.
* **Risk Modeling**: Simulation of 2,000 equity paths to estimate `MaxDD @ 95% Confidence` and `Risk of Ruin`.

### 2.4 CLI & Reporting (`meridian-run`)
* **Workflow**: Unified all commands (`backtest`, `walkforward`, `monte-carlo`) under a single CLI entry point.
* **Reproducibility**:
    * Every run saves a `run_meta.json` (Config Snapshot) and `summary.json`.
    * Results are deterministic based on the provided random seed.

## 3. Challenges & Fixes
* **Bug Fix (Drawdown Anchoring)**:
    * *Issue:* MaxDD reported as 0 if the first trade was a loss (Equity < Starting Capital).
    * *Fix:* Anchored the equity curve at 0 before computing peak-to-valley decline.
* **Data Validation**:
    * Investigated low trade counts; confirmed data integrity (UTC timestamps) and verified that scarcity was due to strict Strategy Logic, not data loss.

## 4. Current Status (12-Month NQ Run)
* **Backtest**: 43 Trades, Expectancy ~0.42R.
* **Walk-Forward**: Robustness confirmed; OOS performance did not collapse vs. IS.
* **Next Steps**: Expand dataset to 5 years and implement cross-asset validation (ES).
