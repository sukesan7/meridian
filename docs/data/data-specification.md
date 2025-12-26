# Meridian Data Specification & Contract

## 1. System Data Contract (1-Minute Granularity)
This specification defines the strict input requirements for the Meridian Event-Driven Engine. To guarantee **deterministic execution** and **O(1) memory access**, all ingested data must conform to this schema before entering the backtest loop.

### 1.1 Core Schema Definition
The engine requires a **Timezone-Aware DatetimeIndex** (`America/New_York`).

| Column    | Type             | Constraint              | Description                           |
| :-------- | :--------------- | :---------------------- | :------------------------------------ |
| **Index** | `datetime64[ns]` | `tz='America/New_York'` | **Primary Key**. Must be monotonic.   |
| `open`    | `float64`        | $> 0$                   | Session open price.                   |
| `high`    | `float64`        | $\ge open, \ge low$     | Session max price.                    |
| `low`     | `float64`        | $> 0$                   | Session min price.                    |
| `close`   | `float64`        | $> 0$                   | Session close price.                  |
| `volume`  | `int64`          | $\ge 0$                 | Total contract turnover.              |
| `symbol`  | `category`       | N/A                     | Metadata identifier (e.g., `NQ.v.0`). |

**Note on File Format:**
* **Storage:** Parquet (Columnar, Snappy compression).
* **Timezone at Rest:** UTC.
* **Timezone at Runtime:** Converted to `America/New_York` immediately upon load.

---

## 2. Market Microstructure & Time Handling

### 2.1 Timezone & DST Determinism
Handling Daylight Savings Time (DST) is a critical failure point in backtesting. Meridian enforces the following hierarchy:
1.  **Source of Truth:** All trading logic uses **Wall Clock Time (ET)**.
2.  **DST Transition:** The loader relies on `pytz`/`zoneinfo` libraries to map UTC timestamps to the correct ET offset.
3.  **Validation:** RTH slicing logic (`09:30` ET) remains constant regardless of the UTC offset (-4 or -5), ensuring session boundaries never drift.

### 2.2 Session Definitions
The system filters tick data to isolate valid liquidity windows.

* **Regular Trading Hours (RTH):** `09:30:00` to `16:00:00` ET.
    * *Expected Density:* ~391 bars per complete session.
    * *Gap Handling (Dense Grid):* To guarantee array alignment, the system enforces a strict 1-minute grid:
        * **Price (`OHLC`):** Forward-filled from the last valid close (Zero-Order Hold).
        * **Volume:** Set to `0` (Explicitly indicating zero liquidity).
* **Opening Range (OR):** `09:30:00` to `09:35:00` ET.
    * Derived Metrics: `or_high`, `or_low`, `or_height`.
* **Entry Window:** `09:35:00` to `11:00:00` ET.
    * Hard constraint for trade initiation; position management may extend beyond.

---

## 3. Resampling & Look-Ahead Bias Mitigation
To prevent "peeking" into the future during aggregation, the system employs **Right-Edge Labeling**.

### 3.1 Aggregation Logic (5m & 30m)
* `open`: First tick of interval
* `high`: Max tick of interval
* `low`: Min tick of interval
* `close`: Last tick of interval
* `volume`: Sum of interval

### 3.2 Causal Guarantees
* **Labeling:** `label='right'`, `closed='right'`.
* **Example:** A 5-minute bar timestamped `10:00:00` aggregates data from `09:55:01` to `10:00:00`.
* **Constraint:** Logic running at `10:00:00` **cannot** access the Close of the `10:00:00` bar until the timestamp `10:00:01` is processed.

---

## 4. Environment Configurations

### 4.1 Development (CI/CD)
* **Asset:** `QQQ` (Equity ETF).
* **Purpose:** Rapid unit testing, regression suites, and logic validation.
* **Cost:** Free.

### 4.2 Production (Strategy Validation)
* **Assets:** `NQ` (Nasdaq 100 Futures), `ES` (S&P 500 Futures).
* **Source:** Databento API (CME Globex MDP 3.0).
* **Type:** Continuous Contract (`NQ.v.0`), adjusted for rolls.
* **Cost:** Credit Dependant.

---

## 5. Known Limitations
* **Holiday Calendar:** Partial days (e.g., Black Friday) are currently processed "as-is" without specialized early-close logic.
* **Overnight Session (Globex):** Core logic currently ignores the `18:00` to `09:30` overnight session.
* **Portfolio Mode:** Multi-instrument correlation is out of scope; system runs single-instrument instances.
