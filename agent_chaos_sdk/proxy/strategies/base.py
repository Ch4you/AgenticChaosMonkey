"""
Base Strategy Pattern for Chaos Attacks.

This module defines the abstract base class for all chaos attack strategies,
following the Strategy Pattern to enable extensibility and modularity.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Pattern
from mitmproxy import http
import logging
import re
import time

from agent_chaos_sdk.config_loader import TargetConfig, get_global_plan
from agent_chaos_sdk.common.resilience import CircuitBreaker, CircuitState
from agent_chaos_sdk.common.security import get_redactor
from agent_chaos_sdk.common.errors import ErrorCode
from agent_chaos_sdk.common.telemetry import record_error_code

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """
    Abstract base class for chaos attack strategies.
    
    This class follows the Strategy Pattern, allowing new attack types to be
    easily added by implementing the intercept() method. Strategies can be
    applied to requests, responses, or both phases of the HTTP flow.
    
    Subclasses must implement:
    - `_intercept_impl()`: Apply the chaos attack to the HTTP flow
    
    The base class provides:
    - `should_trigger()`: Check if the flow matches configured targets
    - Target matching based on ChaosPlan configuration
    """
    
    def __init__(
        self,
        name: str,
        enabled: bool = True,
        target_ref: Optional[str] = None,
        url_pattern: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize the chaos strategy.
        
        Args:
            name: Unique name identifier for this strategy.
            enabled: Whether this strategy is currently enabled.
            target_ref: Reference to a target name from ChaosPlan (optional).
            url_pattern: Direct URL pattern regex (for backward compatibility).
            **kwargs: Additional parameters (for dynamic config loading).
        """
        self.name = name
        self.enabled = enabled
        self.target_ref = target_ref or kwargs.get('target_ref')
        self.url_pattern = url_pattern or kwargs.get('url_pattern')
        
        # Compile URL patterns for performance
        self._compiled_patterns: List[Pattern] = []
        self._update_patterns()
        
        # Circuit breaker for fail-open behavior
        # If strategy fails >5 times, bypass it for 60s to prevent cascading failures
        self._circuit_breaker = CircuitBreaker(
            fail_max=5,
            reset_timeout=60.0,
            name=f"Strategy-{name}"
        )
        
        logger.debug(f"Initialized strategy: {name} (enabled={enabled}, target_ref={target_ref})")
    
    def _update_patterns(self) -> None:
        """Update compiled regex patterns from targets or direct pattern."""
        self._compiled_patterns = []
        
        # If target_ref is set, get patterns from ChaosPlan
        if self.target_ref:
            plan = get_global_plan()
            if plan:
                target = plan.get_target(self.target_ref)
                if target and target.type == "http_endpoint":
                    try:
                        pattern = re.compile(target.pattern)
                        self._compiled_patterns.append(pattern)
                        logger.debug(f"Added pattern from target '{self.target_ref}': {target.pattern}")
                    except re.error as e:
                        logger.warning(f"Invalid regex pattern from target '{self.target_ref}': {e}")
        
        # Also check direct url_pattern (for backward compatibility)
        if self.url_pattern:
            try:
                pattern = re.compile(self.url_pattern)
                self._compiled_patterns.append(pattern)
                logger.debug(f"Added direct URL pattern: {self.url_pattern}")
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{self.url_pattern}': {e}")

    def _redact_url(self, url: str) -> str:
        return get_redactor().redact_url(url)
    
    def should_trigger(self, flow: http.HTTPFlow) -> bool:
        """
        Check if this strategy should trigger for the given flow.
        
        This method checks if the flow matches any configured targets:
        - For http_endpoint targets: matches URL pattern
        - For agent_role targets: matches X-Agent-Role header
        - For tool_call targets: matches endpoint pattern
        
        Args:
            flow: The HTTP flow to check.
            
        Returns:
            True if the strategy should trigger, False otherwise.
        """
        if not self.enabled:
            return False
        
        # If no patterns configured, trigger on all flows (backward compatibility)
        if not self._compiled_patterns:
            return True
        
        # Check URL patterns
        url = flow.request.pretty_url
        for pattern in self._compiled_patterns:
            if pattern.search(url):
                logger.debug(
                    f"Strategy '{self.name}' triggered by URL pattern: {self._redact_url(url)}"
                )
                return True
        
        # Check agent role (if target is agent_role type)
        if self.target_ref:
            plan = get_global_plan()
            if plan:
                target = plan.get_target(self.target_ref)
                if target and target.type == "agent_role":
                    agent_role = flow.request.headers.get("X-Agent-Role") or flow.request.headers.get("Agent-Role")
                    if agent_role:
                        try:
                            role_pattern = re.compile(target.pattern)
                            if role_pattern.search(agent_role):
                                logger.debug(f"Strategy '{self.name}' triggered by agent role: {agent_role}")
                                return True
                        except re.error:
                            pass
        
        return False
    
    async def intercept(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Intercept and potentially modify the HTTP flow.
        
        This method wraps the subclass implementation with circuit breaker protection
        to ensure fail-open behavior. If the strategy fails repeatedly, it
        will be bypassed automatically.
        
        This method is called for both request and response phases.
        The strategy should check the flow state and apply attacks as needed.
        
        This is an async method to support non-blocking operations. Use
        `await asyncio.sleep()` instead of `time.sleep()` for delays.
        
        Args:
            flow: The HTTP flow object from mitmproxy.
            
        Returns:
            True if the strategy was applied, False if skipped, None if not applicable.
        """
        # Check if circuit breaker is open (fail-open behavior)
        current_state = self._circuit_breaker.state
        if current_state == CircuitState.OPEN:
            # Check if reset timeout has elapsed (transition to half-open)
            if self._circuit_breaker._last_failure_time is not None:
                elapsed = time.time() - self._circuit_breaker._last_failure_time
                if elapsed >= self._circuit_breaker.reset_timeout:
                    # Transition to half-open (testing recovery)
                    with self._circuit_breaker._lock:
                        self._circuit_breaker._state = CircuitState.HALF_OPEN
                        self._circuit_breaker._failure_count = 0
                        logger.info(
                            f"Strategy '{self.name}': Circuit breaker transitioning to HALF_OPEN "
                            f"(testing recovery)"
                        )
                else:
                    # Still in timeout period, circuit remains open - bypass strategy
                    logger.debug(
                        f"Strategy '{self.name}': Circuit breaker is OPEN, bypassing strategy "
                        f"(fail-open behavior, {self._circuit_breaker.reset_timeout - elapsed:.1f}s remaining)"
                    )
                    return False  # Indicate strategy was skipped
            else:
                # Circuit is open but no timestamp - bypass strategy
                return False
        
        # Circuit is closed or half-open - attempt the call
        try:
            # Call the actual implementation (subclasses override this, but we make it non-abstract)
            # For backward compatibility, we check if _intercept_impl exists, otherwise use old pattern
            if hasattr(self, '_intercept_impl'):
                result = await self._intercept_impl(flow)
            else:
                # Fallback: call a method that subclasses should implement
                # This is a workaround for backward compatibility
                raise NotImplementedError(
                    f"Strategy {self.__class__.__name__} must implement intercept logic. "
                    f"Override _intercept_impl() method."
                )
            
            # Success - reset failure count and close circuit if needed
            with self._circuit_breaker._lock:
                if self._circuit_breaker._state == CircuitState.HALF_OPEN:
                    # Success in half-open state - circuit recovered!
                    self._circuit_breaker._state = CircuitState.CLOSED
                    self._circuit_breaker._failure_count = 0
                    logger.info(
                        f"Strategy '{self.name}': Circuit breaker recovered! Transitioning to CLOSED"
                    )
                elif self._circuit_breaker._state == CircuitState.CLOSED:
                    # Reset failure count on success
                    self._circuit_breaker._failure_count = 0

            if result:
                try:
                    metadata = getattr(flow, "metadata", None)
                    if isinstance(metadata, dict):
                        applied = metadata.get("chaos_applied")
                        if not isinstance(applied, list):
                            applied = []
                        if self.name not in applied:
                            applied.append(self.name)
                        metadata["chaos_applied"] = applied
                except Exception:
                    # Avoid breaking on mock flows without dict-like metadata
                    pass

            return result
            
        except Exception as e:
            # Failure - increment counter and potentially open circuit
            with self._circuit_breaker._lock:
                self._circuit_breaker._failure_count += 1
                self._circuit_breaker._last_failure_time = time.time()
                
                if self._circuit_breaker._failure_count >= self._circuit_breaker.fail_max:
                    if self._circuit_breaker._state != CircuitState.OPEN:
                        # Open the circuit
                        self._circuit_breaker._state = CircuitState.OPEN
                        logger.warning(
                            f"[{ErrorCode.STRATEGY_DISABLED}] Strategy Disabled: '{self.name}' "
                            f"(opened after {self._circuit_breaker.fail_max} failures, "
                            f"bypassing for {self._circuit_breaker.reset_timeout}s)"
                        )
                        record_error_code(ErrorCode.STRATEGY_DISABLED, strategy=self.name)
            
            # Re-raise the exception so it can be handled by caller
            # But the circuit breaker will prevent future calls for reset_timeout seconds
            raise
    
    @abstractmethod
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Internal implementation of intercept logic.
        
        Subclasses must implement this method. The intercept() method
        wraps this with circuit breaker protection for fail-open behavior.
        
        Args:
            flow: The HTTP flow object from mitmproxy.
            
        Returns:
            True if the strategy was applied, False if skipped, None if not applicable.
        """
        pass
    
    def __repr__(self) -> str:
        """String representation of the strategy."""
        return f"{self.__class__.__name__}(name={self.name}, enabled={self.enabled}, target_ref={self.target_ref})"
