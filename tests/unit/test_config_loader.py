"""
Unit tests for configuration loader.
"""

import pytest
import yaml
from pathlib import Path
from tempfile import NamedTemporaryFile
from agent_chaos_sdk.config_loader import (
    load_chaos_plan, set_global_plan, get_global_plan,
    ChaosPlan, TargetConfig, StrategyConfig
)


def test_target_config_creation():
    """Test creating a TargetConfig."""
    target = TargetConfig(
        name="test_endpoint",
        type="http_endpoint",
        pattern=".*api.example.com.*"
    )
    assert target.name == "test_endpoint"
    assert target.type == "http_endpoint"
    assert target.pattern == ".*api.example.com.*"


def test_target_config_validation_empty_pattern():
    """Test that empty pattern raises validation error."""
    with pytest.raises(ValueError, match="pattern cannot be empty"):
        TargetConfig(
            name="test",
            type="http_endpoint",
            pattern=""
        )


def test_strategy_config_creation():
    """Test creating a StrategyConfig."""
    strategy = StrategyConfig(
        name="test_strategy",
        type="latency",
        target_ref="test_endpoint",
        enabled=True,
        probability=0.5,
        params={"delay": 5.0}
    )
    assert strategy.name == "test_strategy"
    assert strategy.type == "latency"
    assert strategy.target_ref == "test_endpoint"
    assert strategy.enabled is True
    assert strategy.probability == 0.5
    assert strategy.params["delay"] == 5.0


def test_strategy_config_validation_probability():
    """Test that invalid probability raises validation error."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as exc_info:
        StrategyConfig(
            name="test",
            type="latency",
            target_ref="test_endpoint",
            probability=1.5  # Invalid: > 1.0
        )
    # Pydantic validation error should mention the constraint
    assert "less than or equal to 1" in str(exc_info.value) or "probability" in str(exc_info.value)


def test_chaos_plan_creation():
    """Test creating a ChaosPlan."""
    targets = [
        TargetConfig(name="api", type="http_endpoint", pattern=".*api.*")
    ]
    strategies = [
        StrategyConfig(name="delay", type="latency", target_ref="api")
    ]
    
    plan = ChaosPlan(
        version="1.0",
        metadata={"name": "test"},
        targets=targets,
        scenarios=strategies
    )
    assert plan.version == "1.0"
    assert len(plan.targets) == 1
    assert len(plan.scenarios) == 1


def test_chaos_plan_get_target():
    """Test getting target by name."""
    targets = [
        TargetConfig(name="api", type="http_endpoint", pattern=".*api.*"),
        TargetConfig(name="db", type="http_endpoint", pattern=".*db.*")
    ]
    plan = ChaosPlan(targets=targets, scenarios=[])
    
    target = plan.get_target("api")
    assert target is not None
    assert target.name == "api"
    
    assert plan.get_target("nonexistent") is None


def test_chaos_plan_get_scenarios_for_target():
    """Test getting scenarios for a specific target."""
    targets = [
        TargetConfig(name="api", type="http_endpoint", pattern=".*api.*"),
        TargetConfig(name="other_target", type="http_endpoint", pattern=".*other.*")  # Add missing target for validation
    ]
    strategies = [
        StrategyConfig(name="delay", type="latency", target_ref="api", enabled=True),
        StrategyConfig(name="error", type="error", target_ref="api", enabled=True),
        StrategyConfig(name="other", type="latency", target_ref="other_target", enabled=True),
        StrategyConfig(name="disabled", type="latency", target_ref="api", enabled=False)  # Should be excluded
    ]
    plan = ChaosPlan(targets=targets, scenarios=strategies)
    
    scenarios = plan.get_scenarios_for_target("api")
    assert len(scenarios) == 2  # Only enabled ones
    assert all(s.target_ref == "api" for s in scenarios)
    assert all(s.enabled for s in scenarios)
    assert "delay" in [s.name for s in scenarios]
    assert "error" in [s.name for s in scenarios]
    assert "disabled" not in [s.name for s in scenarios]  # Disabled should be excluded
    
    # Test with non-existent target
    assert len(plan.get_scenarios_for_target("nonexistent")) == 0


def test_load_chaos_plan_from_yaml(tmp_path):
    """Test loading a chaos plan from YAML file."""
    yaml_content = """
version: "1.0"
metadata:
  name: "Test Plan"
  description: "Test chaos plan"
targets:
  - name: "api_endpoint"
    type: "http_endpoint"
    pattern: ".*api.example.com.*"
scenarios:
  - name: "latency_attack"
    type: "latency"
    target_ref: "api_endpoint"
    enabled: true
    probability: 0.5
    params:
      delay: 5.0
"""
    yaml_file = tmp_path / "test_plan.yaml"
    yaml_file.write_text(yaml_content)
    
    plan = load_chaos_plan(str(yaml_file))
    
    assert plan.version == "1.0"
    assert plan.metadata["name"] == "Test Plan"
    assert len(plan.targets) == 1
    assert len(plan.scenarios) == 1
    assert plan.targets[0].name == "api_endpoint"
    assert plan.scenarios[0].name == "latency_attack"


def test_load_chaos_plan_invalid_file():
    """Test loading from non-existent file raises error."""
    with pytest.raises((FileNotFoundError, ValueError)):
        load_chaos_plan("nonexistent_file.yaml")


def test_load_chaos_plan_invalid_yaml(tmp_path):
    """Test loading invalid YAML raises error."""
    yaml_file = tmp_path / "invalid.yaml"
    yaml_file.write_text("invalid: yaml: content: [")
    
    with pytest.raises((yaml.YAMLError, ValueError)):
        load_chaos_plan(str(yaml_file))


def test_global_plan_singleton():
    """Test global plan singleton pattern."""
    targets = [TargetConfig(name="test", type="http_endpoint", pattern=".*")]
    plan = ChaosPlan(targets=targets, scenarios=[])
    
    set_global_plan(plan)
    retrieved = get_global_plan()
    
    assert retrieved is not None
    assert retrieved == plan
    assert len(retrieved.targets) == 1


def test_chaos_plan_to_legacy_config():
    """Test converting ChaosPlan to legacy config format."""
    targets = [
        TargetConfig(name="api", type="http_endpoint", pattern=".*api.*")
    ]
    strategies = [
        StrategyConfig(
            name="delay",
            type="latency",
            target_ref="api",
            params={"delay": 5.0}
        )
    ]
    plan = ChaosPlan(targets=targets, scenarios=strategies)
    
    legacy = plan.to_legacy_config()
    
    assert "strategies" in legacy
    assert len(legacy["strategies"]) == 1
    assert legacy["strategies"][0]["name"] == "delay"
    assert legacy["strategies"][0]["type"] == "latency"
    assert legacy["strategies"][0]["params"]["delay"] == 5.0
    # Should include target pattern in params
    assert "url_pattern" in legacy["strategies"][0]["params"] or "target_ref" in legacy["strategies"][0]

