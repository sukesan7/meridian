# System Performance & Latency Profile

## 1. Summary
This document tracks the runtime characteristics of the Meridian Backtesting Engine. It identifies critical bottlenecks in the Event-Driven loop and outlines the roadmap for moving from Pandas-native logic to high-performance NumPy/Polars implementations.

**Current Throughput (v1.0.1):** ~15.6M calls / 14.56s (End-to-End Backtest, 12-month NQ)

---

## 2. Profiling Methodology

Profiling is conducted on "Compute-Only" runs (IO-suppressed) to isolate engine latency.

**Standard Profiling Command:**
```powershell
python scripts/profile_run.py --out outputs/profiles/nq_12m_backtest.prof --top 60 -- `
  backtest `
  --config configs/base.yaml `
  --data data/vendor_parquet/NQ/NQ.v.0_2024-12-01_2025-11-30_RTH.parquet `
  --from 2024-12-01 --to 2025-11-30 `
  --run-id prof_nq_12m_bt
```

---

## 3. Bottleneck Analysis (Hotspots)

Based on `cProfile` data from the v1.0.1 baseline.

| Rank  | Component               | Function                | Cumulative Time  | Root Cause Analysis                                                                 |
| :---- | :---------------------- | :---------------------- | :--------------- | :---------------------------------------------------------------------------------- |
| **1** | **Feature Engineering** | `build_feature_frames`  | **12.77s (87%)** | Global overhead of initial dataframe construction.                                  |
| **2** | **Resampling Logic**    | `structure.py:trend_5m` | **5.20s**        | **Critical Path.** Pandas `.resample()` and `.agg()` inside the loop are expensive. |
| **3** | **Data Ingestion**      | `load_minute_df`        | **2.93s**        | `tz_convert` is CPU-intensive due to `zoneinfo` object instantiation per call.      |
| **4** | **Pattern Recognition** | `find_swings_1m`        | **2.25s**        | Iterative row scanning for swing highs/lows (O(N) Python loop).                     |
| **5** | **Execution Engine**    | `simulate_trades`       | **1.36s**        | Relatively efficient. Most latency is strictly in data prep, not execution.         |

---

## 4. Optimization Roadmap

### Phase 1: Vectorization
* **Target:** `trend_5m` and `find_swings_1m`.
* **Action:** Replace iterative Pandas checks with NumPy vector operations.
* **Expected Gain:** ~3-5x speedup on feature generation.

### Phase 2: I/O Efficiency
* **Target:** `load_minute_df`.
* **Action:** Move timezone conversion to the **ETL Pipeline** (storage) rather than Runtime. Store timestamps as UTC integers and apply offset only for display.

### Phase 3: Memory Layout
* **Target:** Global DataFrame overhead.
* **Action:** Assess migration to **Polars** for lazy evaluation and zero-copy memory mapping.

---

## 5. Artifacts
Raw profile dumps (`.prof`) are stored in `outputs/profiles/` and can be visualized using `snakeviz`:
```bash
snakeviz outputs/profiles/nq_12m_backtest.prof
```
