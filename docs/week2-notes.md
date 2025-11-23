## Week 2 - Structure & Engine (unlock/zone logic) + Futures Data Pipeline

✅ Implemented

- **Price structure (`structure.py`):**
  - `trend_5m(df5, vwap_col="vwap")`:
    - Labels each 5-minute bar as:
      - `+1` → uptrend (HH/HL + price on/above VWAP),
      - `-1` → downtrend (LH/LL + price on/below VWAP),
      - `0` → neutral.
    - This is the canonical trend filter used by the engine.

- **Micro structure (`features.py`):**
  - `find_swings_1m(df1, lb=2, rb=2)`:
    - Marks 1-minute swing highs/lows using left/right bar comparisons.
    - Output is aligned to the 1-minute index and will be used later for:
      - micro swing break triggers,
      - invalidation swing / stop placement logic.

- **Engine signals (`engine.py` — `generate_signals`)**:
  - Signature:
    - Supports both `(df_1m,)` and `(df_1m, df_5m, cfg)` forms.
    - If required columns are missing (early stub usage), it returns the input with default signal columns so tests/CLI don’t explode.
  - Ensures the following per-bar signal columns exist:
    - `time_window_ok`
    - `or_break_unlock`
    - `in_zone`
    - `trigger_ok` (placeholder for Week 3+ trigger logic)
    - `disqualified_2sigma`
    - `disqualified_±2σ` (alias for reporting)
    - `riskcap_ok` (placeholder for future risk filters)
    - `direction` (`+1`, `-1`, or `0`, derived from `trend_5m`)
  - **Entry window / time filter**:
    - Converts timestamps to `America/New_York` when tz-aware.
    - Uses `cfg.entry_window.start` / `cfg.entry_window.end` if provided; otherwise defaults to “all bars allowed” for tests.
    - Populates `time_window_ok` as a boolean mask.
  - **Unlock logic (first OR break in trend direction)**:
    - Long unlock:
      - `direction = +1`
      - `close > or_high`
      - `close >= vwap`
      - `time_window_ok` is `True`
    - Short unlock:
      - `direction = -1`
      - `close < or_low`
      - `close <= vwap`
      - `time_window_ok` is `True`
    - Only the **first** unlock per session is marked via:
      - `or_break_unlock = True` on that bar, `False` elsewhere (grouped by session date).
  - **Opposite 2σ disqualifier**:
    - Uses `vwap_2u`, `vwap_2d` and `direction`:
      - In long context: disqualify when `close <= vwap_2d`.
      - In short context: disqualify when `close >= vwap_2u`.
    - Once triggered, the disqualifier flag remains `True` for the rest of the session:
      - `disqualified_2sigma` and `disqualified_±2σ` are computed as a per-day cumulative state.
  - **Zone marking (first pullback)**:
    - After a valid unlock:
      - **Longs**: first bar *after unlock* where `close ∈ [vwap, vwap_1u]`, `time_window_ok` is `True`, and the session is not disqualified.
      - **Shorts**: first bar *after unlock* where `close ∈ [vwap_1d, vwap]`, under the same conditions.
    - Only **one** zone bar per day is marked:
      - `in_zone = True` on the first valid pullback, `False` elsewhere.

- **Trade simulation stub (`engine.py` — `simulate_trades`)**:
  - Currently returns an empty DataFrame with the full trade-log schema:
    - `date`, `entry_time`, `exit_time`, `side`, `entry`, `stop`, `tp1`, `tp2`,
      `or_height`, `sl_ticks`, `risk_R`, `realized_R`, `t_to_tp1_min`,
      `trigger_type`, `location`, `time_stop`, `disqualifier`,
      `slippage_entry_ticks`, `slippage_exit_ticks`.
  - This will be filled in later with full 3A entry/exit/management rules.

- **Tests extended (`tests/`)**:
  - `tests/test_features.py`:
    - Validates VWAP/bands, OR refs, ATR15, and `find_swings_1m` shape/safety.
  - `tests/test_engine.py`:
    - `test_engine_stubs_run`:
      - Ensures `generate_signals(df1, df5, cfg)` runs and returns all expected signal columns.
    - `test_generate_signals_unlock_and_zone_long`:
      - Synthetic day where:
        - a single long unlock occurs at the designed bar,
        - exactly one zone bar (first pullback into `[VWAP, +1σ]`) is marked,
        - no 2σ disqualification occurs.
    - `test_generate_signals_disqualified_long_if_opposite_2sigma_hit_first`:
      - Synthetic day where the market hits the *opposite* 2σ band before unlock:
        - unlock bar is still identified,
        - session is flagged `disqualified_2sigma = True`.
    - `test_generate_signals_only_first_zone_per_day`:
      - Multiple zone candidates after unlock; only the **first** is marked as `in_zone`.
  - `tests/test_metrics.py`:
    - Confirms that metrics and equity-curve helpers are empty-safe and behave as expected.

- **Futures data pipeline (Databento, NQ/ES)**:
  - Raw Databento CSVs (after zstd decompress) are organized under:
    - `data/raw/databento/NQ/*.csv`
    - `data/raw/databento/ES/*.csv`
  - Normalization script (`scripts/convert_databento_to_parquet.py`):
    - Reads each Databento CSV.
    - Parses vendor timestamps (UTC), converts to `America/New_York`.
    - Selects `open`, `high`, `low`, `close`, `volume` (and `symbol` when present).
    - Sorts by time and writes normalized Parquet to:
      - `data/vendor_parquet/NQ/*.parquet`
      - `data/vendor_parquet/ES/*.parquet`
  - Normalized Parquet files:
    - Have a tz-aware `DatetimeIndex` in `America/New_York`.
    - Conform to the same 1-minute data contract as QQQ dev data.
  - Engine and feature code can now be run against either:
    - QQQ dev CSVs (fast iteration),
    - NQ/ES Parquet (production-like backtests).

---

🚧 Not implemented yet (later weeks)

- Full 3A trade simulation inside `simulate_trades`:
  - 1-minute trigger logic (engulf/micro swing break),
  - entry/stop/TP placement,
  - R accounting and time-stop logic.
- Risk cap enforcement:
  - `riskcap_ok` still a placeholder (e.g. max R per day, max open risk).
- Walk-forward IS/OOS evaluation:
  - `walkforward.py` to orchestrate rolling train/test windows.
- Monte Carlo on trade series:
  - `monte_carlo.py` to simulate equity paths and estimate MaxDD/CAGR distributions.
- ONH/ONL, holidays, and half-days:
  - Overnight high/low not yet integrated,
  - No explicit handling of exchange holidays or shortened sessions.
