"""
Unit tests for MCPProtocolFuzzingStrategy.
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock
from agent_chaos_sdk.proxy.strategies.mcp import MCPProtocolFuzzingStrategy, SchemaAwareFuzzer


@pytest.mark.asyncio
async def test_mcp_fuzzing_detects_tool_calls(mock_flow):
    """Test that MCP fuzzing detects tool call requests."""
    # Set up request body with tool calls that include a numeric field for type_mismatch
    tool_call_body = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "search_flights",
                            "arguments": '{"origin": "NYC", "destination": "LAX", "passengers": 2}'
                        }
                    }
                ]
            }
        ]
    }
    body_text = json.dumps(tool_call_body)
    mock_flow.request.content = body_text.encode('utf-8')
    # Ensure Content-Type is set (our fix now handles both bytes and str)
    mock_flow.request.headers[b"Content-Type"] = b"application/json"
    # Set method to POST (required for some detection paths)
    mock_flow.request.method = "POST"
    # Set URL to match tool endpoint pattern (helps with detection)
    mock_flow.request.pretty_url = "http://localhost:8001/api/chat"
    
    # Ensure get_text() returns the body text (conftest sets this up, but we override)
    mock_flow.request.get_text = Mock(return_value=body_text)
    # Ensure request.text can be set (for modification)
    if not hasattr(mock_flow.request, 'text'):
        mock_flow.request.text = None
    
    strategy = MCPProtocolFuzzingStrategy("test_fuzzing", fuzz_type="type_mismatch")
    result = await strategy.intercept(mock_flow)
    
    # Should detect tool calls (messages with tool_calls) and apply fuzzing
    # type_mismatch needs a numeric field to modify, so we added "passengers": 2
    assert result is True, f"Expected True but got False. Body: {body_text}, Tool calls detected: {strategy._is_tool_call_request(mock_flow)}"


@pytest.mark.asyncio
async def test_mcp_fuzzing_skips_non_tool_calls(mock_flow):
    """Test that MCP fuzzing skips non-tool-call requests."""
    # Regular request without tool calls
    regular_body = {"messages": [{"role": "user", "content": "Hello"}]}
    mock_flow.request.content = json.dumps(regular_body).encode('utf-8')
    mock_flow.request.get_text.return_value = json.dumps(regular_body)
    
    strategy = MCPProtocolFuzzingStrategy("test_fuzzing", fuzz_type="type_mismatch")
    result = await strategy.intercept(mock_flow)
    
    assert result is False


@pytest.mark.asyncio
async def test_mcp_fuzzing_type_mismatch(mock_flow):
    """Test type mismatch fuzzing corrupts JSON payload."""
    tool_call_body = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "search_flights",
                            "arguments": '{"origin": "NYC", "destination": "LAX", "passengers": 2}'
                        }
                    }
                ]
            }
        ]
    }
    original_text = json.dumps(tool_call_body)
    mock_flow.request.content = original_text.encode('utf-8')
    mock_flow.request.get_text.return_value = original_text
    mock_flow.request.headers[b"Content-Type"] = b"application/json"
    
    strategy = MCPProtocolFuzzingStrategy("test_fuzzing", fuzz_type="type_mismatch")
    result = await strategy.intercept(mock_flow)
    
    assert result is True
    # Verify the body was modified
    modified_text = mock_flow.request.text if hasattr(mock_flow.request, 'text') else mock_flow.request.get_text()
    assert modified_text != original_text
    # Should still be valid JSON
    modified_body = json.loads(modified_text)


@pytest.mark.asyncio
async def test_mcp_fuzzing_null_injection(mock_flow):
    """Test null injection fuzzing removes required fields."""
    tool_call_body = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "search_flights",
                            "arguments": '{"origin": "NYC", "destination": "LAX", "date": "2025-12-25"}'
                        }
                    }
                ]
            }
        ]
    }
    original_text = json.dumps(tool_call_body)
    mock_flow.request.content = original_text.encode('utf-8')
    mock_flow.request.get_text.return_value = original_text
    mock_flow.request.headers[b"Content-Type"] = b"application/json"
    
    strategy = MCPProtocolFuzzingStrategy("test_fuzzing", fuzz_type="null_injection")
    result = await strategy.intercept(mock_flow)
    
    assert result is True
    # Get modified text from request.text (which was updated by the strategy)
    modified_text = mock_flow.request.text if hasattr(mock_flow.request, 'text') else mock_flow.request.get_text()
    modified_body = json.loads(modified_text)
    # At least one field should be null or missing
    tool_call = modified_body["messages"][0]["tool_calls"][0]
    args_str = tool_call["function"]["arguments"]
    args = json.loads(args_str) if isinstance(args_str, str) else args_str
    # Check if any field is null or missing
    has_null = any(v is None for v in args.values()) if args else False
    has_fewer_fields = len(args) < 3 if args else False
    assert has_null or has_fewer_fields, f"Expected null or missing field, got: {args}"


@pytest.mark.asyncio
async def test_mcp_fuzzing_schema_violation(mock_flow):
    """Test schema-aware fuzzing applies type-specific attacks."""
    tool_call_body = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "search_flights",
                            "arguments": '{"origin": "NYC", "destination": "LAX", "date": "2025-12-25", "passengers": 2}'
                        }
                    }
                ]
            }
        ]
    }
    original_text = json.dumps(tool_call_body)
    mock_flow.request.content = original_text.encode('utf-8')
    mock_flow.request.get_text.return_value = original_text
    mock_flow.request.headers[b"Content-Type"] = b"application/json"
    # Set URL to match target_endpoint
    mock_flow.request.pretty_url = "http://localhost:8001/search_flights"
    
    strategy = MCPProtocolFuzzingStrategy(
        "test_fuzzing",
        fuzz_type="schema_violation",
        target_endpoint="/search_flights"
    )
    result = await strategy.intercept(mock_flow)
    
    assert result is True
    modified_text = mock_flow.request.text if hasattr(mock_flow.request, 'text') else mock_flow.request.get_text()
    modified_body = json.loads(modified_text)
    # Verify the body was modified (schema violation should change arguments)
    # Note: The modification happens in the nested arguments JSON string
    original_args = json.loads(tool_call_body["messages"][0]["tool_calls"][0]["function"]["arguments"])
    modified_args_str = modified_body["messages"][0]["tool_calls"][0]["function"]["arguments"]
    modified_args = json.loads(modified_args_str) if isinstance(modified_args_str, str) else modified_args_str
    # At least one field should be different
    assert original_args != modified_args, f"Expected modified args, got same: {original_args}"


class TestSchemaAwareFuzzer:
    """Test schema-aware fuzzer functionality."""
    
    def test_detect_field_type_date(self):
        """Test date field detection."""
        assert SchemaAwareFuzzer.detect_field_type("date", "2025-12-25") == "date"
        assert SchemaAwareFuzzer.detect_field_type("departure_date", "2025-12-25") == "date"
        assert SchemaAwareFuzzer.detect_field_type("time", "2025-12-25") == "date"
    
    def test_detect_field_type_numeric(self):
        """Test numeric field detection."""
        assert SchemaAwareFuzzer.detect_field_type("price", 299.99) == "numeric"
        assert SchemaAwareFuzzer.detect_field_type("count", 5) == "numeric"
        assert SchemaAwareFuzzer.detect_field_type("passengers", 2) == "numeric"
    
    def test_detect_field_type_string(self):
        """Test string field detection."""
        assert SchemaAwareFuzzer.detect_field_type("name", "John") == "string"
        assert SchemaAwareFuzzer.detect_field_type("description", "Flight search") == "string"
    
    def test_fuzz_date_field_invalid_format(self):
        """Test date field fuzzing with invalid format."""
        result = SchemaAwareFuzzer.fuzz_date_field("date", "2025-12-25", "invalid_format")
        assert result != "2025-12-25"
        # Should be an invalid date format
        assert isinstance(result, str)
    
    def test_fuzz_date_field_sql_injection(self):
        """Test date field fuzzing with SQL injection."""
        result = SchemaAwareFuzzer.fuzz_date_field("date", "2025-12-25", "sql_injection")
        # Check for SQL injection patterns (case-insensitive)
        result_upper = result.upper()
        assert ("DROP" in result_upper or "1=1" in result or "UNION" in result_upper or 
                "SELECT" in result_upper or "OR" in result_upper or "'" in result)
    
    def test_fuzz_numeric_field_type_mismatch(self):
        """Test numeric field fuzzing with type mismatch."""
        result = SchemaAwareFuzzer.fuzz_numeric_field("price", 299.99, "type_mismatch")
        assert isinstance(result, str)  # Should be string instead of number
    
    def test_fuzz_numeric_field_negative(self):
        """Test numeric field fuzzing with negative value."""
        result = SchemaAwareFuzzer.fuzz_numeric_field("price", 299.99, "negative")
        assert result < 0
    
    def test_fuzz_string_field_buffer_overflow(self):
        """Test string field fuzzing with buffer overflow."""
        result = SchemaAwareFuzzer.fuzz_string_field("name", "John", "buffer_overflow")
        assert len(result) >= 10000  # Should be a large string (at least 10k chars)
    
    def test_fuzz_string_field_empty(self):
        """Test string field fuzzing with empty string."""
        result = SchemaAwareFuzzer.fuzz_string_field("name", "John", "empty")
        assert result == ""
    
    def test_fuzz_string_field_xss(self):
        """Test string field fuzzing with XSS payload."""
        result = SchemaAwareFuzzer.fuzz_string_field("name", "John", "xss")
        assert "<script>" in result or "javascript:" in result.lower()

