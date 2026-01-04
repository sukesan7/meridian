# Meridian Data Pipeline

## Overview
The Meridian data pipeline transforms raw vendor data (Databento) into a normalized, high-performance Parquet format. It enforces strict schema validation, session completeness (RTH), and deterministic ordering as defined in [data-specification.md](data-specification.md).

## Pipeline Stages

### 1. Ingestion (`raw` -> `interim`)
* **Source:** Databento (GLBX.MDP3).
* **Format:** Continuous Contract (Back-adjusted, `stype_in="continuous"`).
* **Script:** `scripts/databento_fetch_continuous.py`
* **Output:** Raw capture files stored in `data/raw/databento_api/`.

**Command:**
```bash
python scripts/databento_fetch_continuous.py \
  --symbol NQ.v.0 \
  --start 2025-01-01 \
  --end 2025-01-31 \
  --out-dir data/raw/databento_api
```

### 2. Normalization & Resampling (`interim` -> `processed`)
* **Operation:**
    * Converts timestamps to UTC (at rest) and aligns to America/New_York (runtime).
    * Resamples to a strict 1-minute grid (09:30–16:00 ET).
    * **Invariant:** Enforces "No Cross-Session Fill" by processing days in isolation.
* **Script:** `scripts/normalize_continuous_to_vendor_parquet.py`
* **Output:** Normalized RTH files in `data/vendor_parquet/{PRODUCT}/`.

**Command:**
```bash
python scripts/normalize_continuous_to_vendor_parquet.py \
  --raw-parquet data/raw/databento_api/GLBX.MDP3_ohlcv-1m_NQ.v.0_2025-01-01_2025-01-31.parquet \
  --symbol NQ.v.0 \
  --product NQ \
  --start 2025-01-01 \
  --end 2025-01-31
```

### 3. Validation & Inventory (`processed` -> `outputs`)
* **Operation:** Scans the processed directory to verify row counts, time ranges, and schema integrity.
* **Script:** `scripts/data_inventory.py`
* **Output:** CSV report at `outputs/data_inventory.csv`.

**Command:**
```bash
python scripts/data_inventory.py \
  --parquet-dir data/vendor_parquet/NQ \
  --out outputs/data_inventory.csv \
  --require-datetime
```

## Data Artifacts & Naming Conventions

### Canonical File Format
The normalization script enforces the following naming convention for baseline datasets. Do not rely on generic names like `combined.parquet`.

**Format:** `{SYMBOL}_{START}_{END}_RTH.parquet`
**Example:** `NQ.v.0_2024-12-01_2025-11-30_RTH.parquet`

### Manifests (Audit Trail)
To guarantee reproducibility, production datasets should be accompanied by a manifest containing:
* **Source Hash:** SHA-256 of the raw input.
* **Row Counts:** Total rows and valid RTH sessions.
* **Time Range:** Exact UTC min/max.
* **Pipeline Version:** Git commit SHA.

*(Note: Manifest generation is currently a manual audit step or part of the CI wrapper)*
