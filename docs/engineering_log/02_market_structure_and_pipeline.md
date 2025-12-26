# Phase 2: Market Structure & Data Pipeline

## 1. Objective
Develop the market structure classification algorithms (Trend, Swings) and establish a production-grade data pipeline using the Databento API for continuous futures (NQ/ES).

## 2. Key Implementations

### 2.1 Trend & Structure Logic
* **Trend Classification (`structure.trend_5m`)**:
    * Implemented a 3-state logic (`+1` Uptrend, `-1` Downtrend, `0` Neutral).
    * **Logic:** Combines Higher-High/Lower-Low analysis with VWAP proximity.
* **Pattern Recognition (`features.find_swings_1m`)**:
    * Developed an O(N) scanner to identify swing highs/lows with a configurable lookback/lookahead window (default 2 bars).

### 2.2 Event-Driven Signals
* **Unlock Logic**: Implemented the state machine for detecting the "First OR Break" per session.
* **Zone Identification**:
    * Defined the "First Pullback" logic (Price testing `[VWAP, VWAP ±1σ]`).
    * **Constraint:** Only the first valid zone per session is marked to filter noise.
* **2σ Disqualifier**: Added a circuit breaker that disables trading for the session if price breaches the *opposite* 2σ band, filtering out high-volatility chop.

### 2.3 ETL Pipeline (Databento)
* **Source:** Migrated from web-portal CSVs to API-based ingestion (`NQ.v.0`, `ES.v.0`).
* **Normalization:**
    * Built `scripts/normalize_continuous_to_vendor_parquet.py`.
    * Transforms raw vendor frames (UTC) into the Meridian Data Contract (ET, RTH-only).
    * Standardized storage on Parquet (Snappy compression) for O(1) IO speeds.

## 3. Validation
* **Unit Tests**: Verified that `generate_signals` correctly handles "Unlock -> Zone" sequences and resets state cleanly at session boundaries.
* **Integration**: Successfully fetched and normalized 3 months of NQ data via the new CLI tools.
