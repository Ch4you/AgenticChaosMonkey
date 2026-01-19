"""
Dashboard Events for Real-Time Visualization.

This module defines event types that are pushed to connected dashboard clients
via WebSocket for real-time visualization of agent traffic and chaos injection.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class DashboardEvent(BaseModel):
    """
    Base class for all dashboard events.
    
    All events have a type and timestamp for ordering.
    """
    event_type: str = Field(..., description="Event type identifier")
    timestamp: str = Field(..., description="ISO timestamp")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump()


class RequestStartedEvent(DashboardEvent):
    """
    Event fired when a request is intercepted by the proxy.
    """
    request_id: str = Field(..., description="Unique request identifier")
    method: str = Field(..., description="HTTP method")
    url: str = Field(..., description="Request URL (redacted)")
    agent_role: Optional[str] = Field(None, description="Agent role if available")
    traffic_type: str = Field(..., description="Traffic type (TOOL_CALL, LLM_API, AGENT_TO_AGENT)")
    traffic_subtype: Optional[str] = Field(None, description="Traffic subtype")
    
    def __init__(self, **data):
        if "event_type" not in data:
            data["event_type"] = "request_started"
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().isoformat()
        super().__init__(**data)


class ChaosInjectedEvent(DashboardEvent):
    """
    Event fired when chaos is injected into a request/response.
    """
    request_id: str = Field(..., description="Request identifier")
    strategy_name: str = Field(..., description="Strategy that was applied")
    phase: str = Field(..., description="Phase (request or response)")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")
    
    def __init__(self, **data):
        if "event_type" not in data:
            data["event_type"] = "chaos_injected"
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().isoformat()
        super().__init__(**data)


class ResponseReceivedEvent(DashboardEvent):
    """
    Event fired when a response is received.
    """
    request_id: str = Field(..., description="Request identifier")
    status_code: int = Field(..., description="HTTP status code")
    success: bool = Field(..., description="Whether request was successful")
    response_size: Optional[int] = Field(None, description="Response body size in bytes")
    latency_ms: Optional[float] = Field(None, description="Request latency in milliseconds")
    
    def __init__(self, **data):
        if "event_type" not in data:
            data["event_type"] = "response_received"
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().isoformat()
        super().__init__(**data)


class SwarmMessageEvent(DashboardEvent):
    """
    Event fired for swarm/agent-to-agent communication.
    """
    request_id: str = Field(..., description="Request identifier")
    from_agent: Optional[str] = Field(None, description="Source agent")
    to_agent: Optional[str] = Field(None, description="Destination agent")
    message_type: str = Field(..., description="Message type (supervisor_to_worker, consensus_vote, etc.)")
    mutated: bool = Field(False, description="Whether message was mutated")
    
    def __init__(self, **data):
        if "event_type" not in data:
            data["event_type"] = "swarm_message"
        if "timestamp" not in data:
            data["timestamp"] = datetime.now().isoformat()
        super().__init__(**data)

