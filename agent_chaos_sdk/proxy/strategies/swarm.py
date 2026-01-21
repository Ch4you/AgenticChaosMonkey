"""
Swarm Communication Strategies.

This module contains strategies that target agent-to-agent communication
in multi-agent systems.
"""

from typing import Optional, Dict, Any, List
from mitmproxy import http
import logging
import json
import random
from datetime import datetime

from agent_chaos_sdk.proxy.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class SwarmDisruptionStrategy(BaseStrategy):
    """
    Strategy that disrupts agent-to-agent communication in swarm systems.

    This cognitive attack tests multi-agent system resilience by:
    - Delaying inter-agent messages
    - Dropping messages between agents
    - Corrupting message payloads
    - Reordering message delivery
    - Isolating specific agents from the swarm

    Example:
        Original: Agent A sends "task_completed" to Agent B
        Disrupted: Message delayed by 5s, or payload corrupted, or never delivered
    """

    def __init__(
        self,
        name: str = "swarm_disruption",
        enabled: bool = True,
        disruption_type: str = "message_delay",
        probability: float = 1.0,
        **kwargs
    ):
        """
        Initialize the swarm disruption strategy.

        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
            disruption_type: Type of disruption ("message_delay", "message_drop", "payload_corruption", "agent_isolation").
            probability: Probability (0.0-1.0) of applying the attack.
            **kwargs: Additional parameters (for dynamic config loading).
        """
        super().__init__(name, enabled, **kwargs)
        self.disruption_type = kwargs.get('disruption_type', disruption_type)
        self.probability = kwargs.get('probability', probability)

        # Disruption parameters
        self.delay_range = kwargs.get('delay_range', (1.0, 10.0))  # seconds
        self.drop_probability = kwargs.get('drop_probability', 0.1)
        self.corruption_fields = kwargs.get('corruption_fields', ["payload", "message_type"])

        # Track disrupted communications for analysis
        self.disruption_log = []

        logger.info(f"SwarmDisruptionStrategy initialized: type={self.disruption_type}, probability={self.probability}")

    def _should_disrupt_message(self, flow: http.HTTPFlow) -> bool:
        """Determine if a message should be disrupted."""
        # Check if this is inter-agent communication
        if not self._is_agent_message(flow):
            return False

        return random.random() < self.probability

    def _is_agent_message(self, flow: http.HTTPFlow) -> bool:
        """Check if the request is an inter-agent message."""
        if not flow.request or not flow.request.pretty_url:
            return False

        url = flow.request.pretty_url

        # Check for agent communication patterns
        agent_patterns = [
            "/agents/",  # Communication server endpoints
            "/messages",  # Message delivery
            "agent_id",  # Agent identifiers in payload
            "message_type",  # Inter-agent message types
        ]

        # Check URL patterns
        for pattern in agent_patterns:
            if pattern in url:
                return True

        # Check request body for agent communication markers
        if flow.request.content:
            try:
                body_text = flow.request.get_text()
                if any(marker in body_text for marker in ["sender", "receiver", "message_type", "agent_id"]):
                    return True
            except:
                pass

        return False

    def _extract_message_info(self, flow: http.HTTPFlow) -> Dict[str, Any]:
        """Extract message information for logging."""
        info = {
            "url": flow.request.pretty_url,
            "method": flow.request.method,
            "timestamp": datetime.now().isoformat(),
        }

        if flow.request.content:
            try:
                body_text = flow.request.get_text()
                data = json.loads(body_text)
                info.update({
                    "sender": data.get("sender"),
                    "receiver": data.get("receiver"),
                    "message_type": data.get("message_type"),
                    "message_id": data.get("message_id"),
                })
            except:
                info["body_preview"] = body_text[:200] if body_text else None

        return info

    def _corrupt_message_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Corrupt message payload based on corruption type."""
        if not isinstance(data, dict):
            return data

        corrupted = data.copy()

        # Corrupt specific fields
        for field in self.corruption_fields:
            if field in corrupted and isinstance(corrupted[field], (str, int, float)):
                if isinstance(corrupted[field], str):
                    # Add noise to strings
                    corrupted[field] = corrupted[field] + "_CORRUPTED_BY_CHAOS"
                elif isinstance(corrupted[field], (int, float)):
                    # Modify numbers
                    corrupted[field] = corrupted[field] * 1.5  # 50% increase

        return corrupted

    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Apply swarm disruption to inter-agent communication.

        Args:
            flow: The HTTP flow object.

        Returns:
            True if attack was applied, False otherwise.
        """
        if not self.should_trigger(flow):
            return False

        if not self._should_disrupt_message(flow):
            return False

        message_info = self._extract_message_info(flow)

        try:
            if self.disruption_type == "message_drop":
                # Drop the message entirely
                flow.response = http.Response.make(
                    500,
                    b"Message dropped by chaos strategy",
                    {"Content-Type": "text/plain"}
                )

                self.disruption_log.append({
                    **message_info,
                    "disruption_type": "message_drop",
                    "action": "dropped"
                })

                logger.warning(
                    f"SwarmDisruptionStrategy '{self.name}' dropped inter-agent message "
                    f"from {message_info.get('sender', 'unknown')} to {message_info.get('receiver', 'unknown')}"
                )
                return True

            elif self.disruption_type == "payload_corruption":
                # Corrupt the message payload
                if flow.request.content:
                    try:
                        body_text = flow.request.get_text()
                        data = json.loads(body_text)
                        corrupted_data = self._corrupt_message_payload(data)
                        new_body = json.dumps(corrupted_data, ensure_ascii=False)
                        flow.request.text = new_body
                        flow.request.headers["Content-Length"] = str(len(new_body.encode('utf-8')))

                        self.disruption_log.append({
                            **message_info,
                            "disruption_type": "payload_corruption",
                            "action": "corrupted"
                        })

                        logger.warning(
                            f"SwarmDisruptionStrategy '{self.name}' corrupted inter-agent message payload "
                            f"from {message_info.get('sender', 'unknown')} to {message_info.get('receiver', 'unknown')}"
                        )
                        return True

                    except json.JSONDecodeError:
                        # Not JSON, skip corruption
                        pass

            elif self.disruption_type == "message_delay":
                # For delay, we can't actually delay in mitmproxy
                # Instead, we'll add a marker that the message was delayed
                if flow.request.content:
                    try:
                        body_text = flow.request.get_text()
                        data = json.loads(body_text)
                        data["_chaos_delayed"] = True
                        data["_chaos_delay_amount"] = random.uniform(*self.delay_range)
                        new_body = json.dumps(data, ensure_ascii=False)
                        flow.request.text = new_body
                        flow.request.headers["Content-Length"] = str(len(new_body.encode('utf-8')))

                        self.disruption_log.append({
                            **message_info,
                            "disruption_type": "message_delay",
                            "delay_amount": data["_chaos_delay_amount"],
                            "action": "marked_for_delay"
                        })

                        logger.warning(
                            f"SwarmDisruptionStrategy '{self.name}' marked inter-agent message for delay "
                            f"({data['_chaos_delay_amount']:.1f}s) "
                            f"from {message_info.get('sender', 'unknown')} to {message_info.get('receiver', 'unknown')}"
                        )
                        return True

                    except json.JSONDecodeError:
                        pass

            elif self.disruption_type == "agent_isolation":
                # Simulate agent isolation by corrupting receiver
                if flow.request.content:
                    try:
                        body_text = flow.request.get_text()
                        data = json.loads(body_text)
                        original_receiver = data.get("receiver", "")
                        data["receiver"] = f"isolated_{original_receiver}"
                        new_body = json.dumps(data, ensure_ascii=False)
                        flow.request.text = new_body
                        flow.request.headers["Content-Length"] = str(len(new_body.encode('utf-8')))

                        self.disruption_log.append({
                            **message_info,
                            "disruption_type": "agent_isolation",
                            "original_receiver": original_receiver,
                            "new_receiver": data["receiver"],
                            "action": "rerouted"
                        })

                        logger.warning(
                            f"SwarmDisruptionStrategy '{self.name}' isolated agent {original_receiver} "
                            f"by rerouting message to {data['receiver']}"
                        )
                        return True

                    except json.JSONDecodeError:
                        pass

        except Exception as e:
            from agent_chaos_sdk.common.errors import ErrorCode
            from agent_chaos_sdk.common.telemetry import record_error_code
            record_error_code(ErrorCode.MUTATION_FAILED, strategy=self.name)
            logger.error(f"[{ErrorCode.MUTATION_FAILED}] Error applying swarm disruption strategy: {e}", exc_info=True)

        return False

    def get_disruption_stats(self) -> Dict[str, Any]:
        """Get statistics about applied disruptions."""
        stats = {
            "total_disruptions": len(self.disruption_log),
            "disruption_types": {},
            "affected_agents": set(),
            "time_range": None,
        }

        if self.disruption_log:
            # Calculate time range
            timestamps = [entry["timestamp"] for entry in self.disruption_log]
            stats["time_range"] = {
                "start": min(timestamps),
                "end": max(timestamps)
            }

            # Count disruption types
            for entry in self.disruption_log:
                disruption_type = entry.get("disruption_type", "unknown")
                stats["disruption_types"][disruption_type] = stats["disruption_types"].get(disruption_type, 0) + 1

                # Track affected agents
                sender = entry.get("sender")
                receiver = entry.get("receiver")
                if sender:
                    stats["affected_agents"].add(sender)
                if receiver:
                    stats["affected_agents"].add(receiver)

            stats["affected_agents"] = list(stats["affected_agents"])

        return stats