# Meridian Data Specification & Contract

## 1. Schema Contract
The engine enforces the following schema for all input Parquet files. This schema is guaranteed by the `normalize_continuous_to_vendor_parquet.py` ETL script.

| Column | Dtype | Description | Invariant |
| :--- | :--- | :--- | :--- |
| `timestamp` | `datetime64[ns, UTC]` | **Primary Key** | Unique, Monotonic Increasing. |
| `open` | `float64` | Opening price | `> 0`, Raw Float (No Rounding) |
| `high` | `float64` | High price | `>= open`, `>= low` |
| `low` | `float64` | Low price | `<= open`, `<= high` |
| `close` | `float64` | Closing price | `> 0`, Forward-Filled (Intra-day only) |
| `volume` | `int64` | Total volume | `>= 0`, `0` for filled gaps |
| `symbol` | `string/cat` | Identifier | e.g., `NQ.v.0` |

### Parquet "At Rest" vs. In-Memory
* **At Rest (Disk):** Data is stored with a specific `timestamp` column in UTC.
* **On Load (Memory):** The loader **must** set the index to `timestamp`, convert to `America/New_York`, and sort.
* **Tick Size:** Prices are stored as raw `float64`. Rounding to tick size (e.g., 0.25) is an **execution-time** responsibility, not a data storage one.

## 2. Time & Session Semantics

### Timestamp Convention (Model A: Bar-Start)
* **Labeling:** Timestamps represent the **Start** of the aggregation interval.
    * Example: `09:30:00` covers activity from `09:30:00.000` to `09:30:59.999`.
* **Causality:**
    * A signal calculated at `09:30:00` (using that bar's Close) can only trigger execution at `09:31:00` (Next Open) or later.
* **RTH Boundary:**
    * **First Bar:** `09:30:00` ET.
    * **Last Bar:** `15:59:00` ET.
    * **Exclusion:** The `16:00:00` closing print is excluded from the RTH grid to prevent look-ahead issues during 1-minute resampling.

### Grid Invariants
To ensure array alignment, the normalizer enforces a strict 1-minute grid:

1.  **Dense Grid:** `pd.date_range(start="09:30", end="15:59", freq="1min")`.
2.  **Zero-Order Hold (ZOH):** Missing price bars are forward-filled from the last valid close.
3.  **No Cross-Session Fill:**
    * Forward-fill **NEVER** crosses session boundaries.
    * Each day is processed in isolation. If `09:30` is missing, it is **not** filled from the prior day's close.
    * *Implementation Reference:* `normalize_continuous_to_vendor_parquet.py` Lines 115-150.

## 3. Continuous Contract Semantics
* **Source:** Databento (`stype_in="continuous"`).
* **Methodology:** Back-adjusted (Difference adjusted) to stitch contract months.
* **Roll Handling:** Adjustments are baked into the data during the Ingestion Phase (`Phase 1`). The engine consumes pre-adjusted prices and treats them as a seamless time series.

## 4. Known Limitations
* **Partial Days:** Early market closes (e.g., Black Friday) are currently processed "as-is" and will appear as short sessions in the inventory report.
* **Overnight Data:** The `normalize` script strictly filters for `09:30-16:00` ET. Overnight price action is discarded.
