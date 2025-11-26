from s3a_backtester.config import load_config
from s3a_backtester.data_io import load_minute_df, slice_rth, resample
from s3a_backtester.features import (
    compute_session_refs,
    compute_session_vwap_bands,
    compute_atr15,
    find_swings_1m,
)
from s3a_backtester.structure import trend_5m
from s3a_backtester.engine import generate_signals
import pandas as pd
import numpy as np


def main() -> None:
    cfg = load_config("configs/base.yaml")

    df1 = load_minute_df("data/QQQ_1min_2025-04_to_2025-10.csv", tz=cfg.tz)
    df1 = slice_rth(df1)
    df1 = compute_session_refs(df1)
    df1 = compute_session_vwap_bands(df1)
    df1["atr15"] = compute_atr15(df1)

    df5 = resample(df1, "5min")

    tr5 = trend_5m(df5)
    if isinstance(tr5, pd.DataFrame):
        tr5 = tr5["trend_5m"]
    df1["trend_5m"] = tr5.reindex(df1.index, method="ffill").fillna(0)

    swings = find_swings_1m(df1)
    df1["swing_high"] = swings["swing_high"]
    df1["swing_low"] = swings["swing_low"]

    sig = generate_signals(df1, df5, cfg)

    # === Basic counts ===
    print("Bars:", len(sig))
    print("unlock (or_break_unlock):", int(sig["or_break_unlock"].sum()))
    print("zones (in_zone):", int(sig["in_zone"].sum()))
    print(
        "trigger_ok:",
        int(sig["trigger_ok"].sum()) if "trigger_ok" in sig.columns else "no col",
    )
    print(
        "riskcap_ok:",
        int(sig["riskcap_ok"].sum()) if "riskcap_ok" in sig.columns else "no col",
    )
    print("disqualified_2sigma:", int(sig["disqualified_2sigma"].sum()))
    print("time_window_ok true bars:", int(sig["time_window_ok"].sum()))

    # === Step-by-step gate diagnostics ===
    close = sig["close"]
    orh = sig["or_high"]
    orl = sig["or_low"]
    trend = sig.get("trend_5m", 0)
    vwap = sig.get("vwap", np.nan)

    # 0) Trend distribution
    print("\ntrend_5m value_counts():")
    print(trend.value_counts(dropna=False).head())

    # 1) Any OR breaks at all?
    or_break_long = close > orh
    or_break_short = close < orl
    print("\nraw OR breaks (no trend/VWAP/time filters):")
    print("  long breaks:", int(or_break_long.sum()))
    print("  short breaks:", int(or_break_short.sum()))

    # 2) OR break + trend direction
    is_long = trend > 0
    is_short = trend < 0
    or_break_long_trend = or_break_long & is_long
    or_break_short_trend = or_break_short & is_short
    print("\nOR breaks with trend alignment:")
    print("  long+trend:", int(or_break_long_trend.sum()))
    print("  short+trend:", int(or_break_short_trend.sum()))

    # 3) Add VWAP side check
    above_vwap = close >= vwap
    below_vwap = close <= vwap
    long_unlock_raw = or_break_long_trend & above_vwap
    short_unlock_raw = or_break_short_trend & below_vwap
    print("\nOR breaks + trend + VWAP side:")
    print("  long_unlock_raw:", int(long_unlock_raw.sum()))
    print("  short_unlock_raw:", int(short_unlock_raw.sum()))

    # 4) Add time window
    time_ok = sig["time_window_ok"].astype(bool)
    long_unlock_tw = long_unlock_raw & time_ok
    short_unlock_tw = short_unlock_raw & time_ok
    print("\n+ time_window_ok:")
    print("  long_unlock_tw:", int(long_unlock_tw.sum()))
    print("  short_unlock_tw:", int(short_unlock_tw.sum()))

    # 5) What generate_signals ultimately marked
    print("\nengine or_break_unlock total:", int(sig["or_break_unlock"].sum()))

    # 6) Zones after unlock (whatever your engine ended up marking)
    print("engine in_zone total:", int(sig["in_zone"].sum()))

    # 7) Final candidate entries (same as before)
    if {"trigger_ok", "riskcap_ok"}.issubset(sig.columns):
        entry_mask = (
            sig["or_break_unlock"]
            & sig["in_zone"]
            & sig["trigger_ok"]
            & sig["time_window_ok"]
            & sig["riskcap_ok"]
            & ~sig["disqualified_2sigma"]
        )
        print("\ncandidate entry bars:", int(entry_mask.sum()))
    else:
        print("\ntrigger_ok / riskcap_ok not present yet; entries can’t fire.")


if __name__ == "__main__":
    main()
