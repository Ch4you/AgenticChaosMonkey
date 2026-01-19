"""
Pytest configuration and shared fixtures.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock
from mitmproxy import http

# Add project root to path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


@pytest.fixture
def mock_flow():
    """Create a mock HTTP flow for testing."""
    flow = Mock(spec=http.HTTPFlow)
    flow.request = Mock(spec=http.Request)
    flow.request.method = "POST"
    flow.request.pretty_url = "http://localhost:8001/search_flights"
    flow.request.url = "http://localhost:8001/search_flights"
    flow.request.pretty_host = "localhost"
    flow.request.host = "localhost"
    flow.request.scheme = "http"
    flow.request.headers = http.Headers([
        (b"Content-Type", b"application/json"),
        (b"X-Agent-Role", b"TravelAgent"),
    ])
    flow.request.content = b'{"origin": "NYC", "destination": "LAX", "date": "2025-12-25"}'
    
    flow.response = None
    flow.metadata = {}
    
    def get_text():
        # Return text from request.text if set, otherwise from content
        if hasattr(flow.request, 'text') and flow.request.text:
            return flow.request.text
        return flow.request.content.decode('utf-8')
    
    flow.request.get_text = Mock(side_effect=get_text)
    flow.request.text = None  # Will be set by strategies
    
    # Add make_response method for request object (used by auth)
    # This mimics mitmproxy's request.make_response() which creates an HTTPResponse
    def make_response(content, status_code=200, headers=None):
        from mitmproxy import http
        import time
        # Convert headers dict to list of tuples for Headers
        header_list = []
        if headers:
            for k, v in headers.items():
                header_list.append((k.encode() if isinstance(k, str) else k, 
                                   v.encode() if isinstance(v, str) else v))
        response = http.Response(
            http_version=b"HTTP/1.1",
            status_code=status_code,
            reason=b"OK" if status_code == 200 else b"Unauthorized",
            headers=http.Headers(header_list),
            content=content if isinstance(content, bytes) else content.encode('utf-8'),
            trailers=http.Headers(),
            timestamp_start=time.time(),
            timestamp_end=time.time()
        )
        return response
    
    flow.request.make_response = make_response
    
    return flow


@pytest.fixture
def mock_flow_with_response(mock_flow):
    """Create a mock HTTP flow with response."""
    mock_flow.response = Mock(spec=http.Response)
    mock_flow.response.status_code = 200
    mock_flow.response.reason = "OK"
    mock_flow.response.headers = http.Headers([(b"Content-Type", b"application/json")])
    mock_flow.response.content = b'{"flights": [{"id": "FL-123", "price": 299.99}]}'
    mock_flow.response.text = '{"flights": [{"id": "FL-123", "price": 299.99}]}'
    
    def get_text():
        return mock_flow.response.text
    
    mock_flow.response.get_text = Mock(return_value=get_text())
    
    return mock_flow


@pytest.fixture
def sample_json_with_pii():
    """Sample JSON containing PII for testing."""
    return {
        "user": {
            "email": "user@example.com",
            "phone": "+1-555-123-4567",
            "ssn": "123-45-6789"
        },
        "api_key": "sk-abc123xyz456789012345678901234567890",
        "token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ",
        "password": "secret123",
        "credit_card": "1234-5678-9012-3456"
    }


@pytest.fixture
def sample_tool_call_json():
    """Sample tool call JSON for MCP fuzzing tests."""
    return {
        "messages": [
            {
                "role": "user",
                "content": "Search for flights"
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "search_flights",
                            "arguments": '{"origin": "NYC", "destination": "LAX", "date": "2025-12-25"}'
                        }
                    }
                ]
            }
        ]
    }

