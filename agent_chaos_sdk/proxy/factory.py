"""
Strategy factory with entry point discovery.

This module discovers strategy plugins via the "agent_chaos.strategies"
entry point group, enabling third-party strategy packages.
"""

from importlib.metadata import entry_points
from typing import Dict, Type, Optional, List

from agent_chaos_sdk.common.config import StrategyConfig
from agent_chaos_sdk.common.logger import get_logger
from agent_chaos_sdk.proxy.strategies.base import BaseStrategy

logger = get_logger(__name__)


class StrategyFactory:
    """
    Factory for creating strategy instances from configuration.

    Uses entry points (group: "agent_chaos.strategies") to discover
    available strategies at runtime.
    """

    _strategy_classes: Dict[str, Type[BaseStrategy]] = {}
    _loaded: bool = False

    @classmethod
    def _load_entry_points(cls) -> None:
        if cls._loaded:
            return

        try:
            eps = entry_points()
            if hasattr(eps, "select"):
                strategy_eps = eps.select(group="agent_chaos.strategies")
            else:
                strategy_eps = eps.get("agent_chaos.strategies", [])

            for ep in strategy_eps:
                try:
                    strategy_class = ep.load()
                    if not isinstance(strategy_class, type) or not issubclass(strategy_class, BaseStrategy):
                        logger.warning(
                            f"Strategy entry point '{ep.name}' ignored: not a BaseStrategy subclass"
                        )
                        continue
                    cls._strategy_classes[ep.name] = strategy_class
                    logger.debug(f"Loaded strategy entry point: {ep.name} -> {strategy_class.__name__}")
                except Exception as e:
                    logger.warning(f"Failed to load strategy entry point '{ep.name}': {e}")
            # Ensure built-in strategies are available for non-installed/dev runs
            cls._register_builtin_strategies()
            cls._loaded = True
        except Exception as e:
            logger.error(f"Failed to load strategy entry points: {e}", exc_info=True)
            cls._register_builtin_strategies()
            cls._loaded = True  # Prevent repeated failures

    @classmethod
    def _register_builtin_strategies(cls) -> None:
        """
        Register built-in strategies if not already present.

        This provides a fallback when entry points are not available,
        such as running from source without installation.
        """
        try:
            from agent_chaos_sdk.proxy.strategies.network import LatencyStrategy, ErrorStrategy
            from agent_chaos_sdk.proxy.strategies.data import JSONCorruptionStrategy
            from agent_chaos_sdk.proxy.strategies.semantic import SemanticStrategy
            from agent_chaos_sdk.proxy.strategies.mcp import MCPProtocolFuzzingStrategy
            from agent_chaos_sdk.proxy.strategies.group import GroupChaosStrategy, GroupFailureStrategy
            from agent_chaos_sdk.proxy.strategies.simple_log import SimpleLogStrategy
            from agent_chaos_sdk.proxy.strategies.cognitive import HallucinationStrategy, ContextOverflowStrategy
            from agent_chaos_sdk.proxy.strategies.rag import PhantomDocumentStrategy
            from agent_chaos_sdk.proxy.strategies.swarm import SwarmDisruptionStrategy
        except Exception as e:
            logger.warning(f"Failed to import built-in strategies: {e}")
            return

        defaults = {
            "latency": LatencyStrategy,
            "error": ErrorStrategy,
            "data_corruption": JSONCorruptionStrategy,
            "semantic": SemanticStrategy,
            "mcp_fuzzing": MCPProtocolFuzzingStrategy,
            "group_chaos": GroupChaosStrategy,
            "group_failure": GroupFailureStrategy,
            "simple_log": SimpleLogStrategy,
            "hallucination": HallucinationStrategy,
            "context_overflow": ContextOverflowStrategy,
            "phantom_document": PhantomDocumentStrategy,
            "rag_poisoning": PhantomDocumentStrategy,
            "swarm_disruption": SwarmDisruptionStrategy,
        }

        for key, value in defaults.items():
            cls._strategy_classes.setdefault(key, value)

    @classmethod
    def register(cls, strategy_type: str, strategy_class: Type[BaseStrategy]) -> None:
        """
        Register a new strategy type.

        Args:
            strategy_type: Type identifier string.
            strategy_class: Strategy class to register.
        """
        cls._strategy_classes[strategy_type] = strategy_class
        logger.debug(f"Registered strategy type: {strategy_type} -> {strategy_class.__name__}")

    @classmethod
    def create(cls, config: StrategyConfig) -> Optional[BaseStrategy]:
        """
        Create a strategy instance from configuration.

        Args:
            config: StrategyConfig instance.

        Returns:
            BaseStrategy instance, or None if type is unknown.
        """
        cls._load_entry_points()
        strategy_class = cls._strategy_classes.get(config.type)
        if strategy_class is None:
            logger.error(f"Unknown strategy type: {config.type}")
            return None

        try:
            # Prepare kwargs for strategy initialization
            strategy_kwargs = config.params.copy()

            # Add target_ref if available (for new ChaosPlan format)
            if hasattr(config, "target_ref") and config.target_ref:
                strategy_kwargs["target_ref"] = config.target_ref
            # Pass probability from config (not stored in params)
            if hasattr(config, "probability"):
                strategy_kwargs["probability"] = config.probability

            # Create strategy instance
            strategy = strategy_class(
                name=config.name,
                enabled=config.enabled,
                **strategy_kwargs
            )
            logger.debug(f"Created strategy: {strategy}")
            return strategy
        except Exception as e:
            logger.error(f"Failed to create strategy {config.name} ({config.type}): {e}", exc_info=True)
            return None

    @classmethod
    def get_available_types(cls) -> List[str]:
        """
        Get list of available strategy types.

        Returns:
            List of registered strategy type identifiers.
        """
        cls._load_entry_points()
        return list(cls._strategy_classes.keys())
