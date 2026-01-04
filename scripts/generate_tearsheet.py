from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec

# --- UTILS ---


def format_currency(x, pos):
    """Format Y-axis values as currency or simple integers."""
    return f"{int(x)}"


def calculate_max_drawdown_duration(times: pd.Series, drawdown: pd.Series) -> str:
    """Calculates the longest time spent underwater."""
    if drawdown.empty:
        return "0 days"

    is_underwater = drawdown < 0
    # Group consecutive underwater periods
    groups = (is_underwater != is_underwater.shift()).cumsum()
    underwater_periods = times[is_underwater].groupby(groups)

    if underwater_periods.ngroups == 0:
        return "0 days"

    # Calculate duration for each group
    durations = underwater_periods.apply(lambda x: x.max() - x.min())
    max_duration = durations.max()

    return f"{max_duration.days} days"


def calculate_metrics(trades: pd.DataFrame) -> dict[str, object]:
    """Computes standard and advanced performance metrics."""
    r = trades["realized_R"]

    # 1. Basics
    n_trades = len(trades)
    n_wins = len(trades[r > 0])
    win_rate = (n_wins / n_trades * 100) if n_trades > 0 else 0.0

    # 2. Profit Factor
    gross_win = r[r > 0].sum()
    gross_loss = r[r < 0].abs().sum()
    pf = (gross_win / gross_loss) if gross_loss > 0 else np.nan

    # 3. Sharpe (Annualized approx)
    mean_r = r.mean()
    std_r = r.std()
    sharpe = (mean_r / std_r) * np.sqrt(252) if std_r > 0 else 0.0

    # 4. Drawdown Stats
    equity = r.cumsum()
    peak = equity.cummax()
    dd = equity - peak
    max_dd = dd.min()

    dd_duration = calculate_max_drawdown_duration(trades["exit_time"], dd)

    return {
        "Total Trades": n_trades,
        "Win Rate": win_rate,
        "Profit Factor": pf,
        "Sharpe (Est)": sharpe,
        "Max Drawdown": max_dd,
        "Max DD Duration": dd_duration,
        "Total Return": equity.iloc[-1] if not equity.empty else 0.0,
    }


