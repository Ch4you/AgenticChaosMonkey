"""
Simple Log Strategy - Basic logging for testing.

This is a minimal strategy that logs intercepted requests/responses
for testing and debugging purposes.
"""

from typing import Optional
from mitmproxy import http
import logging

from .base import BaseStrategy
from agent_chaos_sdk.common.security import get_redactor

logger = logging.getLogger(__name__)


class SimpleLogStrategy(BaseStrategy):
    """
    Simple strategy that logs intercepted HTTP flows.
    
    This strategy is useful for testing and debugging the proxy setup.
    It doesn't modify the flow, only logs information about it.
    """
    
    def __init__(self, name: str = "simple_log", enabled: bool = True):
        """
        Initialize the simple log strategy.
        
        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
        """
        super().__init__(name, enabled)
        logger.info(f"SimpleLogStrategy initialized: {name}")
    
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Log information about the intercepted flow.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if logging was performed, False otherwise.
        """
        if not self.enabled:
            return False
        
        # Log request information
        if flow.request:
            redacted_url = self._redact_url(flow.request.pretty_url)
            logger.info(
                f"Intercepted request: {flow.request.method} {redacted_url}"
            )
            redacted_headers = get_redactor().redact_headers(dict(flow.request.headers))
            logger.debug(
                f"Request headers: {redacted_headers}"
            )
        
        # Log response information
        if flow.response:
            redacted_url = self._redact_url(flow.request.pretty_url)
            logger.info(
                f"Intercepted response: {flow.response.status_code} "
                f"for {redacted_url}"
            )
            redacted_headers = get_redactor().redact_headers(dict(flow.response.headers))
            logger.debug(
                f"Response headers: {redacted_headers}"
            )
        
        return True

