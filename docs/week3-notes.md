## Week 3 – Triggers, Risk Cap & Entry Simulation

✅ Implemented

---

### 1. Micro structure trigger (`structure.py`)

- **`micro_swing_break(df1, high_col="high", low_col="low")`**
  - Consumes a 1-minute DataFrame that already has:
    - `swing_high` / `swing_low` from `find_swings_1m`.
  - For each session (per calendar day, no cross-day bleed) it:
    - Tracks the **most recent swing high** and **most recent swing low**.
    - Marks `micro_break_dir` as:
      - `+1` when price **first breaks above** the latest swing high.
      - `-1` when price **first breaks below** the latest swing low.
      - `0` otherwise.
  - Key rules:
    - No “peeking” – only swings that already existed before the bar can be broken.
    - If there is no valid swing yet, no break is emitted.
    - State resets cleanly at session boundaries.
  - This is the core “micro-structure” trigger used by the engine.

---

### 2. Engine signal extensions (`engine.generate_signals`)

`generate_signals(df_1m, df_5m=None, cfg=None)` is now the central place where
3A’s per-bar state is computed. Week 3 added:

#### 2.1 Time window (unchanged from Week 2)

- Uses `cfg.entry_window.start` / `cfg.entry_window.end` (defaults to **all bars allowed** if `cfg` is `None`).
- Index is converted to `America/New_York` when tz-aware.
- Populates **`time_window_ok`** (bool).

#### 2.2 Unlock logic (Week 2 recap – now feeding the rest of the state)

- Long unlock candidate:
  - `trend_5m > 0`
  - `close > or_high`
  - `close >= vwap`
  - `time_window_ok == True`
- Short unlock candidate:
  - `trend_5m < 0`
  - `close < or_low`
  - `close <= vwap`
  - `time_window_ok == True`
- Only the **first** unlock per session is marked:
  - `or_break_unlock = True` on that bar, `False` elsewhere (grouped by session date).
- **Direction** is now carried per-session:
  - At the unlock bar: `direction = +1` (long) or `-1` (short).
  - Forward-filled within the session; `0` when no unlock has happened.

#### 2.3 Opposite 2σ disqualifier (recap, now fully wired)

- Uses `vwap_2u`, `vwap_2d` and `direction`:
  - Long context: disqualify when `close <= vwap_2d`.
  - Short context: disqualify when `close >= vwap_2u`.
- Once hit, the flag stays **True for the rest of the day**:
  - `disqualified_2sigma` and `disqualified_±2σ` are both set via a per-day cumulative mask.
- The disqualifier:
  - Does **not** cancel the unlock flag (for diagnostics),
  - But **blocks zones and triggers** for that session.

#### 2.4 Zone logic – first pullback after unlock (recap)

- Works per session (calendar day in ET).
- Given a valid unlock and no 2σ disqualifier:

  - **Longs:**
    - Find the **first bar after unlock** where `close ∈ [vwap, vwap_1u]`.
  - **Shorts:**
    - First bar after unlock where `close ∈ [vwap_1d, vwap]`.

- Exactly **one zone per day**:
  - `in_zone = True` at the first qualifying bar, `False` elsewhere.

#### 2.5 Trigger logic – `trigger_ok`

New in Week 3: `trigger_ok` is now a real micro-structure trigger instead of a stub.

Inputs:
- `direction` (`+1/-1` from unlock & forward fill),
- `in_zone` (first pullback per day),
- `micro_break_dir` (from `micro_swing_break`),
- `engulf_dir` (reserved column; not yet fully used),
- `time_window_ok`,
- `disqualified_2sigma`,
- `vwap_1u`, `vwap_1d` (for “≤ 1 tick beyond band” rule),
- `cfg` (for `instrument.tick_size`).

Rules:

- **Pattern direction:**
  - Long pattern: `(micro_break_dir > 0) or (engulf_dir > 0)` with `direction > 0`.
  - Short pattern: `(micro_break_dir < 0) or (engulf_dir < 0)` with `direction < 0`.

- **Zone proximity:**
  - Base requirement: be at the **zone bar** (`in_zone == True`).
  - Optional “no chase” extension:
    - Longs may fire if **up to 1 tick above** `vwap_1u`.
    - Shorts may fire if **up to 1 tick below** `vwap_1d`.
    - Tick size is read from `cfg.instrument.tick_size` (or `cfg.tick_size`, default `1.0` in tests).

- **Filters:**
  - `time_window_ok == True`
  - `disqualified_2sigma == False`

- **Final flag:**
  - `trigger_ok` is `True` when:
    - direction is non-zero,
    - pattern and zone rules are met,
    - time-window and disqualifier filters pass.

This is the bar where the engine is **allowed to enter** (subject to risk cap and
simulation rules below).

---

### 3. Risk cap & stop price (`engine.generate_signals`)

Week 3 wires in entry-side risk control:

- **Config knobs:**
  - `cfg.tick_size` (or `cfg.instrument.tick_size`) → tick value in price.
  - `cfg.risk_cap_multiple` → default `1.25`.

