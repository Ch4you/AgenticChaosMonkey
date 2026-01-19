"""
Unit tests for BaseStrategy.
"""

import pytest
from unittest.mock import Mock
from agent_chaos_sdk.proxy.strategies.base import BaseStrategy
from agent_chaos_sdk.proxy.strategies.network import LatencyStrategy


def test_base_strategy_cannot_instantiate():
    """Test that BaseStrategy cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseStrategy("test")


def test_base_strategy_subclass_works():
    """Test that BaseStrategy subclasses work correctly."""
    strategy = LatencyStrategy("test", delay=1.0)
    assert isinstance(strategy, BaseStrategy)
    assert strategy.name == "test"
    assert strategy.enabled is True


def test_base_strategy_should_trigger_with_pattern(mock_flow):
    """Test should_trigger with URL pattern."""
    strategy = LatencyStrategy("test", url_pattern=".*search_flights.*")
    assert strategy.should_trigger(mock_flow) is True


def test_base_strategy_should_trigger_no_pattern(mock_flow):
    """Test should_trigger without pattern (matches all)."""
    strategy = LatencyStrategy("test")
    # Without pattern, should trigger on all flows
    assert strategy.should_trigger(mock_flow) is True


def test_base_strategy_should_trigger_disabled(mock_flow):
    """Test should_trigger when disabled."""
    strategy = LatencyStrategy("test", enabled=False)
    assert strategy.should_trigger(mock_flow) is False


def test_base_strategy_repr():
    """Test string representation."""
    strategy = LatencyStrategy("test_strategy", enabled=True)
    repr_str = repr(strategy)
    assert "LatencyStrategy" in repr_str
    assert "test_strategy" in repr_str

