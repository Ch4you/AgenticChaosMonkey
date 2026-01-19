"""
Request context management for chaos proxy.

This module manages context information for each HTTP flow, including
trace IDs, request metadata, and strategy execution state.
"""

from typing import Dict, Any, Optional
from mitmproxy import http
import uuid


class RequestContext:
    """
    Context information for a single HTTP request/response flow.
    
    This context is used to track request metadata, trace information,
    and strategy execution state throughout the request lifecycle.
    """
    
    def __init__(self, flow: http.HTTPFlow):
        """
        Initialize request context.
        
        Args:
            flow: The HTTP flow object.
        """
        self.flow = flow
        self.trace_id = str(uuid.uuid4())
        self.request_id = str(uuid.uuid4())
        self.metadata: Dict[str, Any] = {
            "url": flow.request.pretty_url,
            "method": flow.request.method,
            "host": flow.request.pretty_host,
        }
        self.applied_strategies: list[str] = []
    
    def add_strategy(self, strategy_name: str) -> None:
        """
        Record that a strategy was applied.
        
        Args:
            strategy_name: Name of the applied strategy.
        """
        self.applied_strategies.append(strategy_name)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert context to dictionary for logging/serialization.
        
        Returns:
            Dictionary representation of context.
        """
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "metadata": self.metadata,
            "applied_strategies": self.applied_strategies,
        }


# Global context storage (thread-safe for mitmproxy)
_contexts: Dict[str, RequestContext] = {}


def get_context(flow: http.HTTPFlow) -> RequestContext:
    """
    Get or create context for a flow.
    
    Args:
        flow: The HTTP flow object.
        
    Returns:
        RequestContext instance.
    """
    flow_id = id(flow)
    if flow_id not in _contexts:
        _contexts[flow_id] = RequestContext(flow)
    return _contexts[flow_id]


def clear_context(flow: http.HTTPFlow) -> None:
    """
    Clear context for a flow after processing.
    
    Args:
        flow: The HTTP flow object.
    """
    flow_id = id(flow)
    if flow_id in _contexts:
        del _contexts[flow_id]

