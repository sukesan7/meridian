# s3a_backtester/config.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import yaml


@dataclass
class EntryWindow:
    start: str = "09:35"
    end: str = "11:00"


@dataclass
class TimeStopCfg:
    mode: str = "15min"  # "15min" or "none"
    conditional_30m: bool = True


@dataclass
class SlippageCfg:
    normal_ticks: int = 1
    hot_ticks: int = 2
    hot_minutes: List[str] = field(
        default_factory=lambda: ["09:30-09:40", "10:00-10:02"]
    )


@dataclass
class FiltersCfg:
    skip_tiny_or: bool = True
    tiny_or_mult: float = 0.25
    low_atr_percentile: float = 0.2
    news_blackout: bool = False


@dataclass
class ZonesCfg:
    allow_plus2sigma_disqualify: bool = True


@dataclass
class TrendCfg:
    require_vwap_side: bool = True
    swing_lookback_5m: int = 2


@dataclass
class MgmtCfg:
    tp1_R: float = 1.0
    tp2_R: float = 2.0
    scale_at_tp1: float = 0.5
    move_to_BE_on_tp1: bool = True


@dataclass
class Config:
    instrument: str = "NQ"
    tz: str = "America/New_York"
    entry_window: EntryWindow = field(default_factory=EntryWindow)
    time_stop: TimeStopCfg = field(default_factory=TimeStopCfg)
    risk_cap_or_mult: float = 1.25
    slippage: SlippageCfg = field(default_factory=SlippageCfg)
    filters: FiltersCfg = field(default_factory=FiltersCfg)
    zones: ZonesCfg = field(default_factory=ZonesCfg)
    trend: TrendCfg = field(default_factory=TrendCfg)
    management: MgmtCfg = field(default_factory=MgmtCfg)


def _merge_dc(obj, patch):
    """Recursively merge a dict 'patch' into dataclass 'obj'."""
    if not isinstance(patch, dict):
        return obj
    for k, v in patch.items():
        if not hasattr(obj, k):
            continue
        cur = getattr(obj, k)
        # nested dataclass?
        if hasattr(cur, "__dataclass_fields__") and isinstance(v, dict):
            _merge_dc(cur, v)
        else:
            setattr(obj, k, v)
    return obj


def load_config(path: str) -> Config:
    """
    Load YAML/JSON config into a Config dataclass.
    Safe, deterministic. Missing keys fall back to defaults.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = Config()
    _merge_dc(cfg, raw)
    return cfg
