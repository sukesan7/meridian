# Meridian — Strategy Validation Results

## 1. Summary (v1_0_5_baseline)

This document contains the **Audited Performance Report** for the Meridian execution engine.
It is generated programmatically from run artifacts (`run_meta.json`, `summary.json`) and optional profiler timing outputs.

* **Run Label**: `v1_0_5_backtest_baseline`
* **Data Source**: `data\vendor_parquet\NQ\NQ.v.0_2024-12-01_2025-11-30_RTH.parquet`

## 2. Headline Performance Stats (Backtest)

| Metric | Value | Description |
| --- | --- | --- |
| **Total Trades** | `67` |  |
| **Win Rate** | `0.5075` | Target > 40% |
| **Expectancy (R)** | `0.09082` | Risk-adjusted return per trade |
| **Avg R** | `0.09082` |  |
| **Avg Win** | `0.9442` |  |
| **Avg Loss** | `-0.813` |  |
| **Max Drawdown (R)** | `4.886` |  |
| **SQN** | `0.7825` | System Quality Number |

## 3. Walk-Forward Analysis (Robustness)

The Walk-Forward engine prevents overfitting by enforcing a strict separation between In-Sample (IS) calibration and Out-of-Sample (OOS) verification.

* **Window**: `63` Days IS / `21` Days OOS.

| Metric | Value | Interpretation |
| --- | --- | --- |
| **SQN** | `0.9872` |  |
| **avg_R** | `0.326` |  |
| **avg_loss_R** | `-0.7471` |  |
| **avg_win_R** | `1.185` |  |
| **expectancy_R** | `0.326` |  |
| **is_end** | `2025-03-03` |  |
| **is_start** | `2024-12-02` |  |
| **maxDD_R** | `1.988` |  |
| **oos_end** | `2025-04-01` |  |
| **oos_start** | `2025-03-04` |  |
| **sum_R** | `2.934` |  |
| **trades** | `9` |  |
| **trades_per_month** | `9` |  |
| **win_rate** | `0.5556` |  |
| **window_id** | `0` |  |

## 4. Monte Carlo Simulation (Risk Assessment)

Stress-testing sequence risk using block-bootstrap resampling on realized R-multiples.

* **Iterations**: `2500` paths
* **Seed**: `105`
* **Risk Per Trade**: `0.01`

| Risk Metric | Value | Interpretation |
| --- | --- | --- |
| **n_paths** | `2500` |  |
| **risk_per_trade** | `0.01` |  |
| **blowup_rate** | `0` |  |
| **median_cagr** | `0.06208` |  |
| **maxDD_pct_p95** | `0.117` |  |
| **maxDD_pct_p50** | `0.05932` |  |

## 4.5 Performance Profile (Reference Machine)

| Timing File | Seconds | Command (truncated) |
| --- | --- | --- |
| **outputs/profiles/v1_0_5_baseline/backtest_prof/backtest.timing.json** | `13.3` | backtest --config configs\base.yaml --data data\vendor_parquet\NQ\NQ.v.0_2024-12-01_2025-11-30_RTH.parquet --out-dir ... |
| **outputs/profiles/v1_0_5_baseline/walkforward_prof/walkforward.timing.json** | `15.66` | walkforward --config configs\base.yaml --data data\vendor_parquet\NQ\NQ.v.0_2024-12-01_2025-11-30_RTH.parquet --is-days ... |
| **outputs/profiles/v1_0_5_baseline/montecarlo_prof/monte_carlo.timing.json** | `0.4912` | monte-carlo --config configs\base.yaml --trades outputs\backtest\v1_0_5_backtest_baseline\trades.parquet --n-paths ... |

## 5. Reproducibility Contract

Meridian guarantees reproducibility of reported results via immutable inputs and recorded metadata:

* **Config Snapshot**: stored in `run_meta.json`.
* **Deterministic Seeding**: Seed `105` for baseline runs (unless overridden per module).
* **Backtest Artifacts**: `outputs/backtest/v1_0_5_backtest_baseline`
* **Walkforward Artifacts**: `outputs/walkforward/v1_0_5_walkforward_baseline`
* **Monte Carlo Artifacts**: `outputs/monte-carlo/v1_0_5_montecarlo_baseline`

> **Disclaimer:** Past performance is not indicative of future results.
