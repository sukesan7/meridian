# 3A Backtester - Data Notes (Week 1)

## Purpose:

This document defines the 1-minute input data contract for the 3A backtester:
- Schema.
- Timezone/DST decisions.
- RTH Window.
- Resampling Rules.
- Split between Dev Data (QQQ) and the final production futures data (NQ/ES).

## 1. Input Schema (1-minute bars)

- **Index**: `DatetimeIndex`, timezone-aware, `America/New_York`.
- **Frequency**: regular 1-minute bars.
- **Required columns**:
  - `open`, `high`, `low`, `close`, `volume`
- **Optional columns**:
  - `symbol` (for multi-instrument files; ignored by the engine).
- **File formats**:
  - CSV or Parquet. CSV is expected to contain a `datetime` column that can be parsed to UTC or ET.

`load_minute_df` is responsible for reading the raw file and returning a cleaned, tz-aware 1-minute DataFrame in thisshape.

## 2. Timezone & DST Handling

- All trading logic is expressed in **US Eastern time** (`America/New_York`).
- Raw vendor feeds may be UTC; the loader converts timestamps to ET.
- After loading, the index is always tz-aware ET and all subsequent operations run in that timezone.
- The RTH slice and all session logic are defined in **clock time**, not fixed UTC offsets.
- A dedicated test spans the March DST weekend and verifies that the RTH slice still returns 391 bars for a full day both before and after the DST change.

## 3. Session Windows

- **Regular Trading Hours (RTH)**:
  - Defined as `09:30:00 <= t <= 16:00:00` in `America/New_York`.
  - Implemented by `slice_rth`, which keeps only bars in this window.
- **Opening Range (OR)**:
  - Defined as `09:30–09:35` ET on 1-minute data.
  - Used to compute `or_high`, `or_low`, and `or_height`.
- **Entry window**:
  - Strategy entries are only allowed `09:35–11:00` ET (full session is still used for VWAP and exits).

## 4. Resampling (5-minute and 30-minute)

Resampling is applied to the 1-minute ET series using the same aggregation for both 5-minute and 30-minute bars:

- `open` = first value in the window
- `high` = max
- `low`  = min
- `close` = last
- `volume` = sum

The implementation uses `label="right"` and `closed="right"` so that a bar timestamp at 10:00 only contains data from `(09:55, 10:00]`. This avoids look-ahead.
A synthetic monotonic test confirms that 30-minute highs and closes line up with the last minute in each resampled window.

## 5. Dev vs Production data

- **Dev data (current)**:
  - 1-minute QQQ equity data (similar behavior to futures data), RTH only.
  - Lives in `data/` locally and is git-ignored.
  - Used to develop and test data I/O and features while the futures feed is not yet connected (need to acquire NQ/ES 1-min data for > 1 year).

- **Production data (target)**:
  - 1-minute **continuous, back-adjusted** futures series for NQ and ES.
  - Vendor is expected to provide the continuous contract (front-month roll + back-adjust).
  - The backtester assumes the feed already handles contract stitching; this project focuses on session logic and trade simulation.

## 6. Vendor Futures Data (Databento)

**Source:** Databento CME Globex MDP 3.0 OHLCV-1m, CSV, zstd.
**Products:** NQ, ES continuous futures.
**Timezone:** timestamps in UTC, converted to America/New_York in the pipeline.
**Schema:** In the actual parquet, you will see: `timestamp` (index), `symbol`, `open/high/low/close/volume`.
**Note:** Raw files live under data/raw/databento/... (ignored) and normalized parquet under data/vendor_parquet/NQ|ES.

## 7. Limitations / TODO

- Holidays and half-days are not yet inlcuded in the model.
- No special handling for missing RTH bars or zero-volume bars. They are currently treated as gaps. Possible correction in the future for this.
- Overnight session (ONH/ONL) is not yet wired. This will be adjusted in future milestones.
- Single-instrument per run for now. Possible change in the future.
