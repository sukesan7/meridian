# Research Lab

This directory contains Jupyter Notebooks for **Exploratory Data Analysis (EDA)** and **Logic Prototyping**.

## Index

### `01_data_research/`
* **[market_microstructure.ipynb](01_data_research/market_microstructure.ipynb)**:
    * Validates data density (bars per session).
    * Analyzes volatility regimes (ATR/True Range distribution).
    * Sanity checks timestamp alignment (UTC vs ET).

### `02_strategy_prototyping/`
* **[visualize_strategy_logic.ipynb](02_strategy_prototyping/visualize_strategy_logic.ipynb)**:
    * Visual verification of the Strategy 3A State Machine.
    * Plots the **Unlock $\to$ Zone $\to$ Trigger** sequence on price charts.
    * Used to debug logic regressions before deploying to the core engine.

## Usage
Ensure your virtual environment is active and the package is installed in editable mode (`pip install -e .`).

```bash
jupyter lab
```