- **OR height & cap:**
  - `or_height = or_high - or_low`
  - `max_sl_dist = or_height * risk_cap_multiple`
    - With default 1.25, this is **1.25 × OR height**.

- **Stop placement:**
  - Uses last known swings from `find_swings_1m`:
    - `swing_low` / `swing_high` flags are forward-filled **within the session**.
  - For each bar:
    - Long context (`direction > 0`):
      - `stop_price = last_swing_low - tick_size`
    - Short context (`direction < 0`):
      - `stop_price = last_swing_high + tick_size`
  - If no valid prior swing exists, `stop_price` is left `NaN` and the bar is treated as **risk-cap OK** by default.

- **SL distance & cap check:**
  - For longs: `sl_dist = close - stop_price`
  - For shorts: `sl_dist = stop_price - close`
  - `riskcap_ok` is:
    - `True` if `sl_dist <= max_sl_dist`,
    - `True` if no valid stop (`NaN`),
    - `False` only when a real stop exists and exceeds the cap.

This ensures that **deep invalidation swings** relative to OR height
will reject otherwise valid triggers.

---

### 4. Slippage model (`slippage.py`)

- **`apply_slippage(side, ts, raw_price, cfg)`**
  - Returns an **adversely slipped entry price**:
    - `side="long"` → add ticks above `raw_price`.
    - `side="short"` → subtract ticks below `raw_price`.
  - Tick size resolved from:
    - `cfg.instrument.tick_size` → falls back to `cfg.tick_size` → default `0.25`.
  - Slippage schedule:
    - Configurable “normal” vs “hot” windows via `cfg.slippage` (normal_ticks, hot_ticks, hot window times).
    - Tests often use **0-tick slippage** to keep prices clean.
  - This helper is only used at **entry** in Week 3; exit slippage will be handled in Week 4+.

---

### 5. Entry-only trade simulation (`engine.simulate_trades`)

`simulate_trades(df1, signals, cfg)` now produces a real trade log (entry-only).

Inputs:
- `signals`: 1-minute frame returned by `generate_signals`, containing:
  - `direction`, `trigger_ok`, `riskcap_ok`, `time_window_ok`,
  - `disqualified_2sigma`,
  - `stop_price`, `or_high`, `or_low`,
  - `vwap`, `vwap_1u`, `vwap_1d`,
  - `micro_break_dir`, `engulf_dir`,
  - plus OHLCV columns (especially `close`).

Candidate entries:
- Bars where:
  - `direction != 0`
  - `trigger_ok == True`
  - `riskcap_ok == True`
  - `time_window_ok == True`
  - `disqualified_2sigma == False`

For each candidate bar:

- **Side & raw price:**
  - `side = "long"` if `direction > 0`, `"short"` otherwise.
  - `raw_price = close`.

- **Stop & risk per unit:**
  - Skip if `stop_price` is missing.
  - `entry_price = apply_slippage(side, ts, raw_price, cfg)`.
  - `risk_per_unit = |entry_price - stop_price|`.
  - Skip degenerate cases where `risk_per_unit <= 0`.

- **R-space + targets:**
  - `risk_R = 1.0` (one-R risk per trade; sizing comes later).
  - `tp1 = entry_price ± 1R` (sign depends on side).
  - `tp2 = entry_price ± 2R`.

- **OR height, ticks, slippage diagnostics:**
  - `or_height = or_high - or_low` (if both are finite).
  - `sl_ticks = risk_per_unit / tick_size`.
  - `slippage_entry_ticks = (entry_price - raw_price) / tick_size`.

- **Trigger type (for later analytics):**
  - If direction is long:
    - `micro_break_dir > 0` → `"swingbreak"`.
    - Else if `engulf_dir > 0` → `"engulf"`.
  - Symmetric for shorts (negative values).
  - Default `"unknown"` when neither applies.

- **Location vs VWAP bands:**
  - If VWAP bands are present:
    - Long trades:
      - If `price ∈ [vwap, vwap_1u]`, label `"vwap"` or `"+1σ"` based on proximity.
    - Short trades:
      - Analogous `"vwap"` or `"-1σ"` label for `[vwap_1d, vwap]`.
  - Else location is `"none"`.

Output schema (`_TRADE_COLS`):

- `date`, `entry_time`, `exit_time` (NaT for now),
- `side`, `entry`, `stop`, `tp1`, `tp2`,
- `or_height`, `sl_ticks`,
- `risk_R`, `realized_R` (0.0 – exits not implemented yet),
- `t_to_tp1_min` (NaN placeholder),
- `trigger_type`, `location`,
- `time_stop`, `disqualifier`,
- `slippage_entry_ticks`, `slippage_exit_ticks`.

With QQQ dev data (Apr–Oct 2025) and default settings, the CLI currently
produces a **small handful of trades** (e.g. 7) – this is just a sanity
smoke test; serious evaluation waits for futures data + Week 4 exits.

