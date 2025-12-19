## Week 4 – Trade Management, Session Filters, and Databento API Pipeline

✅ Implemented

---

### 0. Naming / Project Identity (3A-Backtester → **Meridian**)

- Project name updated to **Meridian** (the backtester + research harness for Strategy 3A).
- Note: internal Python package/module names may still remain `s3a_backtester/` for now (to avoid breaking imports), but all docs and “public-facing” references should refer to **Meridian**.

(Week 3 baseline reference: triggers + entry simulation + risk cap.)

---

### 1. Trade Management Module (`management.py`)

Week 4 introduces **full lifecycle management** for a trade after entry.

#### 1.1 TP1 logic (`apply_tp1`)
- TP1 is defined in **R-multiples**:
  - default: `tp1_R = +1.0R` (configurable)
- When TP1 is hit:
  - scale out a fraction of size (e.g., `scale_at_tp1 = 0.50`)
  - optionally move stop to **break-even** (`move_to_BE_on_tp1=True`)
- TP1 behavior is deterministic and unit-tested with synthetic intraday paths.

#### 1.2 TP2 target selection (`compute_tp2_target`)
TP2 is defined as the **earliest valid** target among:
- PDH/PDL (if untagged),
- OR measured move,
- fixed R target (`tp2_R`, default +2R),

Tie-break priority is deterministic:
- PDH/PDL > measured move > +R target

This keeps “target arbitration” stable and reproducible.

#### 1.3 Time stop (`run_time_stop`)
Time-based exit policy:
- Must hit TP1 within `tp1_timeout_min` (default 15 minutes) or exit at market
- Optional extension to a longer maximum hold (e.g., 45 minutes total) if extension conditions hold:
  - VWAP side intact
  - 5-minute trend intact
  - no close beyond ±1σ *against* the trade
  - drawdown does not exceed a fixed threshold (e.g., ≤ 0.5R)

The extension logic is wired so **time-stop conditions are computed as a per-bar series**, not ad-hoc checks, making it testable and auditable.

#### 1.4 Unified lifecycle wrapper (`manage_trade_lifecycle`)
- A single helper coordinates:
  - TP1 scaling + BE move
  - TP2 exit
  - time-stop exit
  - stop-loss exit
- Outputs normalized trade fields:
  - `exit_time`, `realized_R`, `t_to_tp1_min`, `time_stop`, and exit slippage ticks

---

### 2. Time-Stop Condition Series (`time_stop_conditions.py`)

To keep `engine.py` readable and reduce “god-function” drift, time-stop eligibility checks were extracted into a dedicated module.

Key helpers:
- `_infer_trend_ok(...)`
  - infers whether trend remains intact (based on the available 5m trend label column)
- `build_time_stop_condition_series(...)`
  - produces a per-bar boolean series that encodes:
    - VWAP-side-ok
    - sigma-ok (±1σ against condition)
    - trend-ok
    - (optional) drawdown-ok (based on R drawdown constraint)

This enables:
- clean engine wiring (engine passes precomputed condition series into time-stop logic)
- deterministic tests that pin down “extension breaks at bar X” behavior

---

### 3. Engine Updates (Signals → Simulation → Managed Exits)

#### 3.1 `engine.simulate_trades` now manages the full lifecycle
Week 3 simulated entry-only trades. Week 4 extends simulation to include:
- TP1 partial exit and BE stop move
- TP2 exit logic via arbitration
- time-stop exit logic
- stop-loss exit logic
- slippage applied at both entry and exit (exit slippage now included in diagnostics)

Additional hardening:
- session-scoped caching/state uses explicit `datetime.date` imports and no multi-day bleed
- managed lifecycle fields are always populated consistently (even if NaN/False)

#### 3.2 Trigger/zone wiring improvements (Meridian robustness)
- The “zone touch → trigger next bar” behavior is supported:
  - zone can arm the setup, and the breakout bar may occur slightly after the zone touch
- A dedicated engine test file was added to lock in:
  - trigger fires on breakout after zone touch
  - trigger does not fire without zone touch
  - direction mismatch blocks trigger
  - zone_seen resets cleanly by session date

---

### 4. Session Filters (Day-level gating) (`filters.py`)

Week 4 introduces **session-level filters** that gate entry attempts for the entire day.

Implemented as:
- `build_session_filter_mask(...)` → returns a per-bar boolean mask `in_session_ok`

Filters include:
- **News blackout placeholder**:
  - per-day flag (or external calendar later)
  - gates entries ± blackout window
- **Tiny-day skip**:
  - skip if OR height is tiny relative to rolling median
  - skip if ATR15 is in the bottom percentile of rolling history
