"""
Network Layer Attack Strategies.

This module contains strategies that target the network layer:
- Latency/delay injection
- HTTP error injection (500, 503, 429)
"""

from typing import Optional
import random
from mitmproxy import http
import logging
import asyncio
import json

from agent_chaos_sdk.proxy.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class LatencyStrategy(BaseStrategy):
    """
    Strategy that injects latency/delays into HTTP flows.
    
    This attack simulates network latency or slow server responses.
    """
    
    def __init__(
        self,
        name: str = "latency",
        enabled: bool = True,
        delay: float = 5.0,
        **kwargs
    ):
        """
        Initialize the latency strategy.
        
        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
            delay: Delay in seconds to inject.
            **kwargs: Additional parameters (for dynamic config loading).
        """
        super().__init__(name, enabled, **kwargs)
        # Support both 'delay' from kwargs and direct parameter
        self.delay = kwargs.get('delay', delay)
        self.probability = kwargs.get('probability', 1.0)
        logger.info(f"LatencyStrategy initialized: delay={self.delay}s, probability={self.probability}")
    
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Apply latency delay to the flow.
        
        This method uses async sleep to avoid blocking the event loop,
        allowing the proxy to handle multiple concurrent requests.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if delay was applied, False otherwise.
        """
        if not self.enabled:
            return False

        if not self.should_trigger(flow):
            return False

        if random.random() >= self.probability:
            return False
        
        # Apply delay during request phase (before response is available)
        if not flow.response:
            redacted_url = self._redact_url(flow.request.pretty_url)
            logger.info(f"Injecting latency of {self.delay}s for {redacted_url}")
            await asyncio.sleep(self.delay)  # Non-blocking async sleep
            return True
        
        return False


class ErrorStrategy(BaseStrategy):
    """
    Strategy that injects HTTP error responses.
    
    This attack simulates server failures, rate limiting, and service unavailability.
    """
    
    def __init__(
        self,
        name: str = "error",
        enabled: bool = True,
        error_code: int = 500,
        **kwargs
    ):
        """
        Initialize the error strategy.
        
        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
            error_code: HTTP error code to inject (default: 500).
            **kwargs: Additional parameters (for dynamic config loading).
        """
        super().__init__(name, enabled, **kwargs)
        # Support both 'error_code' from kwargs and direct parameter
        self.error_code = kwargs.get('error_code', error_code)
        self.probability = kwargs.get('probability', 1.0)
        logger.info(f"ErrorStrategy initialized: error_code={self.error_code}, probability={self.probability}")
    
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Inject an HTTP error into the response.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if error was injected, False otherwise.
        """
        if not self.enabled:
            return False

        if not self.should_trigger(flow):
            return False

        if random.random() >= self.probability:
            return False
        
        # Only inject errors in response phase
        if not flow.response:
            return False
        
        redacted_url = self._redact_url(flow.request.pretty_url)
        logger.info(f"Injecting error {self.error_code} for {redacted_url}")
        
        # Modify response to return error
        flow.response.status_code = self.error_code
        
        # Get appropriate error reason
        error_reasons = {
            500: "Internal Server Error",
            503: "Service Unavailable",
            429: "Too Many Requests",
            502: "Bad Gateway",
            504: "Gateway Timeout",
        }
        flow.response.reason = error_reasons.get(self.error_code, "Chaos Injection")
        
        # Set error body
        error_body = {
            "error": "Chaos injection: Simulated server error",
            "code": self.error_code,
            "type": "chaos_engineering",
        }
        flow.response.text = json.dumps(error_body)
        flow.response.headers["Content-Type"] = "application/json"
        
        return True
