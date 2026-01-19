"""
Main mitmproxy addon entry point.

This module provides the mitmproxy addon that intercepts HTTP/HTTPS traffic
and applies chaos strategies using the Strategy Pattern with dynamic configuration loading.

Usage:
    mitmdump -s src/proxy/addon.py
    or
    mitmweb -s src/proxy/addon.py
"""

from mitmproxy import http
from typing import List, Dict, Optional
import logging
import os
import sys
import asyncio
import json
import hashlib
import traceback
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading
from cachetools import TTLCache

# Add SDK package to Python path for imports
# This allows the addon to work both as a standalone script and as an installed package
try:
    import agent_chaos_sdk
except ImportError:
    # If not installed, add parent directory to path
    _project_root = Path(__file__).resolve().parent.parent.parent
    _project_root_str = str(_project_root)
    if _project_root_str not in sys.path:
        sys.path.insert(0, _project_root_str)

# Now we can use absolute imports from SDK package
from agent_chaos_sdk.proxy.strategies.base import BaseStrategy
from agent_chaos_sdk.proxy.factory import StrategyFactory
from agent_chaos_sdk.proxy.strategies.simple_log import SimpleLogStrategy
from agent_chaos_sdk.proxy.strategies.network import LatencyStrategy, ErrorStrategy
from agent_chaos_sdk.proxy.strategies.data import JSONCorruptionStrategy
from agent_chaos_sdk.proxy.strategies.semantic import SemanticStrategy
from agent_chaos_sdk.proxy.strategies.mcp import MCPProtocolFuzzingStrategy
from agent_chaos_sdk.proxy.strategies.group import GroupChaosStrategy, GroupFailureStrategy
from agent_chaos_sdk.proxy.strategies.cognitive import HallucinationStrategy, ContextOverflowStrategy
from agent_chaos_sdk.proxy.strategies.rag import PhantomDocumentStrategy
from agent_chaos_sdk.proxy.strategies.swarm import SwarmDisruptionStrategy
from agent_chaos_sdk.proxy.classifier import (
    get_classifier, METADATA_TRAFFIC_TYPE, METADATA_TRAFFIC_SUBTYPE
)
from agent_chaos_sdk.storage.tape import (
    TapeRecorder, TapePlayer, ChaosContext
)
from agent_chaos_sdk.proxy.context import get_context, clear_context
from agent_chaos_sdk.common.logger import get_logger
from agent_chaos_sdk.common.config import load_config, ChaosConfig, StrategyConfig
from agent_chaos_sdk.common.telemetry import (
    setup_telemetry, extract_trace_context,
    record_ai_request, record_token_usage, record_ttft, record_chaos_injection
)
from agent_chaos_sdk.common.security import get_redactor, get_auth, AuthContext
from agent_chaos_sdk.common.audit import log_audit
from agent_chaos_sdk.common.async_utils import run_cpu_bound
from agent_chaos_sdk.storage.tape import (
    TapeRecorder, TapePlayer, ChaosContext
)
try:
    from agent_chaos_sdk.dashboard.server import get_dashboard_server
    from agent_chaos_sdk.dashboard.events import (
        DashboardEvent,
        RequestStartedEvent, ChaosInjectedEvent,
        ResponseReceivedEvent, SwarmMessageEvent
    )
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False
    DashboardEvent = None
    RequestStartedEvent = None
    ChaosInjectedEvent = None
    ResponseReceivedEvent = None
    SwarmMessageEvent = None
    get_dashboard_server = None
from opentelemetry import trace

# Proxy modes
PROXY_MODE_LIVE = "LIVE"
PROXY_MODE_RECORD = "RECORD"
PROXY_MODE_PLAYBACK = "PLAYBACK"

# Initialize OpenTelemetry for chaos proxy
tracer = setup_telemetry("chaos-proxy")
logger = get_logger(__name__)
logger.info("OpenTelemetry tracing initialized for chaos-proxy")


