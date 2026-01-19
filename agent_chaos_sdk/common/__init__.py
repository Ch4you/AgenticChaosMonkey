"""
Common utilities for the Agent Chaos SDK.
"""

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_chaos_sdk.common.config import load_config, ChaosConfig, StrategyConfig
    from agent_chaos_sdk.common.telemetry import setup_telemetry, get_tracer, record_chaos_injection
    from agent_chaos_sdk.common.logger import get_logger
    from agent_chaos_sdk.common.security import PIIRedactor, ChaosAuth, get_redactor, get_auth
    from agent_chaos_sdk.common.resilience import (
        CircuitBreaker,
        CircuitBreakerOpenError,
        CircuitState,
    )

_LAZY_IMPORTS = {
    "load_config": ("agent_chaos_sdk.common.config", "load_config"),
    "ChaosConfig": ("agent_chaos_sdk.common.config", "ChaosConfig"),
    "StrategyConfig": ("agent_chaos_sdk.common.config", "StrategyConfig"),
    "setup_telemetry": ("agent_chaos_sdk.common.telemetry", "setup_telemetry"),
    "get_tracer": ("agent_chaos_sdk.common.telemetry", "get_tracer"),
    "record_chaos_injection": ("agent_chaos_sdk.common.telemetry", "record_chaos_injection"),
    "get_logger": ("agent_chaos_sdk.common.logger", "get_logger"),
    "PIIRedactor": ("agent_chaos_sdk.common.security", "PIIRedactor"),
    "ChaosAuth": ("agent_chaos_sdk.common.security", "ChaosAuth"),
    "get_redactor": ("agent_chaos_sdk.common.security", "get_redactor"),
    "get_auth": ("agent_chaos_sdk.common.security", "get_auth"),
    "CircuitBreaker": ("agent_chaos_sdk.common.resilience", "CircuitBreaker"),
    "CircuitBreakerOpenError": ("agent_chaos_sdk.common.resilience", "CircuitBreakerOpenError"),
    "CircuitState": ("agent_chaos_sdk.common.resilience", "CircuitState"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_name, attr_name = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_name)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LAZY_IMPORTS.keys()))

__all__ = [
    "load_config",
    "ChaosConfig",
    "StrategyConfig",
    "setup_telemetry",
    "get_tracer",
    "record_chaos_injection",
    "get_logger",
    "PIIRedactor",
    "ChaosAuth",
    "get_redactor",
    "get_auth",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitState",
]
