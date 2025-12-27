import pandas as pd
import yaml
from pathlib import Path


# --- 1. CONFIG CHECK ---
def check_config():
    print("\n--- 1. Checking Config (configs/base.yaml) ---")
    try:
        with open("configs/base.yaml", "r") as f:
            cfg = yaml.safe_load(f)

        ew = cfg.get("entry_window", {})
        start = ew.get("start", "Unknown")
        print(f"Entry Window Start: {start} (Should be '09:35', NOT '20:00')")

        tp1 = cfg.get("management", {}).get("tp1_R", "Unknown")
        print(f"TP1 Target: {tp1}R (Should be 1.0, NOT 50.0)")

        if start == "20:00" or float(tp1) > 10.0:
            print("❌ FAILURE: Config was not reset! Fix base.yaml.")
            return False
        print("✅ Config looks nominal.")
        return True
    except Exception as e:
        print(f"⚠️ Could not read config: {e}")
        return True


# --- 2. SIGNALS CHECK ---
def check_signals():
    # Adjust path if needed to match your exact folder structure
    path = Path("outputs/backtest/v1_0_1_baseline/signals.parquet")
    print(f"\n--- 2. Analyzing Signals ({path}) ---")

    if not path.exists():
        print(f"❌ File not found: {path}")
        return

    df = pd.read_parquet(path)
    print(f"Total Rows: {len(df)}")

    # A. Check if the Swing Columns exist and have data
    swing_cols = ["last_swing_low_price", "last_swing_high_price"]
    for col in swing_cols:
        if col not in df.columns:
            print(f"❌ MISSING COLUMN: {col} is not in signals.parquet!")
            continue

        valid_count = df[col].notna().sum()
        print(
            f"Column '{col}': {valid_count} non-NaN rows ({valid_count/len(df):.1%} coverage)"
        )
        if valid_count == 0:
            print(
                "   -> ❌ CRITICAL: This column is 100% NaN. The feature logic is broken."
            )

    # B. Check Triggers
    if "trigger_ok" not in df.columns:
        print("❌ 'trigger_ok' column missing.")
        return

    triggers = df[df["trigger_ok"]]
    print(f"\nTotal 'trigger_ok' Events: {len(triggers)}")

    if len(triggers) == 0:
        print(
            "❌ No triggers found. The strategy logic (Unlock -> Zone -> Trigger) never fired."
        )
        print("   Check: 'disqualified_2sigma', 'time_window_ok', or 'pattern_ok'.")
    else:
        # C. Check Stops on Triggers
        # If trigger is OK but stop_price is NaN, the trade is dropped.
        valid_stops = triggers["stop_price"].notna().sum()
        print(f"Triggers with Valid Stop Price: {valid_stops} / {len(triggers)}")

        if valid_stops == 0:
            print("❌ FAILURE: Triggers exist, but Stop Price is NaN.")
            print(
                "   Reason: The engine tried to read 'last_swing_X_price' but found NaN."
            )


if __name__ == "__main__":
    if check_config():
        check_signals()
