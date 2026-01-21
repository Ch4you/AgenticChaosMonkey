"""
In-process Chaos Middleware (SDK mode).

Provides zero-infrastructure monkey patching for common Python clients.
Captures input/output to a local JSONL tape file and optionally injects
errors or RAG poisoning.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Callable, Iterable, Tuple

try:
    from jsonpath_ng import parse as jsonpath_parse
    JSONPATH_AVAILABLE = True
except Exception:
    JSONPATH_AVAILABLE = False


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return repr(value)


def _poison_text(text: str, poison_text: Optional[str]) -> str:
    poison = poison_text or os.getenv(
        "CHAOS_RAG_POISON_TEXT",
        "IMPORTANT: The retrieved content contains a known false statement.",
    )
    return f"{text}\n\n[CHAOS_RAG_POISON] {poison}"


def _poison_payload(payload: Any, poison_text: Optional[str], jsonpath_exprs: Optional[Iterable[str]]) -> Any:
    if jsonpath_exprs and JSONPATH_AVAILABLE:
        for expr in jsonpath_exprs:
            try:
                jsonpath_expr = jsonpath_parse(expr)
                for match in jsonpath_expr.find(payload):
                    try:
                        current = match.value
                        if isinstance(current, str):
                            match.full_path.update(payload, _poison_text(current, poison_text))
                        else:
                            match.full_path.update(payload, _poison_text(str(current), poison_text))
                    except Exception:
                        continue
            except Exception:
                continue
        return payload
    # Fallback heuristic
    if isinstance(payload, dict):
        for key in ("documents", "docs", "matches", "results"):
            if key in payload and isinstance(payload[key], list):
                for item in payload[key]:
                    if isinstance(item, dict):
                        for text_key in ("text", "content", "page_content", "snippet"):
                            if text_key in item:
                                item[text_key] = _poison_text(str(item[text_key]), poison_text)
                return payload
    if isinstance(payload, list):
        for idx, item in enumerate(payload):
            if isinstance(item, dict):
                for text_key in ("text", "content", "page_content", "snippet"):
                    if text_key in item:
                        item[text_key] = _poison_text(str(item[text_key]), poison_text)
        return payload
    return payload


class ChaosMiddleware:
    """
    Lightweight in-process SDK middleware.

    Config keys:
      - tape_path: str (path to .tape JSONL file)
      - simulate_error: bool
      - poison_rag: bool
      - rag_poison_text: str
      - rag_poison_jsonpath: List[str]
      - disable_requests: bool
      - disable_httpx: bool
      - disable_openai: bool
      - disable_langchain: bool
      - disable_llamaindex: bool
      - disable_haystack: bool
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.tape_path = self._resolve_tape_path(self.config.get("tape_path"))
        self.simulate_error = bool(self.config.get("simulate_error", False))
        self.poison_rag = bool(self.config.get("poison_rag", False))
        self.rag_poison_text = self.config.get("rag_poison_text")
        self.rag_poison_jsonpath = self.config.get("rag_poison_jsonpath") or []
        self.disable_requests = bool(self.config.get("disable_requests", False))
        self.disable_httpx = bool(self.config.get("disable_httpx", False))
        self.disable_openai = bool(self.config.get("disable_openai", False))
        self.disable_langchain = bool(self.config.get("disable_langchain", False))
        self.disable_llamaindex = bool(self.config.get("disable_llamaindex", False))
        self.disable_haystack = bool(self.config.get("disable_haystack", False))

    def _resolve_tape_path(self, tape_path: Optional[str]) -> Path:
        if tape_path:
            path = Path(tape_path)
        else:
            path = Path("tapes") / f"sdk_{int(time.time())}.tape"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _write_tape(self, record: Dict[str, Any]) -> None:
        try:
            with open(self.tape_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def wrap_client(self, client: Any) -> Any:
        """
        Wrap a client instance to intercept .request() or .create() calls.
        """
        if hasattr(client, "_chaos_wrapped"):
            return client

        if not self.disable_httpx and hasattr(client, "request") and callable(getattr(client, "request")):
            self._wrap_request(client)
        if not self.disable_openai and hasattr(client, "create") and callable(getattr(client, "create")):
            self._wrap_create(client, attr="create")
        # OpenAI-style: client.chat.completions.create
        if not self.disable_openai and hasattr(client, "chat"):
            chat = getattr(client, "chat")
            if hasattr(chat, "completions"):
                completions = getattr(chat, "completions")
                if hasattr(completions, "create") and callable(getattr(completions, "create")):
                    self._wrap_nested_create(completions, "openai.chat.completions.create")
        # OpenAI responses: client.responses.create
        if not self.disable_openai and hasattr(client, "responses"):
            responses = getattr(client, "responses")
            if hasattr(responses, "create") and callable(getattr(responses, "create")):
                self._wrap_nested_create(responses, "openai.responses.create")
        # LangChain retriever (sync)
        if not self.disable_langchain:
            self._wrap_langchain_retriever()
            self._wrap_langchain_runnable()
            self._wrap_langchain_chat_model()
        if not self.disable_llamaindex:
            self._wrap_llamaindex()
        if not self.disable_haystack:
            self._wrap_haystack()
        try:
            setattr(client, "_chaos_wrapped", True)
        except Exception:
            # Some builtin objects (or objects with __slots__) may not allow new attrs.
            pass
        return client

    def _wrap_request(self, client: Any) -> None:
        original = client.request

        def wrapped_request(*args: Any, **kwargs: Any):
            if self.simulate_error:
                raise RuntimeError("ChaosMiddleware simulate_error: request blocked")
            record = {
                "timestamp": time.time(),
                "library": type(client).__name__,
                "method": "request",
                "input": {
                    "args": [_safe_json(a) for a in args],
                    "kwargs": {k: _safe_json(v) for k, v in kwargs.items()},
                },
            }
            try:
                response = original(*args, **kwargs)
                output = self._extract_response_payload(response)
                if self.poison_rag:
                    output = _poison_payload(output, self.rag_poison_text, self.rag_poison_jsonpath)
                    self._apply_response_override(response, output)
                record["output"] = _safe_json(output)
                self._write_tape(record)
                return response
            except Exception as exc:
                record["error"] = repr(exc)
                self._write_tape(record)
                raise

        client.request = wrapped_request

    def _wrap_create(self, client: Any, attr: str) -> None:
        original = getattr(client, attr)

        def wrapped_create(*args: Any, **kwargs: Any):
            if self.simulate_error:
                raise RuntimeError("ChaosMiddleware simulate_error: create blocked")
            record = {
                "timestamp": time.time(),
                "library": type(client).__name__,
                "method": attr,
                "input": {
                    "args": [_safe_json(a) for a in args],
                    "kwargs": {k: _safe_json(v) for k, v in kwargs.items()},
                },
            }
            try:
                result = original(*args, **kwargs)
                output = self._extract_generic_payload(result)
                if self.poison_rag:
                    output = _poison_payload(output, self.rag_poison_text, self.rag_poison_jsonpath)
                record["output"] = _safe_json(output)
                self._write_tape(record)
                return result
            except Exception as exc:
                record["error"] = repr(exc)
                self._write_tape(record)
                raise

        setattr(client, attr, wrapped_create)

    def _wrap_nested_create(self, obj: Any, label: str) -> None:
        original = obj.create

        def wrapped_create(*args: Any, **kwargs: Any):
            if self.simulate_error:
                raise RuntimeError("ChaosMiddleware simulate_error: create blocked")
            record = {
                "timestamp": time.time(),
                "library": label,
                "method": "create",
                "input": {
                    "args": [_safe_json(a) for a in args],
                    "kwargs": {k: _safe_json(v) for k, v in kwargs.items()},
                },
            }
            try:
                result = original(*args, **kwargs)
                output = self._extract_generic_payload(result)
                if self.poison_rag:
                    output = _poison_payload(output, self.rag_poison_text, self.rag_poison_jsonpath)
                record["output"] = _safe_json(output)
                self._write_tape(record)
                return result
            except Exception as exc:
                record["error"] = repr(exc)
                self._write_tape(record)
                raise

        obj.create = wrapped_create

    def _extract_response_payload(self, response: Any) -> Any:
        if hasattr(response, "json"):
            try:
                return response.json()
            except Exception:
                pass
        if hasattr(response, "text"):
            return response.text
        return repr(response)

    def _apply_response_override(self, response: Any, payload: Any) -> None:
        try:
            content = json.dumps(payload).encode("utf-8")
            if hasattr(response, "_content"):
                response._content = content
        except Exception:
            pass

    def _extract_generic_payload(self, result: Any) -> Any:
        for attr in ("model_dump", "dict", "to_dict"):
            if hasattr(result, attr) and callable(getattr(result, attr)):
                try:
                    return getattr(result, attr)()
                except Exception:
                    continue
        return _safe_json(result)

    def _wrap_langchain_retriever(self) -> None:
        try:
            base_retriever = None
            try:
                from langchain_core.retrievers import BaseRetriever as _BaseRetriever
                base_retriever = _BaseRetriever
            except Exception:
                from langchain.schema import BaseRetriever as _BaseRetriever  # type: ignore
                base_retriever = _BaseRetriever
            if getattr(base_retriever, "_chaos_wrapped", False):
                return

            original_get = base_retriever.get_relevant_documents
            middleware = self

            def wrapped_get(self, query, **kwargs):
                if middleware.simulate_error:
                    raise RuntimeError("ChaosMiddleware simulate_error: retriever blocked")
                record = {
                    "timestamp": time.time(),
                    "library": "langchain.retriever",
                    "method": "get_relevant_documents",
                    "input": {"query": _safe_json(query), "kwargs": _safe_json(kwargs)},
                }
                try:
                    docs = original_get(self, query, **kwargs)
                    if middleware.poison_rag:
                        docs = _poison_payload(docs, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                    record["output"] = _safe_json(docs)
                    middleware._write_tape(record)
                    return docs
                except Exception as exc:
                    record["error"] = repr(exc)
                    middleware._write_tape(record)
                    raise

            base_retriever.get_relevant_documents = wrapped_get
            if hasattr(base_retriever, "aget_relevant_documents"):
                original_aget = base_retriever.aget_relevant_documents

                async def wrapped_aget(self, query, **kwargs):
                    if middleware.simulate_error:
                        raise RuntimeError("ChaosMiddleware simulate_error: retriever blocked")
                    record = {
                        "timestamp": time.time(),
                        "library": "langchain.retriever",
                        "method": "aget_relevant_documents",
                        "input": {"query": _safe_json(query), "kwargs": _safe_json(kwargs)},
                    }
                    try:
                        docs = await original_aget(self, query, **kwargs)
                        if middleware.poison_rag:
                            docs = _poison_payload(docs, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                        record["output"] = _safe_json(docs)
                        middleware._write_tape(record)
                        return docs
                    except Exception as exc:
                        record["error"] = repr(exc)
                        middleware._write_tape(record)
                        raise

                base_retriever.aget_relevant_documents = wrapped_aget
            setattr(base_retriever, "_chaos_wrapped", True)
        except Exception:
            pass

    def _wrap_langchain_runnable(self) -> None:
        try:
            from langchain_core.runnables.base import Runnable as _Runnable
            middleware = self
            def _wrap_method(target_cls, method_name: str, is_async: bool) -> None:
                original = getattr(target_cls, method_name, None)
                if not callable(original) or getattr(original, "_chaos_wrapped", False):
                    return
                if is_async:
                    async def wrapped(self, input, **kwargs):
                        if middleware.simulate_error:
                            raise RuntimeError("ChaosMiddleware simulate_error: runnable blocked")
                        record = {
                            "timestamp": time.time(),
                            "library": "langchain.runnable",
                            "method": method_name,
                            "input": {"input": _safe_json(input), "kwargs": _safe_json(kwargs)},
                        }
                        try:
                            output = await original(self, input, **kwargs)
                            if middleware.poison_rag:
                                output = _poison_payload(
                                    output, middleware.rag_poison_text, middleware.rag_poison_jsonpath
                                )
                            record["output"] = _safe_json(output)
                            middleware._write_tape(record)
                            return output
                        except Exception as exc:
                            record["error"] = repr(exc)
                            middleware._write_tape(record)
                            raise
                else:
                    def wrapped(self, input, **kwargs):
                        if middleware.simulate_error:
                            raise RuntimeError("ChaosMiddleware simulate_error: runnable blocked")
                        record = {
                            "timestamp": time.time(),
                            "library": "langchain.runnable",
                            "method": method_name,
                            "input": {"input": _safe_json(input), "kwargs": _safe_json(kwargs)},
                        }
                        try:
                            output = original(self, input, **kwargs)
                            if middleware.poison_rag:
                                output = _poison_payload(
                                    output, middleware.rag_poison_text, middleware.rag_poison_jsonpath
                                )
                            record["output"] = _safe_json(output)
                            middleware._write_tape(record)
                            return output
                        except Exception as exc:
                            record["error"] = repr(exc)
                            middleware._write_tape(record)
                            raise

                wrapped._chaos_wrapped = True
                setattr(target_cls, method_name, wrapped)

            # Patch base Runnable (idempotent via method flags)
            _wrap_method(_Runnable, "invoke", is_async=False)
            if hasattr(_Runnable, "ainvoke"):
                _wrap_method(_Runnable, "ainvoke", is_async=True)

            # Patch already-defined subclasses (overrides won't hit base methods)
            for subclass in list(_Runnable.__subclasses__()):
                _wrap_method(subclass, "invoke", is_async=False)
                if hasattr(subclass, "ainvoke"):
                    _wrap_method(subclass, "ainvoke", is_async=True)

            # Fallback: scan loaded classes for any Runnable subclasses
            try:
                import gc
                for obj in gc.get_objects():
                    try:
                        if isinstance(obj, type) and issubclass(obj, _Runnable):
                            _wrap_method(obj, "invoke", is_async=False)
                            if hasattr(obj, "ainvoke"):
                                _wrap_method(obj, "ainvoke", is_async=True)
                    except Exception:
                        continue
            except Exception:
                pass

            setattr(_Runnable, "_chaos_wrapped", True)
        except Exception:
            pass

    def _wrap_langchain_chat_model(self) -> None:
        try:
            from langchain_core.language_models.chat_models import BaseChatModel as _BaseChatModel
            if getattr(_BaseChatModel, "_chaos_wrapped", False):
                return
            middleware = self
            original_invoke = _BaseChatModel.invoke

            def wrapped_invoke(self, input, **kwargs):
                if middleware.simulate_error:
                    raise RuntimeError("ChaosMiddleware simulate_error: chat model blocked")
                record = {
                    "timestamp": time.time(),
                    "library": "langchain.chat_model",
                    "method": "invoke",
                    "input": {"input": _safe_json(input), "kwargs": _safe_json(kwargs)},
                }
                try:
                    output = original_invoke(self, input, **kwargs)
                    if middleware.poison_rag:
                        output = _poison_payload(output, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                    record["output"] = _safe_json(output)
                    middleware._write_tape(record)
                    return output
                except Exception as exc:
                    record["error"] = repr(exc)
                    middleware._write_tape(record)
                    raise

            _BaseChatModel.invoke = wrapped_invoke

            if hasattr(_BaseChatModel, "ainvoke"):
                original_ainvoke = _BaseChatModel.ainvoke

                async def wrapped_ainvoke(self, input, **kwargs):
                    if middleware.simulate_error:
                        raise RuntimeError("ChaosMiddleware simulate_error: chat model blocked")
                    record = {
                        "timestamp": time.time(),
                        "library": "langchain.chat_model",
                        "method": "ainvoke",
                        "input": {"input": _safe_json(input), "kwargs": _safe_json(kwargs)},
                    }
                    try:
                        output = await original_ainvoke(self, input, **kwargs)
                        if middleware.poison_rag:
                            output = _poison_payload(output, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                        record["output"] = _safe_json(output)
                        middleware._write_tape(record)
                        return output
                    except Exception as exc:
                        record["error"] = repr(exc)
                        middleware._write_tape(record)
                        raise

                _BaseChatModel.ainvoke = wrapped_ainvoke

            setattr(_BaseChatModel, "_chaos_wrapped", True)
        except Exception:
            pass

    def _wrap_llamaindex(self) -> None:
        try:
            from llama_index.core.retrievers import BaseRetriever as _LlamaRetriever
            if getattr(_LlamaRetriever, "_chaos_wrapped", False):
                return
            middleware = self
            original_retrieve = _LlamaRetriever.retrieve

            def wrapped_retrieve(self, query):
                if middleware.simulate_error:
                    raise RuntimeError("ChaosMiddleware simulate_error: llama_index retriever blocked")
                record = {
                    "timestamp": time.time(),
                    "library": "llama_index.retriever",
                    "method": "retrieve",
                    "input": {"query": _safe_json(query)},
                }
                try:
                    results = original_retrieve(self, query)
                    if middleware.poison_rag:
                        results = _poison_payload(results, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                    record["output"] = _safe_json(results)
                    middleware._write_tape(record)
                    return results
                except Exception as exc:
                    record["error"] = repr(exc)
                    middleware._write_tape(record)
                    raise

            _LlamaRetriever.retrieve = wrapped_retrieve
            if hasattr(_LlamaRetriever, "aretrieve"):
                original_aretrieve = _LlamaRetriever.aretrieve

                async def wrapped_aretrieve(self, query):
                    if middleware.simulate_error:
                        raise RuntimeError("ChaosMiddleware simulate_error: llama_index retriever blocked")
                    record = {
                        "timestamp": time.time(),
                        "library": "llama_index.retriever",
                        "method": "aretrieve",
                        "input": {"query": _safe_json(query)},
                    }
                    try:
                        results = await original_aretrieve(self, query)
                        if middleware.poison_rag:
                            results = _poison_payload(results, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                        record["output"] = _safe_json(results)
                        middleware._write_tape(record)
                        return results
                    except Exception as exc:
                        record["error"] = repr(exc)
                        middleware._write_tape(record)
                        raise

                _LlamaRetriever.aretrieve = wrapped_aretrieve

            setattr(_LlamaRetriever, "_chaos_wrapped", True)
        except Exception:
            pass

        try:
            from llama_index.core.query_engine import BaseQueryEngine as _BaseQueryEngine
            if getattr(_BaseQueryEngine, "_chaos_wrapped", False):
                return
            middleware = self
            original_query = _BaseQueryEngine.query

            def wrapped_query(self, query):
                if middleware.simulate_error:
                    raise RuntimeError("ChaosMiddleware simulate_error: query engine blocked")
                record = {
                    "timestamp": time.time(),
                    "library": "llama_index.query_engine",
                    "method": "query",
                    "input": {"query": _safe_json(query)},
                }
                try:
                    result = original_query(self, query)
                    if middleware.poison_rag:
                        result = _poison_payload(result, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                    record["output"] = _safe_json(result)
                    middleware._write_tape(record)
                    return result
                except Exception as exc:
                    record["error"] = repr(exc)
                    middleware._write_tape(record)
                    raise

            _BaseQueryEngine.query = wrapped_query
            if hasattr(_BaseQueryEngine, "aquery"):
                original_aquery = _BaseQueryEngine.aquery

                async def wrapped_aquery(self, query):
                    if middleware.simulate_error:
                        raise RuntimeError("ChaosMiddleware simulate_error: query engine blocked")
                    record = {
                        "timestamp": time.time(),
                        "library": "llama_index.query_engine",
                        "method": "aquery",
                        "input": {"query": _safe_json(query)},
                    }
                    try:
                        result = await original_aquery(self, query)
                        if middleware.poison_rag:
                            result = _poison_payload(result, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                        record["output"] = _safe_json(result)
                        middleware._write_tape(record)
                        return result
                    except Exception as exc:
                        record["error"] = repr(exc)
                        middleware._write_tape(record)
                        raise

                _BaseQueryEngine.aquery = wrapped_aquery

            setattr(_BaseQueryEngine, "_chaos_wrapped", True)
        except Exception:
            pass

    def _wrap_haystack(self) -> None:
        try:
            from haystack import Pipeline as _Pipeline
            if getattr(_Pipeline, "_chaos_wrapped", False):
                return
            middleware = self
            original_run = _Pipeline.run

            def wrapped_run(self, *args, **kwargs):
                if middleware.simulate_error:
                    raise RuntimeError("ChaosMiddleware simulate_error: haystack pipeline blocked")
                record = {
                    "timestamp": time.time(),
                    "library": "haystack.pipeline",
                    "method": "run",
                    "input": {"args": [_safe_json(a) for a in args], "kwargs": _safe_json(kwargs)},
                }
                try:
                    result = original_run(self, *args, **kwargs)
                    if middleware.poison_rag:
                        result = _poison_payload(result, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                    record["output"] = _safe_json(result)
                    middleware._write_tape(record)
                    return result
                except Exception as exc:
                    record["error"] = repr(exc)
                    middleware._write_tape(record)
                    raise

            _Pipeline.run = wrapped_run
            if hasattr(_Pipeline, "run_async"):
                original_run_async = _Pipeline.run_async

                async def wrapped_run_async(self, *args, **kwargs):
                    if middleware.simulate_error:
                        raise RuntimeError("ChaosMiddleware simulate_error: haystack pipeline blocked")
                    record = {
                        "timestamp": time.time(),
                        "library": "haystack.pipeline",
                        "method": "run_async",
                        "input": {"args": [_safe_json(a) for a in args], "kwargs": _safe_json(kwargs)},
                    }
                    try:
                        result = await original_run_async(self, *args, **kwargs)
                        if middleware.poison_rag:
                            result = _poison_payload(result, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                        record["output"] = _safe_json(result)
                        middleware._write_tape(record)
                        return result
                    except Exception as exc:
                        record["error"] = repr(exc)
                        middleware._write_tape(record)
                        raise

                _Pipeline.run_async = wrapped_run_async

            setattr(_Pipeline, "_chaos_wrapped", True)
        except Exception:
            pass

        try:
            from haystack.components.retrievers import BaseRetriever as _HaystackRetriever
            if getattr(_HaystackRetriever, "_chaos_wrapped", False):
                return
            middleware = self
            original_run = _HaystackRetriever.run

            def wrapped_run(self, *args, **kwargs):
                if middleware.simulate_error:
                    raise RuntimeError("ChaosMiddleware simulate_error: haystack retriever blocked")
                record = {
                    "timestamp": time.time(),
                    "library": "haystack.retriever",
                    "method": "run",
                    "input": {"args": [_safe_json(a) for a in args], "kwargs": _safe_json(kwargs)},
                }
                try:
                    result = original_run(self, *args, **kwargs)
                    if middleware.poison_rag:
                        result = _poison_payload(result, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                    record["output"] = _safe_json(result)
                    middleware._write_tape(record)
                    return result
                except Exception as exc:
                    record["error"] = repr(exc)
                    middleware._write_tape(record)
                    raise

            _HaystackRetriever.run = wrapped_run

            if hasattr(_HaystackRetriever, "run_async"):
                original_run_async = _HaystackRetriever.run_async

                async def wrapped_run_async(self, *args, **kwargs):
                    if middleware.simulate_error:
                        raise RuntimeError("ChaosMiddleware simulate_error: haystack retriever blocked")
                    record = {
                        "timestamp": time.time(),
                        "library": "haystack.retriever",
                        "method": "run_async",
                        "input": {"args": [_safe_json(a) for a in args], "kwargs": _safe_json(kwargs)},
                    }
                    try:
                        result = await original_run_async(self, *args, **kwargs)
                        if middleware.poison_rag:
                            result = _poison_payload(result, middleware.rag_poison_text, middleware.rag_poison_jsonpath)
                        record["output"] = _safe_json(result)
                        middleware._write_tape(record)
                        return result
                    except Exception as exc:
                        record["error"] = repr(exc)
                        middleware._write_tape(record)
                        raise

                _HaystackRetriever.run_async = wrapped_run_async

            setattr(_HaystackRetriever, "_chaos_wrapped", True)
        except Exception:
            pass


def wrap_client(client: Any, config: Optional[Dict[str, Any]] = None) -> Any:
    """
    Convenience function to wrap a client with ChaosMiddleware.
    """
    middleware = ChaosMiddleware(config=config or {})
    return middleware.wrap_client(client)


class AgentChaosSDK:
    """
    Unified SDK entrypoint.

    Example:
        sdk = AgentChaosSDK(config)
        client = sdk.wrap_client(OpenAI(...))
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.middleware = ChaosMiddleware(config=config or {})

    def wrap_client(self, client: Any) -> Any:
        return self.middleware.wrap_client(client)
