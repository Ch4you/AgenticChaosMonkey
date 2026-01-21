import json
from pathlib import Path

import pytest

from agent_chaos_sdk.middleware import ChaosMiddleware


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload
        self._content = json.dumps(payload).encode("utf-8")

    def json(self):
        return json.loads(self._content.decode("utf-8"))


class DummyClient:
    def __init__(self):
        self.called = False

    def request(self, method, url, **kwargs):
        self.called = True
        return DummyResponse({"results": [{"text": "hello"}]})


def test_middleware_simulate_error(tmp_path):
    middleware = ChaosMiddleware(
        config={"simulate_error": True, "tape_path": str(tmp_path / "sdk.tape")}
    )
    client = middleware.wrap_client(DummyClient())
    with pytest.raises(RuntimeError):
        client.request("GET", "http://example.com")


def test_middleware_poison_and_tape(tmp_path):
    tape_path = tmp_path / "sdk.tape"
    middleware = ChaosMiddleware(
        config={"poison_rag": True, "tape_path": str(tape_path)}
    )
    client = middleware.wrap_client(DummyClient())
    response = client.request("GET", "http://example.com")

    data = response.json()
    assert "CHAOS_RAG_POISON" in data["results"][0]["text"]

    lines = tape_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines, "tape should contain at least one record"


def test_middleware_disable_requests(tmp_path):
    tape_path = tmp_path / "sdk.tape"
    middleware = ChaosMiddleware(
        config={"poison_rag": True, "tape_path": str(tape_path), "disable_httpx": True}
    )
    client = middleware.wrap_client(DummyClient())
    response = client.request("GET", "http://example.com")

    data = response.json()
    assert "CHAOS_RAG_POISON" not in data["results"][0]["text"]
    assert not tape_path.exists() or tape_path.read_text(encoding="utf-8").strip() == ""
