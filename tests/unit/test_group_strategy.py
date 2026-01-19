"""
Unit tests for GroupChaosStrategy and GroupFailureStrategy.
"""

import pytest
import asyncio
from unittest.mock import Mock
from agent_chaos_sdk.proxy.strategies.group import GroupChaosStrategy, GroupFailureStrategy


@pytest.mark.asyncio
async def test_group_chaos_strategy_matches_role(mock_flow):
    """Test that group chaos strategy matches agent role."""
    strategy = GroupChaosStrategy(
        "test_group",
        target_role="TravelAgent",
        action="latency",
        delay=0.1
    )
    
    start = asyncio.get_event_loop().time()
    result = await strategy.intercept(mock_flow)
    elapsed = asyncio.get_event_loop().time() - start
    
    assert result is True
    assert elapsed >= 0.1


@pytest.mark.asyncio
async def test_group_chaos_strategy_skips_wrong_role(mock_flow):
    """Test that group chaos strategy skips when role doesn't match."""
    strategy = GroupChaosStrategy(
        "test_group",
        target_role="WrongRole",
        action="latency",
        delay=0.1
    )
    
    result = await strategy.intercept(mock_flow)
    assert result is False


@pytest.mark.asyncio
async def test_group_chaos_strategy_error_action(mock_flow_with_response):
    """Test group chaos strategy with error action."""
    strategy = GroupChaosStrategy(
        "test_group",
        target_role="TravelAgent",
        action="error",
        error_code=503
    )
    
    result = await strategy.intercept(mock_flow_with_response)
    assert result is True
    assert mock_flow_with_response.response.status_code == 503


@pytest.mark.asyncio
async def test_group_chaos_strategy_disable_action(mock_flow):
    """Test group chaos strategy with disable action."""
    strategy = GroupChaosStrategy(
        "test_group",
        target_role="TravelAgent",
        action="disable"
    )
    
    result = await strategy.intercept(mock_flow)
    # Disable action should return True but not modify flow
    assert result is True


@pytest.mark.asyncio
async def test_group_failure_strategy(mock_flow_with_response):
    """Test group failure strategy returns 503."""
    strategy = GroupFailureStrategy(
        "test_failure",
        target_role="TravelAgent"
    )
    
    result = await strategy.intercept(mock_flow_with_response)
    assert result is True
    assert mock_flow_with_response.response.status_code == 503
    assert "Service Unavailable" in mock_flow_with_response.response.reason


@pytest.mark.asyncio
async def test_group_failure_strategy_skips_wrong_role(mock_flow_with_response):
    """Test group failure strategy skips when role doesn't match."""
    strategy = GroupFailureStrategy(
        "test_failure",
        target_role="WrongRole"
    )
    
    original_status = mock_flow_with_response.response.status_code
    result = await strategy.intercept(mock_flow_with_response)
    
    assert result is False
    assert mock_flow_with_response.response.status_code == original_status


def test_group_chaos_strategy_initialization():
    """Test group chaos strategy initialization."""
    strategy = GroupChaosStrategy(
        "test",
        target_role="TestRole",
        action="latency",
        delay=5.0
    )
    assert strategy.name == "test"
    assert strategy.target_role == "TestRole"
    assert strategy.action == "latency"
    assert strategy.delay == 5.0


def test_group_failure_strategy_initialization():
    """Test group failure strategy initialization."""
    strategy = GroupFailureStrategy("test", target_role="TestRole")
    assert strategy.name == "test"
    assert strategy.target_role == "TestRole"

