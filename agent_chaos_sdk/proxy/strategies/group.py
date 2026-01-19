"""
Group-Based Chaos Strategies.

This module provides chaos strategies that target groups of agents based on
their role, rather than individual agents. This enables scalable attacks that
affect entire organizational functions (e.g., all QA Engineers, all Developers).

Key Feature: One rule can affect multiple agents instantly.
"""

from typing import Optional, Dict, Any
from mitmproxy import http
import logging
import asyncio

from agent_chaos_sdk.proxy.strategies.base import BaseStrategy
from agent_chaos_sdk.proxy.strategies.network import LatencyStrategy, ErrorStrategy

logger = logging.getLogger(__name__)


class GroupChaosStrategy(BaseStrategy):
    """
    Group-based chaos strategy that targets agents by role.
    
    This strategy applies chaos to all agents with a specific role,
    enabling scalable attacks on organizational functions.
    
    Example:
        - target_role="PythonDeveloper", action="latency", delay=5.0
        - This affects ALL PythonDevelopers instantly (4 agents in software_house.yaml)
    
    Supported actions:
    - "latency": Add delay
    - "error": Return HTTP error
    - "disable": Block requests (return 503)
    """
    
    def __init__(
        self,
        name: str = "group_chaos",
        enabled: bool = True,
        target_role: str = "",
        action: str = "latency",
        **kwargs
    ):
        """
        Initialize the group chaos strategy.
        
        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
            target_role: Target agent role (e.g., "PythonDeveloper", "QAEngineer").
            action: Action to apply ("latency", "error", "disable").
            **kwargs: Additional parameters (delay, error_code, etc.).
        """
        super().__init__(name, enabled)
        self.target_role = kwargs.get('target_role', target_role)
        self.action = kwargs.get('action', action)
        
        if not self.target_role:
            raise ValueError("target_role is required for GroupChaosStrategy")
        
        # Action-specific parameters
        self.delay = kwargs.get('delay', 1.0)  # For latency action
        self.error_code = kwargs.get('error_code', 500)  # For error action
        
        valid_actions = ["latency", "error", "disable"]
        if self.action not in valid_actions:
            raise ValueError(
                f"action must be one of {valid_actions}, got {self.action}"
            )
        
        logger.info(
            f"GroupChaosStrategy initialized: target_role={self.target_role}, "
            f"action={self.action}"
        )
    
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Apply group-based chaos to the flow.
        
        Checks the X-Agent-Role header to determine if this request
        should be affected by the group strategy.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if chaos was applied, False otherwise.
        """
        if not self.enabled:
            return False
        
        # Extract agent role from headers
        agent_role = self._extract_agent_role(flow)
        
        if not agent_role:
            # No role header, skip
            return False
        
        # Check if this agent's role matches target
        if agent_role != self.target_role:
            return False
        
        # Apply the action
        redacted_url = self._redact_url(flow.request.pretty_url)
        logger.info(
            f"Group chaos applied: role={agent_role}, action={self.action}, "
            f"target={redacted_url}"
        )
        
        if self.action == "latency":
            return await self._apply_latency(flow)
        elif self.action == "error":
            return await self._apply_error(flow)
        elif self.action == "disable":
            return await self._apply_disable(flow)
        
        return False
    
    def _extract_agent_role(self, flow: http.HTTPFlow) -> Optional[str]:
        """
        Extract agent role from request headers or flow metadata.
        
        The SwarmFactory should inject X-Agent-Role header for each agent.
        The proxy's request hook also extracts and stores it in flow.metadata.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            Agent role string, or None if not found.
        """
        # First check flow metadata (set by proxy's request hook)
        role = flow.metadata.get("agent_role")
        if role:
            return role
        
        # Check for X-Agent-Role header (direct injection)
        role = flow.request.headers.get("X-Agent-Role")
        if role:
            return role
        
        # Fallback: Check for other possible header names
        role = flow.request.headers.get("Agent-Role")
        if role:
            return role
        
        # Try to extract from User-Agent or other headers
        user_agent = flow.request.headers.get("User-Agent", "")
        if "role=" in user_agent.lower():
            # Extract role from User-Agent if present
            parts = user_agent.split("role=")
            if len(parts) > 1:
                role = parts[1].split()[0] if parts[1] else None
                return role
        
        return None
    
    async def _apply_latency(self, flow: http.HTTPFlow) -> bool:
        """Apply latency to the request."""
        logger.debug(f"Applying latency: {self.delay}s to role {self.target_role}")
        await asyncio.sleep(self.delay)  # Non-blocking async sleep
        return True
    
    async def _apply_error(self, flow: http.HTTPFlow) -> bool:
        """Apply HTTP error to the request."""
        if not flow.response:
            # Create error response
            flow.response = http.Response.make(
                self.error_code,
                b"Chaos Injection: Group-based error",
                {"Content-Type": "text/plain"}
            )
        else:
            # Modify existing response
            flow.response.status_code = self.error_code
            flow.response.text = "Chaos Injection: Group-based error"
        
        logger.debug(
            f"Applied error {self.error_code} to role {self.target_role}"
        )
        return True
    
    async def _apply_disable(self, flow: http.HTTPFlow) -> bool:
        """Disable the request (simulate service unavailable)."""
        flow.response = http.Response.make(
            503,
            b"Service Unavailable: Group disabled by chaos strategy",
            {"Content-Type": "text/plain", "Retry-After": "60"}
        )
        
        logger.debug(f"Disabled request for role {self.target_role}")
        return True


class GroupFailureStrategy(BaseStrategy):
    """
    Group failure strategy - simulates entire organizational function going down.
    
    This is a specialized version of GroupChaosStrategy that specifically
    simulates a group failure (e.g., "Testing Dept is down").
    
    Example:
        target_role="QAEngineer" → All QA engineers are disabled
    """
    
    def __init__(
        self,
        name: str = "group_failure",
        enabled: bool = True,
        target_role: str = "",
        **kwargs
    ):
        """
        Initialize the group failure strategy.
        
        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
            target_role: Target agent role to disable.
            **kwargs: Additional parameters.
        """
        super().__init__(name, enabled)
        self.target_role = kwargs.get('target_role', target_role)
        
        if not self.target_role:
            raise ValueError("target_role is required for GroupFailureStrategy")
        
        logger.info(
            f"GroupFailureStrategy initialized: target_role={self.target_role} "
            f"(simulating {self.target_role} group failure)"
        )
    
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Apply group failure - disable all agents with target role.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if failure was applied, False otherwise.
        """
        if not self.enabled:
            return False
        
        # Extract agent role
        agent_role = self._extract_agent_role(flow)
        
        if not agent_role or agent_role != self.target_role:
            return False
        
        # Apply failure (503 Service Unavailable)
        flow.response = http.Response.make(
            503,
            b"Service Unavailable: Group failure - " + self.target_role.encode(),
            {
                "Content-Type": "text/plain",
                "Retry-After": "300",  # Suggest retry after 5 minutes
                "X-Chaos-Reason": f"Group failure: {self.target_role}"
            }
        )
        
        redacted_url = self._redact_url(flow.request.pretty_url)
        logger.warning(
            f"Group failure applied: {self.target_role} is disabled "
            f"(request to {redacted_url})"
        )
        
        return True
    
    def _extract_agent_role(self, flow: http.HTTPFlow) -> Optional[str]:
        """Extract agent role from request headers."""
        role = flow.request.headers.get("X-Agent-Role")
        if role:
            return role
        
        role = flow.request.headers.get("Agent-Role")
        if role:
            return role
        
        return None

