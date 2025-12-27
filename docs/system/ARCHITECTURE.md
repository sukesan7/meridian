# Meridian Engine Architecture

## 1. System Design
Meridian is an **Event-Driven, Vector-Hybrid Backtester**. It uses vectorized operations for feature pre-calculation (for speed) and an event loop for execution simulation (for path-dependence accuracy).

```mermaid
graph TD
    Data[(Parquet Store)] -->|Load & Normalize| IO[Data IO Layer]
    IO -->|Raw 1m Bars| Feat[Feature Engine]

    subgraph "Pre-Calculation Phase"
        Feat -->|Resample| T5[5m Trend Logic]
        Feat -->|Scan| Swing[Confirmed Swing Detection]
        Feat -->|Compute| Ind[VWAP / Bands / OR]
    end

    subgraph "Event Loop (Bar-by-Bar)"
        Ind -->|Stream State| Sig{Signal Logic}
        Sig -->|Trigger| Exec[Execution Simulator]
        Exec -->|Fill/Stop/TP| Port[Portfolio State]
    end

    Port -->|Trade Log| Perf[Performance Analytics]
    Perf -->|Bootstrap| MC[Monte Carlo Engine]
```

## 2. Core Subsystems

### 2.1 Feature Engine (`/features`)
Responsible for transforming raw OHLCV data into tradable signals.
* **Hybrid Approach:** Heavy calculations (e.g., VWAP, ATR) are pre-calculated vectorially.
* **Look-Ahead Safety:**
    * All features use strict right-edge labeling.
    * **Swing Detection:** Uses a `find_swings_1m` algorithm that requires `rb` (right-bars) confirmation before marking a pivot, preventing look-ahead bias.

### 2.2 Signal Logic (`/logic`)
Implements the specific trading strategy (Strategy 3A).
* **Constraints:** `OR Break`, `Pullback Zone`, `Micro-Structure Entry`.
* **Gating:** `disqualify_after_unlock` ensures failed setups are discarded immediately.

### 2.3 Execution Simulator (`/engine`)
A deterministic simulation of an exchange matching engine.
* **Slippage Model:** Dynamic slippage based on volatility regimes.
* **Lifecycle:** Handles `TP1` scaling, `Breakeven` adjustments, and `Time-Based Exits`.

## 3. Reliability & Reproducibility
* **Deterministic Seeds:** All random processes (Monte Carlo, slippage noise) are seeded via `run_meta.json`.
* **Artifacts:** Every run produces a self-contained output folder with `summary.json`, `trades.parquet`, and config snapshots.
