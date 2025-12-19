# QQQ 1-min OHLCV data for scaffolding during Week 1.
# This QQQ dev dataset is no longer used.

from s3a_backtester.engine import generate_signals
from s3a_backtester.data_io import load_minute_df, slice_rth, resample
from s3a_backtester.features import (
    compute_session_vwap_bands,
    compute_session_refs,
    find_swings_1m,
)
from s3a_backtester.structure import trend_5m, micro_swing_break

# 1) Load and slice to RTH
df1 = load_minute_df("data/QQQ_1min_2025-04_to_2025-10.csv")
df1 = slice_rth(df1)

# 2) OR levels / session refs (or_high/or_low, PDH/PDL, ONH/ONL, etc.)
df1 = compute_session_refs(df1)

# 3) VWAP + bands
bands = compute_session_vwap_bands(df1)
df1["vwap"] = bands["vwap"]
df1["vwap_1u"] = bands["band_p1"]
df1["vwap_1d"] = bands["band_m1"]
df1["vwap_2u"] = bands["band_p2"]
df1["vwap_2d"] = bands["band_m2"]

# 4) 5-minute trend
df5 = resample(df1, "5min")
tr5 = trend_5m(df5)
df1["trend_5m"] = tr5["trend_5m"].reindex(df1.index, method="ffill").fillna(0)

# 5) 1-minute swings + micro swing breaks
sw = find_swings_1m(df1)
df1["swing_high"] = sw["swing_high"]
df1["swing_low"] = sw["swing_low"]

mb = micro_swing_break(df1)
df1["micro_break_dir"] = mb["micro_break_dir"]

# 6) Engine signals
sig = generate_signals(df1)

required = {
    "close",
    "or_high",
    "or_low",
    "vwap",
    "vwap_1u",
    "vwap_1d",
    "vwap_2u",
    "vwap_2d",
    "trend_5m",
}

print("type(df1):", type(df1))
print("required missing:", required - set(sig.columns))
print("sum(or_break_unlock) =", int(sig["or_break_unlock"].sum()))
print("sum(in_zone)         =", int(sig["in_zone"].sum()))
print("sum(trigger_ok)      =", int(sig["trigger_ok"].sum()))
