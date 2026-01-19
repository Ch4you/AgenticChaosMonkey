"""
OpenTelemetry utilities for distributed tracing and metrics.

This module provides OpenTelemetry tracing and metrics setup with trace context
propagation for observability across the chaos engineering platform.
"""

import logging
import os
from typing import Dict, Optional
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import View, ExplicitBucketHistogramAggregation
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.propagate import inject, extract

from agent_chaos_sdk.common.logger import get_logger

logger = get_logger(__name__)

# Global providers
_tracer_provider: Optional[TracerProvider] = None
_tracer: Optional[trace.Tracer] = None
_meter_provider: Optional[MeterProvider] = None
_meter: Optional[metrics.Meter] = None

# Global metrics instruments
_ai_requests_counter: Optional[metrics.Counter] = None
_ai_token_usage_counter: Optional[metrics.Counter] = None
_ai_latency_ttft_histogram: Optional[metrics.Histogram] = None
_ai_chaos_injections_counter: Optional[metrics.Counter] = None
_chaos_injection_skipped_counter: Optional[metrics.Counter] = None
_error_code_counter: Optional[metrics.Counter] = None


def _get_trace_sample_rate() -> float:
    """
    Get trace sampling rate from environment.

    Uses OTEL_SAMPLE_RATE, defaults to 0.1 (10%).
    Ensures value is clamped between 0.0 and 1.0.
    """
    raw_value = os.getenv("OTEL_SAMPLE_RATE", "0.1")
    try:
        rate = float(raw_value)
    except ValueError:
        logger.warning(f"Invalid OTEL_SAMPLE_RATE='{raw_value}', defaulting to 0.1")
        return 0.1

    if rate < 0.0 or rate > 1.0:
        logger.warning(f"OTEL_SAMPLE_RATE out of range ({rate}), clamping to [0.0, 1.0]")
        rate = max(0.0, min(1.0, rate))

    return rate


def setup_telemetry(
    service_name: str,
    otlp_endpoint: str = "http://localhost:4317"
) -> trace.Tracer:
    """
    Setup OpenTelemetry tracing and metrics with OTLP exporters.
    
    Configures both TracerProvider and MeterProvider with OTLP exporters
    sending data to OpenTelemetry Collector via OTLP gRPC endpoint.
    
    Args:
        service_name: Name of the service (e.g., "victim-agent", "chaos-proxy").
        otlp_endpoint: OTLP gRPC endpoint URL (default: "http://localhost:4317").
        
    Returns:
        Tracer instance for creating spans.
    """
    global _tracer_provider, _tracer, _meter_provider, _meter
    global _ai_requests_counter, _ai_token_usage_counter, _ai_latency_ttft_histogram, _ai_chaos_injections_counter
    global _chaos_injection_skipped_counter, _error_code_counter
    
    try:
        # Allow environment override for containerized deployments
        endpoint_from_env = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint_from_env:
            otlp_endpoint = endpoint_from_env
            logger.info(f"Using OTLP endpoint from env OTEL_EXPORTER_OTLP_ENDPOINT={otlp_endpoint}")
        # Create resource with service name
        resource = Resource.create({
            "service.name": service_name,
            "service.version": "1.0.0",
        })
        
        # Setup Tracing with sampling
        sample_rate = _get_trace_sample_rate()
        _tracer_provider = TracerProvider(
            resource=resource,
            sampler=TraceIdRatioBased(sample_rate)
        )
        otlp_trace_exporter = OTLPSpanExporter(
            endpoint=otlp_endpoint,
            insecure=True,  # For local development
        )
        span_processor = BatchSpanProcessor(otlp_trace_exporter)
        _tracer_provider.add_span_processor(span_processor)
        trace.set_tracer_provider(_tracer_provider)
        _tracer = trace.get_tracer(__name__)
        
        # Setup Metrics
        otlp_metric_exporter = OTLPMetricExporter(
            endpoint=otlp_endpoint,
            insecure=True,  # For local development
        )
        metric_reader = PeriodicExportingMetricReader(otlp_metric_exporter, export_interval_millis=5000)
        # Define histogram buckets optimized for latency (seconds)
        latency_buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]

        # Apply explicit bucket boundaries to latency histogram
        views = [
            View(
                instrument_name="ai_latency_ttft",
                aggregation=ExplicitBucketHistogramAggregation(boundaries=latency_buckets),
            )
        ]

        _meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
            views=views,
        )
        metrics.set_meter_provider(_meter_provider)
        _meter = metrics.get_meter(__name__)
        
        # Create metrics instruments
        _ai_requests_counter = _meter.create_counter(
            name="ai_requests_total",
            description="Total number of AI requests",
            unit="1"
        )
        
        _ai_token_usage_counter = _meter.create_counter(
            name="ai_token_usage",
            description="Total token usage (estimated)",
            unit="token"
        )
        
        _ai_latency_ttft_histogram = _meter.create_histogram(
            name="ai_latency_ttft",
            description="Time to first token (TTFT) in seconds",
            unit="s"
        )
        
        _ai_chaos_injections_counter = _meter.create_counter(
            name="ai_chaos_injections",
            description="Total number of chaos injections",
            unit="1"
        )

        _chaos_injection_skipped_counter = _meter.create_counter(
            name="chaos_injection_skipped_total",
            description="Total number of skipped chaos injections",
            unit="1"
        )

        _error_code_counter = _meter.create_counter(
            name="chaos_error_codes_total",
            description="Total number of chaos errors by code",
            unit="1"
        )
        
        logger.info(
            f"OpenTelemetry tracing and metrics initialized for service '{service_name}' "
            f"with OTLP endpoint: {otlp_endpoint} (sample_rate={sample_rate})"
        )
        
        return _tracer
    
    except Exception as e:
        logger.error(f"Failed to setup OpenTelemetry: {e}", exc_info=True)
        # Return a no-op tracer if setup fails
        return trace.NoOpTracer()


