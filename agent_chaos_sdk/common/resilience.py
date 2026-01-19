"""
Resilience utilities for fail-open behavior.

This module provides Circuit Breaker pattern implementation to ensure that
if chaos strategies fail, they don't break the user's agent traffic.
"""

import time
import logging
from enum import Enum
from typing import Optional, Callable, Any
from threading import Lock

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Circuit is open, bypassing calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker implementation for fail-open behavior.
    
    Prevents cascading failures by opening the circuit after a threshold
    of failures, then automatically attempting to recover after a timeout.
    
    Example:
        breaker = CircuitBreaker(fail_max=5, reset_timeout=60)
        
        try:
            result = breaker.call(some_function, arg1, arg2)
        except CircuitBreakerOpenError:
            # Circuit is open, skip this operation
            pass
    """
    
    def __init__(
        self,
        fail_max: int = 5,
        reset_timeout: float = 60.0,
        name: Optional[str] = None
    ):
        """
        Initialize the circuit breaker.
        
        Args:
            fail_max: Maximum number of consecutive failures before opening circuit.
            reset_timeout: Time in seconds before attempting to close circuit (half-open state).
            name: Optional name for logging/debugging.
        """
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.name = name or "CircuitBreaker"
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = Lock()
        
        logger.debug(
            f"CircuitBreaker '{self.name}' initialized: "
            f"fail_max={fail_max}, reset_timeout={reset_timeout}s"
        )
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function call through the circuit breaker.
        
        If the circuit is open, raises CircuitBreakerOpenError.
        If the circuit is half-open, allows one call to test recovery.
        
        Args:
            func: Function to call.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.
            
        Returns:
            Return value from func.
            
        Raises:
            CircuitBreakerOpenError: If circuit is open.
        """
        with self._lock:
            # Check if we should attempt recovery (half-open state)
            if self._state == CircuitState.OPEN:
                if self._last_failure_time is not None:
                    elapsed = time.time() - self._last_failure_time
                    if elapsed >= self.reset_timeout:
                        # Transition to half-open (testing recovery)
                        self._state = CircuitState.HALF_OPEN
                        self._failure_count = 0
                        logger.info(
                            f"CircuitBreaker '{self.name}': Transitioning to HALF_OPEN "
                            f"(elapsed: {elapsed:.1f}s)"
                        )
                    else:
                        # Still in timeout period, circuit remains open
                        raise CircuitBreakerOpenError(
                            f"CircuitBreaker '{self.name}' is OPEN. "
                            f"Will retry in {self.reset_timeout - elapsed:.1f}s"
                        )
                else:
                    # Shouldn't happen, but handle gracefully
                    raise CircuitBreakerOpenError(f"CircuitBreaker '{self.name}' is OPEN")
        
        # Attempt the call
        try:
            result = func(*args, **kwargs)
            # Success - reset failure count and close circuit if needed
            with self._lock:
                if self._state == CircuitState.HALF_OPEN:
                    # Success in half-open state - circuit recovered!
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info(f"CircuitBreaker '{self.name}': Recovered! Transitioning to CLOSED")
                elif self._state == CircuitState.CLOSED:
                    # Reset failure count on success
                    self._failure_count = 0
            
            return result
            
        except Exception as e:
            # Failure - increment counter and potentially open circuit
            with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()
                
                if self._failure_count >= self.fail_max:
                    if self._state != CircuitState.OPEN:
                        # Open the circuit
                        self._state = CircuitState.OPEN
                        logger.warning(
                            f"CircuitBreaker '{self.name}': OPENING circuit after {self.fail_max} failures. "
                            f"Will attempt recovery in {self.reset_timeout}s"
                        )
                
            # Re-raise the original exception
            raise
    
    def reset(self) -> None:
        """
        Manually reset the circuit breaker to CLOSED state.
        
        Useful for testing or manual recovery.
        """
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            logger.info(f"CircuitBreaker '{self.name}': Manually reset to CLOSED")
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state (thread-safe read)."""
        with self._lock:
            return self._state
    
    @property
    def failure_count(self) -> int:
        """Get current failure count (thread-safe read)."""
        with self._lock:
            return self._failure_count
    
    def __repr__(self) -> str:
        """String representation."""
        return (
            f"CircuitBreaker(name={self.name}, state={self.state.value}, "
            f"failures={self.failure_count}/{self.fail_max})"
        )


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass

