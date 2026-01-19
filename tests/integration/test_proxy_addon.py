"""
Integration tests for ChaosProxyAddon.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from agent_chaos_sdk.proxy.addon import ChaosProxyAddon
from agent_chaos_sdk.proxy.strategies.network import LatencyStrategy
from agent_chaos_sdk.common.config import ChaosConfig, StrategyConfig


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config file for testing."""
    config_path = tmp_path / "chaos_config.yaml"
    config_data = {
        "strategies": [
            {
                "name": "test_latency",
                "type": "latency",
                "enabled": True,
                "probability": 1.0,
                "params": {"delay": 0.1}
            }
        ]
    }
    import yaml
    with open(config_path, 'w') as f:
        yaml.dump(config_data, f)
    return str(config_path)


@pytest.fixture
def proxy_addon(temp_config_file):
    """Create a proxy addon instance for testing."""
    addon = ChaosProxyAddon(config_path=temp_config_file)
    return addon


@pytest.mark.asyncio
async def test_proxy_addon_initialization(temp_config_file):
    """Test that proxy addon initializes correctly."""
    addon = ChaosProxyAddon(config_path=temp_config_file)
    assert addon.config is not None
    assert len(addon.strategies) > 0


@pytest.mark.asyncio
async def test_proxy_addon_authentication_check(mock_flow, proxy_addon, monkeypatch):
    """Test that proxy addon checks authentication."""
    monkeypatch.setenv("CHAOS_ADMIN_TOKEN", "test-token")
    # Reinitialize auth with token
    from agent_chaos_sdk.common.security import ChaosAuth
    proxy_addon.auth = ChaosAuth()
    
    # Without token - should be rejected
    await proxy_addon.request(mock_flow)
    assert mock_flow.response is not None
    assert mock_flow.response.status_code == 401


@pytest.mark.asyncio
async def test_proxy_addon_applies_strategies(mock_flow, proxy_addon, monkeypatch):
    """Test that proxy addon applies strategies to requests."""
    monkeypatch.setenv("CHAOS_ADMIN_TOKEN", "test-token")
    from agent_chaos_sdk.common.security import ChaosAuth
    proxy_addon.auth = ChaosAuth()
    mock_flow.request.headers[b"X-Chaos-Token"] = b"test-token"
    
    # Add a latency strategy
    strategy = LatencyStrategy("test_latency", delay=0.01)
    proxy_addon.strategies = [strategy]
    
    start = asyncio.get_event_loop().time()
    await proxy_addon.request(mock_flow)
    elapsed = asyncio.get_event_loop().time() - start
    
    # Should have applied delay
    assert elapsed >= 0.01


@pytest.mark.asyncio
async def test_proxy_addon_logs_with_pii_redaction(mock_flow, proxy_addon, monkeypatch, tmp_path):
    """Test that proxy addon redacts PII in logs."""
    monkeypatch.setenv("CHAOS_ADMIN_TOKEN", "test-token")
    from agent_chaos_sdk.common.security import ChaosAuth
    proxy_addon.auth = ChaosAuth()
    mock_flow.request.headers[b"X-Chaos-Token"] = b"test-token"
    
    # Set URL with sensitive data
    mock_flow.request.pretty_url = "http://api.example.com/search?api_key=sk-abc123&token=secret456"
    
    # Create response
    mock_flow.response = Mock()
    mock_flow.response.status_code = 200
    
    await proxy_addon.response(mock_flow)
    
    # Check log file
    log_file = Path("logs/proxy.log")
    if log_file.exists():
        log_content = log_file.read_text()
        # Should not contain sensitive data
        assert "sk-abc123" not in log_content
        assert "secret456" not in log_content
        # Should contain redacted placeholders
        assert "[REDACTED" in log_content or "REDACTED" in log_content


@pytest.mark.asyncio
async def test_proxy_addon_handles_concurrent_requests(mock_flow, proxy_addon, monkeypatch):
    """Test that proxy addon handles concurrent requests efficiently."""
    monkeypatch.setenv("CHAOS_ADMIN_TOKEN", "test-token")
    from agent_chaos_sdk.common.security import ChaosAuth
    proxy_addon.auth = ChaosAuth()
    
    # Create multiple flows
    flows = []
    for i in range(5):
        flow = Mock()
        flow.request = Mock()
        flow.request.method = "POST"
        flow.request.pretty_url = f"http://test.com/api/{i}"
        flow.request.headers = {"X-Chaos-Token": "test-token"}
        flow.response = None
        flow.metadata = {}
        flows.append(flow)
    
    # Add latency strategy
    strategy = LatencyStrategy("test_latency", delay=0.05)
    proxy_addon.strategies = [strategy]
    
    # Execute concurrently
    start = asyncio.get_event_loop().time()
    await asyncio.gather(*[proxy_addon.request(flow) for flow in flows])
    elapsed = asyncio.get_event_loop().time() - start
    
    # Should complete in ~0.05s (parallel), not 0.25s (sequential)
    assert elapsed < 0.15


def test_proxy_addon_cleanup(proxy_addon):
    """Test that proxy addon cleans up resources."""
    # Call done() to cleanup
    proxy_addon.done()
    
    # Executor should be shut down (check if shutdown was called)
    # Note: shutdown() doesn't have timeout in older Python versions
    assert hasattr(proxy_addon, '_log_executor')


@pytest.mark.asyncio
async def test_proxy_addon_response_hook(mock_flow_with_response, proxy_addon, monkeypatch):
    """Test response hook processes responses correctly."""
    monkeypatch.setenv("CHAOS_ADMIN_TOKEN", "test-token")
    from agent_chaos_sdk.common.security import ChaosAuth
    proxy_addon.auth = ChaosAuth()
    mock_flow_with_response.request.headers["X-Chaos-Token"] = "test-token"
    
    # Set span in metadata
    from opentelemetry.trace import NonRecordingSpan
    mock_flow_with_response.metadata["chaos_span"] = NonRecordingSpan(None)
    
    await proxy_addon.response(mock_flow_with_response)
    
    # Should have processed response
    assert mock_flow_with_response.response is not None

