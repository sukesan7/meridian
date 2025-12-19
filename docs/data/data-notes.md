# 3A Backtester — Data Notes

## Purpose

This document defines the **1-minute input data contract** for Meridian (3A-Backtester) and the core, stable assumptions used throughout the codebase:

- Required schema and types
- Timezone + DST handling
- RTH slicing + session definitions (OR, entry window)
- Resampling rules (5m / 30m) without look-ahead
- Dev vs Production datasets (QQQ vs NQ/ES)

If you are looking for **how to fetch and normalize futures data**, see `docs/data-pipeline.md`.

---

## 1) Input Data Contract (1-minute bars)

### Index / Time
- Engine logic is expressed in **US Eastern time**: `America/New_York`.
- After loading, the DataFrame is expected to have a **tz-aware DatetimeIndex in ET**.
- Timestamps must be aligned to **exact 1-minute boundaries**.

### Required columns
- `open`, `high`, `low`, `close`, `volume`

### Optional columns
- `symbol` (allowed; engine treats it as metadata)

### File formats
- CSV or Parquet.
- Files may contain timestamps in UTC or ET; loader normalizes to `America/New_York`.


## 2) Timezone & DST

- All trading/session logic uses **clock time in ET** (`America/New_York`).
- Vendor feeds may be UTC; loader converts UTC → ET.
- RTH slicing and session grouping are done in ET and must remain correct across DST.
- Tests validate correct behavior across DST transitions (RTH slicing stays consistent).


## 3) Session Definitions

### Regular Trading Hours (RTH)
- Defined as `09:30:00 <= t <= 16:00:00` ET.
- Implemented via `slice_rth(df)`.

Note:
- A “perfect” RTH day at 1-minute granularity is typically **391 bars** (09:30 through 16:00 inclusive).
- Real vendor feeds may contain missing minutes or abnormal sessions; the backtester currently treats missing minutes as gaps.

### Opening Range (OR)
- OR window: `09:30–09:35` ET on 1-minute data.
- Used to compute:
  - `or_high`, `or_low`, `or_height`

### Entry Window
- Entries allowed only during `09:35–11:00` ET (configurable).
- Full session is still used for VWAP calculation and exits.


## 4) Resampling (5-minute and 30-minute)

Resampling uses the same OHLCV aggregation for 5m and 30m:
- `open` = first
- `high` = max
- `low`  = min
- `close` = last
- `volume` = sum

To avoid look-ahead:
- `label="right"`, `closed="right"`
- A bar timestamp at 10:00 only uses data from `(09:55, 10:00]`.


## 5) Dev vs Production Data

### Dev dataset (QQQ)
- 1-minute QQQ equity bars (RTH).
- Used for fast iteration + unit tests when futures data is not available or too expensive to pull repeatedly.

### Production dataset (NQ / ES)
- 1-minute continuous futures series for:
  - NQ (Nasdaq futures)
  - ES (S&P 500 futures)
- Primary source is now **Databento API** (continuous symbols like `NQ.v.0`, `ES.v.0`).
- Pipeline outputs Parquet in a consistent schema for the backtester.


## 6) Current Futures Source (Databento API)

- Dataset: CME Globex MDP (e.g., `GLBX.MDP3`)
- Schema: `ohlcv-1m`
- Requested instrument type: **continuous** (e.g., `NQ.v.0`, `ES.v.0`)
- Raw API Parquet may contain vendor fields (e.g., `ts_event`, `instrument_id`, etc.).
- Normalization produces a clean backtester-ready schema:
  - `timestamp` (UTC in file)
  - `symbol`
  - `open`, `high`, `low`, `close`, `volume`

Loader converts timestamps to ET and sets `DatetimeIndex`.


## 7) Limitations / Known TODOs

- Holidays / half-days not explicitly modeled yet (sessions are processed “as-is”).
- Missing RTH minutes are treated as gaps (no repair / no forward-fill).
- Overnight session levels (ONH/ONL) are not wired into core logic yet.
- Single-instrument backtest runs (multi-instrument portfolio is out of scope for now).
