import pytest

from agent_chaos_sdk.middleware import ChaosMiddleware


def test_langchain_runnable_invoke_patch(tmp_path):
    try:
        from langchain_core.runnables.base import Runnable
    except Exception:
        pytest.skip("langchain_core not available")

    class DummyRunnable(Runnable):
        def invoke(self, input, **kwargs):
            return {"results": [{"text": "hello"}]}

    tape_path = tmp_path / "sdk_langchain.tape"
    middleware = ChaosMiddleware(
        config={
            "poison_rag": True,
            "rag_poison_jsonpath": ["$.results[*].text"],
            "tape_path": str(tape_path),
        }
    )
    middleware.wrap_client(object())  # triggers global patch for Runnable

    runnable = DummyRunnable()
    output = runnable.invoke("hi")
    assert "CHAOS_RAG_POISON" in output["results"][0]["text"]
    assert tape_path.exists()


@pytest.mark.asyncio
async def test_langchain_runnable_ainvoke_patch(tmp_path):
    try:
        from langchain_core.runnables.base import Runnable
    except Exception:
        pytest.skip("langchain_core not available")

    class DummyRunnable(Runnable):
        def invoke(self, input, **kwargs):
            return {"results": [{"text": "hello"}]}

        async def ainvoke(self, input, **kwargs):
            return {"results": [{"text": "hello"}]}

    tape_path = tmp_path / "sdk_langchain_async.tape"
    middleware = ChaosMiddleware(
        config={
            "poison_rag": True,
            "rag_poison_jsonpath": ["$.results[*].text"],
            "tape_path": str(tape_path),
        }
    )
    middleware.wrap_client(object())

    runnable = DummyRunnable()
    output = await runnable.ainvoke("hi")
    assert "CHAOS_RAG_POISON" in output["results"][0]["text"]
    assert tape_path.exists()
