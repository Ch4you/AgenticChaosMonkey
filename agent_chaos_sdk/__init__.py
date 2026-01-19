"""
Agent Chaos SDK - Universal Chaos Engineering for AI Agents

This SDK provides chaos engineering capabilities for AI agents, supporting both
HTTP-level interception (via mitmproxy) and function-level decorators for
internal agent communication.
"""

import importlib
from typing import TYPE_CHECKING

__version__ = "0.1.0"

if TYPE_CHECKING:
    from agent_chaos_sdk.decorators import simulate_chaos
    from agent_chaos_sdk.proxy.addon import ChaosProxyAddon
    from agent_chaos_sdk.swarm_runner import SwarmFactory, build_swarm_from_yaml
    from agent_chaos_sdk.config_loader import (
        load_chaos_plan,
        set_global_plan,
        get_global_plan,
        load_and_set_global_plan,
        ChaosPlan,
        TargetConfig,
        StrategyConfig,
    )
    from agent_chaos_sdk.storage.tape import (
        TapeRecorder,
        TapePlayer,
        Tape,
        TapeEntry,
        RequestFingerprint,
        ResponseSnapshot,
        ChaosContext,
    )

_LAZY_IMPORTS = {
    "simulate_chaos": ("agent_chaos_sdk.decorators", "simulate_chaos"),
    "ChaosProxyAddon": ("agent_chaos_sdk.proxy.addon", "ChaosProxyAddon"),
    "SwarmFactory": ("agent_chaos_sdk.swarm_runner", "SwarmFactory"),
    "build_swarm_from_yaml": ("agent_chaos_sdk.swarm_runner", "build_swarm_from_yaml"),
    "load_chaos_plan": ("agent_chaos_sdk.config_loader", "load_chaos_plan"),
    "set_global_plan": ("agent_chaos_sdk.config_loader", "set_global_plan"),
    "get_global_plan": ("agent_chaos_sdk.config_loader", "get_global_plan"),
    "load_and_set_global_plan": ("agent_chaos_sdk.config_loader", "load_and_set_global_plan"),
    "ChaosPlan": ("agent_chaos_sdk.config_loader", "ChaosPlan"),
    "TargetConfig": ("agent_chaos_sdk.config_loader", "TargetConfig"),
    "StrategyConfig": ("agent_chaos_sdk.config_loader", "StrategyConfig"),
    "TapeRecorder": ("agent_chaos_sdk.storage.tape", "TapeRecorder"),
    "TapePlayer": ("agent_chaos_sdk.storage.tape", "TapePlayer"),
    "Tape": ("agent_chaos_sdk.storage.tape", "Tape"),
    "TapeEntry": ("agent_chaos_sdk.storage.tape", "TapeEntry"),
    "RequestFingerprint": ("agent_chaos_sdk.storage.tape", "RequestFingerprint"),
    "ResponseSnapshot": ("agent_chaos_sdk.storage.tape", "ResponseSnapshot"),
    "ChaosContext": ("agent_chaos_sdk.storage.tape", "ChaosContext"),
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
    "simulate_chaos",
    "ChaosProxyAddon",
    "SwarmFactory",
    "build_swarm_from_yaml",
    "load_chaos_plan",
    "set_global_plan",
    "get_global_plan",
    "load_and_set_global_plan",
    "ChaosPlan",
    "TargetConfig",
    "StrategyConfig",
    "TapeRecorder",
    "TapePlayer",
    "Tape",
    "TapeEntry",
    "RequestFingerprint",
    "ResponseSnapshot",
    "ChaosContext",
    "__version__",
]

