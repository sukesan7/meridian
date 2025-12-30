import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# --- CONFIG ---
TRADES_PATH = "outputs/backtest/v1.0.3_release/trades.parquet"
OUTPUT_PATH = "assets/v1_0_3_performance.png"
# --------------


def plot_tearsheet():
    # 1. Load Data
    try:
        trades = pd.read_parquet(TRADES_PATH)
    except FileNotFoundError:
        print(f"Error: Could not find {TRADES_PATH}. Did you run the backtest?")
        return

    if trades.empty:
        print("No trades found in the simulation!")
        return

    # 2. Prepare Series
    trades = trades.sort_values("exit_time")
    # Cumulative Sum of Realized R-Multiples
    trades["equity_curve"] = trades["realized_R"].cumsum()

    # Calculate Drawdown
    running_max = trades["equity_curve"].cummax()
    trades["drawdown"] = trades["equity_curve"] - running_max

    # 3. Setup Plot (Dual Axis: Equity Top, Drawdown Bottom)
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )

    # --- Top Panel: Equity ---
    ax1.plot(
        trades["exit_time"],
        trades["equity_curve"],
        color="#2980b9",
        linewidth=2,
        label="Cumulative R",
    )

    # Add High Water Mark dots
    new_highs = trades[trades["equity_curve"] == trades["equity_curve"].cummax()]
    ax1.scatter(
        new_highs["exit_time"],
        new_highs["equity_curve"],
        color="#27ae60",
        s=10,
        alpha=0.6,
        label="New Equity High",
    )

    ax1.set_title(
        "Meridian v1.0.3 | Strategy 3A (NQ) | Cumulative Performance",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax1.set_ylabel("Return (R-Multiples)", fontsize=12)
    ax1.grid(True, which="both", linestyle="--", alpha=0.3)
    ax1.legend(loc="upper left")

    # --- Bottom Panel: Drawdown ---
    ax2.fill_between(
        trades["exit_time"], trades["drawdown"], 0, color="#c0392b", alpha=0.3
    )
    ax2.plot(
        trades["exit_time"],
        trades["drawdown"],
        color="#c0392b",
        linewidth=1,
        label="Drawdown",
    )

    ax2.set_ylabel("Drawdown (R)", fontsize=12)
    ax2.set_xlabel("Date", fontsize=12)
    ax2.grid(True, which="both", linestyle="--", alpha=0.3)

    # Formatting Dates
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()

    # 4. Save
    plt.tight_layout()
    plt.savefig(OUTPUT_PATH, dpi=300)
    print(f"Success! Performance chart saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    plot_tearsheet()
