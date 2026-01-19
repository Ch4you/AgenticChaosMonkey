"""
Traffic Classifier for Multi-Agent Swarm Testing.

This module provides intelligent traffic classification to identify different types
of communication patterns in multi-agent systems:
- TOOL_CALL: Agent calling external tools/APIs
- LLM_API: Agent calling LLM services (OpenAI, Anthropic, etc.)
- AGENT_TO_AGENT: Inter-agent communication (AutoGen, OpenAI Swarm, etc.)

The classifier is highly extensible and can be configured via chaos plans to
support new protocols and communication patterns.
"""

from typing import Optional, Dict, Any, List, Literal, Pattern
from mitmproxy import http
import logging
import re
import json
from urllib.parse import urlparse

from agent_chaos_sdk.config_loader import get_global_plan, TargetConfig, ClassifierRules
from agent_chaos_sdk.common.security import get_auth, get_redactor
import os
from agent_chaos_sdk.common.async_utils import run_cpu_bound

logger = logging.getLogger(__name__)

# Traffic type constants
TRAFFIC_TYPE_TOOL_CALL = "TOOL_CALL"
TRAFFIC_TYPE_LLM_API = "LLM_API"
TRAFFIC_TYPE_AGENT_TO_AGENT = "AGENT_TO_AGENT"
TRAFFIC_TYPE_UNKNOWN = "UNKNOWN"

# Metadata key for storing traffic type
METADATA_TRAFFIC_TYPE = "traffic_type"
METADATA_TRAFFIC_SUBTYPE = "traffic_subtype"  # e.g., "supervisor_to_worker", "consensus_vote"


