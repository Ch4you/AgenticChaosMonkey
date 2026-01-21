from agent_chaos_sdk.middleware import ChaosMiddleware


class DummyResponses:
    def __init__(self):
        self.called = False

    def create(self, **kwargs):
        self.called = True
        return {"results": [{"text": "hello"}]}


class DummyOpenAI:
    def __init__(self):
        self.responses = DummyResponses()


def test_openai_responses_create_patch(tmp_path):
    tape_path = tmp_path / "sdk_openai.tape"
    middleware = ChaosMiddleware(
        config={
            "poison_rag": True,
            "rag_poison_jsonpath": ["$.results[*].text"],
            "tape_path": str(tape_path),
        }
    )
    client = middleware.wrap_client(DummyOpenAI())
    result = client.responses.create(prompt="hi")

    assert client.responses.called is True
    assert "CHAOS_RAG_POISON" in result["results"][0]["text"]
    assert tape_path.exists()
