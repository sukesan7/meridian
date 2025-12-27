import pandas as pd
import sys
from pathlib import Path

# Add project root to path so we can import the module
sys.path.append(str(Path(__file__).parent.parent))

from s3a_backtester.features import find_swings_1m


def test_swing_delay():
    print("--- Starting Look-Ahead Bias Verification ---")

    # 1. Create Synthetic Data: A perfect pyramid top
    # Prices: 10, 11, 12, 13, 15 (TOP), 13, 12, 11, 10
    prices = [10, 11, 12, 13, 15, 13, 12, 11, 10]
    dates = pd.date_range("2024-01-01 09:30", periods=len(prices), freq="1min")

    df = pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": 1000,
        },
        index=dates,
    )

    # 2. Parameters
    LB = 2
    RB = 2

    # 3. Run the NEW Logic
    print(f"Running find_swings_1m with lb={LB}, rb={RB}...")
    out = find_swings_1m(df, lb=LB, rb=RB)

    # 4. Analyze the Peak
    # The Peak is at index 4 (Value 15)
    # Time: 09:34
    peak_idx = 4
    print(f"\nPeak occurs at index {peak_idx} (Time: {out.index[peak_idx].time()})")

    # CHECK A: Did it mark the peak as confirmed AT the peak? (The Cheat)
    cheat_signal = out.iloc[peak_idx]["swing_high_confirmed"]
    print(f"Signal at Peak Time (Index {peak_idx}): {cheat_signal}")

    if cheat_signal:
        print("❌ FAILED: Signal fired AT the peak. This is Look-Ahead Bias.")
        return

    # CHECK B: Did it mark the peak confirmed 'rb' bars later? (The Correct Behavior)
    # Confirmation should be at index 4 + 2 = 6
    confirm_idx = peak_idx + RB
    confirm_signal = out.iloc[confirm_idx]["swing_high_confirmed"]
    print(
        f"Signal at Confirmation Time (Index {confirm_idx}, Time: {out.index[confirm_idx].time()}): {confirm_signal}"
    )

    if confirm_signal:
        print("✅ PASSED: Signal fired exactly rb bars later.")
        print("   -> The engine is waiting for confirmation before acting.")
    else:
        print("❌ FAILED: Signal did not fire at confirmation time.")

    # CHECK C: Does the 'last_swing_high_price' carry the correct value?
    # At index 6, 'last_swing_high_price' should be 15.0
    recorded_price = out.iloc[confirm_idx]["last_swing_high_price"]
    print(f"Recorded Swing Price at Confirmation: {recorded_price} (Expected: 15.0)")

    if recorded_price == 15.0:
        print("✅ PASSED: Correct price captured.")
    else:
        print(f"❌ FAILED: Incorrect price captured. Got {recorded_price}")


if __name__ == "__main__":
    test_swing_delay()
