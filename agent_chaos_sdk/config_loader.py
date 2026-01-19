"""
Configuration-Driven Chaos Plan Loader

This module provides a configuration-driven approach to chaos engineering,
allowing users to define complex chaos experiments in YAML files with targets
and scenarios.

Example:
    from agent_chaos_sdk.config_loader import load_chaos_plan
    
    plan = load_chaos_plan("examples/plans/payment_failure.yaml")
    # Use plan.targets and plan.scenarios to configure chaos strategies
"""

from typing import List, Dict, Any, Optional, Literal
from pathlib import Path
import yaml
import logging
import hashlib
from pydantic import BaseModel, Field, field_validator, model_validator

from agent_chaos_sdk.common.logger import get_logger

logger = get_logger(__name__)


class TargetConfig(BaseModel):
    """
    Configuration for a chaos target (what to attack).
    
    Targets define what should be affected by chaos strategies.
    Examples: HTTP endpoints, LLM inputs, specific API calls.
    
    Attributes:
        name: Unique identifier for this target.
        type: Target type (e.g., "http_endpoint", "llm_input", "tool_call").
        pattern: Pattern to match (regex for URLs, content patterns, etc.).
        description: Optional human-readable description.
    """
    name: str = Field(..., description="Unique target identifier")
    type: Literal["http_endpoint", "llm_input", "tool_call", "agent_role", "custom"] = Field(
        ..., 
        description="Type of target"
    )
    pattern: str = Field(..., description="Pattern to match (regex for URLs, content, etc.)")
    description: Optional[str] = Field(None, description="Human-readable description")
    
    @field_validator('pattern')
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """Validate pattern is not empty."""
        if not v or not v.strip():
            raise ValueError("pattern cannot be empty")
        return v.strip()


class StrategyConfig(BaseModel):
    """
    Configuration for a chaos strategy (how to attack).
    
    Strategies define what kind of chaos to inject and reference targets
    to determine when to apply the chaos.
    
    Attributes:
        name: Unique identifier for this strategy.
        type: Strategy type (e.g., "network_delay", "hallucination", "mcp_fuzzing").
        target_ref: Reference to a Target name (must exist in targets list).
        enabled: Whether this strategy is currently enabled.
        probability: Probability (0.0-1.0) of applying the strategy.
        params: Strategy-specific parameters (flexible dict).
    """
    name: str = Field(..., description="Unique strategy identifier")
    type: str = Field(..., description="Strategy type identifier")
    target_ref: str = Field(..., description="Reference to target name")
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


DEFAULT_REPLAY_IGNORE_PATHS = [
    "$.timestamp",
    "$.created_at",
    "$.date",
    "$.uuid",
    "$.trace_id",
    "$.request_id",
    "$.headers.Date",
    "$.headers.Server",
]


class ReplayConfig(BaseModel):
    """
    Replay masking configuration for deterministic fingerprinting.

    - ignore_paths: JSONPath expressions to mask volatile fields.
    - ignore_params: Query param names to remove before hashing.
    """
    ignore_paths: List[str] = Field(
        default_factory=lambda: list(DEFAULT_REPLAY_IGNORE_PATHS),
        description="JSONPath fields to mask",
    )
    ignore_params: List[str] = Field(default_factory=list, description="Query params to ignore")


class ClassifierRules(BaseModel):
    """
    Optional traffic classifier rules for enterprise environments.

    Each list contains regex patterns (case-insensitive) to classify traffic types.
    """
    llm_patterns: List[str] = Field(default_factory=list, description="Regexes for LLM API traffic")
    tool_patterns: List[str] = Field(default_factory=list, description="Regexes for tool call traffic")
    agent_patterns: List[str] = Field(default_factory=list, description="Regexes for agent-to-agent traffic")


class ClassifierRulePack(BaseModel):
    """
    Mandatory classifier rule pack for production environments.
    """
    name: str = Field(..., description="Rule pack name")
    rules: ClassifierRules = Field(..., description="Classifier rule patterns")


