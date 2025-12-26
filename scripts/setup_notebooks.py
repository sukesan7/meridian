"""
Script: Notebook Generator
Purpose: Programmatically creates professional Jupyter Notebooks for the portfolio.

Description:
    Generates .ipynb files with structured Markdown and Code cells.
    - Aligns documentation with 'engine.py' (Strong Trend Variant).
    - Targets 12-Month NQ Production Data.
    - Includes robust feature engineering steps to prevent KeyErrors.

Usage:
    python scripts/setup_notebooks.py
"""

import nbformat as nbf
from pathlib import Path


def create_strategy_viz_notebook():
    nb = nbf.v4.new_notebook()

    nb.cells.append(
        nbf.v4.new_markdown_cell(
            """
# Strategy 3A: Logic Visualization
**Objective:** Visually verify the Event-Driven State Machine (Unlock -> Zone -> Trigger) on Real Market Data.

## 1. Thesis (Strong Trend Variant)
This implementation of Strategy 3A optimizes for **Strong Trend Continuation**. Unlike mean-reversion systems that wait for deep crosses, this engine targets shallow pullbacks that hold value.

1.  **Unlock:** Price breaks the Opening Range (OR) in the direction of the 5-minute trend.
2.  **Zone (Momentum):** Price pulls back into value but **holds VWAP**.
    * *Longs:* Price tests `[VWAP, +1σ]`.
    * *Shorts:* Price tests `[-1σ, VWAP]`.
3.  **Trigger:** Micro-structure confirms the resumption of the trend.

> **Implementation Note:** The core engine is configured for this "Shallow Pullback" logic to filter out choppy markets. Deep pullbacks (crossing VWAP) are filtered out by the zone definition in `engine.py`.
"""
        )
    )

    nb.cells.append(
        nbf.v4.new_code_cell(
            """
# 1. Environment Setup
%pip install matplotlib seaborn

import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Add project root to path so we can import 's3a_backtester'
sys.path.append(os.path.abspath("../.."))

from s3a_backtester.data_io import load_minute_df, slice_rth
from s3a_backtester.features import compute_session_refs, compute_session_vwap_bands, find_swings_1m
from s3a_backtester.structure import trend_5m, micro_swing_break
from s3a_backtester.engine import generate_signals

# Professional Plotting Style
plt.style.use('bmh')
print("Imports Complete.")
"""
        )
    )

    nb.cells.append(
        nbf.v4.new_code_cell(
            """
# 2. Data Loading (12-Month NQ)
# Adjust path if your filename differs slightly (e.g. date range).
DATA_PATH = "../../data/vendor_parquet/NQ/NQ.v.0_2024-12-01_2025-11-30_RTH.parquet"

if not os.path.exists(DATA_PATH):
    print(f"WARNING: {DATA_PATH} not found.")
    print("Falling back to synthetic sample for demonstration...")
    DATA_PATH = "../../data/sample/synth_3d_RTH.parquet"

if os.path.exists(DATA_PATH):
    df = load_minute_df(DATA_PATH, tz="America/New_York")
    df = slice_rth(df)
    print(f"Loaded {len(df)} bars from {DATA_PATH}")

    # Optional: Slice to a smaller window for faster visualization processing
    # df = df.loc["2025-01-01":"2025-01-31"]
    # print(f"Sliced to {len(df)} bars for visualization.")
else:
    raise FileNotFoundError("No data found. Please run 'quickstart.sh' or check vendor_parquet folder.")
"""
        )
    )

    nb.cells.append(
        nbf.v4.new_code_cell(
            """
# 3. Feature Engineering Pipeline
print("--- Starting Feature Engineering ---")

# A. Session References (OR High/Low)
df = compute_session_refs(df)

# B. VWAP Bands
# compute_session_vwap_bands returns the full DF with new cols
bands_df = compute_session_vwap_bands(df)
df = bands_df.copy()

# EXPLICIT MAPPING: Map library columns to Engine/Plot columns
# This prevents 'KeyError: vwap_1u' downstream
if "band_p1" in df.columns:
    df["vwap_1u"] = df["band_p1"]
    df["vwap_1d"] = df["band_m1"]
    df["vwap_2u"] = df["band_p2"]
    df["vwap_2d"] = df["band_m2"]
    print("✅ VWAP Bands mapped successfully.")
else:
    print(f"❌ WARNING: 'band_p1' not found. Columns: {df.columns.tolist()}")

# C. 5-Minute Trend
df_5m = df.resample("5min", label="right", closed="right").agg({
    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
})
tr5 = trend_5m(df_5m)
df["trend_5m"] = tr5["trend_5m"].reindex(df.index, method="ffill")

# D. Micro-Structure
sw = find_swings_1m(df)
df["swing_high"] = sw["swing_high"]
df["swing_low"] = sw["swing_low"]
mb = micro_swing_break(df)
df["micro_break_dir"] = mb["micro_break_dir"]

# VERIFICATION
if "vwap_1u" in df.columns:
    print(f"--- Feature Engineering COMPLETE. DF Shape: {df.shape} ---")
else:
    raise RuntimeError("CRITICAL FAILURE: 'vwap_1u' column is missing.")
"""
        )
    )

    nb.cells.append(
        nbf.v4.new_code_cell(
            """
# 4. Generate Signals (The Engine)
# We mock a minimal config to ensure "Production" behavior

class MockConfig:
    class Signals:
        disqualify_after_unlock = True
        zone_touch_mode = "range"
        trigger_lookback_bars = 5
    class Instrument:
        tick_size = 0.25
    class Risk:
        max_stop_or_mult = 1.5

cfg = MockConfig()
signals = generate_signals(df, cfg=cfg)

# Quick Diagnostic
unlocks = signals['or_break_unlock'].sum()
zones = signals['in_zone'].sum()
triggers = signals['trigger_ok'].sum()
print(f"Engine Run Complete.")
print(f"Unlock Events: {unlocks} | Zone Touches: {zones} | Valid Triggers: {triggers}")
"""
        )
    )

    nb.cells.append(
        nbf.v4.new_code_cell(
            """
# 5. Visualization: The "Golden Setup"
# automatically find a day with a TRIGGER to plot
trigger_days = signals[signals['trigger_ok'] == True].index.normalize().unique()

if len(trigger_days) > 0:
    # Pick the first day with a valid trade trigger
    TARGET_DATE = str(trigger_days[0].date())
    print(f"Visualizing Target Date: {TARGET_DATE}")

    subset = signals[signals.index.strftime('%Y-%m-%d') == TARGET_DATE].copy()

    fig, ax = plt.subplots(figsize=(16, 9))

    # A. Price & Bands
    ax.plot(subset.index, subset['close'], color='black', alpha=0.7, label='Price', linewidth=1)
    ax.plot(subset.index, subset['vwap'], color='orange', linestyle='--', label='VWAP')
    ax.fill_between(subset.index, subset['vwap_1u'], subset['vwap_1d'], color='gray', alpha=0.1, label='1σ Band')

    # B. OR Levels
    or_h = subset['or_high'].iloc[-1]
    or_l = subset['or_low'].iloc[-1]
    ax.axhline(or_h, color='blue', linestyle='-', alpha=0.3, label='OR High')
    ax.axhline(or_l, color='blue', linestyle='-', alpha=0.3, label='OR Low')

    # C. Events
    # Unlock
    unlocks = subset[subset['or_break_unlock'] == True]
    ax.scatter(unlocks.index, unlocks['close'], color='purple', marker='*', s=200, label='Unlock Event', zorder=5)

    # Zone Touch
    zones = subset[subset['in_zone'] == True]
    ax.scatter(zones.index, zones['close'], color='gold', s=50, label='First Zone Touch', zorder=4)

    # Trigger
    triggers = subset[subset['trigger_ok'] == True]
    ax.scatter(triggers.index, triggers['close'], color='lime', marker='^', s=150, label='ENTRY TRIGGER', zorder=6)

    ax.set_title(f"Strategy 3A Logic Flow: {TARGET_DATE} (N={len(subset)})")
    ax.legend(loc='upper left')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=subset.index.tz))

    plt.tight_layout()
    plt.show()
else:
    print("No triggers found in the loaded dataset to visualize.")
"""
        )
    )

    out_path = Path("notebooks/02_strategy_prototyping/visualize_strategy_logic.ipynb")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        nbf.write(nb, f)
    print(f"Created: {out_path}")


