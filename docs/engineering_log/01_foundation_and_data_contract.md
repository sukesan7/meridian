# Phase 1: Data Foundation & Deterministic Scaffolding

## 1. Objective
Establish the core data ingestion layer and ensure deterministic handling of time-series data across Daylight Savings Time (DST) transitions. This phase lays the invariant ground rules for the backtesting engine.

## 2. Key Implementations

### 2.1 Data I/O Layer (`s3a_backtester.data`)
* **Strict Loader (`load_minute_df`)**: Implemented a parser that enforces a specific schema (`open`, `high`, `low`, `close`, `volume`) and rejects non-compliant inputs.
* **RTH Slicing (`slice_rth`)**:
    * Defined Regular Trading Hours as `09:30 – 16:00` ET.
    * **Constraint:** Logic is timezone-aware (`America/New_York`) to handle the UTC offset shift (-4/-5) correctly.
* **Resampling Engine**:
    * Standardized 5-minute and 30-minute aggregation.
    * **Invariant:** Enforced `label="right", closed="right"` to strictly prevent look-ahead bias in higher-timeframe features.

### 2.2 Feature Engineering (Vectorized)
* **Session References**: Computed Opening Range (OR) metrics (`or_high`, `or_low`) and Previous Day bounds (PDH/PDL).
* **VWAP Bands**: Implemented session-anchored VWAP with standard deviation bands (±1σ, ±2σ) for mean-reversion logic.
* **ATR15**: Added 15-minute Average True Range (calculated on 1-minute source) as a volatility normalization factor.

## 3. DevOps & Quality Assurance
* **CI/CD Pipeline**: Configured GitHub Actions to run `pytest` and `ruff` (linter) on every push/PR.
* **Branch Strategy**: Enforced a Protected `main` branch policy; all changes require PR validation.
* **Regression Testing**: Created synthetic datasets to prove RTH slicing remains consistent across March/November DST boundaries.

## 4. Artifacts
* **Data Contract**: `docs/data/DATA_SPECIFICATION.md` defining the input schema.
