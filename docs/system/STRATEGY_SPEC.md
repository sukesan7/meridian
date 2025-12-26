# Strategy 3A: Event-Driven Momentum (Specification)

## 1. Thesis
Strategy 3A is a **Session-Breakout Mean-Reversion Hybrid**. It capitalizes on the expansion of volatility following the initial Opening Range (OR) of the US Equity Futures session.

* **Instrument:** NQ (Nasdaq 100 Futures)
* **Session:** RTH (09:30 – 16:00 ET)
* **Directionality:** Trend Following (matches 5-minute structure).

## 2. Setup Logic

### 2.1 The "Unlock" (State 1)
The session is considered "unlocked" for trading when price successfully breaks the Opening Range (09:30-09:35) in the direction of the trend.
* **Long Unlock:** `Close > OR_High` AND `Trend_5m == Bullish`
* **Short Unlock:** `Close < OR_Low` AND `Trend_5m == Bearish`

### 2.2 The "Zone" (State 2)
Once unlocked, the algo waits for a mean-reversion pullback into value.
* **Long Zone:** First pullback into `[VWAP, VWAP + 1σ]`.
* **Short Zone:** First pullback into `[VWAP - 1σ, VWAP]`.
* **Constraint:** Only the *first* valid zone touch per session is tradeable.

### 2.3 The "Trigger" (State 3)
Entry occurs on micro-structure validation within the Zone.
* **Signal:** 1-Minute Micro-Swing Break (breaking the most recent high in a Long setup).
* **Confirmation:** Must occur while price is interacting with the Zone.

## 3. Risk & Execution

### 3.1 Invalidations (Gating)
* **2σ Disqualifier:** If price touches the *opposite* 2σ band (e.g., Short Band while looking for Longs), the session is disqualified immediately.
* **Risk Cap:** If `(Entry - Stop)` > `1.25 * OR_Height`, the trade is skipped (Volatility too high).

### 3.2 Management
* **Stop Loss:** Placed at the most recent invalidation swing.
* **Target 1:** +1R (Scale 50%, Move Stop to Breakeven).
* **Target 2:** Technical Target (Measured Move or PDH/PDL).
* **Time Stop:** Exit if stuck for >15 minutes without hitting TP1.
