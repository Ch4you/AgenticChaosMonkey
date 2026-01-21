# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **pyproject.toml**: Modern Python project configuration (PEP 518/621)
- **Sphinx Documentation**: Complete API documentation system
- **Documentation Organization**: All markdown files moved to `docs/markdown/`
- Comprehensive project review and optimization
- CONTRIBUTING.md with contribution guidelines
- CHANGELOG.md for tracking changes
- Improved dependency management

### Changed
- **Documentation Structure**: All markdown documentation moved to `docs/markdown/` directory
- **Installation**: Now uses `pyproject.toml` as primary configuration
- **Project Structure**: Cleaner organization with all docs in one place

## [0.2.0] - 2026-01-20

### Added
- **In-Process SDK Mode**: `AgentChaosSDK` + `wrap_client` (zero-infra)
- **OpenAI SDK Hooks**: `chat.completions.create` + `responses.create`
- **LangChain 2.x Hooks**: Runnable, ChatModel, Retriever (sync/async)
- **LlamaIndex Hooks**: Retriever + QueryEngine (sync/async)
- **Haystack Hooks**: Pipeline + Retriever (sync/async)
- **JSONPath RAG Poisoning** in SDK mode
- **SDK Tape Viewer**: `scripts/tape_viewer.py`

## [0.1.0] - 2025-12-17

### Added
- **Core SDK Package**: Universal Agent Chaos SDK with modular architecture
- **Proxy-based Chaos Injection**: mitmproxy addon for HTTP/HTTPS interception
- **Strategy Pattern**: Modular chaos strategies with dynamic configuration
- **Network Chaos Strategies**:
  - Latency injection
  - Error injection
  - Data corruption
- **Protocol Fuzzing**: Schema-aware MCP protocol fuzzing
  - Type mismatch injection
  - Null injection
  - Garbage value injection
  - Schema-aware fuzzing for dates, numerics, strings
- **Cognitive Layer Attacks**:
  - Hallucination strategy (data swapping)
  - Context overflow strategy
- **RAG Poisoning**: Phantom document injection with JSONPath support
- **Swarm Disruption**: Agent-to-agent communication disruption
- **Group-based Chaos**: Role-based chaos injection
- **Function-level Decorator**: `@simulate_chaos` decorator for internal functions
- **Configuration System**: YAML-based chaos plan configuration with Pydantic validation
- **Observability Integration**:
  - OpenTelemetry support
  - Distributed tracing with Jaeger
  - Prometheus metrics export
  - Grafana dashboard support
- **Real-time Dashboard**: WebSocket-based visualization dashboard
- **Compliance Audit Report**: Security-focused audit reporting
  - Tool call statistics
  - Fuzzing effectiveness
  - Recovery rate analysis
  - Race condition detection
- **Deterministic Replay**: Record & Replay system (VCR pattern)
- **Security Features**:
  - PII redaction (emails, API keys, tokens, etc.)
  - Authentication middleware
- **Multi-Agent Swarm Support**: YAML-driven swarm builder
- **Mock Server**: FastAPI-based external service simulation
- **Professional CLI**: typer/rich-based command-line interface
  - `agent-chaos init`: Generate chaos plan template
  - `agent-chaos validate`: Validate chaos plan YAML
  - `agent-chaos run`: Run chaos experiment with live dashboard
  - `agent-chaos record`: Record interactions for replay
  - `agent-chaos replay`: Replay recorded interactions
- **Test Suite**: Comprehensive pytest-based test suite (127 tests)
- **Documentation**:
  - README.md with quick start guide
  - QUICK_START.md with detailed usage instructions
  - API documentation in docstrings

### Technical Details
- **Python Version**: 3.10+
- **Architecture**: Async/await for high performance
- **Type Safety**: Comprehensive type hints with mypy support
- **Test Coverage**: 120+ unit tests and integration tests
- **CI/CD**: GitHub Actions with multi-Python version testing

[Unreleased]: https://github.com/AgenticChaosMonkey/AgenticChaosMonkey/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/AgenticChaosMonkey/AgenticChaosMonkey/releases/tag/v0.2.0
[0.1.0]: https://github.com/AgenticChaosMonkey/AgenticChaosMonkey/releases/tag/v0.1.0