- **Spread/DOM skip placeholder**:
  - per-day boolean flag (to be wired to real spread/DOM later)

The important part:
- filters apply at the **session/day** level (mask), not as scattered inline conditions,
  which keeps the engine deterministic and auditable.

---

### 5. Databento Data Pipeline (Portal → API Continuous Futures)

Week 4 finalizes a stable, credit-safe approach to acquiring NQ/ES futures data for Meridian using the **Databento API**, avoiding portal “parent product” downloads that include unwanted child instruments/spreads.

#### 5.1 Active scripts (Meridian pipeline)
- `scripts/databento_fetch_continuous.py`
  - fetch continuous futures OHLCV-1m (e.g., `NQ.v.0`, `ES.v.0`)
  - writes RAW vendor parquet under `data/raw/databento_api/`
  - enforces a max-range guard to protect remaining credits
  - uses env var: `DATABENTO_API_KEY`

- `scripts/normalize_continuous_to_vendor_parquet.py`
  - normalizes raw vendor parquet into backtester-ready schema
  - slices to **RTH** and produces:
    - combined file: `data/vendor_parquet/<PRODUCT>/<symbol>_<start>_<end>_RTH.parquet`
    - optional by-day files under `data/vendor_parquet/<PRODUCT>/by_day/<symbol>/YYYY/MM/YYYY-MM-DD.parquet`

- `scripts/data_inventory.py`
  - inventories parquet folders for QA:
    - row counts, time ranges, columns, bytes
  - outputs CSVs under `outputs/`

#### 5.2 Script organization (repo hygiene)
- Legacy portal conversion remains available (not used in current pipeline):
  - `convert_databento_to_parquet.py` should live under `scripts/legacy/`
- QQQ-only debug remains available (dev tooling):
  - `debug_signals_qqq.py` should live under `scripts/dev/`

#### 5.3 Week 4 Gate dataset (3-month NQ)
- Successfully fetched and normalized **3 recent months** of NQ continuous futures:
  - continuous symbol: `NQ.v.0`
  - RTH-sliced vendor parquet produced and validated with inventory checks
- Same pipeline supports ES (future Week 5+ cross-validation / robustness checks)

---

### 6. CLI / Runs (End-to-end)

`threea-run run-backtest --config configs/base.yaml --data <vendor_parquet.parquet>` now supports:

- load + tz normalize + RTH slice
- features + structure + triggers
- session filters gating
- trade simulation with full lifecycle management (TP1/TP2/time-stop)
- summary output and artifacts written under `outputs/` (run-scoped folders recommended)

A lightweight “signal coverage” debug mode was used during integration to ensure:
- expected columns exist (`micro_break_dir`, `in_zone`, `trigger_ok`, etc.)
- entry candidates are non-zero on real data
- missing feature columns are detected early (rather than silently producing zero trades)

---

### 7. Tests Added / Extended (Week 4)

Key additions:
- Management unit tests:
  - TP1 scaling + BE move
  - TP2 arbitration and tie-break priority
  - time-stop and extension break conditions
- Engine integration tests:
  - wiring of management module into `simulate_trades`
  - trigger behavior around zone touch / breakout timing
- Session filters unit tests:
  - tiny-day and placeholder flags gate entire sessions correctly

Tooling hygiene:
- ruff failures (unused locals, etc.) were addressed so CI/pre-commit remains strict
- pandas deprecation warnings in IO were fixed by updating dtype checks

Proof commands:
- `pytest -q`
- `pytest -q -k engine_triggers`
- `pre-commit run --all-files`

---

### 8. Week 4 Gate Artifacts (Definition of Done)

Week 4 is considered complete with:
- **3-month NQ** dataset fetched + normalized via Databento API pipeline
- full 3-month Meridian backtest run completed with:
  - trades output (CSV/Parquet)
  - run summary (JSON or printed summary captured)
  - config used for reproducibility
- manual audit performed:
  - 30-trade random sample exported
  - audit notes written and stored under docs

Docs delivered:
- `docs/data-notes.md` (contract / invariants updated)
- `docs/data-pipeline.md` (current API pipeline)

---

### 9. Not implemented yet (Week 5+)

- Walk-forward (rolling IS/OOS) and output reports (`walkforward.py`)
- Monte Carlo bootstrap of R-multiples and DD percentiles (`monte_carlo.py`)
- Full metrics suite:
  - grouping by OR quartile, day-of-week, month
  - additional robustness stats / slicing
- Larger regime coverage:
  - multi-year NQ (and ES cross-validation)
  - sensitivity / parameter sweeps
- Stronger “golden-days” fixture set:
  - curated sessions with expected unlock/zone/trigger/management outcomes
  - bar-by-bar assertion tests for deterministic replay
