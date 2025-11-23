# 3A Backtester - Data Notes (Week 1)

## Objective:

This document defines the 1-minute input data contract for the 3A backtester:
- Schema.
- Timezone/DST decisions.
- RTH Window.
- Resampling Rules.
- Split between Dev Data (QQQ) and the final production futures data (NQ/ES).

### 1. Input Schema (1-minute bars)

- **Index**: `DatetimeIndex`, timezone-aware, `America/New_York`.
- **Frequency**: regular 1-minute bars.
- **Required columns**:
  - `open`, `high`, `low`, `close`, `volume`
- **Optional columns**:
  - `symbol` (for multi-instrument files; ignored by the engine).
- **File formats**:
  - CSV or Parquet. CSV is expected to contain a `datetime` column that can be parsed to UTC or ET.

`load_minute_df` is responsible for reading the raw file and returning a cleaned, tz-aware 1-minute DataFrame in thisshape.

### 2. Timezone & DST Handling

- All trading logic is expressed in **US Eastern time** (`America/New_York`).
- Raw vendor feeds may be UTC; the loader converts timestamps to ET.
- After loading, the index is always tz-aware ET and all subsequent operations run in that timezone.
- The RTH slice and all session logic are defined in **clock time**, not fixed UTC offsets.
- A dedicated test spans the March DST weekend and verifies that the RTH slice still returns 391 bars for a full day both before and after the DST change.

### 3. Session Windows

- **Regular Trading Hours (RTH)**:
  - Defined as `09:30:00 <= t <= 16:00:00` in `America/New_York`.
  - Implemented by `slice_rth`, which keeps only bars in this window.
- **Opening Range (OR)**:
  - Defined as `09:30–09:35` ET on 1-minute data.
  - Used to compute `or_high`, `or_low`, and `or_height`.
- **Entry window**:
  - Strategy entries are only allowed `09:35–11:00` ET (full session is still used for VWAP and exits).

### 4. Resampling (5-minute and 30-minute)

Resampling is applied to the 1-minute ET series using the same aggregation for both 5-minute and 30-minute bars:

- `open` = first value in the window
- `high` = max
- `low`  = min
- `close` = last
- `volume` = sum

The implementation uses `label="right"` and `closed="right"` so that a bar timestamp at 10:00 only contains data from `(09:55, 10:00]`. This avoids look-ahead.
A synthetic monotonic test confirms that 30-minute highs and closes line up with the last minute in each resampled window.

### 5. Dev vs Production data

- **Dev data (current)**:
  - 1-minute QQQ equity data (similar behavior to futures data), RTH only.
  - Lives in `data/` locally and is git-ignored.
  - Used to develop and test data I/O and features while the futures feed is not yet connected (need to acquire NQ/ES 1-min data for > 1 year).

- **Production data (target)**:
  - 1-minute **continuous, back-adjusted** futures series for NQ and ES.
  - Vendor is expected to provide the continuous contract (front-month roll + back-adjust).
  - The backtester assumes the feed already handles contract stitching; this project focuses on session logic and trade simulation.

### 6. Vendor Futures Data (Databento)

**Source:** Databento CME Globex MDP 3.0 OHLCV-1m, CSV, zstd.
**Products:** NQ, ES continuous futures.
**Timezone:** timestamps in UTC, converted to America/New_York in the pipeline.
**Schema:** In the actual parquet, you will see: `timestamp` (index), `symbol`, `open/high/low/close/volume`.
**Note:** Raw files live under data/raw/databento/... (ignored) and normalized parquet under data/vendor_parquet/NQ|ES.

### 7. Limitations / TODO

- Holidays and half-days are not yet inlcuded in the model.
- No special handling for missing RTH bars or zero-volume bars. They are currently treated as gaps. Possible correction in the future for this.
- Overnight session (ONH/ONL) is not yet wired. This will be adjusted in future milestones.
- Single-instrument per run for now. Possible change in the future.

---

# 3A Backtester - Data Notes (Week 2)

## Objective

Week 2 moved the project from "QQQ-only dev data" to having a **real futures data pipeline** for NQ/ES via Databento:
- Organize raw vendor files under a stable directory layout.
- Normalize Databento CSVs into consistent Parquet for fast, repeatable loading.
- Ensure timestamps, schema, and symbols match the 3A data contract defined in Week 1.

This section documents the futures-specific setup.

### 1. Directory layout for vendor futures data

All vendor futures data is kept under `data/` and git-ignored:
- **Raw vendor files (as delivered / decompressed CSV)**:
  - `data/raw/databento/NQ/*.csv`
  - `data/raw/databento/ES/*.csv`
