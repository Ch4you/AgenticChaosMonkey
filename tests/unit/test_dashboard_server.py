import os
import pytest


@pytest.mark.asyncio
async def test_dashboard_server_initializes_and_disables_proxy(monkeypatch) -> None:
    from agent_chaos_sdk.dashboard import server as dashboard_server

    if not dashboard_server.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available")

    monkeypatch.setenv("HTTP_PROXY", "http://proxy.local:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.local:8080")
    monkeypatch.setenv("NO_PROXY", "")

    server = dashboard_server.DashboardServer(port=8099)

    assert "HTTP_PROXY" not in os.environ
    assert "HTTPS_PROXY" not in os.environ
    assert "localhost" in os.environ.get("NO_PROXY", "")
    assert "127.0.0.1" in os.environ.get("NO_PROXY", "")

    assert server.get_url().endswith(":8099")

    # Ensure restore happens even if server was never started
    await server.stop()
    assert os.environ.get("HTTP_PROXY") == "http://proxy.local:8080"
    assert os.environ.get("HTTPS_PROXY") == "http://proxy.local:8080"
