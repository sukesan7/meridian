# Phase 1: Foundation & Data Contract

**Status:** Complete

**Focus:** Data Ingestion, Schema Enforcement, Timezone Determinism

## 1. Objectives
* Establish a rigid Data Contract to prevent "Garbage In, Garbage Out."
* Implement `America/New_York` timezone handling that survives DST transitions.
* Enforce a dense 1-minute grid (390 bars/session) to guarantee array alignment.

## 2. Implementation Details

### A. The Data Contract
We defined a strict schema in [`docs/data/data-specification.md`](../data/data-specification.md).
* **Format:** Parquet (Snappy compression).
* **Primary Key:** `datetime64[ns, America/New_York]`.
* **Invariant:** Timestamps must be monotonic increasing and unique.

### B. Session Handling
To prevent look-ahead bias during resampling, we enforce **Right-Edge Labeling** (Model A).
* **RTH:** 09:30:00 to 16:00:00 ET.
* **Filtering:** The `16:00:00` closing print is excluded from the RTH dataset to prevent resampling logic from "seeing" the close before the bar is complete.
* **Gap Filling:** Zero-Order Hold (ZOH) for price; `0` for volume.

### C. The "Cross-Session" Invariant
A critical bug risk in continuous contracts is bleeding data across days.
* **Rule:** Forward-fill operations **must never** cross session boundaries.
* **Mechanism:** `normalize_continuous_to_vendor_parquet.py` processes each trading day in isolation before concatenation.

## 3. Proof & Verification

### Verified Contracts
* **Schema Validity:** Verified that all output Parquet files contain `open`, `high`, `low`, `close` (float64) and `volume` (int64).
* **Timezone Correctness:** Verified that 09:30 ET aligns correctly regardless of UTC offset (-4/-5).

### Artifacts
* **Inventory Report:** `outputs/data_inventory.csv` (Audits row counts per session).

### Test Coverage
| Invariant | Test ID |
| :--- | :--- |
| **Schema Enforcement** | `tests/test_data_io.py::test_load_schema_validity` |
| **Session Completeness** | `tests/test_data_io.py::test_rth_bar_count` |
| **DST Handling** | `tests/test_data_io.py::test_dst_transition_alignment` |
| **No Session Bleed** | `tests/test_data_io.py::test_no_cross_session_ffill` |

## 4. Definition of Done
- Data Specification Documented (`docs/data/data-specification.md`)
- Ingestion Script Implemented (`scripts/databento_fetch_continuous.py`)
- Normalization Script Implemented (`scripts/normalize_continuous_to_vendor_parquet.py`)
- Inventory Audit Tool Implemented (`scripts/data_inventory.py`)
- CI Tests Green (Python 3.10/3.11)