class TrafficClassifier:
    """
    Classifies HTTP traffic into different categories for targeted chaos injection.
    
    This classifier analyzes request patterns (headers, URL structure, body shape)
    to identify the type of communication, enabling swarm-specific attacks.
    
    The classifier is highly decoupled and extensible, supporting:
    - Configurable patterns via ChaosPlan
    - Protocol-agnostic design (HTTP, future: gRPC, WebSocket)
    - Pattern-based and ML-ready architecture
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the traffic classifier.
        
        Args:
            config: Optional configuration dictionary with classification rules.
        """
        self.config = config or {}
        
        # Compiled patterns for performance
        self._llm_patterns: List[Pattern] = []
        self._tool_call_patterns: List[Pattern] = []
        self._agent_patterns: List[Pattern] = []
        
        # Load patterns from global plan if available
        self._load_patterns_from_plan()
        
        # Load default patterns
        self._load_default_patterns()
        
        logger.info(
            f"TrafficClassifier initialized: "
            f"LLM={len(self._llm_patterns)}, "
            f"Tool={len(self._tool_call_patterns)}, "
            f"Agent={len(self._agent_patterns)}"
        )
    
    def _load_patterns_from_plan(self) -> None:
        """Load classification patterns from ChaosPlan configuration."""
        plan = get_global_plan()
        if not plan:
            return
        
        # Look for targets with specific types that indicate traffic classification
        for target in plan.targets:
            if target.type == "llm_input":
                try:
                    pattern = re.compile(target.pattern)
                    self._llm_patterns.append(pattern)
                    logger.debug(f"Loaded LLM pattern from plan: {target.pattern}")
                except re.error as e:
                    logger.warning(f"Invalid LLM pattern '{target.pattern}': {e}")
            
            elif target.type == "tool_call":
                try:
                    pattern = re.compile(target.pattern)
                    self._tool_call_patterns.append(pattern)
                    logger.debug(f"Loaded tool call pattern from plan: {target.pattern}")
                except re.error as e:
                    logger.warning(f"Invalid tool call pattern '{target.pattern}': {e}")
            
            elif target.type == "custom" and "agent" in target.name.lower():
                # Custom targets with "agent" in name are likely agent-to-agent
                try:
                    pattern = re.compile(target.pattern)
                    self._agent_patterns.append(pattern)
                    logger.debug(f"Loaded agent pattern from plan: {target.pattern}")
                except re.error as e:
                    logger.warning(f"Invalid agent pattern '{target.pattern}': {e}")

        # Optional: enterprise classifier rules (first-class config)
        if plan.classifier_rules:
            rules = plan.classifier_rules
            self._load_patterns_from_rule_set(rules.dict(), "llm_patterns", self._llm_patterns)
            self._load_patterns_from_rule_set(rules.dict(), "tool_patterns", self._tool_call_patterns)
            self._load_patterns_from_rule_set(rules.dict(), "agent_patterns", self._agent_patterns)

        # Mandatory production rule packs (all merged)
        if plan.classifier_rule_packs:
            merged = ClassifierRules()
            for pack in plan.classifier_rule_packs:
                merged.llm_patterns.extend(pack.rules.llm_patterns)
                merged.tool_patterns.extend(pack.rules.tool_patterns)
                merged.agent_patterns.extend(pack.rules.agent_patterns)
            self._load_patterns_from_rule_set(merged.dict(), "llm_patterns", self._llm_patterns)
            self._load_patterns_from_rule_set(merged.dict(), "tool_patterns", self._tool_call_patterns)
            self._load_patterns_from_rule_set(merged.dict(), "agent_patterns", self._agent_patterns)

    def _load_patterns_from_rule_set(
        self, rules: Dict[str, Any], key: str, target_list: List[Pattern]
    ) -> None:
        patterns = rules.get(key, [])
        if not isinstance(patterns, list):
            return
        for pattern_str in patterns:
            if not isinstance(pattern_str, str):
                continue
            try:
                target_list.append(re.compile(pattern_str, re.IGNORECASE))
                logger.debug(f"Loaded classifier rule pattern: {pattern_str}")
            except re.error as e:
                logger.warning(f"Invalid classifier rule pattern '{pattern_str}': {e}")
    
    def _load_default_patterns(self) -> None:
        """Load default patterns for common services."""
        # LLM API patterns
        default_llm_patterns = [
            r".*openai\.com.*/v1/(chat|completions|embeddings)",
            r".*anthropic\.com.*/v1/messages",
            r".*api\.cohere\.ai.*/v1/generate",
            r".*api\.mistral\.ai.*/v1/chat",
            r".*127\.0\.0\.1:11434.*/api/(chat|generate)",  # Ollama
            r".*ollama.*/api/(chat|generate)",
        ]
        
        for pattern_str in default_llm_patterns:
            try:
                self._llm_patterns.append(re.compile(pattern_str, re.IGNORECASE))
            except re.error:
                pass
        
        # Tool call patterns (external APIs)
        default_tool_patterns = [
            r".*api\.(stripe|twilio|sendgrid|mailchimp)",
            r".*\.googleapis\.com.*",
            r".*localhost:8001.*",  # Mock server
            r".*/api/(search|book|query|execute)",
        ]
        
        for pattern_str in default_tool_patterns:
            try:
                self._tool_call_patterns.append(re.compile(pattern_str, re.IGNORECASE))
            except re.error:
                pass
        
        # Agent-to-agent patterns (AutoGen, OpenAI Swarm, etc.)
        default_agent_patterns = [
            r".*agent-[a-z0-9]+.*",  # AutoGen agent URLs
            r".*swarm.*/messages",  # OpenAI Swarm
            r".*localhost:\d+/agent-.*",  # Local agent endpoints
            r".*/api/agent/.*",  # Generic agent API
        ]
        
        for pattern_str in default_agent_patterns:
            try:
                self._agent_patterns.append(re.compile(pattern_str, re.IGNORECASE))
            except re.error:
                pass
    
    async def classify(self, flow: http.HTTPFlow) -> str:
        """
        Classify the traffic type for a given HTTP flow.
        
        This method analyzes:
        - URL patterns
        - Headers (User-Agent, X-Agent-*, etc.)
        - Request body structure (for tool calls vs LLM calls)
        - Response structure
        
        Args:
            flow: The HTTP flow to classify.
            
        Returns:
            Traffic type string: TOOL_CALL, LLM_API, AGENT_TO_AGENT, or UNKNOWN
        """
        url = flow.request.pretty_url

        # Explicit override via header (manual control)
        override = flow.request.headers.get("X-Agent-Chaos-Type")
        if override and self._is_override_allowed(flow):
            override_value = str(override).upper()
            override_map = {
                "TOOL_CALL": TRAFFIC_TYPE_TOOL_CALL,
                "LLM_API": TRAFFIC_TYPE_LLM_API,
                "AGENT_TO_AGENT": TRAFFIC_TYPE_AGENT_TO_AGENT,
                "UNKNOWN": TRAFFIC_TYPE_UNKNOWN,
            }
            traffic_type = override_map.get(override_value, TRAFFIC_TYPE_UNKNOWN)
            subtype = flow.request.headers.get("X-Agent-Chaos-Subtype")
            flow.metadata[METADATA_TRAFFIC_TYPE] = traffic_type
            if subtype:
                flow.metadata[METADATA_TRAFFIC_SUBTYPE] = subtype
            logger.debug(f"Traffic type override via header: {traffic_type}")
            return traffic_type
        
        # If production requires rule packs, enforce presence
        plan = get_global_plan()
        if os.getenv("CHAOS_CLASSIFIER_STRICT", "true").lower() == "true":
            if plan and not plan.classifier_rule_packs:
                from agent_chaos_sdk.common.errors import ErrorCode
                from agent_chaos_sdk.common.telemetry import record_error_code
                logger.error(
                    f"[{ErrorCode.CLASSIFIER_STRICT_MISSING_RULES}] "
                    "Classifier strict mode enabled but no classifier_rule_packs configured"
                )
                record_error_code(ErrorCode.CLASSIFIER_STRICT_MISSING_RULES, strategy="classifier")
                flow.metadata[METADATA_TRAFFIC_TYPE] = TRAFFIC_TYPE_UNKNOWN
                return TRAFFIC_TYPE_UNKNOWN

        # Score URL patterns and pick most specific match
        agent_score, agent_len = self._best_pattern_score(url, self._agent_patterns)
        llm_score, llm_len = self._best_pattern_score(url, self._llm_patterns)
        tool_score, tool_len = self._best_pattern_score(url, self._tool_call_patterns)

        scores = {
            TRAFFIC_TYPE_AGENT_TO_AGENT: (agent_score, agent_len),
            TRAFFIC_TYPE_LLM_API: (llm_score, llm_len),
            TRAFFIC_TYPE_TOOL_CALL: (tool_score, tool_len),
        }
        max_score = max(score for score, _ in scores.values())

        if max_score > 0:
            # Prefer higher score; tie-break by explicit priority
            priority = [TRAFFIC_TYPE_AGENT_TO_AGENT, TRAFFIC_TYPE_LLM_API, TRAFFIC_TYPE_TOOL_CALL]
            best_type = None
            for t in priority:
                if scores[t][0] == max_score:
                    best_type = t
                    break
            traffic_type = best_type or TRAFFIC_TYPE_UNKNOWN
            subtype = await self._detect_agent_subtype(flow) if traffic_type == TRAFFIC_TYPE_AGENT_TO_AGENT else None

            # Body-based classification can override URL pattern when it is more specific
            body_type, body_subtype = await self._classify_by_body(flow)
            if body_type != TRAFFIC_TYPE_UNKNOWN and body_type != traffic_type:
                traffic_type, subtype = body_type, body_subtype
        else:
            # Try header-based classification
            traffic_type, subtype = self._classify_by_headers(flow)
            if traffic_type == TRAFFIC_TYPE_UNKNOWN:
                # Try body-based classification
                traffic_type, subtype = await self._classify_by_body(flow)
        
        # Store in flow metadata for strategies to use
        flow.metadata[METADATA_TRAFFIC_TYPE] = traffic_type
        if subtype:
            flow.metadata[METADATA_TRAFFIC_SUBTYPE] = subtype
        
        redacted_url = get_redactor().redact_url(url)
        logger.debug(
            f"Classified traffic: {redacted_url[:50]}... -> {traffic_type}"
            + (f" ({subtype})" if subtype else "")
        )
        
        return traffic_type
    
    def _matches_patterns(self, url: str, patterns: List[Pattern]) -> bool:
        """Check if URL matches any of the compiled patterns."""
        for pattern in patterns:
            if pattern.search(url):
                return True
        return False

    def _best_pattern_score(self, url: str, patterns: List[Pattern]) -> tuple[int, int]:
        """
        Compute best match score for URL patterns.

        Score is match length + path bonus to favor path-specific matches.
        """
        best_score = 0
        best_len = 0
        parsed = urlparse(url)
        path_index = url.find(parsed.path) if parsed.path else len(url)

        for pattern in patterns:
            match = pattern.search(url)
            if not match:
                continue
            match_len = match.end() - match.start()
            path_bonus = 100 if match.start() >= path_index else 0
            score = match_len + path_bonus
            if score > best_score:
                best_score = score
                best_len = match_len

        return best_score, best_len

    def _is_override_allowed(self, flow: http.HTTPFlow) -> bool:
        """
        Allow override only when explicitly permitted.

        - If plan has metadata.allow_client_override == True
        - OR request is authenticated (X-Chaos-Token or Authorization via ChaosAuth)
        """
        plan = get_global_plan()
        if plan and plan.metadata.get("allow_client_override") is True:
            return True

        auth = get_auth()
        if not auth.enabled:
            return False
        try:
            return auth.validate(flow, required_scope="READ")
        except Exception:
            return False

    async def classify_flow(self, flow: http.HTTPFlow) -> str:
        """Alias for classify() to make intent explicit."""
        return await self.classify(flow)
    
    def _classify_by_headers(self, flow: http.HTTPFlow) -> tuple[str, Optional[str]]:
        """
        Classify traffic based on HTTP headers.
        
        Returns:
            Tuple of (traffic_type, subtype)
        """
        headers = flow.request.headers
        
        # Check for agent-to-agent headers
        if headers.get("X-Agent-To-Agent") or headers.get("X-Swarm-Message"):
            return TRAFFIC_TYPE_AGENT_TO_AGENT, "swarm_message"

        # Explicit agent role headers indicate agent-to-agent context
        if headers.get("X-Agent-Role") or headers.get("Agent-Role"):
            return TRAFFIC_TYPE_AGENT_TO_AGENT, "role_header"
        
        # Check for AutoGen headers
        if "autogen" in headers.get("User-Agent", "").lower():
            return TRAFFIC_TYPE_AGENT_TO_AGENT, "autogen"
        
        # Check for LLM API keys in headers
        if headers.get("Authorization"):
            auth = headers.get("Authorization", "")
            if isinstance(auth, bytes):
                auth = auth.decode('utf-8', errors='ignore')
            if "sk-" in auth or "Bearer" in auth:
                # Could be LLM API, check URL
                if "openai" in flow.request.pretty_url or "anthropic" in flow.request.pretty_url:
                    return TRAFFIC_TYPE_LLM_API, None
        
        return TRAFFIC_TYPE_UNKNOWN, None
    
    async def _classify_by_body(self, flow: http.HTTPFlow) -> tuple[str, Optional[str]]:
        """
        Classify traffic based on request body structure.
        
        Returns:
            Tuple of (traffic_type, subtype)
        """
        if not flow.request.content:
            return TRAFFIC_TYPE_UNKNOWN, None

        if len(flow.request.content) > 1_000_000:
            # Avoid CPU-heavy parsing for very large bodies
            return TRAFFIC_TYPE_UNKNOWN, None
        
        try:
            body_text = flow.request.get_text()
            if not body_text:
                return TRAFFIC_TYPE_UNKNOWN, None
            
            body = await run_cpu_bound(json.loads, body_text)
            
            # Check for LLM API structure (OpenAI, Anthropic format)
            if "messages" in body and isinstance(body["messages"], list):
                # Check if it's a tool call or regular LLM call
                for msg in body["messages"]:
                    if isinstance(msg, dict):
                        if "tool_calls" in msg or "function_call" in msg:
                            return TRAFFIC_TYPE_TOOL_CALL, "llm_tool_call"
                        if "role" in msg and msg["role"] in ["system", "user", "assistant"]:
                            # Likely LLM API call
                            if "model" in body or "temperature" in body:
                                return TRAFFIC_TYPE_LLM_API, None
            
            # Check for agent-to-agent structure (AutoGen format)
            if "sender" in body and "receiver" in body:
                return TRAFFIC_TYPE_AGENT_TO_AGENT, "autogen_message"
            
            if "agent_id" in body or "swarm_id" in body:
                return TRAFFIC_TYPE_AGENT_TO_AGENT, "swarm_message"

            if "from_agent" in body or "to_agent" in body or "agent_role" in body:
                return TRAFFIC_TYPE_AGENT_TO_AGENT, "agent_metadata"
            
            # Check for tool call structure (direct API call)
            if any(key in body for key in ["tool", "function", "action", "command"]):
                return TRAFFIC_TYPE_TOOL_CALL, "direct_tool_call"
            
        except (json.JSONDecodeError, AttributeError) as e:
            logger.debug(f"Body classification failed: {e}")
        
        return TRAFFIC_TYPE_UNKNOWN, None
    
    async def _detect_agent_subtype(self, flow: http.HTTPFlow) -> Optional[str]:
        """
        Detect specific subtype of agent-to-agent communication.
        
        Returns:
            Subtype string (e.g., "supervisor_to_worker", "consensus_vote", "autogen")
        """
        url = flow.request.pretty_url.lower()
        headers = flow.request.headers
        
        # Check URL patterns
        if "supervisor" in url or "manager" in url:
            return "supervisor_to_worker"
        if "consensus" in url or "vote" in url:
            return "consensus_vote"
        if "worker" in url or "agent-" in url:
            return "worker_communication"
        
        # Check headers
        if headers.get("X-Swarm-Phase") == "consensus":
            return "consensus_vote"
        if headers.get("X-Agent-Role") == "supervisor":
            return "supervisor_to_worker"
        
        # Check body for consensus indicators
        if flow.request.content:
            try:
                body_text = flow.request.get_text()
                if body_text and ("consensus" in body_text.lower() or "vote" in body_text.lower()):
                    return "consensus_vote"
            except Exception as e:
                logger.debug(f"Failed to inspect body for subtype: {e}")
        
        return "agent_to_agent"  # Generic agent communication
    
    async def get_traffic_type(self, flow: http.HTTPFlow) -> str:
        """
        Get the classified traffic type from flow metadata.
        
        If not classified yet, classifies it first.
        
        Args:
            flow: The HTTP flow.
            
        Returns:
            Traffic type string.
        """
        if METADATA_TRAFFIC_TYPE in flow.metadata:
            return flow.metadata[METADATA_TRAFFIC_TYPE]
        
        return await self.classify(flow)
    
    def get_traffic_subtype(self, flow: http.HTTPFlow) -> Optional[str]:
        """
        Get the traffic subtype from flow metadata.
        
        Args:
            flow: The HTTP flow.
            
        Returns:
            Subtype string or None.
        """
        return flow.metadata.get(METADATA_TRAFFIC_SUBTYPE)


# Global classifier instance (singleton pattern)
_classifier_instance: Optional[TrafficClassifier] = None


def get_classifier() -> TrafficClassifier:
    """
    Get the global TrafficClassifier instance.
    
    Returns:
        TrafficClassifier instance.
    """
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = TrafficClassifier()
    return _classifier_instance


def set_classifier(classifier: TrafficClassifier) -> None:
    """
    Set the global TrafficClassifier instance.
    
    Args:
        classifier: TrafficClassifier instance to use.
    """
    global _classifier_instance
    _classifier_instance = classifier

