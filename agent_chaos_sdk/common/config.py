"""
Configuration Management for Chaos Engineering.

This module provides Pydantic models and YAML loading for chaos strategy configuration.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import yaml
import logging

from pydantic import BaseModel, Field, field_validator

from agent_chaos_sdk.common.logger import get_logger

logger = get_logger(__name__)


class StrategyConfig(BaseModel):
    """
    Configuration for a single chaos strategy.
    
    Attributes:
        name: Unique name identifier for the strategy.
        type: Strategy type (e.g., "latency", "error", "data_corruption").
        enabled: Whether the strategy is currently enabled.
        probability: Probability (0.0-1.0) of applying the strategy when triggered.
        params: Strategy-specific parameters (e.g., delay, error_code).
    """
    name: str = Field(..., description="Strategy name identifier")
    type: str = Field(..., description="Strategy type identifier")
    enabled: bool = Field(default=True, description="Whether strategy is enabled")
    probability: float = Field(default=1.0, ge=0.0, le=1.0, description="Application probability")
    params: Dict[str, Any] = Field(default_factory=dict, description="Strategy-specific parameters")
    
    @field_validator('probability')
    @classmethod
    def validate_probability(cls, v: float) -> float:
        """Validate probability is between 0.0 and 1.0."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("probability must be between 0.0 and 1.0")
        return v


class ChaosConfig(BaseModel):
    """
    Complete chaos engineering configuration.
    
    Attributes:
        experiment_id: Unique identifier for this experiment.
        strategies: List of strategy configurations.
    """
    experiment_id: str = Field(default="default_experiment", description="Experiment identifier")
    strategies: List[StrategyConfig] = Field(default_factory=list, description="List of strategy configurations")
    
    def get_strategy(self, name: str) -> Optional[StrategyConfig]:
        """
        Get a strategy configuration by name.
        
        Args:
            name: Strategy name.
            
        Returns:
            StrategyConfig if found, None otherwise.
        """
        for strategy in self.strategies:
            if strategy.name == name:
                return strategy
        return None
    
    def update_strategy(self, name: str, **updates) -> bool:
        """
        Update a strategy configuration.
        
        Args:
            name: Strategy name to update.
            **updates: Fields to update (e.g., enabled=True, params={"delay": 10.0}).
            
        Returns:
            True if strategy was found and updated, False otherwise.
        """
        strategy = self.get_strategy(name)
        if strategy is None:
            return False
        
        for key, value in updates.items():
            if hasattr(strategy, key):
                setattr(strategy, key, value)
            elif key == "params" and isinstance(value, dict):
                # Merge params dict
                strategy.params.update(value)
            else:
                logger.warning(f"Unknown field '{key}' for strategy '{name}'")
        
        return True


def load_config(config_path: str = "config/chaos_config.yaml") -> ChaosConfig:
    """
    Load chaos configuration from a YAML file.
    
    Args:
        config_path: Path to the YAML configuration file.
        
    Returns:
        ChaosConfig instance loaded from the file.
        
    Raises:
        FileNotFoundError: If the configuration file doesn't exist.
        yaml.YAMLError: If the YAML file is invalid.
        ValidationError: If the configuration doesn't match the Pydantic model.
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    try:
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
        
        if data is None:
            data = {}
        
        # Ensure strategies is a list
        if 'strategies' not in data:
            data['strategies'] = []
        
        config = ChaosConfig(**data)
        logger.info(f"Loaded configuration from {config_path}: {len(config.strategies)} strategies")
        return config
    
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML file {config_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to load configuration from {config_path}: {e}")
        raise


def save_config(config: ChaosConfig, config_path: str = "config/chaos_config.yaml") -> None:
    """
    Save chaos configuration to a YAML file.
    
    Args:
        config: ChaosConfig instance to save.
        config_path: Path where to save the configuration file.
        
    Raises:
        IOError: If the file cannot be written.
    """
    config_file = Path(config_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Convert Pydantic model to dict
        data = config.model_dump()
        
        with open(config_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Saved configuration to {config_path}")
    
    except Exception as e:
        logger.error(f"Failed to save configuration to {config_path}: {e}")
        raise

