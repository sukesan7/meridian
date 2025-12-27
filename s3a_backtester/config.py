"""
Configuration Schemas
---------------------
Defines the dataclasses used to validate and structure the YAML configuration.
Acts as the single source of truth for all strategy parameters.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path
import yaml


@dataclass
class EntryWindow:
    """Defines the active trading hours (ET) for signal acceptance."""

    start: str = "09:35"
    end: str = "11:00"


@dataclass
class TimeStopCfg:
    """Configuration for time-based exits."""

    mode: str = "15m"
    tp1_timeout_min: int = 15
    max_holding_min: int = 45
    allow_extension: bool = True


@dataclass
class SlippageCfg:
    """Slippage simulation parameters."""

    normal_ticks: int = 1
    hot_ticks: int = 2
    hot_start: str = "09:30"
    hot_end: str = "09:40"
    tick_size: float = 0.25


@dataclass
class FiltersCfg:
    """Session-level filters to reject unfavorable days."""

    skip_tiny_or: bool = True
    tiny_or_mult: float = 0.25
    low_atr_percentile: float = 20.0
    news_blackout: bool = False


@dataclass
class ZonesCfg:
    """Configuration for zone-based interaction logic."""

    allow_plus2sigma_disqualify: bool = True


@dataclass
class TrendCfg:
    """Trend identification parameters."""

    require_vwap_side: bool = True
    swing_lookback_5m: int = 2


@dataclass
class MgmtCfg:
    """Trade management rules."""

    tp1_R: float = 1.0
    tp2_R: float = 2.0
    scale_at_tp1: float = 0.5
    move_to_BE_on_tp1: bool = True


@dataclass
class RiskCfg:
    """Risk management and position sizing constraints."""

    max_stop_or_mult: float = 1.25


@dataclass
class SignalsCfg:
    """Signal generation logic toggles."""

    disqualify_after_unlock: bool = True
    zone_touch_mode: str = "range"
    trigger_lookback_bars: int = 5


@dataclass
class Config:
    """Root configuration object."""

    instrument: str = "NQ"
    tz: str = "America/New_York"
    entry_window: EntryWindow = field(default_factory=EntryWindow)
    time_stop: TimeStopCfg = field(default_factory=TimeStopCfg)
    risk: RiskCfg = field(default_factory=RiskCfg)
    slippage: SlippageCfg = field(default_factory=SlippageCfg)
    filters: FiltersCfg = field(default_factory=FiltersCfg)
    signals: SignalsCfg = field(default_factory=SignalsCfg)
    zones: ZonesCfg = field(default_factory=ZonesCfg)
    trend: TrendCfg = field(default_factory=TrendCfg)
    management: MgmtCfg = field(default_factory=MgmtCfg)


def _merge_dc(obj: Any, patch: dict[str, Any], *, path: str = "") -> Any:
    """Recursively merges a dictionary into a dataclass."""
    if not isinstance(patch, dict):
        return obj
    for k, v in patch.items():
        if not hasattr(obj, k):
            continue
        cur = getattr(obj, k)

        if hasattr(cur, "__dataclass_fields__") and isinstance(v, dict):
            _merge_dc(cur, v, path=path + k + ".")
        else:
            setattr(obj, k, v)
    return obj


def load_config(path: str | Path) -> Config:
    """
    Loads configuration from a YAML file.
    Strictly reads the file ONCE to avoid stream consumption issues.
    Recursively updates the default config object to ensure type safety.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    cfg = Config()
    _merge_dc(cfg, data)

    return cfg