def create_market_micro_notebook():
    nb = nbf.v4.new_notebook()

    nb.cells.append(
        nbf.v4.new_markdown_cell(
            """
# Market Microstructure Analysis
**Objective:** Validate input data density, check for session gaps, and analyze volatility regimes.
"""
        )
    )

    nb.cells.append(
        nbf.v4.new_code_cell(
            """
%pip install matplotlib seaborn

import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.append(os.path.abspath("../.."))
from s3a_backtester.data_io import load_minute_df

plt.style.use('bmh')

# Load Data (Production NQ)
DATA_PATH = "../../data/vendor_parquet/NQ/NQ.v.0_2024-12-01_2025-11-30_RTH.parquet"

if not os.path.exists(DATA_PATH):
    print("Production data not found. Falling back to synthetic sample.")
    DATA_PATH = "../../data/sample/synth_3d_RTH.parquet"

if os.path.exists(DATA_PATH):
    df = load_minute_df(DATA_PATH, tz="America/New_York")
    print(f"Loaded {len(df)} rows.")
else:
    print("No data found.")
    df = pd.DataFrame()
"""
        )
    )

    nb.cells.append(
        nbf.v4.new_code_cell(
            """
# 1. Session Density Check
# We expect ~390 bars per RTH session (09:30 - 16:00)
if not df.empty:
    counts = df.groupby(df.index.date).size()
    print(counts.describe())

    plt.figure(figsize=(10, 4))
    counts.plot(kind='bar', color='steelblue')
    plt.title("Bars per Session")
    plt.axhline(390, color='red', linestyle='--', label='Target (390)')
    plt.legend()
    plt.show()
"""
        )
    )

    nb.cells.append(
        nbf.v4.new_code_cell(
            """
# 2. Volatility Analysis (True Range)
if not df.empty:
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    plt.figure(figsize=(10, 5))
    sns.histplot(true_range, kde=True, bins=50, color='purple')
    plt.title("1-Minute True Range Distribution")
    plt.xlabel("Points")
    plt.show()
"""
        )
    )

    out_path = Path("notebooks/01_data_research/market_microstructure.ipynb")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        nbf.write(nb, f)
    print(f"Created: {out_path}")


if __name__ == "__main__":
    create_strategy_viz_notebook()
    create_market_micro_notebook()
