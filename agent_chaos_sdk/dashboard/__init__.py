"""Dashboard module for real-time visualization."""

from agent_chaos_sdk.dashboard.server import DashboardServer, get_dashboard_server
from agent_chaos_sdk.dashboard.events import (
    DashboardEvent,
    RequestStartedEvent,
    ChaosInjectedEvent,
    ResponseReceivedEvent,
    SwarmMessageEvent,
)

__all__ = [
    "DashboardServer",
    "get_dashboard_server",
    "DashboardEvent",
    "RequestStartedEvent",
    "ChaosInjectedEvent",
    "ResponseReceivedEvent",
    "SwarmMessageEvent",
]

