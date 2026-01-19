import re
import pytest

from agent_chaos_sdk.proxy.classifier import (
    TrafficClassifier,
    TRAFFIC_TYPE_LLM_API,
)


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


@pytest.mark.asyncio
async def test_classifier_priority_llm_over_tool_when_more_specific() -> None:
    classifier = TrafficClassifier()
    classifier._llm_patterns = [re.compile(r"/v1/chat$")]
    classifier._tool_call_patterns = [re.compile(r"localhost:8001")]
    classifier._agent_patterns = []

    flow = _MockFlow("http://localhost:8001/v1/chat")
    traffic_type = await classifier.classify(flow)

    assert traffic_type == TRAFFIC_TYPE_LLM_API
