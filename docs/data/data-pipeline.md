# Meridian Data Ingestion & ETL Pipeline

## 1. Overview
This document details the **Extract-Transform-Load (ETL)** operations for Meridian. The pipeline ingests high-fidelity tick data from the **Databento API**, normalizes it into a proprietary Parquet schema, and prepares it for the simulation engine.

**Supported Source:** CME Globex MDP 3.0 (via Databento)
**Target Output:** Normalized Parquet (RTH, 1-minute bars)

---

## 2. Architecture & Folder Layout

```text
data/
├── raw/                      # Immutable Source of Truth (Vendor Schema)
│   └── databento_api/
│       └── <dataset>_<symbol>_<date>.parquet
├── vendor_parquet/           # Normalized / Production-Ready (Meridian Schema)
│   ├── NQ/
│   │   ├── NQ.v.0_RTH_COMBINED.parquet
│   │   └── by_day/           # Partitioned for parallel processing
│   └── ES/
└── outputs/
    └── data_inventory.csv    # Quality Assurance Reports
```

---

## 3. Operational Workflow

### Phase 1: Ingestion (Extract)
Fetches continuous contract data using smart chunking to manage API rate limits and memory usage.

**Script:** `scripts/databento_fetch_continuous.py`
```bash
# Example: Fetch 1 week of NQ data
python scripts/databento_fetch_continuous.py \
  --symbol NQ.v.0 \
  --start 2025-11-03 \
  --end 2025-11-07
```
* **Rate Limiting:** Script enforces request chunking (max 120 days) to prevent timeout and credit overage.
* **Output:** Saves raw `.parquet` with UTC timestamps and vendor-specific fields.

### Phase 2: Normalization (Transform)
Cleanses raw data to meet the **Meridian Data Contract** (see `data-specifications.md`).

**Script:** `scripts/normalize_continuous_to_vendor_parquet.py`
```bash
python scripts/normalize_continuous_to_vendor_parquet.py \
  --raw-parquet data/raw/databento_api/raw_NQ_dump.parquet \
  --symbol NQ.v.0 \
  --product NQ
```
* **Timezone Conversion:** Maps `UTC` $\to$ `America/New_York`.
* **RTH Filtering:** Drops rows outside `09:30-16:00 ET`.
* **Partitioning:** Optional splitting into `by_day/` directories for unit test isolation.

### Phase 3: Validation (Load & QA)
Verifies data integrity before strategy execution.

**Script:** `scripts/data_inventory.py`
```bash
python scripts/data_inventory.py \
  --parquet-dir data/vendor_parquet/NQ \
  --out outputs/inventory_report.csv
```
* **Checks:** Verifies row counts (~391/day), detects missing sessions, and flags outliers.

---

## 4. Execution
Running the Meridian Backtest Engine on the prepared dataset:

```bash
meridian-run run-backtest \
  --config configs/base.yaml \
  --data data/vendor_parquet/NQ/NQ.v.0_RTH_COMBINED.parquet
```

---

## 5. Security & Configuration

### API Key Management
Use environment variables for authentication:

**Mac/Linux:**
```bash
export DATABENTO_API_KEY="db-xxxxxxxxxxxx"
```

**PowerShell:**
```powershell
$env:DATABENTO_API_KEY = "db-xxxxxxxxxxxx"
```

---

## 6. Troubleshooting & Failure Modes

| Error Mode             | Root Cause                | Resolution                                                                                        |
| :--------------------- | :------------------------ | :------------------------------------------------------------------------------------------------ |
| **Time Range Error**   | `start == end` in request | Ensure `end` date is exclusive or at least `start + 1 day`.                                       |
| **Zero Trades**        | Timezone Misalignment     | Verify loader is converting to `America/New_York` before RTH slicing.                             |
| **Row Count Variance** | Half-Days / Holidays      | Check `data_inventory.csv`. Low row counts (e.g., 210 vs 391) often indicate early market closes. |
| **Spread Explosion**   | Wrong Instrument Type     | Ensure `stype_in='continuous'` is set. Do not fetch `parent` product codes.                       |

## 7. Reproducibility
* **Immutability:** Raw API dumps in `data/raw` are never modified, only read.
* **Versioning:** Pipeline scripts are version-controlled; API request parameters are logged to stdout for audit trails.
