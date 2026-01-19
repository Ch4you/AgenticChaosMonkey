from agent_chaos_sdk.common.telemetry import setup_telemetry, record_chaos_injection_skipped


def test_setup_telemetry_and_skip_metric() -> None:
    tracer = setup_telemetry("test-service", otlp_endpoint="http://localhost:4317")
    assert tracer is not None

    # Should not raise even if metrics exporter is not running
    record_chaos_injection_skipped(strategy_type="rag", reason="jsonpath_miss")
