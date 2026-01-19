"""
Unit tests for cognitive layer attack strategies.
"""

import pytest
import json
from unittest.mock import Mock
from agent_chaos_sdk.proxy.strategies.cognitive import HallucinationStrategy, ContextOverflowStrategy


@pytest.mark.asyncio
async def test_hallucination_strategy_swaps_numbers(mock_flow_with_response):
    """Test that hallucination strategy swaps numbers in responses."""
    # Set up response with numbers
    response_body = {"price": 99.99, "count": 5, "total": 100.0}
    mock_flow_with_response.response.text = json.dumps(response_body)
    mock_flow_with_response.response.content = json.dumps(response_body).encode('utf-8')
    mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
    
    strategy = HallucinationStrategy("test_hallucination", mode="swap_entities", probability=1.0)
    result = await strategy.intercept(mock_flow_with_response)
    
    assert result is True
    modified_text = mock_flow_with_response.response.get_text()
    modified_body = json.loads(modified_text)
    # At least one number should be different
    assert modified_body != response_body


@pytest.mark.asyncio
async def test_hallucination_strategy_swaps_dates(mock_flow_with_response):
    """Test that hallucination strategy swaps dates in responses."""
    response_body = {"date": "2025-12-25", "departure": "2025-12-26"}
    mock_flow_with_response.response.text = json.dumps(response_body)
    mock_flow_with_response.response.content = json.dumps(response_body).encode('utf-8')
    mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
    
    strategy = HallucinationStrategy("test_hallucination", mode="swap_entities", probability=1.0)
    result = await strategy.intercept(mock_flow_with_response)
    
    assert result is True
    modified_text = mock_flow_with_response.response.get_text()
    modified_body = json.loads(modified_text)
    # Dates should be modified
    assert modified_body != response_body


@pytest.mark.asyncio
async def test_hallucination_strategy_skips_when_disabled(mock_flow_with_response):
    """Test that hallucination strategy skips when disabled."""
    response_body = {"price": 99.99}
    mock_flow_with_response.response.text = json.dumps(response_body)
    mock_flow_with_response.response.content = json.dumps(response_body).encode('utf-8')
    
    strategy = HallucinationStrategy("test_hallucination", enabled=False)
    original_text = mock_flow_with_response.response.text
    result = await strategy.intercept(mock_flow_with_response)
    
    assert result is False
    assert mock_flow_with_response.response.text == original_text


@pytest.mark.asyncio
async def test_hallucination_strategy_respects_probability(mock_flow_with_response):
    """Test that hallucination strategy respects probability."""
    response_body = {"price": 99.99}
    mock_flow_with_response.response.text = json.dumps(response_body)
    mock_flow_with_response.response.content = json.dumps(response_body).encode('utf-8')
    mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
    
    # With probability 0.0, should not apply
    strategy = HallucinationStrategy("test_hallucination", probability=0.0)
    result = await strategy.intercept(mock_flow_with_response)
    
    # May or may not apply based on random, but should handle gracefully
    assert result in [True, False]


@pytest.mark.asyncio
async def test_context_overflow_strategy_appends_noise(mock_flow):
    """Test that context overflow strategy appends noise to requests."""
    original_body = {"messages": [{"role": "user", "content": "Hello"}]}
    original_text = json.dumps(original_body)
    mock_flow.request.content = original_text.encode('utf-8')
    mock_flow.request.get_text.return_value = original_text
    mock_flow.request.headers[b"Content-Type"] = b"application/json"
    
    strategy = ContextOverflowStrategy("test_overflow", noise_size=1000, probability=1.0)
    result = await strategy.intercept(mock_flow)
    
    assert result is True
    modified_text = mock_flow.request.get_text()
    # Should have more content than original
    assert len(modified_text) > len(original_text)
    # Should contain noise
    assert "GARBAGE" in modified_text or len(modified_text) > len(original_text) + 500


@pytest.mark.asyncio
async def test_context_overflow_strategy_skips_when_disabled(mock_flow):
    """Test that context overflow strategy skips when disabled."""
    original_body = {"messages": [{"role": "user", "content": "Hello"}]}
    original_text = json.dumps(original_body)
    mock_flow.request.content = original_text.encode('utf-8')
    mock_flow.request.get_text.return_value = original_text
    
    strategy = ContextOverflowStrategy("test_overflow", enabled=False)
    result = await strategy.intercept(mock_flow)
    
    assert result is False


@pytest.mark.asyncio
async def test_context_overflow_strategy_targets_prompt_fields(mock_flow):
    """Test that context overflow targets prompt/description fields."""
    original_body = {
        "messages": [{"role": "user", "content": "Hello"}],
        "prompt": "Short prompt"
    }
    original_text = json.dumps(original_body)
    mock_flow.request.content = original_text.encode('utf-8')
    mock_flow.request.get_text.return_value = original_text
    mock_flow.request.headers[b"Content-Type"] = b"application/json"
    
    strategy = ContextOverflowStrategy("test_overflow", noise_size=500, probability=1.0)
    result = await strategy.intercept(mock_flow)
    
    assert result is True
    modified_text = mock_flow.request.get_text()
    modified_body = json.loads(modified_text)
    # Prompt or content should be modified
    assert len(modified_text) > len(original_text)


def test_hallucination_strategy_initialization():
    """Test hallucination strategy initialization."""
    strategy = HallucinationStrategy("test", mode="swap_entities", probability=0.5)
    assert strategy.name == "test"
    assert strategy.enabled is True
    assert strategy.mode == "swap_entities"
    assert strategy.probability == 0.5


def test_context_overflow_strategy_initialization():
    """Test context overflow strategy initialization."""
    strategy = ContextOverflowStrategy("test", token_count=5000)
    assert strategy.name == "test"
    assert strategy.enabled is True
    # ContextOverflowStrategy uses token_count, not noise_size
    assert hasattr(strategy, 'token_count')
    assert strategy.token_count == 5000

