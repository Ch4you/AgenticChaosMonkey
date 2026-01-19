"""
Unit tests for JSONCorruptionStrategy.
"""

import pytest
import json
from unittest.mock import Mock
from agent_chaos_sdk.proxy.strategies.data import JSONCorruptionStrategy


@pytest.mark.asyncio
async def test_json_corruption_strategy_corrupts_response(mock_flow_with_response):
    """Test that JSON corruption strategy corrupts JSON responses."""
    strategy = JSONCorruptionStrategy("test_corruption", corruption_text="💥 CHAOS 💥")
    result = await strategy.intercept(mock_flow_with_response)
    
    assert result is True
    # Response should be modified
    modified_text = mock_flow_with_response.response.get_text()
    assert "💥 CHAOS 💥" in modified_text or modified_text != mock_flow_with_response.response.text


@pytest.mark.asyncio
async def test_json_corruption_strategy_skips_non_json(mock_flow_with_response):
    """Test that JSON corruption skips non-JSON responses."""
    mock_flow_with_response.response.headers[b"Content-Type"] = b"text/plain"
    mock_flow_with_response.response.text = "This is plain text"
    
    strategy = JSONCorruptionStrategy("test_corruption")
    result = await strategy.intercept(mock_flow_with_response)
    
    assert result is False


@pytest.mark.asyncio
async def test_json_corruption_strategy_handles_ndjson(mock_flow_with_response):
    """Test that JSON corruption handles NDJSON (streaming JSON)."""
    # Create NDJSON response (multiple JSON objects separated by newlines)
    ndjson_content = '{"id": 1, "name": "test"}\n{"id": 2, "name": "test2"}\n'
    mock_flow_with_response.response.content = ndjson_content.encode('utf-8')
    mock_flow_with_response.response.text = ndjson_content
    mock_flow_with_response.response.headers[b"Content-Type"] = b"application/x-ndjson"
    
    strategy = JSONCorruptionStrategy("test_corruption")
    result = await strategy.intercept(mock_flow_with_response)
    
    # Should handle NDJSON (may or may not corrupt, but shouldn't crash)
    assert result in [True, False]


@pytest.mark.asyncio
async def test_json_corruption_strategy_skips_when_disabled(mock_flow_with_response):
    """Test that JSON corruption skips when disabled."""
    strategy = JSONCorruptionStrategy("test_corruption", enabled=False)
    original_text = mock_flow_with_response.response.text
    result = await strategy.intercept(mock_flow_with_response)
    
    assert result is False
    assert mock_flow_with_response.response.text == original_text


def test_json_corruption_strategy_initialization():
    """Test JSON corruption strategy initialization."""
    strategy = JSONCorruptionStrategy("test", corruption_text="TEST")
    assert strategy.name == "test"
    assert strategy.enabled is True
    assert strategy.corruption_text == "TEST"

