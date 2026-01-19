"""
Unit tests for chaos decorators.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from agent_chaos_sdk.decorators import simulate_chaos


def test_simulate_chaos_latency():
    """Test latency chaos decorator."""
    @simulate_chaos(strategy="latency", probability=1.0, delay=0.1)
    def test_function():
        return "result"
    
    start = time.time()
    result = test_function()
    elapsed = time.time() - start
    
    assert result == "result"
    assert elapsed >= 0.1


def test_simulate_chaos_latency_with_probability():
    """Test latency chaos with probability (may or may not apply)."""
    @simulate_chaos(strategy="latency", probability=0.0, delay=0.1)
    def test_function():
        return "result"
    
    # With probability 0.0, should not apply delay
    start = time.time()
    result = test_function()
    elapsed = time.time() - start
    
    assert result == "result"
    assert elapsed < 0.1  # Should be fast


def test_simulate_chaos_exception():
    """Test exception chaos decorator."""
    @simulate_chaos(strategy="exception", probability=1.0, message="Test error")
    def test_function():
        return "result"
    
    with pytest.raises(RuntimeError, match="Test error"):
        test_function()


def test_simulate_chaos_exception_custom_type():
    """Test exception chaos with custom exception type."""
    @simulate_chaos(strategy="exception", probability=1.0, exception_type=ValueError, message="Custom error")
    def test_function():
        return "result"
    
    with pytest.raises(ValueError, match="Custom error"):
        test_function()


def test_simulate_chaos_return_error():
    """Test return_error chaos decorator."""
    @simulate_chaos(strategy="return_error", probability=1.0, error_value="ERROR")
    def test_function():
        return "normal_result"
    
    result = test_function()
    assert result == "ERROR"


def test_simulate_chaos_skip():
    """Test skip chaos decorator."""
    @simulate_chaos(strategy="skip", probability=1.0, return_value="skipped")
    def test_function():
        return "normal_result"
    
    result = test_function()
    assert result == "skipped"


def test_simulate_chaos_unknown_strategy():
    """Test that unknown strategy executes normally."""
    @simulate_chaos(strategy="unknown_strategy", probability=1.0)
    def test_function():
        return "normal_result"
    
    result = test_function()
    assert result == "normal_result"


def test_simulate_chaos_preserves_function_metadata():
    """Test that decorator preserves function metadata."""
    @simulate_chaos(strategy="latency", probability=0.0)
    def test_function():
        """Test function docstring."""
        return "result"
    
    assert test_function.__name__ == "test_function"
    assert "Test function docstring" in test_function.__doc__


def test_simulate_chaos_with_args_and_kwargs():
    """Test decorator works with function arguments."""
    @simulate_chaos(strategy="latency", probability=0.0, delay=0.1)
    def test_function(arg1, arg2, kwarg1=None):
        return f"{arg1}_{arg2}_{kwarg1}"
    
    result = test_function("a", "b", kwarg1="c")
    assert result == "a_b_c"


@patch('agent_chaos_sdk.decorators.record_chaos_injection')
def test_simulate_chaos_records_metrics(mock_record):
    """Test that decorator records chaos injection metrics."""
    @simulate_chaos(strategy="latency", probability=1.0, delay=0.01)
    def test_function():
        return "result"
    
    test_function()
    mock_record.assert_called_once()


@patch('agent_chaos_sdk.decorators.tracer')
def test_simulate_chaos_creates_span(mock_tracer):
    """Test that decorator creates OpenTelemetry span."""
    mock_span = MagicMock()
    mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span
    
    @simulate_chaos(strategy="latency", probability=1.0, delay=0.01)
    def test_function():
        return "result"
    
    test_function()
    mock_tracer.start_as_current_span.assert_called_once()
    assert mock_span.set_attribute.called

