"""
Swarm Disruption Strategies for Multi-Agent System Testing.

This module implements strategies specifically designed to disrupt inter-agent
communication in multi-agent swarms (AutoGen, OpenAI Swarm, etc.).

Key Features:
- MessageMutation: Modify instructions between agents
- ConsensusDelay: Inject latency during consensus/voting phases
- AgentIsolation: Block communication from specific agents
"""

from typing import Optional, Dict, Any, List
from mitmproxy import http
import logging
import json
import random
import re
import asyncio

from agent_chaos_sdk.proxy.strategies.base import BaseStrategy
from agent_chaos_sdk.proxy.classifier import (
    get_classifier, TRAFFIC_TYPE_AGENT_TO_AGENT,
    METADATA_TRAFFIC_TYPE, METADATA_TRAFFIC_SUBTYPE
)
from agent_chaos_sdk.common.async_utils import run_cpu_bound
from agent_chaos_sdk.common.security import get_redactor

logger = logging.getLogger(__name__)


class SwarmDisruptionStrategy(BaseStrategy):
    """
    Strategy that disrupts inter-agent communication in multi-agent swarms.
    
    This strategy specifically targets AGENT_TO_AGENT traffic and can:
    - Mutate messages between agents
    - Inject delays during consensus phases
    - Isolate specific agents
    
    Example:
        Original message: {"instruction": "Process this task", "priority": "high"}
        Mutated: {"instruction": "Process this task", "priority": "low"}  # Flipped boolean/flag
    """
    
    def __init__(
        self,
        name: str = "swarm_disruption",
        enabled: bool = True,
        target_ref: Optional[str] = None,
        url_pattern: Optional[str] = None,
        attack_type: str = "message_mutation",
        target_subtype: Optional[str] = None,  # e.g., "consensus_vote", "supervisor_to_worker"
        probability: float = 1.0,
        **kwargs
    ):
        """
        Initialize the swarm disruption strategy.
        
        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
            target_ref: Reference to a target name from ChaosPlan.
            url_pattern: Direct URL pattern regex.
            attack_type: Type of attack ("message_mutation", "consensus_delay", "agent_isolation").
            target_subtype: Specific agent communication subtype to target.
            probability: Probability (0.0-1.0) of applying the attack.
            **kwargs: Additional parameters.
        """
        super().__init__(name, enabled, target_ref, url_pattern, **kwargs)
        
        self.attack_type = attack_type or kwargs.get('attack_type', "message_mutation")
        self.target_subtype = target_subtype or kwargs.get('target_subtype')
        self.probability = probability or kwargs.get('probability', 1.0)
        
        # Attack-specific parameters
        self.mutation_rules = kwargs.get('mutation_rules', {})
        self.consensus_delay = kwargs.get('consensus_delay', 5.0)
        self.isolated_agents = kwargs.get('isolated_agents', [])
        
        logger.info(
            f"SwarmDisruptionStrategy initialized: "
            f"attack_type={self.attack_type}, "
            f"target_subtype={self.target_subtype}, "
            f"probability={self.probability}"
        )
    
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Intercept and disrupt agent-to-agent communication.
        
        Only applies to AGENT_TO_AGENT traffic.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if disruption was applied, False otherwise.
        """
        if not self.should_trigger(flow):
            return False
        
        # CRITICAL: Only target agent-to-agent traffic
        classifier = get_classifier()
        traffic_type = await classifier.get_traffic_type(flow)
        
        if traffic_type != TRAFFIC_TYPE_AGENT_TO_AGENT:
            return False
        
        # Check subtype if specified
        if self.target_subtype:
            subtype = classifier.get_traffic_subtype(flow)
            if subtype != self.target_subtype:
                return False
        
        # Check probability
        if random.random() >= self.probability:
            return False
        
        # Apply attack based on type
        if self.attack_type == "message_mutation":
            return await self._apply_message_mutation(flow)
        elif self.attack_type == "consensus_delay":
            return await self._apply_consensus_delay(flow)
        elif self.attack_type == "agent_isolation":
            return await self._apply_agent_isolation(flow)
        else:
            logger.warning(f"Unknown attack type: {self.attack_type}")
            return False
    
    async def _apply_message_mutation(self, flow: http.HTTPFlow) -> bool:
        """
        Mutate messages between agents (e.g., flip boolean flags, modify instructions).
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if mutation was applied.
        """
        if not flow.request.content:
            return False
        
        try:
            body_text = flow.request.get_text()
            if not body_text:
                return False
            
            body = await run_cpu_bound(json.loads, body_text)
            mutated = False
            
            # Apply mutation rules
            if self.mutation_rules:
                mutated = self._apply_mutation_rules(body, self.mutation_rules)
            else:
                # Default: flip boolean values, modify numeric values
                mutated = self._apply_default_mutations(body)
            
            if mutated:
                # Update request body
                flow.request.text = await run_cpu_bound(json.dumps, body, ensure_ascii=False)
                flow.request.headers["Content-Length"] = str(
                    len(flow.request.text.encode('utf-8'))
                )
                
                redacted_url = get_redactor().redact_url(flow.request.pretty_url)
                logger.info(
                    f"SwarmDisruptionStrategy '{self.name}' mutated agent message "
                    f"from {redacted_url}"
                )
                return True
            
            return False
            
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"Failed to mutate agent message: {e}")
            return False
    
    def _apply_mutation_rules(self, body: Dict[str, Any], rules: Dict[str, Any]) -> bool:
        """
        Apply custom mutation rules to the message body.
        
        Args:
            body: JSON body dictionary.
            rules: Mutation rules (e.g., {"priority": "low", "enabled": false}).
            
        Returns:
            True if any mutation was applied.
        """
        mutated = False
        
        def mutate_recursive(obj: Any, path: str = "") -> None:
            nonlocal mutated
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    
                    # Check if this key should be mutated
                    if key in rules:
                        if isinstance(rules[key], dict) and isinstance(value, dict):
                            # Nested mutation
                            mutate_recursive(value, current_path)
                        else:
                            # Direct mutation
                            obj[key] = rules[key]
                            mutated = True
                            logger.debug(f"Mutated {current_path}: {value} -> {rules[key]}")
                    else:
                        # Recurse into nested objects
                        if isinstance(value, (dict, list)):
                            mutate_recursive(value, current_path)
            
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    mutate_recursive(item, f"{path}[{i}]")
        
        mutate_recursive(body)
        return mutated
    
    def _apply_default_mutations(self, body: Dict[str, Any]) -> bool:
        """
        Apply default mutations (flip booleans, modify numbers).
        
        Args:
            body: JSON body dictionary.
            
        Returns:
            True if any mutation was applied.
        """
        mutated = False
        
        def mutate_recursive(obj: Any) -> None:
            nonlocal mutated
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(value, bool):
                        # Flip boolean
                        obj[key] = not value
                        mutated = True
                        logger.debug(f"Flipped boolean {key}: {value} -> {not value}")
                    elif isinstance(value, (int, float)) and value > 0:
                        # Modify numeric value (±20% or ±1, whichever is larger)
                        change = max(abs(value * 0.2), 1)
                        obj[key] = value + random.choice([-1, 1]) * change
                        mutated = True
                        logger.debug(f"Modified number {key}: {value} -> {obj[key]}")
                    elif isinstance(value, str) and value.lower() in ["true", "false"]:
                        # String boolean
                        obj[key] = "false" if value.lower() == "true" else "true"
                        mutated = True
                        logger.debug(f"Flipped string boolean {key}: {value} -> {obj[key]}")
                    elif isinstance(value, (dict, list)):
                        mutate_recursive(value)
            
            elif isinstance(obj, list):
                for item in obj:
                    mutate_recursive(item)
        
        mutate_recursive(body)
        return mutated
    
    async def _apply_consensus_delay(self, flow: http.HTTPFlow) -> bool:
        """
        Inject high latency during consensus/voting phases.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if delay was applied.
        """
        # Check if this is a consensus phase
        classifier = get_classifier()
        subtype = classifier.get_traffic_subtype(flow)
        
        if subtype != "consensus_vote" and "consensus" not in flow.request.pretty_url.lower():
            # Not a consensus phase, skip
            return False
        
        # Inject delay
        delay = self.consensus_delay
        logger.info(
            f"SwarmDisruptionStrategy '{self.name}' injecting {delay}s delay "
            f"during consensus phase"
        )
        await asyncio.sleep(delay)
        
        return True
    
    async def _apply_agent_isolation(self, flow: http.HTTPFlow) -> bool:
        """
        Block communication from isolated agents.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if agent was isolated (blocked).
        """
        # Extract agent identifier from URL or headers
        agent_id = await self._extract_agent_id(flow)
        
        if agent_id and agent_id in self.isolated_agents:
            # Block this agent's communication
            logger.warning(
                f"SwarmDisruptionStrategy '{self.name}' blocking isolated agent: {agent_id}"
            )
            
            # Create error response
            error_response = flow.request.make_response(
                content=json.dumps({
                    "error": "Agent isolated",
                    "agent_id": agent_id,
                    "message": "This agent has been isolated by chaos engineering"
                }).encode('utf-8'),
                status_code=503,
                headers={"Content-Type": "application/json"}
            )
            
            flow.response = error_response
            return True
        
        return False
    
    async def _extract_agent_id(self, flow: http.HTTPFlow) -> Optional[str]:
        """
        Extract agent identifier from flow.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            Agent ID string or None.
        """
        # Try headers first
        agent_id = flow.request.headers.get("X-Agent-ID") or flow.request.headers.get("Agent-ID")
        if agent_id:
            if isinstance(agent_id, bytes):
                return agent_id.decode('utf-8', errors='ignore')
            return str(agent_id)
        
        # Try URL pattern
        url = flow.request.pretty_url
        match = re.search(r'agent[_-]?([a-z0-9-]+)', url, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # Try body
        if flow.request.content:
            try:
                body_text = flow.request.get_text()
                if body_text:
                    body = await run_cpu_bound(json.loads, body_text)
                    for key in ["agent_id", "agentId", "sender", "from"]:
                        if key in body:
                            return str(body[key])
            except (json.JSONDecodeError, AttributeError) as e:
                logger.debug(f"Failed to extract agent id from body: {e}")
        
        return None

