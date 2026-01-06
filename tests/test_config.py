import pytest
from dataclasses import dataclass, field
from s3a_backtester.config import Config, load_config, RiskCfg, EntryWindow, SlippageCfg
from s3a_backtester.validator import validate_keys

# --- 1. Validator Tests (The "Typos" Check) ---


@dataclass
class MockSubConfig:
    sub_param: int = 10


@dataclass
class MockConfig:
    main_param: int = 1
    nested: MockSubConfig = field(default_factory=MockSubConfig)


def test_validator_detects_unknown_keys_root():
    """Test that the validator catches extra keys at the top level."""
    bad_data = {"main_param": 1, "fake_key": 999}

    with pytest.raises(
        ValueError, match=r"Unknown keys detected at 'root': \['fake_key'\]"
    ):
        validate_keys(bad_data, MockConfig)


def test_validator_detects_unknown_keys_nested():
    """Test that the validator recurses into nested dictionaries."""
    bad_data = {"main_param": 1, "nested": {"sub_param": 10, "fake_nested_key": 999}}

    # Expect error path to point specifically to 'nested.fake_nested_key'
    with pytest.raises(
        ValueError, match=r"Unknown keys detected at 'nested': \['fake_nested_key'\]"
    ):
        validate_keys(bad_data, MockConfig)


def test_validator_passes_valid_data():
    """Test that perfect data passes silently."""
    good_data = {"main_param": 5, "nested": {"sub_param": 20}}
    try:
        validate_keys(good_data, MockConfig)
    except ValueError:
        pytest.fail("Validator raised ValueError on valid data.")


# --- 2. Business Logic Tests (The "Safety" Check) ---


def test_config_risk_cap_enforcement():
    """Ensure we cannot initialize a config with dangerous risk settings."""
    # This should fail immediately upon creation due to __post_init__
    with pytest.raises(ValueError, match="Risk Cap Violation"):
        Config(risk=RiskCfg(max_stop_or_mult=1.50))


def test_config_entry_window_logic():
    """Ensure entry start time cannot be after end time."""
    with pytest.raises(ValueError, match="Configuration Error"):
        Config(entry_window=EntryWindow(start="11:00", end="09:30"))


def test_load_config_integration(tmp_path):
    """Full integration test: Write a yaml file and load it."""
    # 1. Create a temporary valid yaml file
    config_file = tmp_path / "valid.yaml"
    config_file.write_text(
        """
    risk:
      max_stop_or_mult: 1.0
    slippage:
      normal_ticks: 2
    filters:
      enable_low_atr: false
      enable_dom_filter: false
    """,
        encoding="utf-8",
    )

    # 2. Load it
    cfg = load_config(str(config_file))

    # 3. Assert values were merged correctly
    assert cfg.risk.max_stop_or_mult == 1.0
    assert cfg.slippage.normal_ticks == 2
    assert cfg.filters.enable_low_atr is False
    assert cfg.filters.enable_dom_filter is False
    # Assert defaults remained for untouched fields
    assert cfg.instrument == "NQ"


def test_load_config_fails_on_typo(tmp_path):
    """Integration test: Loading a file with a typo should crash."""
    config_file = tmp_path / "typo.yaml"
    config_file.write_text(
        """
    risk:
      max_stop_or_mult: 1.0
      fake_risk_param: 123  # <--- The Typo
    """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown keys detected at 'risk'"):
        load_config(str(config_file))


def test_slippage_mode_validation():
    """Ensure invalid slippage modes are rejected immediately."""
    # These should pass
    SlippageCfg(mode="close")
    SlippageCfg(mode="next_open")

    # This must fail
    with pytest.raises(ValueError, match="Invalid slippage mode"):
        SlippageCfg(mode="typo_mode")