---

### 6. CLI – End-to-end pipeline (`cli.py`)

`threea-run run-backtest --config configs/base.yaml --data <path>` now does:

1. **Config**
   `cfg = load_config(config_path)`.

2. **Load + RTH slice**
   - `df1 = load_minute_df(data_path, tz=cfg.tz)`
   - `df1 = slice_rth(df1)`

3. **Session features**
   - `refs = compute_session_refs(df1)` → adds `or_high`, `or_low`, `pdh`, `pdl`, `onh`, `onl`.
   - `bands = compute_session_vwap_bands(df1)` → `vwap`, `vwap_1u`, `vwap_1d`, `vwap_2u`, `vwap_2d`.
   - `atr15 = compute_atr15(df1)` → `atr15` column.

4. **5-minute structure**
   - `df5 = resample(df1, "5min")`.
   - `tr5 = trend_5m(df5)` → use `trend_5m` column, forward-filled back to 1-minute `df1["trend_5m"]`.

5. **1-minute swings + micro breaks**
   - `swings_1m = find_swings_1m(df1)` → `swing_high`, `swing_low`.
   - `micro = micro_swing_break(df1)` → `micro_break_dir`.

6. **Signals + trades**
   - `signals = generate_signals(df1, df5, cfg)`
   - `trades = simulate_trades(df1, signals, cfg)`

7. **Summary**
   - `SUMMARY = compute_summary(trades)` → prints `{trades, win_rate, avg_R, maxDD_R, SQN}`.
   - (Optionally) trades can be written to CSV for inspection.

---

### 7. Tests added / extended (Week 3)

- **Structure & trigger tests (`tests/test_structure.py`, `tests/test_engine.py`)**
  - New tests for `micro_swing_break`:
    - Correctly marks single upside / downside breaks.
    - Ignores breaks until a swing exists.
    - Resets per session.
  - Trigger tests:
    - `test_trigger_ok_long_micro_break_inside_zone`
      - Synthetic day with OR, VWAP bands, unlock, zone, and a micro break:
      - Verifies `trigger_ok` fires **only** on the micro-break zone bar and direction is `+1`.

- **Risk-cap tests (`tests/test_engine.py`)**
  - `test_riskcap_ok_when_stop_within_cap`
    - OR height 10 → cap 12.5.
    - Swing low close enough that the stop is **within** cap; `riskcap_ok` stays `True`.
  - `test_riskcap_rejects_when_stop_too_far`
    - Deeper swing low → stop is **beyond** 12.5; at least one bar has `riskcap_ok == False`.

- **Trade-sim scenario tests (`tests/test_engine_week3.py`)**
  - Helper `_make_long_day_df(...)` builds a single synthetic day with:
    - OR band, unlock, zone, micro break, and swings wired so `generate_signals` + `simulate_trades` see a full path.
  - `test_engine_week3_basic_entry_long`
    - Verifies a valid trigger + riskcap combo results in **exactly one trade** with the expected:
      - side (`"long"`),
      - entry timestamp (zone/trigger bar),
      - positive `risk_R` and non-zero SL distance.
  - `test_engine_week3_riskcap_blocks_trade_when_stop_too_far`
    - Same path but earlier swing low is much deeper:
      - `trigger_ok` still `True`,
      - `riskcap_ok` `False` at the trigger bar,
      - `simulate_trades` returns **no trades**.

- **Proof commands / smoke tests**
  - Week 3 blocks can be re-verified with:
    - `pytest -q -k "micro_swing or engulf or trigger_ok"`
    - `pytest -q -k engine_week3`
    - Full suite: `pytest -q` → all tests passing.
  - QQQ smoke run:
    - `threea-run run-backtest --config configs/base.yaml --data data/QQQ_1min_2025-04_to_2025-10.csv`

- **Commands**
  - Populate the test debug file in output:
    - `python -c "import pandas as pd; print(pd.read_csv('outputs/trades_debug.csv').head())” - to populate the test debug file in output`
  - Debugging QQQ data signals script:
    - `python scripts/debug_signals_qqq.py`

---

### 8. Not implemented yet (Week 4+)

- **Exit & management (Week 4 objective):**
  - TP1/TP2 execution, scaling out, stop-to-BE logic.
  - Time-based exit rules (must reach TP1 within X minutes, session end, etc.).
  - Realized R and trade lifecycle metrics.

- **Filters:**
  - News blackout windows, tiny-day skip (small OR / ATR15), spread/DOM skip flag.

- **Session-scoped state checks:**
  - More robust guards against multi-day leakage in trade management.

- **Golden-day dataset on futures:**
  - 20+ hand-marked NQ/ES sessions with unlock/zone/trigger annotations,
  - Tests to ensure engine decisions match manual marks bar-for-bar.

- **Walk-forward & Monte Carlo:**
  - Rolling IS/OOS (`walkforward.py`),
  - Equity-path simulations (`monte_carlo.py`) on finalized trade logs.