class ChaosProxyAddon:
    """
    Main mitmproxy addon for chaos injection with dynamic configuration loading.
    
    This addon orchestrates multiple chaos strategies using the Strategy Pattern.
    It supports hot-reloading of configuration without restarting mitmproxy.
    
    Attributes:
        strategies: List of active chaos strategies.
        config_path: Path to the configuration file.
        config: Current configuration instance.
        last_config_mtime: Last modification time of config file (for hot reload).
    """
    
    def __init__(
        self,
        config_path: str = "config/chaos_config.yaml",
        mode: str = PROXY_MODE_LIVE,
        tape_path: Optional[Path] = None
    ):
        """
        Initialize the chaos proxy addon.
        
        Args:
            config_path: Path to the chaos configuration YAML file.
            mode: Proxy mode (LIVE, RECORD, PLAYBACK).
            tape_path: Path to tape file (required for RECORD/PLAYBACK modes).
        """
        self.config_path = Path(config_path)
        self.config: Optional[ChaosConfig] = None
        self.strategies: List[BaseStrategy] = []
        self.last_config_mtime: float = 0.0
        self._last_config_hash: Optional[str] = None
        self._last_auth_context: Optional[AuthContext] = None
        self._request_counter = 0
        self.dashboard_server = None
        self._dashboard_thread = None
        self._dashboard_loop = None
        self._dashboard_autostart = os.getenv("CHAOS_DASHBOARD_AUTOSTART", "false").lower() == "true"
        
        # Proxy mode (LIVE, RECORD, PLAYBACK)
        self.mode = mode.upper()
        if self.mode not in [PROXY_MODE_LIVE, PROXY_MODE_RECORD, PROXY_MODE_PLAYBACK]:
            raise ValueError(f"Invalid mode: {mode}. Must be LIVE, RECORD, or PLAYBACK")
        
        # Tape recording/playback
        self.tape_recorder: Optional[TapeRecorder] = None
        self.tape_player: Optional[TapePlayer] = None
        
        if self.mode == PROXY_MODE_RECORD:
            if not tape_path:
                raise ValueError("tape_path is required for RECORD mode")
            self.tape_recorder = TapeRecorder(tape_path)
            logger.info(f"RECORD mode enabled: {tape_path}")
        elif self.mode == PROXY_MODE_PLAYBACK:
            if not tape_path:
                raise ValueError("tape_path is required for PLAYBACK mode")
            if not tape_path.exists():
                raise FileNotFoundError(f"Tape file not found: {tape_path}")
            self.tape_player = TapePlayer(tape_path)
            logger.info(f"PLAYBACK mode enabled: {tape_path} (no network access)")
        
        # Track TTFT timing per flow (using TTLCache to prevent memory leaks)
        # maxsize=10000: Maximum 10k concurrent requests tracked
        # ttl=300: Auto-evict entries after 5 minutes (prevents stale data accumulation)
        self._ttft_start_times: TTLCache[int, float] = TTLCache(maxsize=10000, ttl=300)
        
        # Initialize security components
        self.redactor = get_redactor()
        self.auth = get_auth()
        
        # Setup structured JSON logging with backpressure
        log_file_override = os.getenv("CHAOS_LOG_FILE")
        log_dir_override = os.getenv("CHAOS_LOG_DIR")
        if log_file_override:
            log_file_path = Path(log_file_override)
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            log_dir = Path(log_dir_override) if log_dir_override else Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file_path = log_dir / "proxy.log"
        self.log_file = open(log_file_path, 'a', encoding='utf-8')
        # Thread pool executor for non-blocking file I/O
        # max_workers=2: Limit concurrent log writes
        # Note: ThreadPoolExecutor uses an unbounded queue, so we implement backpressure
        # by tracking pending tasks and dropping logs if too many are queued
        self._log_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="log-writer")
        self._log_pending_tasks = 0  # Track number of pending log write tasks
        self._log_max_pending = 100  # Maximum pending tasks before dropping logs
        self._log_queue_full_count = 0  # Track dropped logs for monitoring
        self._log_pending_lock = threading.Lock()  # Lock for pending counter
        logger.info(f"Structured JSON logging enabled: {log_file_path}")
        
        # Thread-safe configuration reload lock
        self._config_lock = threading.RLock()
        
        # Load initial configuration
        self._reload_config()
        
        # Optionally start dashboard server inside the proxy process
        if self._dashboard_autostart and DASHBOARD_AVAILABLE and get_dashboard_server:
            self._start_dashboard_server()

        logger.info(
            f"ChaosProxyAddon initialized (mode={self.mode}) with {len(self.strategies)} strategies: "
            f"{[s.name for s in self.strategies]}"
        )
    
    def _reload_config(self) -> None:
        """
        Reload configuration from file and recreate strategies.
        
        This method checks if the config file has been modified and reloads if necessary.
        Uses atomic swap (copy-on-write) pattern to ensure thread-safe configuration updates.
        """
        # Fast path: Check hash without lock (read-only check)
        try:
            if not self.config_path.exists():
                with self._config_lock:
                    logger.warning(f"Configuration file not found: {self.config_path}")
                    # Use default empty config
                    self.config = ChaosConfig()
                    self.strategies = []
                return

            current_hash = self._compute_config_hash()

            # Only reload if file hash has changed (avoid lock contention)
            if current_hash == self._last_config_hash:
                return
        except OSError:
            # File may have been deleted/renamed, handle gracefully
            return
        
        # Slow path: Acquire lock and rebuild strategies (atomic swap)
        with self._config_lock:
            # Double-check hash after acquiring lock (another thread may have reloaded)
            try:
                current_hash = self._compute_config_hash()
                if current_hash == self._last_config_hash:
                    return
            except OSError:
                logger.warning(f"Configuration file disappeared: {self.config_path}")
                return
            
            try:
                # Load configuration
                new_config = load_config(str(self.config_path))
                old_config = self.config
                
                # Build new strategies list (this is the "copy" phase)
                new_strategies = []
                for strategy_config in new_config.strategies:
                    strategy = StrategyFactory.create(strategy_config)
                    if strategy is not None:
                        new_strategies.append(strategy)
                
                # Atomic swap: Replace old strategies with new ones
                # In Python, variable assignment is atomic (GIL ensures this)
                # This means readers will see either old or new list, never a partially built one
                self.config = new_config
                self.strategies = new_strategies  # Atomic swap
                self._last_config_hash = current_hash
                
                logger.info(
                    f"Configuration reloaded: {len(self.strategies)} strategies "
                    f"({sum(1 for s in self.strategies if s.enabled)} enabled)"
                )

                self._audit_config_change(old_config, new_config)
            
            except Exception as e:
                logger.error(f"Failed to reload configuration: {e}", exc_info=True)
                # Keep existing strategies on error (don't swap on failure)

    def _compute_config_hash(self) -> str:
        """
        Compute SHA-256 hash of the config file.
        """
        sha256 = hashlib.sha256()
        with open(self.config_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _audit_config_change(self, old_config: Optional[ChaosConfig], new_config: ChaosConfig) -> None:
        """
        Audit config and strategy state changes.
        """
        user_id = self._last_auth_context.user_id if self._last_auth_context else "system"
        outcome = "initial_load" if old_config is None else "reloaded"
        log_audit(user_id, "CONFIG_CHANGE", str(self.config_path), outcome)

        if old_config is None:
            return

        old_states = {s.name: s.enabled for s in old_config.strategies}
        new_states = {s.name: s.enabled for s in new_config.strategies}

        for name, enabled in new_states.items():
            if name not in old_states:
                continue
            if old_states[name] != enabled:
                state = "enabled" if enabled else "disabled"
                log_audit(user_id, "STATE_CHANGE", f"strategy:{name}", state)
    
    async def request(self, flow: http.HTTPFlow) -> None:
        """
        Mitmproxy request hook wrapper with fail-open safety.

        Any unexpected exception is logged and the flow continues unmodified.
        """
        try:
            await self._request_impl(flow)
        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error(
                f"CRITICAL: Unexpected error in request hook (fail-open - flow continues): {e}\n"
                f"Traceback:\n{error_traceback}",
                exc_info=False
            )

    async def _request_impl(self, flow: http.HTTPFlow) -> None:
        """
        Intercept and potentially modify outgoing requests.
        
        This method is called by mitmproxy for each request. It applies
        all enabled strategies that can modify requests. It also checks for
        configuration changes (hot reload).
        
        Creates OpenTelemetry spans to track chaos injection.
        
        This is an async method to support non-blocking strategy execution,
        allowing the proxy to handle multiple concurrent requests efficiently.
        
        Args:
            flow: The HTTP flow object containing request and response data.
        """
        # CRITICAL: PLAYBACK mode - return recorded response immediately (no network access)
        if self.mode == PROXY_MODE_PLAYBACK:
            await self._handle_playback_request(flow)
            return
        
        # Generate unique request ID for tracking
        request_id = f"req_{self._request_counter}_{id(flow)}"
        self._request_counter += 1
        flow.metadata["request_id"] = request_id
        
        # CRITICAL: Authentication check - must happen FIRST
        # Only authenticated requests can trigger chaos injection
        auth_context = self.auth.authenticate(flow, required_scope="READ")
        self._last_auth_context = auth_context if auth_context.allowed else None
        if not auth_context.allowed:
            self.auth.create_unauthorized_response(flow, required_scope="READ")
            # Log unauthorized attempt (with PII redaction)
            redacted_url = self.redactor.redact_url(flow.request.pretty_url)
            redacted_headers = self.redactor.redact_headers(dict(flow.request.headers))
            logger.warning(
                f"Unauthorized chaos control plane access attempt: "
                f"URL={redacted_url}, Headers={redacted_headers}"
            )
            log_audit(auth_context.user_id, "AUTH", redacted_url, "denied")
            return  # Do not process chaos logic for unauthorized requests
        
        # Hot reload: check for config changes (only in LIVE/RECORD modes)
        if self.mode != PROXY_MODE_PLAYBACK:
            self._reload_config()
        
        # CRITICAL: Classify traffic BEFORE applying strategies
        # This enables swarm-specific attacks
        classifier = get_classifier()
        traffic_type = await classifier.classify(flow)
        
        # Emit dashboard event: Request Started
        if DASHBOARD_AVAILABLE:
            await self._emit_dashboard_event(RequestStartedEvent(
                request_id=request_id,
                method=flow.request.method,
                url=self.redactor.redact_url(flow.request.pretty_url),
                agent_role=flow.metadata.get("agent_role"),
                traffic_type=traffic_type,
                traffic_subtype=flow.metadata.get(METADATA_TRAFFIC_SUBTYPE),
            ))
        
        # Extract trace context from incoming request headers
        # This links the proxy span to the victim agent's trace
        request_headers = dict(flow.request.headers)
        parent_context = extract_trace_context(request_headers)
        
        # Start a new span for proxy interception
        if parent_context:
            # Link to parent trace
            ctx = trace.set_span_in_context(trace.NonRecordingSpan(parent_context))
            span = tracer.start_span("chaos.proxy.intercept", context=ctx)
        else:
            # Start new trace if no parent context
            span = tracer.start_span("chaos.proxy.intercept")
        
        # Store span in flow metadata for later use
        flow.metadata["chaos_span"] = span
        
        # Extract agent role from headers (for group-based strategies)
        # SwarmFactory should inject X-Agent-Role header via custom httpx client
        # The proxy extracts it here for group-based chaos strategies
        agent_role = flow.request.headers.get("X-Agent-Role") or flow.request.headers.get("Agent-Role")
        
        # Fallback: Try to extract from User-Agent if it contains role info
        # (SwarmFactory can inject role in User-Agent as workaround)
        if not agent_role:
            user_agent = flow.request.headers.get("User-Agent", "")
            # Check for role= pattern in User-Agent
            if "role=" in user_agent.lower():
                parts = user_agent.split("role=")
                if len(parts) > 1:
                    agent_role = parts[1].split()[0].strip() if parts[1] else None
        
        # If still no role, try to infer from request patterns
        # (This is a fallback - ideally SwarmFactory injects the header)
        if not agent_role:
            # For now, we'll rely on SwarmFactory to inject via custom httpx client
            # or we can add role to User-Agent as a workaround
            pass
        
        if agent_role:
            span.set_attribute("agent.role", agent_role)
            # Store in flow metadata for strategies to use
            flow.metadata["agent_role"] = agent_role
            redacted_url = self.redactor.redact_url(flow.request.pretty_url)
            logger.debug(f"Extracted agent role: {agent_role} from request to {redacted_url}")
        
        # Add HTTP attributes (with PII redaction)
        redacted_url = self.redactor.redact_url(flow.request.pretty_url)
        span.set_attribute("http.method", flow.request.method)
        span.set_attribute("http.url", redacted_url)  # Redacted URL in spans
        span.set_attribute("http.host", flow.request.pretty_host)
        span.set_attribute("http.scheme", flow.request.scheme)
        
        # Add traffic classification to span
        span.set_attribute("traffic.type", traffic_type)
        if METADATA_TRAFFIC_SUBTYPE in flow.metadata:
            span.set_attribute("traffic.subtype", flow.metadata[METADATA_TRAFFIC_SUBTYPE])
        
        try:
            # Get or create context for this flow
            context = get_context(flow)
            
            # Track applied strategies
            applied_strategies = []
            
            # Thread-safe: Create local reference to strategies list
            # This ensures we use a consistent snapshot even if config reloads during iteration
            # Python's GIL makes list reference assignment atomic, so this is safe
            strategies_snapshot = self.strategies
            
            # Apply strategies to request phase (async)
            for strategy in strategies_snapshot:
                if not strategy.enabled:
                    continue
                
                try:
                    result = await strategy.intercept(flow)  # Await async strategy
                    if result:
                        context.add_strategy(strategy.name)
                        applied_strategies.append(strategy.name)
                        
                        # Add chaos attributes to span
                        span.set_attribute("chaos.injected", True)
                        span.set_attribute("chaos.strategy", strategy.name)
                        span.set_attribute("chaos.strategy_type", strategy.__class__.__name__)
                        
                        # Add strategy-specific attributes
                        if isinstance(strategy, LatencyStrategy):
                            span.set_attribute("chaos.latency_delay", strategy.delay)
                        elif isinstance(strategy, ErrorStrategy):
                            span.set_attribute("chaos.error_code", strategy.error_code)
                        elif isinstance(strategy, JSONCorruptionStrategy):
                            span.set_attribute("chaos.corruption_text", strategy.corruption_text)
                        elif isinstance(strategy, SemanticStrategy):
                            span.set_attribute("chaos.attack_mode", strategy.attack_mode)
                        elif isinstance(strategy, MCPProtocolFuzzingStrategy):
                            span.set_attribute("chaos.fuzz_type", strategy.fuzz_type)
                            if strategy.fuzz_type == "schema_violation":
                                span.set_attribute("chaos.schema_aware", True)
                                if strategy.field_mode:
                                    field_mode_json = await run_cpu_bound(json.dumps, strategy.field_mode)
                                    span.set_attribute("chaos.field_mode", field_mode_json)
                            if strategy.target_endpoint:
                                span.set_attribute("chaos.target_endpoint", strategy.target_endpoint)
                            # Create nested span for tool call fuzzing
                            await self._create_tool_call_span(span, flow, strategy)
                        elif isinstance(strategy, GroupChaosStrategy):
                            span.set_attribute("chaos.target_role", strategy.target_role)
                            span.set_attribute("chaos.group_action", strategy.action)
                            if strategy.action == "latency":
                                span.set_attribute("chaos.delay", strategy.delay)
                            elif strategy.action == "error":
                                span.set_attribute("chaos.error_code", strategy.error_code)
                        elif isinstance(strategy, GroupFailureStrategy):
                            span.set_attribute("chaos.target_role", strategy.target_role)
                            span.set_attribute("chaos.group_failure", True)
                        
                        # Record chaos injection metric with agent role
                        # Get agent role from flow metadata (set in request hook)
                        agent_role_for_chaos = flow.metadata.get("agent_role", "")
                        record_chaos_injection(strategy.name, model="unknown", agent_role=agent_role_for_chaos)
                        
                        # Emit dashboard event: Chaos Injected
                        if DASHBOARD_AVAILABLE:
                            await self._emit_dashboard_event(ChaosInjectedEvent(
                                request_id=request_id,
                                strategy_name=strategy.name,
                                phase="request",
                                details={"agent_role": agent_role_for_chaos}
                            ))
                        
                        redacted_url = self.redactor.redact_url(flow.request.pretty_url)
                        logger.debug(
                            f"Strategy {strategy.name} applied to request: "
                            f"{redacted_url}"
                        )
                        
                        # Log fuzzing event for scorecard analysis
                        if isinstance(strategy, MCPProtocolFuzzingStrategy):
                            # Log in format parseable by scorecard generator
                            logger.warning(
                                f"Schema-aware fuzzing applied by {strategy.name}: "
                                f"type={strategy.fuzz_type}"
                            )
                except Exception as e:
                    # Strategy failed - log but don't break the flow (fail-open)
                    # Circuit breaker will handle repeated failures and bypass the strategy
                    logger.warning(
                        f"Strategy '{strategy.name}' failed (circuit breaker will bypass if repeated): {e}",
                        exc_info=False  # Don't log full traceback for strategy failures
                    )
                    if span:
                        span.record_exception(e)
            
            # Add summary attribute
            if applied_strategies:
                span.set_attribute("chaos.strategies_applied", ",".join(applied_strategies))
            else:
                span.set_attribute("chaos.injected", False)
        
        except Exception as e:
            # CRITICAL: Global exception handler - fail-open behavior
            # Log the error but allow the flow to continue unmodified
            error_traceback = traceback.format_exc()
            logger.error(
                f"CRITICAL: Unexpected error in request hook (fail-open - flow continues): {e}\n"
                f"Traceback:\n{error_traceback}",
                exc_info=False  # Already have traceback above
            )
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
            # Don't raise - allow flow to continue unmodified (fail-open)
    
    async def responseheaders(self, flow: http.HTTPFlow) -> None:
        """
        Called when response headers are received (before response body).
        
        This is used to record the start time for TTFT calculation.
        
        Args:
            flow: The HTTP flow object.
        """
        # Record start time for TTFT calculation
        # Only for LLM API requests
        if self._is_llm_request(flow):
            self._ttft_start_times[id(flow)] = asyncio.get_event_loop().time()
    
    async def response(self, flow: http.HTTPFlow) -> None:
        """
        Mitmproxy response hook wrapper with fail-open safety.

        Any unexpected exception is logged and the flow continues unmodified.
        """
        try:
            await self._response_impl(flow)
        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.error(
                f"CRITICAL: Unexpected error in response hook (fail-open - flow continues): {e}\n"
                f"Traceback:\n{error_traceback}",
                exc_info=False
            )

    async def _response_impl(self, flow: http.HTTPFlow) -> None:
        """
        Intercept and potentially modify incoming responses.
        
        This method is called by mitmproxy for each response. It applies
        all enabled strategies that can modify responses. It also checks for
        configuration changes (hot reload).
        
        Updates OpenTelemetry span with response information and ends it.
        
        This is an async method to support non-blocking strategy execution,
        allowing the proxy to handle multiple concurrent requests efficiently.
        
        Args:
            flow: The HTTP flow object containing request and response data.
        """
        # Get span from flow metadata
        span = flow.metadata.get("chaos_span")
        
        # Get or create context for this flow
        context = get_context(flow)
        
        # Hot reload: check for config changes
        self._reload_config()
        
        if not flow.response:
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, "No response"))
                span.end()
            return
        
        try:
            # Extract agent role from headers (for group-based strategies)
            agent_role = flow.request.headers.get("X-Agent-Role") or flow.request.headers.get("Agent-Role")
            if agent_role and span:
                span.set_attribute("agent.role", agent_role)
            
            # Check if this is an LLM request for metrics
            is_llm_request = self._is_llm_request(flow)
            model = "unknown"
            
            # Try to extract model from request
            if flow.request.content:
                try:
                    body_text = flow.request.get_text()
                    if body_text:
                        body = await run_cpu_bound(json.loads, body_text)
                        model = body.get("model", "unknown")
                except (json.JSONDecodeError, AttributeError):
                    pass
            
            # Record AI request metric with agent role
            if is_llm_request:
                record_ai_request(model=model, agent_role=agent_role)
            
            # Log HTTP response for scorecard analysis (with PII redaction)
            if flow.response:
                redacted_url = self.redactor.redact_url(flow.request.pretty_url)
                logger.info(f"Response: {flow.response.status_code} for {redacted_url}")
            
            # Calculate and record TTFT (Time To First Token)
            # TTLCache supports get() and pop() like a dict, but pop() removes the item
            if is_llm_request and id(flow) in self._ttft_start_times:
                start_time = self._ttft_start_times.pop(id(flow), None)
                if start_time is not None:
                    current_time = asyncio.get_event_loop().time()
                    ttft = current_time - start_time
                    record_ttft(ttft, model=model, agent_role=agent_role)
                if span:
                    span.set_attribute("ai.ttft", ttft)
            
            # Estimate and record token usage
            if is_llm_request and flow.response:
                response_text = flow.response.get_text() or ""
                if response_text:
                    # Simple estimation: ~4 characters per token
                    estimated_tokens = len(response_text) // 4
                    record_token_usage(estimated_tokens, model=model, token_type="completion", agent_role=agent_role)
                    
                    # Also estimate prompt tokens from request
                    if flow.request.content:
                        try:
                            request_text = flow.request.get_text() or ""
                            if request_text:
                                prompt_tokens = len(request_text) // 4
                                record_token_usage(prompt_tokens, model=model, token_type="prompt", agent_role=agent_role)
                        except Exception:
                            pass
            
            # Add response attributes to span
            if span:
                span.set_attribute("http.status_code", flow.response.status_code)
                span.set_attribute("http.status_text", flow.response.reason or "")
            
            # Get context for this flow
            context = get_context(flow)
            
            # Track applied strategies in response phase
            applied_strategies = []
            
            # Thread-safe: Create local reference to strategies list
            # This ensures we use a consistent snapshot even if config reloads during iteration
            # Python's GIL makes list reference assignment atomic, so this is safe
            strategies_snapshot = self.strategies
            
            # Apply strategies to response phase (async)
            for strategy in strategies_snapshot:
                if not strategy.enabled:
                    continue
                
                try:
                    result = await strategy.intercept(flow)  # Await async strategy
                    if result:
                        context.add_strategy(strategy.name)
                        applied_strategies.append(strategy.name)
                        
                        # Update chaos attributes in span
                        if span:
                            span.set_attribute("chaos.injected", True)
                            span.set_attribute("chaos.strategy", strategy.name)
                            span.set_attribute("chaos.strategy_type", strategy.__class__.__name__)
                            
                            # Add strategy-specific attributes
                            if isinstance(strategy, LatencyStrategy):
                                span.set_attribute("chaos.latency_delay", strategy.delay)
                            elif isinstance(strategy, ErrorStrategy):
                                span.set_attribute("chaos.error_code", strategy.error_code)
                            elif isinstance(strategy, JSONCorruptionStrategy):
                                span.set_attribute("chaos.corruption_text", strategy.corruption_text)
                            elif isinstance(strategy, SemanticStrategy):
                                span.set_attribute("chaos.attack_mode", strategy.attack_mode)
                        
                        # Record chaos injection metric with agent role
                        agent_role_for_chaos = flow.metadata.get("agent_role", "")
                        record_chaos_injection(strategy.name, model=model if is_llm_request else "unknown", agent_role=agent_role_for_chaos)
                        
                        # Emit dashboard event: Chaos Injected (response phase)
                        if DASHBOARD_AVAILABLE:
                            request_id = flow.metadata.get("request_id", "unknown")
                            await self._emit_dashboard_event(ChaosInjectedEvent(
                                request_id=request_id,
                                strategy_name=strategy.name,
                                phase="response",
                                details={"model": model, "agent_role": agent_role_for_chaos}
                            ))
                        
                        redacted_url = self.redactor.redact_url(flow.request.pretty_url)
                        logger.debug(
                            f"Strategy {strategy.name} applied to response: "
                            f"{redacted_url}"
                        )
                except Exception as e:
                    # Strategy failed - log but don't break the flow (fail-open)
                    # Circuit breaker will handle repeated failures and bypass the strategy
                    logger.warning(
                        f"Strategy '{strategy.name}' failed (circuit breaker will bypass if repeated): {e}",
                        exc_info=False  # Don't log full traceback for strategy failures
                    )
                    if span:
                        span.record_exception(e)
            
            # Update summary attribute
            # Get existing strategies from context if available
            if span and applied_strategies:
                # Get all applied strategies from context (includes request phase)
                all_applied = context.applied_strategies
                if all_applied:
                    span.set_attribute("chaos.strategies_applied", ",".join(all_applied))
                else:
                    span.set_attribute("chaos.strategies_applied", ",".join(applied_strategies))
            
            # Set span status based on HTTP status code
            if span:
                if flow.response.status_code >= 400:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, f"HTTP {flow.response.status_code}"))
                else:
                    span.set_status(trace.Status(trace.StatusCode.OK))
            
            # Emit dashboard event: Response Received
            if DASHBOARD_AVAILABLE:
                request_id = flow.metadata.get("request_id", "unknown")
                response_size = len(flow.response.content) if flow.response.content else None
                latency_ms = None
                if id(flow) in self._ttft_start_times:
                    start_time = self._ttft_start_times.pop(id(flow), None)
                    if start_time is not None:
                        current_time = asyncio.get_event_loop().time()
                        latency_ms = (current_time - start_time) * 1000  # Convert to milliseconds
                
                await self._emit_dashboard_event(ResponseReceivedEvent(
                    request_id=request_id,
                    status_code=flow.response.status_code,
                    success=flow.response.status_code < 400,
                    response_size=response_size,
                    latency_ms=latency_ms,
                ))
                
                # Emit swarm message event if applicable
                if traffic_type == "AGENT_TO_AGENT":
                    await self._emit_dashboard_event(SwarmMessageEvent(
                        request_id=request_id,
                        from_agent=flow.metadata.get("agent_role"),
                        to_agent=None,  # Could be extracted from URL or headers
                        message_type=flow.metadata.get(METADATA_TRAFFIC_SUBTYPE, "agent_to_agent"),
                        mutated=len(all_applied_strategies) > 0,
                    ))
            
            # RECORD mode: Save to tape after all chaos logic is applied
            all_applied_strategies = context.applied_strategies if context else applied_strategies
            if self.mode == PROXY_MODE_RECORD and self.tape_recorder:
                await self._record_to_tape(flow, agent_role, all_applied_strategies)
            
            # Write structured JSON log entry (after all chaos logic is applied)
            await self._write_log_entry(flow, agent_role, all_applied_strategies)
        
        except Exception as e:
            # CRITICAL: Global exception handler - fail-open behavior
            # Log the error but allow the flow to continue unmodified
            error_traceback = traceback.format_exc()
            logger.error(
                f"CRITICAL: Unexpected error in response hook (fail-open - flow continues): {e}\n"
                f"Traceback:\n{error_traceback}",
                exc_info=False  # Already have traceback above
            )
            if span:
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                span.record_exception(e)
            
            # Try to write log entry even on error
            try:
                await self._write_log_entry(flow, agent_role, [])
            except Exception:
                pass  # Don't fail on logging errors
            # Don't raise - allow flow to continue unmodified (fail-open)
        
        finally:
            # End the span
            if span:
                span.end()
            
            # Clear context and timing data after processing
            clear_context(flow)
            # Clean up TTFT timing if still present (TTLCache will auto-evict, but explicit cleanup is safe)
            # Note: TTLCache handles eviction automatically, but we can still remove if needed
            if id(flow) in self._ttft_start_times:
                self._ttft_start_times.pop(id(flow), None)
    
    async def _create_tool_call_span(
        self,
        parent_span: trace.Span,
        flow: http.HTTPFlow,
        strategy: BaseStrategy
    ) -> None:
        """
        Create a nested span for tool call fuzzing.
        
        This allows us to see in Jaeger: Planner -> (Chaos: Fuzzed Params) -> Searcher
        
        Args:
            parent_span: Parent span (chaos.proxy.intercept).
            flow: HTTP flow object.
            strategy: The strategy that was applied.
        """
        try:
            if not flow.request.content:
                return
            
            body_text = flow.request.get_text()
            if not body_text:
                return
            body = await run_cpu_bound(json.loads, body_text)
            
            # Detect tool calls
            tool_calls = []
            
            # Check for OpenAI format
            if "messages" in body:
                for message in body.get("messages", []):
                    if "tool_calls" in message:
                        tool_calls.extend(message["tool_calls"])
                    elif "function_call" in message:
                        tool_calls.append(message["function_call"])
            
            # Check for Anthropic format
            if "messages" in body:
                for message in body.get("messages", []):
                    if isinstance(message, dict) and "content" in message:
                        content = message["content"]
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "tool_use":
                                    tool_calls.append(block)
            
            # Create nested spans for each tool call
            for i, tool_call in enumerate(tool_calls):
                with tracer.start_as_current_span(
                    "chaos.tool_call.fuzz",
                    context=trace.set_span_in_context(parent_span)
                ) as tool_span:
                    # Extract tool/function name
                    tool_name = "unknown"
                    if isinstance(tool_call, dict):
                        if "function" in tool_call:
                            tool_name = tool_call["function"].get("name", "unknown")
                        elif "name" in tool_call:
                            tool_name = tool_call["name"]
                        elif "function_name" in tool_call:
                            tool_name = tool_call["function_name"]
                    
                    tool_span.set_attribute("tool.name", tool_name)
                    tool_span.set_attribute("tool.index", i)
                    tool_span.set_attribute("chaos.strategy", strategy.name)
                    tool_span.set_attribute("chaos.fuzzed", True)
                    
                    if isinstance(strategy, MCPProtocolFuzzingStrategy):
                        tool_span.set_attribute("chaos.fuzz_type", strategy.fuzz_type)
                    
                    logger.debug(
                        f"Created tool call span: {tool_name} "
                        f"(fuzzed by {strategy.name})"
                    )
        
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            logger.debug(f"Could not create tool call span: {e}")
    
    async def _log_request(self, flow: http.HTTPFlow, span: Optional[trace.Span], context) -> None:
        """
        Log structured JSON entry for a request/response.
        
        This method uses async file I/O to avoid blocking the event loop.
        
        Args:
            flow: HTTP flow object
            span: OpenTelemetry span (optional)
            context: Request context
        """
        try:
            # Detect tool name from URL
            tool_name = None
            url = flow.request.pretty_url.lower()
            if "/search_flights" in url:
                tool_name = "search_flights"
            elif "/book_ticket" in url or "/book" in url:
                tool_name = "book_ticket"
            elif "/api/" in url or "/v1/chat" in url:
                tool_name = "llm_request"
            
            # Check if any chaos was applied
            chaos_applied = []
            fuzzed = False
            
            # Get applied strategies from context or span attributes
            applied_strategies = []
            if hasattr(context, 'applied_strategies'):
                applied_strategies = context.applied_strategies
            elif span:
                # Try to get from span attributes
                strategies_attr = span.attributes.get("chaos.strategies_applied")
                if strategies_attr:
                    applied_strategies = strategies_attr.split(",")
            
            for strategy_name in applied_strategies:
                chaos_applied.append(strategy_name)
                # Check if fuzzing was applied
                if "fuzzing" in strategy_name.lower() or "mcp" in strategy_name.lower():
                    fuzzed = True
            
            # Extract agent role if available
            agent_role = flow.request.headers.get("X-Agent-Role") or flow.request.headers.get("Agent-Role") or None
            
            # CRITICAL: Redact PII before logging
            redacted_url = self.redactor.redact_url(flow.request.pretty_url)
            
            # Get traffic classification from flow metadata
            traffic_type = flow.metadata.get(METADATA_TRAFFIC_TYPE, "UNKNOWN")
            traffic_subtype = flow.metadata.get(METADATA_TRAFFIC_SUBTYPE)
            
            # Build log entry with redacted data
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "method": flow.request.method,
                "url": redacted_url,  # Redacted URL
                "status_code": flow.response.status_code if flow.response else None,
                "tool_name": tool_name,
                "agent_role": agent_role,
                "chaos_applied": chaos_applied if chaos_applied else None,
                "fuzzed": fuzzed,
                "traffic_type": traffic_type,  # From classifier
                "traffic_subtype": traffic_subtype,  # From classifier
            }
            
            # Write JSON line to file asynchronously (non-blocking)
            # Implement backpressure: if too many logs are pending, drop log rather than blocking
            log_line = await run_cpu_bound(json.dumps, log_entry, ensure_ascii=False)
            log_line = log_line + "\n"
            
            # Check if we should drop this log due to backpressure
            with self._log_pending_lock:
                if self._log_pending_tasks >= self._log_max_pending:
                    # Too many pending tasks, drop this log
                    self._log_queue_full_count += 1
                    if self._log_queue_full_count % 100 == 1:  # Log every 100th drop to avoid spam
                        logger.warning(
                            f"Log queue full ({self._log_pending_tasks} pending), dropping logs "
                            f"(total dropped: {self._log_queue_full_count}). "
                            f"Consider increasing log workers or reducing log volume."
                        )
                    return  # Drop this log
                # Increment pending counter before submitting
                self._log_pending_tasks += 1
            
            # Submit log write to executor (non-blocking)
            loop = asyncio.get_event_loop()
            try:
                loop.run_in_executor(
                    self._log_executor,
                    self._write_log_sync,
                    log_line
                )
                # Note: We don't await the future - it runs in background
                # The _write_log_sync method will decrement the counter when done
            except Exception as e:
                # If submission fails, decrement counter
                with self._log_pending_lock:
                    self._log_pending_tasks = max(0, self._log_pending_tasks - 1)
                logger.debug(f"Error submitting log write: {e}")
            
        except Exception as e:
            logger.error(f"Error logging request: {e}", exc_info=True)
    
    def done(self) -> None:
        """
        Called when the proxy is shutting down.
        Clean up resources (close log file and executor, save tape).
        """
        # RECORD mode: Save tape before shutdown
        if self.mode == PROXY_MODE_RECORD and self.tape_recorder:
            try:
                tape_path = self.tape_recorder.save()
                logger.info(f"Tape saved: {tape_path} ({len(self.tape_recorder.tape.entries)} entries)")
            except Exception as e:
                logger.error(f"Error saving tape: {e}", exc_info=True)
        
        # Shutdown thread pool executor
        if hasattr(self, '_log_executor') and self._log_executor:
            self._log_executor.shutdown(wait=True)
            if hasattr(self, '_log_queue_full_count') and self._log_queue_full_count > 0:
                logger.info(
                    f"Log executor shutdown. Total logs dropped due to backpressure: {self._log_queue_full_count}"
                )
            else:
                logger.info("Log executor shutdown")
        
        # Close log file
        if hasattr(self, 'log_file') and self.log_file:
            try:
                self.log_file.close()
                logger.info("Structured JSON log file closed")
            except Exception as e:
                logger.error(f"Error closing log file: {e}")

        # Stop dashboard server if we started it
        if self._dashboard_autostart and self.dashboard_server and self._dashboard_loop:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.dashboard_server.stop(),
                    self._dashboard_loop
                )
                future.result(timeout=5)
                self._dashboard_loop.call_soon_threadsafe(self._dashboard_loop.stop)
                logger.info("Dashboard server stopped")
            except Exception as e:
                logger.warning(f"Error stopping dashboard server: {e}")
    
    async def _write_log_entry(self, flow: http.HTTPFlow, agent_role: Optional[str], applied_strategies: List[str]) -> None:
        """
        Write a structured JSON log entry for a request/response.
        
        CRITICAL: All PII is redacted before logging to prevent sensitive data
        from being written to disk.
        
        Args:
            flow: The HTTP flow object.
            agent_role: Agent role (if available).
            applied_strategies: List of applied strategy names.
        """
        try:
            # CRITICAL: Redact URL before processing
            url = flow.request.pretty_url
            redacted_url = self.redactor.redact_url(url)
            url_lower = redacted_url.lower()
            
            # Detect tool name from redacted URL
            tool_name = None
            if "/search_flights" in url_lower:
                tool_name = "search_flights"
            elif "/book_ticket" in url_lower or "/book" in url_lower:
                tool_name = "book_ticket"
            
            # Get applied strategies
            metadata_applied = flow.metadata.get("chaos_applied")
            if isinstance(metadata_applied, list):
                merged = list(dict.fromkeys((applied_strategies or []) + metadata_applied))
            else:
                merged = applied_strategies or []
            chaos_applied = ",".join(merged) if merged else None
            
            # Detect if data was fuzzed
            fuzzed = False
            if applied_strategies and any("fuzzing" in s.lower() or "mcp" in s.lower() or "corruption" in s.lower() for s in applied_strategies):
                fuzzed = True
            
            # Get agent role if available
            if not agent_role:
                agent_role = flow.metadata.get("agent_role") or flow.request.headers.get("X-Agent-Role")
            
            # Get traffic classification from flow metadata
            traffic_type = flow.metadata.get(METADATA_TRAFFIC_TYPE, "UNKNOWN")
            traffic_subtype = flow.metadata.get(METADATA_TRAFFIC_SUBTYPE)
            
            # Create log entry with redacted data
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "method": flow.request.method,
                "url": redacted_url,  # Redacted URL
                "status_code": flow.response.status_code if flow.response else None,
                "chaos_applied": chaos_applied,
                "tool_name": tool_name,
                "fuzzed": fuzzed,
                "agent_role": agent_role,
                "traffic_type": traffic_type,  # From classifier
                "traffic_subtype": traffic_subtype,  # From classifier
            }
            
            # Write JSON line to file asynchronously (non-blocking)
            # Implement backpressure: if too many logs are pending, drop log rather than blocking
            log_line = await run_cpu_bound(json.dumps, log_entry, ensure_ascii=False)
            log_line = log_line + "\n"
            
            # Check if we should drop this log due to backpressure
            with self._log_pending_lock:
                if self._log_pending_tasks >= self._log_max_pending:
                    # Too many pending tasks, drop this log
                    self._log_queue_full_count += 1
                    if self._log_queue_full_count % 100 == 1:  # Log every 100th drop to avoid spam
                        logger.warning(
                            f"Log queue full ({self._log_pending_tasks} pending), dropping logs "
                            f"(total dropped: {self._log_queue_full_count}). "
                            f"Consider increasing log workers or reducing log volume."
                        )
                    return  # Drop this log
                # Increment pending counter before submitting
                self._log_pending_tasks += 1
            
            # Submit log write to executor (non-blocking)
            loop = asyncio.get_event_loop()
            try:
                loop.run_in_executor(
                    self._log_executor,
                    self._write_log_sync,
                    log_line
                )
                # Note: We don't await the future - it runs in background
                # The _write_log_sync method will decrement the counter when done
            except Exception as e:
                # If submission fails, decrement counter
                with self._log_pending_lock:
                    self._log_pending_tasks = max(0, self._log_pending_tasks - 1)
                logger.debug(f"Error submitting log write: {e}")
            
        except Exception as e:
            # Don't let logging errors break the proxy
            logger.debug(f"Error writing log entry: {e}")
    
    def _write_log_sync(self, log_line: str) -> None:
        """
        Synchronous file write helper for thread pool executor.
        
        This method is called from a thread pool to avoid blocking
        the async event loop with file I/O operations.
        
        Args:
            log_line: JSON log line to write.
        """
        try:
            self.log_file.write(log_line)
            self.log_file.flush()  # Critical for real-time reporting
        except Exception as e:
            logger.error(f"Error in synchronous log write: {e}")
    
    def _is_llm_request(self, flow: http.HTTPFlow) -> bool:
        """
        Check if this is an LLM API request.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if this appears to be an LLM API request.
        """
        # Check URL patterns common to LLM APIs
        url = flow.request.pretty_url.lower()
        llm_patterns = [
            "/api/chat",
            "/v1/chat/completions",
            "/api/generate",
            "/api/completions",
        ]
        
        return any(pattern in url for pattern in llm_patterns)
    
    async def _handle_playback_request(self, flow: http.HTTPFlow) -> None:
        """
        Handle request in PLAYBACK mode (return recorded response, no network access).
        
        Args:
            flow: The HTTP flow object.
        """
        request_id = flow.metadata.get("request_id")
        if not request_id:
            request_id = f"req_{self._request_counter}_{id(flow)}"
            self._request_counter += 1
            flow.metadata["request_id"] = request_id

        if not self.tape_player:
            logger.error("TapePlayer not initialized in PLAYBACK mode")
            # Create error response
            error_response = flow.request.make_response(
                content=b'{"error": "TapePlayer not initialized"}',
                status_code=500,
                headers={"Content-Type": "application/json"}
            )
            flow.response = error_response
            return
        
        # Extract request information
        method = flow.request.method
        url = flow.request.pretty_url
        body = flow.request.content
        headers = dict(flow.request.headers)
        
        # Find matching entry in tape
        entry = self.tape_player.find_match(method, url, body, headers)
        
        if not entry:
            logger.warning(f"No match found in tape for {method} {url}")
            # Create 404 response
            error_response = flow.request.make_response(
                content=b'{"error": "No matching entry in tape"}',
                status_code=404,
                headers={"Content-Type": "application/json"}
            )
            flow.response = error_response
            return
        
        # Reconstruct response from snapshot
        response_snapshot = entry.response
        
        # Create response from snapshot
        from mitmproxy import http as http_module
        response_headers = http_module.Headers([
            (k.encode() if isinstance(k, str) else k, 
             v.encode() if isinstance(v, str) else v)
            for k, v in response_snapshot.headers.items()
        ])
        
        response = http_module.Response(
            http_version=b"HTTP/1.1",
            status_code=response_snapshot.status_code,
            reason=response_snapshot.reason.encode('utf-8') if isinstance(response_snapshot.reason, str) else response_snapshot.reason,
            headers=response_headers,
            content=response_snapshot.content,
            trailers=http_module.Headers(),
            timestamp_start=asyncio.get_event_loop().time(),
            timestamp_end=asyncio.get_event_loop().time(),
        )
        
        # Restore Content-Encoding if present
        if response_snapshot.content_encoding:
            response.headers["Content-Encoding"] = response_snapshot.content_encoding
        
        flow.response = response
        
        # Store chaos context in flow metadata for logging
        flow.metadata["chaos_context"] = entry.chaos_context
        flow.metadata[METADATA_TRAFFIC_TYPE] = entry.chaos_context.traffic_type or "UNKNOWN"
        if entry.chaos_context.traffic_subtype:
            flow.metadata[METADATA_TRAFFIC_SUBTYPE] = entry.chaos_context.traffic_subtype

        if DASHBOARD_AVAILABLE and self.dashboard_server:
            await self._emit_dashboard_event(RequestStartedEvent(
                request_id=request_id,
                method=method,
                url=self.redactor.redact_url(url),
                agent_role=entry.chaos_context.agent_role,
                traffic_type=entry.chaos_context.traffic_type or "UNKNOWN",
                traffic_subtype=entry.chaos_context.traffic_subtype,
            ))
            await self._emit_dashboard_event(ResponseReceivedEvent(
                request_id=request_id,
                status_code=response_snapshot.status_code,
                success=200 <= response_snapshot.status_code < 400,
                response_size=len(response_snapshot.content) if response_snapshot.content else 0,
                latency_ms=None,
            ))
        
        redacted_url = self.redactor.redact_url(url)
        logger.info(
            f"PLAYBACK: Matched {method} {redacted_url} -> {response_snapshot.status_code} "
            f"(sequence {entry.sequence}, chaos: {entry.chaos_context.chaos_applied})"
        )
    
    async def _record_to_tape(
        self,
        flow: http.HTTPFlow,
        agent_role: Optional[str],
        applied_strategies: List[str]
    ) -> None:
        """
        Record request-response pair to tape in RECORD mode.
        
        Args:
            flow: The HTTP flow object.
            agent_role: Agent role if available.
            applied_strategies: List of applied strategy names.
        """
        if not flow.response:
            return
        
        try:
            # Extract request information
            method = flow.request.method
            url = flow.request.pretty_url
            body = flow.request.content
            headers = dict(flow.request.headers)
            
            # Extract response information
            response_status = flow.response.status_code
            response_reason = flow.response.reason or "OK"
            response_headers = {
                k.decode('utf-8', errors='ignore') if isinstance(k, bytes) else str(k):
                v.decode('utf-8', errors='ignore') if isinstance(v, bytes) else str(v)
                for k, v in flow.response.headers.items()
            }
            response_content = flow.response.content or b""
            response_encoding = None
            if "Content-Encoding" in flow.response.headers:
                enc = flow.response.headers["Content-Encoding"]
                response_encoding = enc.decode('utf-8', errors='ignore') if isinstance(enc, bytes) else str(enc)
            
            # Create chaos context
            chaos_context = ChaosContext(
                applied_strategies=applied_strategies,
                chaos_applied=len(applied_strategies) > 0,
                traffic_type=flow.metadata.get(METADATA_TRAFFIC_TYPE),
                traffic_subtype=flow.metadata.get(METADATA_TRAFFIC_SUBTYPE),
                agent_role=agent_role,
            )
            
            # Record to tape
            await run_cpu_bound(
                self.tape_recorder.record,
                method,
                url,
                body,
                headers,
                response_status,
                response_reason,
                response_headers,
                response_content,
                response_encoding,
                chaos_context,
            )
            
        except Exception as e:
            logger.error(f"Error recording to tape: {e}", exc_info=True)
    
    async def _emit_dashboard_event(self, event: DashboardEvent) -> None:
        """
        Emit an event to the dashboard server (if available).
        
        Args:
            event: DashboardEvent instance to emit.
        """
        if not self.dashboard_server:
            return
        
        try:
            await self.dashboard_server.broadcast_event(event)
        except Exception as e:
            logger.debug(f"Error emitting dashboard event: {e}")
    
    def set_dashboard_server(self, server) -> None:
        """
        Set the dashboard server instance.
        
        Args:
            server: DashboardServer instance.
        """
        self.dashboard_server = server

    def _start_dashboard_server(self) -> None:
        """
        Start dashboard server in a background thread (proxy process).
        """
        try:
            self.dashboard_server = get_dashboard_server(port=8081, host="127.0.0.1")

            def run_dashboard():
                try:
                    loop = asyncio.new_event_loop()
                    self._dashboard_loop = loop
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.dashboard_server.start())
                    loop.run_forever()
                except Exception as e:
                    logger.error(f"Dashboard server error: {e}", exc_info=True)

            self._dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
            self._dashboard_thread.start()
            logger.info("Dashboard server started in proxy process")
        except Exception as e:
            logger.warning(f"Failed to start dashboard server: {e}", exc_info=True)


# Create addon instance
# This is what mitmproxy will load
addons = [ChaosProxyAddon()]
