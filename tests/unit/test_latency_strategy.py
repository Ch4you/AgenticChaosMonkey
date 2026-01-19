"""
Unit tests for LatencyStrategy.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from agent_chaos_sdk.proxy.strategies.network import LatencyStrategy


@pytest.mark.asyncio
async def test_latency_strategy_applies_delay(mock_flow):
    """Test that latency strategy applies correct delay."""
    strategy = LatencyStrategy("test_latency", delay=0.1)
    
    start = asyncio.get_event_loop().time()
    result = await strategy.intercept(mock_flow)
    elapsed = asyncio.get_event_loop().time() - start
    
    assert result is True
    assert elapsed >= 0.1
    assert elapsed < 0.2  # Should be close to 0.1s


@pytest.mark.asyncio
async def test_latency_strategy_skips_when_disabled(mock_flow):
    """Test that latency strategy skips when disabled."""
    strategy = LatencyStrategy("test_latency", enabled=False, delay=0.1)
    result = await strategy.intercept(mock_flow)
    assert result is False


@pytest.mark.asyncio
async def test_latency_strategy_only_applies_to_requests(mock_flow_with_response):
    """Test that latency strategy only applies during request phase."""
    strategy = LatencyStrategy("test_latency", delay=0.1)
    
    # Should return False when response already exists
    result = await strategy.intercept(mock_flow_with_response)
    assert result is False


@pytest.mark.asyncio
async def test_latency_strategy_uses_async_sleep():
    """Test that latency strategy uses async sleep (non-blocking)."""
    strategy = LatencyStrategy("test_latency", delay=0.05)
    
    # Create multiple flows
    flows = [Mock() for _ in range(5)]
    for flow in flows:
        flow.response = None
    
    # Execute concurrently
    start = asyncio.get_event_loop().time()
    results = await asyncio.gather(*[strategy.intercept(flow) for flow in flows])
    elapsed = asyncio.get_event_loop().time() - start
    
    # All should succeed
    assert all(results)
    # Should complete in ~0.05s (parallel), not 0.25s (sequential)
    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_latency_strategy_with_different_delays():
    """Test latency strategy with different delay values."""
    for delay in [0.01, 0.1, 0.5]:
        strategy = LatencyStrategy(f"test_{delay}", delay=delay)
        flow = Mock()
        flow.response = None
        
        start = asyncio.get_event_loop().time()
        await strategy.intercept(flow)
        elapsed = asyncio.get_event_loop().time() - start
        
        assert elapsed >= delay
        assert elapsed < delay + 0.1  # Allow small overhead


def test_latency_strategy_initialization():
    """Test latency strategy initialization."""
    strategy = LatencyStrategy("test", delay=5.0)
    assert strategy.name == "test"
    assert strategy.enabled is True
    assert strategy.delay == 5.0


def test_latency_strategy_initialization_from_kwargs():
    """Test latency strategy initialization from kwargs."""
    # When delay is provided in kwargs only
    strategy = LatencyStrategy("test", **{"delay": 7.0})
    # Should use kwargs value
    assert strategy.delay == 7.0

