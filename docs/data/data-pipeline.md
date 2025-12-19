# 3A Backtester — Data Pipeline (Databento API → Meridian Vendor Parquet)

## Purpose

This document describes the **current, supported pipeline** for acquiring and normalizing **continuous futures** data (NQ / ES) for Meridian:

1) Fetch 1-minute OHLCV from Databento API (continuous symbol)
2) Normalize into a clean, backtester-ready Parquet schema
3) (Optional) Split into `by_day/` files for faster iteration and QA
4) Inventory/QA to confirm coverage and expected row counts

For stable data assumptions (schema, tz/DST, RTH, resampling), see `docs/data-notes.md`.


---

## Folder Layout

```text
data/
  raw/
    databento_api/
      <dataset>_<schema>_<symbol>_<start>_<end>.parquet     # RAW vendor parquet from Databento API
  vendor_parquet/
    NQ/
      NQ.v.0_<start>_<end>_RTH.parquet                      # COMBINED RTH-only, normalized
      by_day/
        NQ.v.0/
          YYYY/
            MM/
              YYYY-MM-DD.parquet                            # OPTIONAL per-day RTH bars
    ES/
      ES.v.0_<start>_<end>_RTH.parquet
      by_day/
        ES.v.0/
          YYYY/
            MM/
              YYYY-MM-DD.parquet
outputs/
  data_inventory_*.csv                                      # optional QA inventories
```

Notes:
- `raw/` is vendor-shaped data. Kept it for reproducibility.
- `vendor_parquet/` is what the backtester should consume.


---

## Active Scripts (Supported)

These scripts are considered **active** and used in the current pipeline:

- `scripts/databento_fetch_continuous.py`
- `scripts/normalize_continuous_to_vendor_parquet.py`
- `scripts/data_inventory.py`

Other scripts (e.g., legacy portal converters, QQQ debug utilities) live under `scripts/legacy/` or `scripts/dev/`.


---

## API Key Setup

### Preferred: environment variable

Set your key once per terminal session:

**PowerShell**
```powershell
$env:DATABENTO_API_KEY = "YOUR_KEY_HERE"
```

**macOS/Linux**
```bash
export DATABENTO_API_KEY="YOUR_KEY_HERE"
```

Important:
- Do **not** hardcode the key in scripts.
- Do **not** commit keys to git.
- Optionally, store it in your shell profile / Windows user env vars.

### Credit protection

The fetch script should refuse large ranges (example guard):
- refuse requests over ~120 days unless explicitly changed


---

## Pipeline: 3-Month Gate Dataset (Week 4)

Goal: produce **~3 months** of NQ RTH 1-minute bars for Meridian to run:
- expected rows ≈ `~390–391 * trading_days`

### 1) Fetch RAW continuous OHLCV (Databento API)

Example (NQ):

```powershell
python scripts\databento_fetch_continuous.py `
  --symbol NQ.v.0 `
  --start 2025-11-03 `
  --end   2025-11-07
```

Outputs:
- `data/raw/databento_api/<dataset>_<schema>_NQ.v.0_<start>_<end>.parquet`

Quick sanity check:

```powershell
python -c "import pandas as pd, glob; p=sorted(glob.glob('data/raw/databento_api/*.parquet'))[-1]; df=pd.read_parquet(p); print('rows',len(df)); print('cols',df.columns.tolist()); print('tmin',df.index.min(),'tmax',df.index.max());"
```

You should see:
- Index named `ts_event` (UTC)
- Columns like `open/high/low/close/volume/symbol` (plus vendor fields)


### 2) Normalize RAW → Vendor Parquet (RTH-only)

```powershell
python scripts\normalize_continuous_to_vendor_parquet.py `
  --raw-parquet data\raw\databento_api\GLBX.MDP3_ohlcv-1m_NQ.v.0_2025-11-03_2025-11-07.parquet `
  --symbol NQ.v.0 `
  --product NQ `
  --start 2025-11-03 `
  --end   2025-11-07
```

Outputs:
- `data/vendor_parquet/NQ/NQ.v.0_<start>_<end>_RTH.parquet`
- `data/vendor_parquet/NQ/by_day/NQ.v.0/YYYY/MM/YYYY-MM-DD.parquet` (optional but recommended)

Sanity check (rows and timestamps):

```powershell
python -c "import pandas as pd; p=r'data/vendor_parquet/NQ/NQ.v.0_2025-11-03_2025-11-07_RTH.parquet'; df=pd.read_parquet(p); print('rows',len(df)); print('tmin',df['timestamp'].min(),'tmax',df['timestamp'].max()); print(df.head()); print(df.tail());"
```

Expected:
- Rows ≈ `~390 * trading_days` (depending on inclusive/exclusive rules)
- `timestamp` in UTC (file), convertible to ET by loader
- Columns: `timestamp, symbol, open, high, low, close, volume`


### 3) Inventory / QA (optional but recommended)

Inventory combined file or by-day directory:

```powershell
python scripts\data_inventory.py --parquet-dir data\vendor_parquet\NQ --out outputs\data_inventory_nq.csv
```

Review:
- unexpected tiny days (rows=1, etc.) should be investigated
- check date ranges and missing days


---

## Running Meridian on Vendor Parquet

Once you have a combined RTH parquet:

```powershell
threea-run run-backtest --config configs\base.yaml --data data\vendor_parquet\NQ\NQ.v.0_2025-11-03_2025-11-07_RTH.parquet
```

If trades are unexpectedly low/zero, debug by inspecting:
- `or_break_unlock` counts
- `in_zone` counts
- `micro_break_dir` / `engulf_dir` availability

A quick “signal coverage” debug print is typically enough to confirm whether the issue is:
- data alignment (timezone/session)
- missing features/columns (engulf/swings not computed)
- overly strict filters


---

## Common Failure Modes

### 1) Time range errors (start == end)

Databento API expects an interval. If you pass a single date, the fetch script must internally make the end inclusive by adding one day (or use an end timestamp).

### 2) Wrong instrument type

Use continuous symbols like:
- `NQ.v.0`
- `ES.v.0`

and `stype_in=continuous`.

### 3) Parent-product “spread explosion”

This is the problem the API pipeline avoids. The portal often returns many child instruments/spreads.

### 4) RTH row counts look wrong

- Confirm you’re slicing to `09:30–16:00 ET` (RTH)
- Confirm timestamps are UTC in file and converted to ET in the loader
- Confirm you didn’t accidentally write `by_day` for non-RTH data


---

## Reproducibility Notes

- Keep raw Parquet files (API output) alongside normalized vendor Parquet.
- Kept the exact CLI commands used to fetch/normalize in Week 4 gate notes.
- Prefer deterministic runs (fixed seeds for MC later; not part of Week 4).
