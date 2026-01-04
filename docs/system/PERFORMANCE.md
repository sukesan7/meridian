# System Performance & Latency Profile

## 1. Summary
This document tracks the runtime characteristics of the Meridian Backtesting Engine. It identifies critical bottlenecks in the Event-Driven loop and outlines the roadmap for optimization.

**Current Throughput (v1.0.5):** ~13.3s (End-to-End Backtest, 12-month NQ)

---

## 2. Profiling Methodology
Profiling is conducted on **Compute-Only** runs.
* **Definition:** "Compute-Only" means data loading time is excluded (or data is pre-cached in memory) to isolate the engine's processing speed.
* **Tool:** `cProfile` exporting to `.prof`.

## 3. Benchmark Results (v1.0.5 Baseline)

| Module | Duration | Description |
| :--- | :--- | :--- |
| **Backtest (1 Year)** | `13.30s` | Full event loop + feature gen. |
| **Walk-Forward** | `15.66s` | 12 Windows (Re-optimization). |
| **Monte Carlo** | `0.49s` | 2,500 Iterations (Bootstrap). |

## 4. Bottleneck Analysis (Hotspots)
Based on `cProfile` analysis of `backtest.prof`:

| Rank | Component | Function | Root Cause Analysis |
| :--- | :--- | :--- | :--- |
| **1** | **Feature Engineering** | `build_feature_frames` | **~60%** of runtime. Global dataframe construction overhead. |
| **2** | **Resampling Logic** | `trend_5m` | Pandas `.resample()` is expensive in Python. |
| **3** | **Execution Engine** | `simulate_trades` | Efficient (<15% total). Iteration cost is minimal. |

## 5. Optimization Roadmap

### Phase 1: Vectorization (Completed)
* Replaced iterative swing detection with vectorized NumPy calls.

### Phase 2: Memory Layout (Next)
* **Target:** `load_minute_df`.
* **Action:** Move timezone conversion to the **ETL Pipeline** (storage) to save ~2s of load time.

### Phase 3: Polars Migration (Future)
* **Goal:** Zero-copy memory mapping to eliminate Pandas overhead.
