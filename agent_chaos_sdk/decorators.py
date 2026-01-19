"""
Chaos Decorators for Function-Level Fault Injection

This module provides decorators to inject chaos into internal function calls,
useful for testing agent-to-agent communication in frameworks like AutoGen.
"""

import functools
import random
import time
import logging
from typing import Callable, Any, Optional, Dict
from opentelemetry import trace

from agent_chaos_sdk.common.telemetry import get_tracer, record_chaos_injection
from agent_chaos_sdk.common.logger import get_logger

logger = get_logger(__name__)
tracer = get_tracer()


def simulate_chaos(
    strategy: str = "latency",
    probability: float = 0.5,
    **strategy_params: Any
) -> Callable:
    """
    Decorator to inject chaos into function calls.
    
    This allows users to inject faults into internal function calls
    (e.g., local Agent-to-Agent communication in AutoGen), not just HTTP requests.
    
    Supported strategies:
    - "latency": Add delay before function execution
      - params: delay (float, seconds, default=1.0)
    - "exception": Raise an exception
      - params: exception_type (Exception class, default=RuntimeError), message (str)
    - "return_error": Return an error value instead of executing
      - params: error_value (Any, default=None)
    - "skip": Skip function execution entirely
      - params: return_value (Any, default=None)
    
    Args:
        strategy: Type of chaos to inject ("latency", "exception", "return_error", "skip")
        probability: Probability (0.0-1.0) of applying the chaos
        **strategy_params: Strategy-specific parameters
    
    Returns:
        Decorated function with chaos injection
    
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

