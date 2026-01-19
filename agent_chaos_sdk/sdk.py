"""
Public SDK surface for third-party strategy authors.

Exposes BaseStrategy and common type hints to avoid importing deep internals.
"""

from typing import Optional, Dict, Any

from mitmproxy import http

from agent_chaos_sdk.proxy.strategies.base import BaseStrategy
from agent_chaos_sdk.common.config import StrategyConfig, ChaosConfig

__all__ = [
    "BaseStrategy",
    "StrategyConfig",
    "ChaosConfig",
    "http",
    "Optional",
    "Dict",
    "Any",
]
