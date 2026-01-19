import pytest

from agent_chaos_sdk.config_loader import (
    ChaosPlan,
    ClassifierRules,
    ClassifierRulePack,
    set_global_plan,
)
from agent_chaos_sdk.proxy.classifier import TrafficClassifier, TRAFFIC_TYPE_TOOL_CALL


class _MockRequest:
    def __init__(self, url: str) -> None:
        self.pretty_url = url
        self.headers = {}
        self.content = b""

    def get_text(self) -> str:
        return ""


class _MockFlow:
    def __init__(self, url: str) -> None:
        self.request = _MockRequest(url)
        self.metadata = {}


@pytest.mark.asyncio
async def test_classifier_metadata_rules(monkeypatch) -> None:
    monkeypatch.setenv("CHAOS_CLASSIFIER_STRICT", "false")
    plan = ChaosPlan(
        classifier_rules=ClassifierRules(
            tool_patterns=[r"example\.internal/tools/"],
        ),
        targets=[],
        scenarios=[],
    )
    set_global_plan(plan)

    classifier = TrafficClassifier()
    flow = _MockFlow("http://example.internal/tools/search")
    traffic_type = await classifier.classify(flow)

    assert traffic_type == TRAFFIC_TYPE_TOOL_CALL


@pytest.mark.asyncio
async def test_classifier_rule_packs_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("CHAOS_CLASSIFIER_STRICT", "true")
    plan = ChaosPlan(
        classifier_rule_packs=[
            ClassifierRulePack(
                name="prod-default",
                rules=ClassifierRules(tool_patterns=[r"example\.internal/tools/"]),
            )
        ],
        targets=[],
        scenarios=[],
    )
    set_global_plan(plan)

    classifier = TrafficClassifier()
    flow = _MockFlow("http://example.internal/tools/search")
    traffic_type = await classifier.classify(flow)

    assert traffic_type == TRAFFIC_TYPE_TOOL_CALL
