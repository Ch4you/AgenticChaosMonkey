import pytest

from agent_chaos_sdk.proxy.classifier import TrafficClassifier, TRAFFIC_TYPE_TOOL_CALL
from agent_chaos_sdk.config_loader import ChaosPlan, set_global_plan, get_global_plan
from agent_chaos_sdk.common import security


class _MockRequest:
    def __init__(self, url: str, headers: dict | None = None) -> None:
        self.pretty_url = url
        self.headers = headers or {}
        self.content = b""

    def get_text(self) -> str:
        return ""


class _MockFlow:
    def __init__(self, url: str, headers: dict | None = None) -> None:
        self.request = _MockRequest(url, headers)
        self.metadata = {}


def _set_plan_metadata(metadata: dict) -> None:
    plan = ChaosPlan(version="1.0", revision=0, metadata=metadata, targets=[], scenarios=[])
    set_global_plan(plan)


@pytest.mark.asyncio
async def test_override_ignored_without_auth_or_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHAOS_ADMIN_TOKEN", raising=False)
    security._auth = None
    _set_plan_metadata({})

    classifier = TrafficClassifier()
    flow = _MockFlow(
        "http://example.com/unknown",
        headers={"X-Agent-Chaos-Type": "TOOL_CALL"},
    )
    traffic_type = await classifier.classify(flow)

    assert traffic_type != TRAFFIC_TYPE_TOOL_CALL


@pytest.mark.asyncio
async def test_override_allowed_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAOS_ADMIN_TOKEN", "secret-token")
    security._auth = None
    _set_plan_metadata({})

    classifier = TrafficClassifier()
    flow = _MockFlow(
        "http://localhost:8001/api",
        headers={"X-Agent-Chaos-Type": "TOOL_CALL", "X-Chaos-Token": "secret-token"},
    )
    traffic_type = await classifier.classify(flow)

    assert traffic_type == TRAFFIC_TYPE_TOOL_CALL


@pytest.mark.asyncio
async def test_override_allowed_with_plan_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHAOS_ADMIN_TOKEN", raising=False)
    security._auth = None
    _set_plan_metadata({"allow_client_override": True})

    classifier = TrafficClassifier()
    flow = _MockFlow(
        "http://localhost:8001/api",
        headers={"X-Agent-Chaos-Type": "TOOL_CALL"},
    )
    traffic_type = await classifier.classify(flow)

    assert traffic_type == TRAFFIC_TYPE_TOOL_CALL
