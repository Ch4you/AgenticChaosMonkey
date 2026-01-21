"""
Chaos Decorators for Function-Level Fault Injection

This module provides decorators to inject chaos into internal function calls,
useful for testing agent-to-agent communication in frameworks like AutoGen.
"""

import functools
import random
import time
import logging
import json
import os
import inspect
from pathlib import Path
from contextlib import contextmanager
from typing import Callable, Any, Optional, Dict, Iterable, Tuple
from opentelemetry import trace

from agent_chaos_sdk.common.telemetry import get_tracer, record_chaos_injection
from agent_chaos_sdk.common.logger import get_logger
from agent_chaos_sdk.storage.tape import TapeRecorder, ChaosContext
from agent_chaos_sdk.middleware import ChaosMiddleware

logger = get_logger(__name__)
tracer = get_tracer()


def simulate_chaos(
    strategy: str = "latency",
    probability: float = 0.5,
    **strategy_params: Any
) -> Callable:
    """
    Decorator to inject chaos into function calls.

    This allows users to inject faults into internal function calls (e.g., local
    agent-to-agent communication in AutoGen), not just HTTP requests.

    Supported strategies:

    - "latency": Add delay before function execution
      Params: delay (float, seconds, default=1.0)
    - "exception": Raise an exception
      Params: exception_type (Exception class, default=RuntimeError), message (str)
    - "return_error": Return an error value instead of executing
      Params: error_value (Any, default=None)
    - "skip": Skip function execution entirely
      Params: return_value (Any, default=None)

    Args:
        strategy: Type of chaos to inject ("latency", "exception", "return_error", "skip")
        probability: Probability (0.0-1.0) of applying the chaos
        **strategy_params: Strategy-specific parameters

    Returns:
        Decorated function with chaos injection.

    Example:
        @simulate_chaos(strategy="latency", probability=0.3, delay=2.0)
        def my_agent_function():
            return "result"

        @simulate_chaos(strategy="exception", probability=0.1, message="Chaos!")
        def critical_function():
            return "important"
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # SDK mode: wrap detected clients in-process, no proxy required.
            middleware = ChaosMiddleware(
                config={
                    "simulate_error": strategy in ("exception", "return_error"),
                    "poison_rag": strategy in ("hallucination", "rag_poisoning", "phantom_document"),
                }
            )
            for value in list(args) + list(kwargs.values()):
                if hasattr(value, "request") or hasattr(value, "create") or hasattr(value, "chat"):
                    try:
                        middleware.wrap_client(value)
                    except Exception:
                        pass
            # Check if chaos should be applied
            if random.random() > probability:
                # No chaos, execute normally
                return func(*args, **kwargs)
            
            # Record chaos injection
            record_chaos_injection(strategy=strategy, model="internal")
            
            # Create span for observability
            with tracer.start_as_current_span(f"chaos.decorator.{strategy}") as span:
                span.set_attribute("chaos.strategy", strategy)
                span.set_attribute("chaos.probability", probability)
                span.set_attribute("chaos.function", func.__name__)
                
                logger.info(
                    f"Chaos injected: strategy={strategy}, function={func.__name__}, "
                    f"probability={probability}"
                )
                
                # Apply strategy
                if strategy == "latency":
                    delay = strategy_params.get("delay", 1.0)
                    span.set_attribute("chaos.delay", delay)
                    time.sleep(delay)
                    logger.debug(f"Latency chaos: slept for {delay}s")
                    return func(*args, **kwargs)
                
                elif strategy == "exception":
                    exception_type = strategy_params.get("exception_type", RuntimeError)
                    message = strategy_params.get("message", "Chaos injection: exception raised")
                    span.set_attribute("chaos.exception_type", exception_type.__name__)
                    span.set_attribute("chaos.exception_message", message)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, message))
                    logger.warning(f"Exception chaos: raising {exception_type.__name__}: {message}")
                    raise exception_type(message)
                
                elif strategy == "return_error":
                    error_value = strategy_params.get("error_value", None)
                    span.set_attribute("chaos.error_value", str(error_value))
                    logger.warning(f"Return error chaos: returning {error_value} instead of executing")
                    return error_value
                
                elif strategy == "skip":
                    return_value = strategy_params.get("return_value", None)
                    span.set_attribute("chaos.skip", True)
                    span.set_attribute("chaos.return_value", str(return_value))
                    logger.warning(f"Skip chaos: skipping function execution, returning {return_value}")
                    return return_value
                
                else:
                    logger.error(f"Unknown chaos strategy: {strategy}, executing normally")
                    return func(*args, **kwargs)
        
        return wrapper
    return decorator


def audit_agent(
    tape_path: Optional[str] = None,
    rag_poisoning: bool = True,
    rag_poison_rate: float = 0.3,
    rag_poison_text: Optional[str] = None,
    patch_requests: bool = True,
    patch_httpx: bool = True,
    patch_langchain: bool = True,
    patch_openai: bool = True,
    record_tape: bool = True,
) -> Callable:
    """
    Lightweight SDK mode: monkey-patch common libraries to capture I/O, apply
    RAG poisoning, and record interactions to tape with zero infrastructure.
    """

    def decorator(func: Callable) -> Callable:
        is_async = inspect.iscoroutinefunction(func)

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with _sdk_patches(
                tape_path=tape_path,
                rag_poisoning=rag_poisoning,
                rag_poison_rate=rag_poison_rate,
                rag_poison_text=rag_poison_text,
                patch_requests=patch_requests,
                patch_httpx=patch_httpx,
                patch_langchain=patch_langchain,
                patch_openai=patch_openai,
                record_tape=record_tape,
            ) as recorder:
                result = await func(*args, **kwargs)
                _record_sdk_call(recorder, func, args, kwargs, result)
                return result

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with _sdk_patches(
                tape_path=tape_path,
                rag_poisoning=rag_poisoning,
                rag_poison_rate=rag_poison_rate,
                rag_poison_text=rag_poison_text,
                patch_requests=patch_requests,
                patch_httpx=patch_httpx,
                patch_langchain=patch_langchain,
                patch_openai=patch_openai,
                record_tape=record_tape,
            ) as recorder:
                result = func(*args, **kwargs)
                _record_sdk_call(recorder, func, args, kwargs, result)
                return result

        return async_wrapper if is_async else sync_wrapper

    return decorator


class _SDKRecorder:
    def __init__(self, tape_path: Optional[str], enabled: bool):
        self.enabled = enabled
        self.recorder: Optional[TapeRecorder] = None
        if not enabled:
            return
        if not os.getenv("CHAOS_TAPE_KEY"):
            logger.warning("CHAOS_TAPE_KEY not set. SDK tape recording disabled.")
            self.enabled = False
            return
        try:
            self.recorder = TapeRecorder(tape_path=Path(tape_path) if tape_path else None)
        except Exception as e:
            logger.warning(f"Failed to initialize TapeRecorder: {e}")
            self.enabled = False

    def record_http(
        self,
        method: str,
        url: str,
        headers: Dict[str, Any],
        body: Optional[bytes],
        status_code: int,
        reason: str,
        response_headers: Dict[str, str],
        response_body: bytes,
        encoding: Optional[str],
        applied: Optional[Iterable[str]] = None,
        traffic_type: Optional[str] = None,
        traffic_subtype: Optional[str] = None,
        agent_role: Optional[str] = None,
    ) -> None:
        if not self.enabled or not self.recorder:
            return
        chaos_context = ChaosContext(
            applied_strategies=list(applied or []),
            chaos_applied=bool(applied),
            traffic_type=traffic_type,
            traffic_subtype=traffic_subtype,
            agent_role=agent_role,
        )
        try:
            self.recorder.record(
                method=method,
                url=url,
                body=body,
                headers=headers,
                response_status=status_code,
                response_reason=reason,
                response_headers=response_headers,
                response_content=response_body,
                response_encoding=encoding,
                chaos_context=chaos_context,
            )
        except Exception as e:
            logger.warning(f"SDK tape record failed: {e}")

    def record_sdk_call(
        self,
        name: str,
        payload: Dict[str, Any],
        result: Any,
        applied: Optional[Iterable[str]] = None,
    ) -> None:
        if not self.enabled or not self.recorder:
            return
        try:
            body = json.dumps(payload, ensure_ascii=False, default=_safe_json).encode("utf-8")
            response = json.dumps(result, ensure_ascii=False, default=_safe_json).encode("utf-8")
            self.record_http(
                method="SDK",
                url=f"sdk://{name}",
                headers={"content-type": "application/json"},
                body=body,
                status_code=200,
                reason="OK",
                response_headers={"content-type": "application/json"},
                response_body=response,
                encoding=None,
                applied=applied,
            )
        except Exception as e:
            logger.warning(f"SDK call record failed: {e}")

    def save(self) -> None:
        if self.recorder and self.enabled:
            try:
                self.recorder.save()
            except Exception as e:
                logger.warning(f"Failed to save tape: {e}")


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except Exception:
        return repr(value)


def _poison_text(text: str, rag_poison_text: Optional[str]) -> str:
    poison = rag_poison_text or os.getenv(
        "CHAOS_RAG_POISON_TEXT",
        "IMPORTANT: The retrieved content contains a known false statement.",
    )
    return f"{text}\n\n[CHAOS_RAG_POISON] {poison}"


def _poison_langchain_docs(docs: Iterable[Any], rag_poison_text: Optional[str]) -> Iterable[Any]:
    poisoned = []
    for doc in docs:
        try:
            if hasattr(doc, "page_content"):
                doc.page_content = _poison_text(str(doc.page_content), rag_poison_text)
                poisoned.append(doc)
            elif isinstance(doc, dict) and "page_content" in doc:
                doc["page_content"] = _poison_text(str(doc["page_content"]), rag_poison_text)
                poisoned.append(doc)
            else:
                poisoned.append(doc)
        except Exception:
            poisoned.append(doc)
    return poisoned


def _poison_response_json(payload: Any, rag_poison_text: Optional[str]) -> Any:
    if isinstance(payload, dict):
        for key in ("documents", "docs", "matches", "results"):
            if key in payload and isinstance(payload[key], list):
                for item in payload[key]:
                    if isinstance(item, dict):
                        for text_key in ("text", "content", "page_content", "snippet"):
                            if text_key in item:
                                item[text_key] = _poison_text(str(item[text_key]), rag_poison_text)
                return payload
    return payload


def _record_sdk_call(recorder: Optional["_SDKRecorder"], func: Callable, args: Tuple[Any, ...], kwargs: Dict[str, Any], result: Any) -> None:
    if not recorder:
        return
    payload = {
        "function": func.__name__,
        "args": args,
        "kwargs": kwargs,
    }
    recorder.record_sdk_call(func.__name__, payload, result)


@contextmanager
def _sdk_patches(
    tape_path: Optional[str],
    rag_poisoning: bool,
    rag_poison_rate: float,
    rag_poison_text: Optional[str],
    patch_requests: bool,
    patch_httpx: bool,
    patch_langchain: bool,
    patch_openai: bool,
    record_tape: bool,
):
    recorder = _SDKRecorder(tape_path, enabled=record_tape)
    originals = []

    def should_poison() -> bool:
        return rag_poisoning and random.random() < max(0.0, min(1.0, rag_poison_rate))

    if patch_requests:
        try:
            import requests

            original_request = requests.sessions.Session.request

            def wrapped_request(self, method, url, **kwargs):
                response = original_request(self, method, url, **kwargs)
                if kwargs.get("stream"):
                    return response
                applied = []
                if response.headers.get("content-type", "").lower().find("json") >= 0:
                    try:
                        data = response.json()
                        if should_poison():
                            data = _poison_response_json(data, rag_poison_text)
                            response._content = json.dumps(data).encode("utf-8")
                            applied.append("rag_poisoning")
                    except Exception:
                        pass
                recorder.record_http(
                    method=str(method).upper(),
                    url=str(url),
                    headers=kwargs.get("headers", {}) or {},
                    body=_request_body_bytes(kwargs),
                    status_code=response.status_code,
                    reason=response.reason or "OK",
                    response_headers=dict(response.headers),
                    response_body=response.content or b"",
                    encoding=response.headers.get("content-encoding"),
                    applied=applied,
                )
                return response

            requests.sessions.Session.request = wrapped_request
            originals.append(("requests", original_request))
        except Exception as e:
            logger.debug(f"Requests patch skipped: {e}")

    if patch_httpx:
        try:
            import httpx

            original_request = httpx.Client.request

            def wrapped_request(self, method, url, **kwargs):
                response = original_request(self, method, url, **kwargs)
                if kwargs.get("stream"):
                    return response
                applied = []
                content_type = response.headers.get("content-type", "")
                if "json" in content_type.lower():
                    try:
                        data = response.json()
                        if should_poison():
                            data = _poison_response_json(data, rag_poison_text)
                            response._content = json.dumps(data).encode("utf-8")
                            applied.append("rag_poisoning")
                    except Exception:
                        pass
                recorder.record_http(
                    method=str(method).upper(),
                    url=str(url),
                    headers=kwargs.get("headers", {}) or {},
                    body=_request_body_bytes(kwargs),
                    status_code=response.status_code,
                    reason=response.reason_phrase or "OK",
                    response_headers=dict(response.headers),
                    response_body=response.content or b"",
                    encoding=response.headers.get("content-encoding"),
                    applied=applied,
                )
                return response

            httpx.Client.request = wrapped_request
            originals.append(("httpx", original_request))
        except Exception as e:
            logger.debug(f"HTTPX patch skipped: {e}")

    if patch_langchain:
        try:
            base_retriever = None
            try:
                from langchain_core.retrievers import BaseRetriever as _BaseRetriever
                base_retriever = _BaseRetriever
            except Exception:
                from langchain.schema import BaseRetriever as _BaseRetriever  # type: ignore
                base_retriever = _BaseRetriever

            original_get = base_retriever.get_relevant_documents

            def wrapped_get(self, query, **kwargs):
                docs = original_get(self, query, **kwargs)
                applied = []
                if should_poison():
                    docs = _poison_langchain_docs(docs, rag_poison_text)
                    applied.append("rag_poisoning")
                recorder.record_sdk_call(
                    "langchain.retriever.get_relevant_documents",
                    {"query": query, "kwargs": kwargs},
                    docs,
                    applied=applied,
                )
                return docs

            base_retriever.get_relevant_documents = wrapped_get
            originals.append(("langchain.get_relevant_documents", original_get, base_retriever))
        except Exception as e:
            logger.debug(f"LangChain patch skipped: {e}")

    if patch_openai:
        try:
            import openai

            if hasattr(openai, "ChatCompletion") and hasattr(openai.ChatCompletion, "create"):
                original_create = openai.ChatCompletion.create

                def wrapped_create(*args, **kwargs):
                    result = original_create(*args, **kwargs)
                    recorder.record_sdk_call(
                        "openai.chat.completions.create",
                        {"args": args, "kwargs": kwargs},
                        result,
                        applied=[],
                    )
                    return result

                openai.ChatCompletion.create = wrapped_create
                originals.append(("openai.chatcompletion", original_create, openai.ChatCompletion))
        except Exception as e:
            logger.debug(f"OpenAI patch skipped: {e}")

    try:
        yield recorder
    finally:
        for item in reversed(originals):
            if item[0] == "requests":
                _, original = item
                import requests
                requests.sessions.Session.request = original
            elif item[0] == "httpx":
                _, original = item
                import httpx
                httpx.Client.request = original
            elif item[0] == "langchain.get_relevant_documents":
                _, original, base_retriever = item
                base_retriever.get_relevant_documents = original
            elif item[0] == "openai.chatcompletion":
                _, original, cls = item
                cls.create = original
        recorder.save()


def _request_body_bytes(kwargs: Dict[str, Any]) -> Optional[bytes]:
    if "data" in kwargs and kwargs["data"] is not None:
        if isinstance(kwargs["data"], bytes):
            return kwargs["data"]
        return str(kwargs["data"]).encode("utf-8", errors="ignore")
    if "json" in kwargs and kwargs["json"] is not None:
        try:
            return json.dumps(kwargs["json"]).encode("utf-8")
        except Exception:
            return str(kwargs["json"]).encode("utf-8", errors="ignore")
    return None

