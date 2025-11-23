### Week 1 - Data Foundation & Determinstic Scallfolding

✅ Implemented

- Python package `s3a_backtester` with CLI entrypoint.
- Data I/O:
  - `load_minute_df` – strict 1-minute OHLCV loader.
  - `slice_rth` – RTH filter (`09:30–16:00` ET, tz-aware, DST-safe).
  - `resample(rule="5min"|"30min")` – right-labeled, right-closed, no look-ahead.
- Session features:
  - `compute_session_refs` – OR (09:30–09:35), `or_high`, `or_low`, `or_height`, PDH/PDL placeholders.
  - `compute_session_vwap_bands` – session-anchored VWAP with ±1σ/±2σ bands.
  - `compute_atr15` – 15-minute ATR over the 1-minute series.
- Tests:
  - I/O + RTH slicing.
  - 5-min and 30-min resample alignment (no peek).
  - OR/VWAP/bands.
  - ATR15.
  - Synthetic DST regression (RTH behavior across the DST switch).
- Docs:
  - `docs/data-notes.md` – data contract (schema, tz/DST, RTH, resampling, dev vs prod data).
- CI:
  - GitHub Actions matrix (Python 3.10/3.11) running pre-commit (ruff/black) + pytest on every push/PR.
  - Protected `main`: changes go through feature branches and PRs.

🚧 Not implemented yet (Week 2+)

- 3A signal generation (trend unlock, pullback zone, triggers).
- Trade simulation & portfolio accounting.
- Walk-forward IS/OOS evaluation.
- Monte Carlo on trade series.

The current code is a **solid data/feature layer** ready for strategy logic.