class ChaosPlan(BaseModel):
    """
    Complete chaos engineering plan.
    
    A plan defines targets (what to attack) and scenarios (how to attack them).
    This provides a configuration-driven approach to chaos engineering.
    
    Attributes:
        version: Plan schema version.
        revision: Plan revision number (config iteration).
        replay_config: Replay masking configuration for deterministic replay.
        metadata: Additional metadata (experiment name, description, etc.).
        targets: List of targets to attack.
        scenarios: List of chaos strategies (scenarios) to apply.
    """
    version: str = Field(default="1.0", description="Plan schema version")
    revision: int = Field(default=0, ge=0, description="Plan revision number (config iteration)")
    replay_config: ReplayConfig = Field(
        default_factory=ReplayConfig,
        description="Replay masking configuration",
    )
    classifier_rules: Optional[ClassifierRules] = Field(
        default=None,
        description="Optional traffic classifier rules (enterprise overrides)",
    )
    classifier_rule_packs: List[ClassifierRulePack] = Field(
        default_factory=list,
        description="Mandatory classifier rule packs for production",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Plan metadata")
    targets: List[TargetConfig] = Field(default_factory=list, description="List of targets")
    scenarios: List[StrategyConfig] = Field(default_factory=list, description="List of scenarios")
    
    @model_validator(mode="before")
    @classmethod
    def hydrate_classifier_rules(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("classifier_rules") is None:
                metadata = data.get("metadata", {})
                rules = metadata.get("classifier_rules") if isinstance(metadata, dict) else None
                if isinstance(rules, dict):
                    data = dict(data)
                    data["classifier_rules"] = rules
        return data

    @model_validator(mode='after')
    def validate_target_references(self) -> 'ChaosPlan':
        """Validate that all scenario target_refs exist in targets."""
        target_names = {target.name for target in self.targets}
        
        for scenario in self.scenarios:
            if scenario.target_ref not in target_names:
                raise ValueError(
                    f"Scenario '{scenario.name}' references unknown target '{scenario.target_ref}'. "
                    f"Available targets: {sorted(target_names)}"
                )
        
        return self

    @model_validator(mode="after")
    def validate_classifier_rule_packs(self) -> "ChaosPlan":
        if self.classifier_rule_packs:
            if not isinstance(self.classifier_rule_packs, list):
                raise ValueError("classifier_rule_packs must be a list")
        return self
    
    def get_target(self, name: str) -> Optional[TargetConfig]:
        """Get a target by name."""
        for target in self.targets:
            if target.name == name:
                return target
        return None
    
    def get_scenarios_for_target(self, target_name: str) -> List[StrategyConfig]:
        """Get all scenarios that target a specific target."""
        return [s for s in self.scenarios if s.target_ref == target_name and s.enabled]
    
    def to_legacy_config(self) -> Dict[str, Any]:
        """
        Convert this plan to legacy ChaosConfig format for backward compatibility.
        
        This allows the plan to be used with existing proxy addon code.
        """
        strategies = []
        for scenario in self.scenarios:
            if not scenario.enabled:
                continue
            
            strategy = {
                "name": scenario.name,
                "type": scenario.type,
                "enabled": scenario.enabled,
                "probability": scenario.probability,
                "params": scenario.params.copy()
            }
            
            # Add target_ref to params so strategies can use it
            strategy["params"]["target_ref"] = scenario.target_ref
            
            # Also add target pattern to params for backward compatibility
            target = self.get_target(scenario.target_ref)
            if target:
                if target.type == "http_endpoint":
                    # For HTTP endpoints, add URL pattern matching
                    strategy["params"]["url_pattern"] = target.pattern
                elif target.type == "agent_role":
                    # For agent roles, add role matching
                    strategy["params"]["target_role"] = target.pattern
                elif target.type == "tool_call":
                    # For tool calls, add endpoint pattern
                    strategy["params"]["target_endpoint"] = target.pattern
            
            strategies.append(strategy)
        
        return {
            "experiment_id": self.metadata.get("experiment_id", "chaos_plan"),
            "strategies": strategies
        }


# Singleton instance for global access
_global_plan: Optional[ChaosPlan] = None
_last_plan_hash: Optional[str] = None


def _compute_file_hash(path: Path) -> str:
    """
    Compute SHA-256 hash of a file.

    Args:
        path: Path to file.

    Returns:
        Hex digest of SHA-256 hash.
    """
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_chaos_plan(path: str) -> ChaosPlan:
    """
    Load a chaos plan from a YAML file.
    
    Args:
        path: Path to the YAML file containing the chaos plan.
        
    Returns:
        Validated ChaosPlan object.
        
    Raises:
        FileNotFoundError: If the file doesn't exist.
        yaml.YAMLError: If the YAML is invalid.
        ValidationError: If the schema validation fails.
    """
    plan_path = Path(path)
    
    if not plan_path.exists():
        raise FileNotFoundError(f"Chaos plan file not found: {path}")
    
    logger.info(f"Loading chaos plan from: {plan_path}")
    
    try:
        with open(plan_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not data:
            raise ValueError("YAML file is empty or contains no data")
        
        # Validate and create plan
        plan = ChaosPlan(**data)
        
        logger.info(
            f"Loaded chaos plan: {len(plan.targets)} targets, "
            f"{len(plan.scenarios)} scenarios "
            f"({sum(1 for s in plan.scenarios if s.enabled)} enabled)"
        )
        
        return plan
    
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML file {path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to load chaos plan from {path}: {e}")
        raise


def set_global_plan(plan: ChaosPlan) -> None:
    """
    Set the global chaos plan (singleton).
    
    This allows the proxy addon to access the plan without passing it around.
    
    Args:
        plan: The chaos plan to set as global.
    """
    global _global_plan
    _global_plan = plan
    logger.info(f"Set global chaos plan: {plan.metadata.get('name', 'unnamed')}")


def get_global_plan() -> Optional[ChaosPlan]:
    """
    Get the global chaos plan (singleton).
    
    Returns:
        The global chaos plan, or None if not set.
    """
    return _global_plan


def load_and_set_global_plan(path: str) -> ChaosPlan:
    """
    Load a chaos plan and set it as the global plan.
    
    Convenience function that combines load_chaos_plan() and set_global_plan().
    
    Args:
        path: Path to the YAML file containing the chaos plan.
        
    Returns:
        The loaded ChaosPlan object.
    """
    global _last_plan_hash, _global_plan
    plan_path = Path(path)

    if not plan_path.exists():
        raise FileNotFoundError(f"Chaos plan file not found: {path}")

    current_hash = _compute_file_hash(plan_path)
    if _global_plan is not None and _last_plan_hash == current_hash:
        logger.debug("Chaos plan unchanged (hash match); skipping reload")
        return _global_plan

    plan = load_chaos_plan(path)
    set_global_plan(plan)
    _last_plan_hash = current_hash
    return plan