def get_tracer() -> trace.Tracer:
    """
    Get the global tracer instance.
    
    Returns:
        Tracer instance, or NoOpTracer if not initialized.
    """
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(__name__)
    return _tracer


def inject_trace_context(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Inject trace context into HTTP headers for propagation.
    
    This allows trace context to be propagated across service boundaries.
    
    Args:
        headers: Dictionary of HTTP headers (will be modified in-place).
        
    Returns:
        Updated headers dictionary with trace context injected.
    """
    try:
        inject(headers)
        logger.debug("Trace context injected into headers")
    except Exception as e:
        logger.warning(f"Failed to inject trace context: {e}")
    
    return headers


def extract_trace_context(headers: Dict[str, str]) -> Optional[trace.SpanContext]:
    """
    Extract trace context from HTTP headers.
    
    This allows the proxy to link its spans to the victim agent's trace.
    
    Args:
        headers: Dictionary of HTTP headers containing trace context.
        
    Returns:
        SpanContext extracted from headers, or None if not found.
    """
    try:
        context = extract(headers)
        span_context = trace.get_current_span(context).get_span_context()
        
        if span_context.is_valid:
            logger.debug(f"Trace context extracted: trace_id={span_context.trace_id}")
            return span_context
        else:
            logger.debug("No valid trace context found in headers")
            return None
    
    except Exception as e:
        logger.warning(f"Failed to extract trace context: {e}")
        return None


def get_meter() -> metrics.Meter:
    """
    Get the global meter instance.
    
    Returns:
        Meter instance, or NoOpMeter if not initialized.
    """
    global _meter
    if _meter is None:
        _meter = metrics.get_meter(__name__)
    return _meter


def record_ai_request(model: str = "unknown", agent_role: Optional[str] = None) -> None:
    """
    Record an AI request.
    
    Args:
        model: Model name (e.g., "llama3.2").
        agent_role: Optional agent role (ignored to prevent high cardinality).
    """
    global _ai_requests_counter
    if _ai_requests_counter:
        _ai_requests_counter.add(1, {"model": model})
    else:
        logger.warning("Metrics not initialized, cannot record AI request")


def record_token_usage(tokens: int, model: str = "unknown", token_type: str = "completion", agent_role: Optional[str] = None) -> None:
    """
    Record token usage.
    
    Args:
        tokens: Number of tokens (estimated or actual).
        model: Model name.
        token_type: Type of tokens - "prompt" or "completion".
        agent_role: Optional agent role (ignored to prevent high cardinality).
    """
    global _ai_token_usage_counter
    if _ai_token_usage_counter:
        _ai_token_usage_counter.add(tokens, {"model": model, "type": token_type})
    else:
        logger.warning("Metrics not initialized, cannot record token usage")


def record_ttft(seconds: float, model: str = "unknown", agent_role: Optional[str] = None) -> None:
    """
    Record Time To First Token (TTFT).
    
    Args:
        seconds: TTFT in seconds.
        model: Model name.
        agent_role: Optional agent role (ignored to prevent high cardinality).
    """
    global _ai_latency_ttft_histogram
    if _ai_latency_ttft_histogram:
        _ai_latency_ttft_histogram.record(seconds, {"model": model})
    else:
        logger.warning("Metrics not initialized, cannot record TTFT")


def record_chaos_injection(strategy: str, model: str = "unknown", agent_role: Optional[str] = None) -> None:
    """
    Record a chaos injection event.
    
    Args:
        strategy: Strategy name that was applied.
        model: Model name (if applicable).
        agent_role: Optional agent role (ignored to prevent high cardinality).
    """
    global _ai_chaos_injections_counter
    if _ai_chaos_injections_counter:
        _ai_chaos_injections_counter.add(1, {"strategy": strategy, "model": model})
    else:
        logger.warning("Metrics not initialized, cannot record chaos injection")


def record_chaos_injection_skipped(strategy_type: str, reason: str) -> None:
    """
    Record a skipped chaos injection event.

    Args:
        strategy_type: Strategy type identifier (e.g., "rag").
        reason: Skip reason (e.g., "jsonpath_miss", "parsing_error").
    """
    global _chaos_injection_skipped_counter
    if _chaos_injection_skipped_counter:
        _chaos_injection_skipped_counter.add(1, {"strategy_type": strategy_type, "reason": reason})
    else:
        logger.warning("Metrics not initialized, cannot record skipped chaos injection")


def record_error_code(error_code: str, strategy: Optional[str] = None) -> None:
    """
    Record a structured error code for observability.
    """
    global _error_code_counter
    if _error_code_counter:
        attrs = {"error_code": error_code}
        if strategy:
            attrs["strategy"] = strategy
        _error_code_counter.add(1, attrs)
    else:
        logger.warning("Metrics not initialized, cannot record error code")