- **Normalized Parquet (ready for backtests):**
  - `data/vendor_parquet/NQ/*.parquet`
  - `data/vendor_parquet/ES/*.parquet`

Notes:
- One file per instrument per slice (ex: per day or per Databento delivery chunk).
- The backtester wil later load from `vendor_parquet` via `data_io.load_minute_df` or a thin wrapper that globs multiple files.

QQQ dev files remain as simple CSVs directly under `data/` for fast iteration and are seperate from the futures vendor folder.

### 2. Databento CSV -> Parquet pipeline

A small, repeatable pipeline that converts Databento OHLCV-1m CSVs into normalized Parquet:
- **Source:** Databento CME Globex MDP 3.0, 1-minute OHLCV for:
  - `NQ` (Nasdaq Futures)
  - `ES` (S&P 500 Futures)
- **Intermediate Format:**
  - Vendor delivers compressed CSV (zstd).
  - These are decompressed to plain `.csv` under `data/raw/databento/NQ|ES`
- **Normalization Script** (Python, under `/scripts`):
  - Reads each Databento CSV.
  - Parses the vendor timestamp column to a tz-aware `DatetimeIndex`.
  - Converts from **UTC -> America/New_York**.
  - Selects Columns:
    - `open`, `high`, `low`, `close`, `volume`, and `symbol` where available
  - Sorts by time and writes to Parquet in:
    - `data/vendor_parquet/NQ/`
    - `data/vendor_parquet/ES/`

This keeps the on-disk futures data in the same schema as the 1-minute data contract defined in Week 1.

### 3. Schema & Timezone for Normalized Futures Data

The normalized NQ/ES Parquet files follow the same contract as the generic 1-minute loader:
- **Index:**
  - `DatetimeIndex`, tz-aware, `America/New_York`.
  - Suitable for direct use with `slice_rth`, VWAP, OR, etc.
- **Columns:**
  - Required: `open`, `high`, `low`, `close`, `volume`.
  - Optiona: `symbol` (carried through from Databento. Engine currently ignores it)
- **Frequency:**
  - Regular 1-minute bars over the full trading session (RTH + globex in raw. RTH is enforced later via `slice_rth`)

This means **Dev QQQ data and Production NQ/ES data now share the same loader assumptions**.

### 4. Validation performed in Week 2

To avoid silently bad data, several sanity checks were done during Week 2:
- **Parquet Shape Checks:**
  - Loaded sample Parquet files from `data/vendor_parquet/NQ` and `ES`.
  - Confirmed:
    - Datetime Index is tz-aware and in `America/New_York`.
    - OHLCV columns present and numeric.
    - No obvious NaN explosions or duplicate timestamps in the sample.
- **Range Checks:**
- Verified:
    - The date range matches the Databento request window.
    - Intraday timestamps line up on exact minute boundaries.
- **Compatability Check:**
  - Confirmed that the normalized futures could be passed through the same pipeline as QQQ:
    - `load_minute_df` -> `slice_rth` -> `resample` -> `features` -> `structure` -> `engine`.

For Week 2, the primary engine and feature development still targets QQQ, but the NQ/ES futures data is now in place for final backtests.

### 5. Usage Plan (Dev vs Futures)

- **Dev (current):**
  - QQQ 1-minute CSVs remain the primary dataset for:
    - Unit tests,
    - Feature/Engine iteration,
    - Quick CLI sanity checks.
  - Keeps iteration fast and decouples engine work from vendor-specific quirks.
- **Futures (later weeks):**
  - Once the full 3A engine + trade simulation is stable, NQ and ES Parquet will be used to:
    - Run 12-24 month backtests,
    - Compute final performance stats (expectancy, MaxDD, SQN, trades/month)
    - Drive walk-forward splits and Monte Carlo on the future series.

This is the current Usage plan as of Week 2.

### 6. Limitations / TODO (Week 2 scope)

- Loader still assumes one file at a time. A higher-level helper to:
  - Glob multiple Parquets,
  - Concatenate them into a single continuous series,
  - Filter by date range,
    These will be added in later weeks.
- Holidays and half-days remain unmodeled:
  - They pass through the pipeline as-is.
  - Strategy will later need to explicit rules to skip/flag abnormal sessions.
- Overnight session (Globex) is still **ignored at the engine level:**
  - RTH is enforced via `slice_rth`.
  - ONH/ONL wiring into `features.compute_session_refs` will be done after core engine work is complete.