def plot_tearsheet(trades_path: Path, out_path: Path, title: str) -> None:
    # 1. Load & Validate
    if not trades_path.exists():
        raise FileNotFoundError(f"Trades file not found: {trades_path}")

    trades = pd.read_parquet(trades_path)
    if trades.empty:
        print("Warning: No trades found.")
        return

    required = {"exit_time", "realized_R"}
    if not required.issubset(trades.columns):
        raise ValueError(f"Missing columns: {required - set(trades.columns)}")

    # 2. Preprocessing
    df = trades.copy()
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True).dt.tz_convert(None)
    df = df.sort_values("exit_time")

    df["equity"] = df["realized_R"].cumsum()
    df["peak"] = df["equity"].cummax()
    df["drawdown"] = df["equity"] - df["peak"]

    # Rolling Win Rate (20-trade window)
    df["is_win"] = (df["realized_R"] > 0).astype(int)
    df["rolling_wr"] = df["is_win"].rolling(20, min_periods=5).mean() * 100

    stats = calculate_metrics(df)

    # 3. Setup Layout (3 Rows: Equity, Drawdown/Rolling, Monthly/Hist)
    plt.style.use("seaborn-v0_8-whitegrid")
    fig = plt.figure(figsize=(14, 12))
    gs = GridSpec(4, 2, height_ratios=[3, 1.5, 1.5, 2], hspace=0.4, wspace=0.2)

    # --- ROW 1: EQUITY CURVE (Full Width) ---
    ax_equity = fig.add_subplot(gs[0, :])
    ax_equity.plot(
        df["exit_time"], df["equity"], color="#2980b9", lw=1.5, label="Equity (R)"
    )

    # High Water Marks
    new_highs = df[df["equity"] == df["peak"]]
    ax_equity.scatter(
        new_highs["exit_time"],
        new_highs["equity"],
        color="#27ae60",
        s=15,
        alpha=0.6,
        label="New High",
    )

    ax_equity.set_title(title, fontsize=16, fontweight="bold", pad=20)
    ax_equity.set_ylabel("Cumulative R", fontweight="bold")
    ax_equity.legend(loc="upper left")
    ax_equity.grid(True, alpha=0.3)

    # Stats Box
    stats_text = (
        f"Trades:      {stats['Total Trades']:d}\n"
        f"Win Rate:    {stats['Win Rate']:.1f}%\n"
        f"PF:          {stats['Profit Factor']:.2f}\n"
        f"Sharpe:      {stats['Sharpe (Est)']:.2f}\n"
        f"Return:      {stats['Total Return']:+.1f} R\n"
        f"Max DD:      {stats['Max Drawdown']:.2f} R\n"
        f"DD Duration: {stats['Max DD Duration']}"
    )
    props = dict(
        boxstyle="round,pad=0.8", facecolor="white", alpha=0.9, edgecolor="#bdc3c7"
    )
    ax_equity.text(
        0.02,
        0.05,
        stats_text,
        transform=ax_equity.transAxes,
        fontsize=10,
        fontfamily="monospace",
        verticalalignment="bottom",
        bbox=props,
    )

    # --- ROW 2 LEFT: UNDERWATER PLOT ---
    ax_dd = fig.add_subplot(gs[1, 0])
    ax_dd.fill_between(df["exit_time"], df["drawdown"], 0, color="#c0392b", alpha=0.3)
    ax_dd.plot(df["exit_time"], df["drawdown"], color="#c0392b", lw=1)
    ax_dd.set_title("Drawdown Profile", fontsize=10, fontweight="bold")
    ax_dd.set_ylabel("Drawdown (R)", fontsize=9)
    ax_dd.grid(True, alpha=0.3)
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    # --- ROW 2 RIGHT: ROLLING WIN RATE ---
    ax_roll = fig.add_subplot(gs[1, 1])
    ax_roll.plot(df["exit_time"], df["rolling_wr"], color="#8e44ad", lw=1.5)
    ax_roll.axhline(50, color="gray", linestyle="--", alpha=0.5, lw=1)
    ax_roll.set_title("Rolling Win Rate (20-Trade)", fontsize=10, fontweight="bold")
    ax_roll.set_ylabel("Win Rate %", fontsize=9)
    ax_roll.set_ylim(0, 100)
    ax_roll.grid(True, alpha=0.3)
    ax_roll.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    # --- ROW 3 LEFT: TRADE DISTRIBUTION (Histogram) ---
    ax_hist = fig.add_subplot(gs[2, 0])
    ax_hist.hist(
        df["realized_R"], bins=30, color="#34495e", alpha=0.7, edgecolor="white"
    )
    ax_hist.axvline(0, color="black", linestyle="-", lw=1)
    ax_hist.set_title("Trade Outcome Distribution", fontsize=10, fontweight="bold")
    ax_hist.set_xlabel("Realized R", fontsize=9)
    ax_hist.grid(True, alpha=0.3)

    # --- ROW 3 RIGHT: MONTHLY RETURNS ---
    ax_monthly = fig.add_subplot(gs[2, 1])
    monthly_r = df.set_index("exit_time")["realized_R"].resample("ME").sum()

    colors = ["#27ae60" if x >= 0 else "#c0392b" for x in monthly_r]
    ax_monthly.bar(monthly_r.index, monthly_r, color=colors, width=20, alpha=0.8)
    ax_monthly.axhline(0, color="black", lw=0.5)
    ax_monthly.set_title("Monthly Net R", fontsize=10, fontweight="bold")
    ax_monthly.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax_monthly.grid(True, axis="y", alpha=0.3)

    # 4. Save
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Artifact Saved: {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--title", default="Meridian | Strategy 3A Performance")
    args = parser.parse_args()

    plot_tearsheet(args.trades, args.out, args.title)


if __name__ == "__main__":
    main()
