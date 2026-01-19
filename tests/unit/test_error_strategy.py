"""
Unit tests for ErrorStrategy.
"""

import pytest
from unittest.mock import Mock
from agent_chaos_sdk.proxy.strategies.network import ErrorStrategy


@pytest.mark.asyncio
async def test_error_strategy_injects_error(mock_flow_with_response):
    """Test that error strategy injects HTTP error."""
    strategy = ErrorStrategy("test_error", error_code=500)
    result = await strategy.intercept(mock_flow_with_response)
    
    assert result is True
    assert mock_flow_with_response.response.status_code == 500
    assert "Internal Server Error" in mock_flow_with_response.response.reason


@pytest.mark.asyncio
async def test_error_strategy_skips_when_disabled(mock_flow_with_response):
    """Test that error strategy skips when disabled."""
    strategy = ErrorStrategy("test_error", enabled=False, error_code=500)
    original_status = mock_flow_with_response.response.status_code
    result = await strategy.intercept(mock_flow_with_response)
    
    assert result is False
    assert mock_flow_with_response.response.status_code == original_status


@pytest.mark.asyncio
async def test_error_strategy_only_applies_to_responses(mock_flow):
    """Test that error strategy only applies during response phase."""
    strategy = ErrorStrategy("test_error", error_code=500)
    result = await strategy.intercept(mock_flow)
    
    assert result is False


@pytest.mark.asyncio
async def test_error_strategy_different_error_codes(mock_flow_with_response):
    """Test error strategy with different error codes."""
    error_codes = [400, 401, 403, 404, 429, 500, 502, 503, 504]
    
    for code in error_codes:
        flow = Mock()
        flow.response = Mock()
        flow.response.status_code = 200
        flow.response.reason = "OK"
        flow.response.headers = {}
        flow.response.text = ""
        
        strategy = ErrorStrategy(f"test_{code}", error_code=code)
        result = await strategy.intercept(flow)
        
        assert result is True
        assert flow.response.status_code == code


@pytest.mark.asyncio
async def test_error_strategy_sets_error_body(mock_flow_with_response):
    """Test that error strategy sets appropriate error body."""
    strategy = ErrorStrategy("test_error", error_code=500)
    await strategy.intercept(mock_flow_with_response)
    
    assert mock_flow_with_response.response.text
    error_body = mock_flow_with_response.response.text
    assert "error" in error_body.lower()
    assert "chaos" in error_body.lower()
    assert "500" in error_body or "Internal Server Error" in error_body


def test_error_strategy_initialization():
    """Test error strategy initialization."""
    strategy = ErrorStrategy("test", error_code=503)
    assert strategy.name == "test"
    assert strategy.enabled is True
    assert strategy.error_code == 503

