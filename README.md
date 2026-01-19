# 🐵 Agent Chaos Platform

<div align="center">

**Universal Chaos Engineering SDK for AI Agents**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tests](https://img.shields.io/badge/tests-127%20passing-brightgreen)](https://github.com/AgenticChaosMonkey/AgenticChaosMonkey)

*Test agent robustness against network failures, data corruption, protocol fuzzing, and cognitive attacks.*

[Quick Start](#-quick-start) • [Documentation](docs/markdown/QUICK_START.md) • [Examples](examples/) • [Contributing](docs/markdown/CONTRIBUTING.md)

</div>

---

## 🌟 What Makes This Different?

While traditional chaos engineering tools (like Chaos Monkey) focus on **infrastructure failures**, Agent Chaos Platform is the **first tool designed specifically for AI Agent systems**, testing failures that matter to agents:

- 🧠 **Cognitive Attacks**: RAG poisoning, hallucination injection, context overflow
- 🤝 **Swarm Disruption**: Agent-to-agent message mutation, consensus delays
- 🔄 **Deterministic Replay**: 100% reproduce flaky agent failures
- 📊 **Agent-Native Observability**: See exactly how your 10-agent swarm communicates

**This is not just "mitmproxy for agents"** — it's a complete platform for Agent SRE.

---

## 🧭 What Is This Project?

**Agent Chaos Platform** is a chaos engineering toolkit for AI Agents. It sits in front of your agent’s outbound HTTP/HTTPS traffic (as a proxy or sidecar) and injects failures, records/replays interactions, and provides observability so you can measure and improve agent resilience.

**In one line:** it helps you prove your agent keeps working when real-world failures happen.

---

## ✅ Why Validate Agents Under Real Failure Conditions?

Agents rarely fail in the happy path — they fail when the environment deviates from ideal assumptions. In production, those deviations are normal.

- **Real failures are inevitable**: network jitter, API timeouts, rate limits, partial responses, and tool outages happen daily.
- **Agents are more fragile than typical services**: multi-step reasoning means a small error can cause a wrong decision, not just a visible crash.
- **Silent failures are the norm**: many agent failures look “successful” but return incorrect results, which traditional tests miss.
- **Reproducibility is the hardest problem**: flaky issues are nearly impossible to debug without deterministic replay.

**Industry pain points this solves:**
- Unreproducible production incidents (Replay makes them debuggable)
- RAG/tool uncertainty (Chaos makes them testable before production)
- Lack of resilience metrics (Scorecards make stability measurable)
- High-risk domains where a single bad decision is costly (finance, healthcare, enterprise ops)

---

## ✨ Key Features

### 🔥 Agent-Native Chaos (What Makes Us Unique)

#### 1. **RAG Poisoning** 🧠
Test if your agent can detect misinformation:
- Inject fake documents into vector database responses (Pinecone, Weaviate, custom APIs)
- Overwrite or inject conflicting information
- Test agent resilience against hallucination

```yaml
scenarios:
  - name: "poison_rag"
    type: "phantom_document"
    enabled: true
    params:
      target_json_path: "$.matches[*].metadata.text"
      mode: "overwrite"
      misinformation_source: "examples/misinformation.json"
```

#### 2. **Swarm Disruption** 🤝
Test multi-agent system robustness:
- **Message Mutation**: Flip boolean flags, modify instructions between agents
- **Consensus Delay**: Inject latency during voting/consensus phases
- **Agent Isolation**: Block communication from specific agents

```yaml
scenarios:
  - name: "mutate_messages"
    type: "swarm_disruption"
    enabled: true
    params:
      attack_type: "message_mutation"
      target_subtype: "supervisor_to_worker"
      mutation_rules:
        priority: "low"  # Flip from high to low
```

#### 2.1 **Classifier Rules (Enterprise Overrides)**
Override traffic classification with explicit regex rules:

```yaml
metadata:
  classifier_rules:
    llm_patterns:
      - "openai\\.com.*/v1/(chat|completions)"
    tool_patterns:
      - "example\\.internal/tools/"
    agent_patterns:
      - ".*agent-[a-z0-9]+.*"
```

#### 2.2 **Classifier Rule Packs (Production Required)**
In production, enable strict mode and provide rule packs:

```yaml
classifier_rule_packs:
  - name: "prod-default"
    rules:
      llm_patterns:
        - "openai\\.com.*/v1/(chat|completions)"
      tool_patterns:
        - "example\\.internal/tools/"
      agent_patterns:
        - ".*agent-[a-z0-9]+.*"
```

#### 3. **Deterministic Replay** 🔄
100% reproduce flaky failures:
- Record complete HTTP interactions with chaos context
- Replay exact network conditions (even when APIs are down)
- Debug failures deterministically

```bash
# Record a session
agent-chaos record examples/plans/travel_agent_chaos.yaml --tape session.tape

# Replay 100% deterministically
agent-chaos replay session.tape --plan examples/plans/travel_agent_chaos.yaml
```

#### 4. **Real-Time Visualization** 📊
See how your agents interact:
- Live topology graph of agent communication
- Traffic classification (Tool Calls, LLM API, Agent-to-Agent)
- Role-based metrics and statistics
- WebSocket-based real-time dashboard

Access at: `http://127.0.0.1:8081` when running experiments

### 🛠️ Traditional Chaos (Network Layer)

- **Network Chaos**: Latency injection, error injection, data corruption
- **Protocol Fuzzing**: Schema-aware fuzzing for tool calls (MCP protocol)
  - Date fields: Invalid formats, SQL injection
  - Numeric fields: Type mismatches, boundary values
  - String fields: Buffer overflows, XSS payloads
- **Race Condition Detection (Heuristic)**: Detect tool-call ordering issues via scorecard analysis
- **Group-based Chaos**: Apply chaos to agents by role (e.g., disable all QA engineers)

### 📈 Observability & Reporting

- **OpenTelemetry Integration**: Distributed tracing with Jaeger
- **Prometheus Metrics**: Token usage, latency, error rates by agent role
- **Resilience Scorecard**: Automated analysis and reporting (A-F grade)
- **Real-time Dashboard**: WebSocket-based visualization

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai/) (for local LLM testing)
- [mitmproxy](https://mitmproxy.org/) (`pip install mitmproxy`)
- **jsonpath-ng** (required for replay masking in strict mode)
- **pyjwt** (required for JWT auth in strict mode)

### Installation

```bash
# Clone the repository
git clone https://github.com/AgenticChaosMonkey/AgenticChaosMonkey.git
cd AgenticChaosMonkey

# Install the SDK (uses pyproject.toml)
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

### Run Your First Chaos Test

**Core 3-Step Flow (Recommended)**

**A. Validation Plan (see chaos now)**

1) Start the chaos proxy + dashboard:

```bash
agent-chaos run examples/plans/travel_agent_chaos_validate.yaml --mock-server --repeat 10
```

2) View results:
- Dashboard: `http://127.0.0.1:8081`
- Run summary: select the latest run in Dashboard

**B. Production Plan (low-probability)**

1) Start the chaos proxy + dashboard:

```bash
agent-chaos run examples/plans/travel_agent_chaos_prod.yaml --mock-server --repeat 200 --repeat-concurrency 2
```

2) View results:
- Dashboard: `http://127.0.0.1:8081`
- Run summary: select the latest run in Dashboard

**Advanced / Optional**

One-command demo (auto-runs mock server + proxy + agent + report):

```bash
./scripts/run_chaos_test.sh
```

Kubernetes sidecar deployment (production-ready flow):

```bash
kubectl apply -f k8s/
```

Record & replay for deterministic debugging:

```bash
agent-chaos record examples/plans/travel_agent_chaos.yaml --tape session.tape
agent-chaos replay session.tape --plan examples/plans/travel_agent_chaos.yaml
```

---

## 🧩 Usage Modes (Pick One)

1) **Proxy Mode (Recommended)**  
Run the chaos proxy and route your agent traffic through it (most common).

2) **Record & Replay**  
Capture a real failure once, replay it deterministically for debugging.

3) **Kubernetes Sidecar**  
Deploy in clusters with a sidecar to avoid app code changes.

4) **SDK / Decorators**  
Inject chaos inside Python functions for unit-level testing.

If you’re new, start with **Proxy Mode** in the Quick Start above.

---

## 📖 Documentation

- **[Quick Start Guide](docs/markdown/QUICK_START.md)** - Detailed usage instructions
- **[Comprehensive Testing Guide](docs/markdown/COMPREHENSIVE_TESTING_GUIDE.md)** - Complete test suite guide
- **[RAG Poisoning](docs/RAG_POISONING.md)** - Inject misinformation into RAG responses
- **[Swarm Disruption](docs/SWARM_DISRUPTION.md)** - Disrupt multi-agent communication
- **[Deterministic Replay](docs/TAPE_REPLAY.md)** - Record & replay system
- **[Kubernetes Deployment](docs/KUBERNETES.md)** - Sidecar deployment guide
- **[Production Validation](docs/markdown/PRODUCTION_VALIDATION.md)** - Local/K8s/CI checklist
- **[API Documentation](docs/index.rst)** - Complete API reference (Sphinx)

---

## 🎯 Use Cases

### 1. RAG System Testing
**Problem**: Your agent uses RAG. What if the vector database returns false information?

**Solution**: Use `PhantomDocumentStrategy` to inject fake documents and test if your agent detects and handles misinformation.

```yaml
scenarios:
  - name: "test_rag_resilience"
    type: "phantom_document"
    target_ref: "pinecone_api"
    enabled: true
    params:
      target_json_path: "$.matches[*].metadata.text"
      mode: "injection"  # Append conflicting info
```

### 2. Multi-Agent Swarm Testing
**Problem**: You have 10 agents. What if messages between them get corrupted?

**Solution**: Use `SwarmDisruptionStrategy` to mutate agent-to-agent messages and test swarm resilience.

```yaml
scenarios:
  - name: "test_swarm_robustness"
    type: "swarm_disruption"
    enabled: true
    params:
      attack_type: "message_mutation"
      target_subtype: "supervisor_to_worker"
```

### 3. Flaky Failure Debugging
**Problem**: Your agent failed yesterday. How do you reproduce it today?

**Solution**: Use Record & Replay to capture the exact failure and replay it deterministically.

```bash
# Yesterday: Record the failure
agent-chaos record --tape failure.tape

# Today: Replay 100% deterministically
agent-chaos replay failure.tape
```

### 4. Agent Communication Analysis
**Problem**: How do your 10 agents actually communicate? Who talks to whom?

**Solution**: Use the real-time dashboard to visualize agent communication topology.

```bash
agent-chaos run examples/plans/travel_agent_chaos.yaml --mock-server
# Open http://127.0.0.1:8081 to see live topology
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Chaos Platform                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐      ┌──────────────┐                   │
│  │   Agent 1    │──────│  Chaos Proxy │                   │
│  └──────────────┘      │  (mitmproxy) │                   │
│                        └──────┬───────┘                   │
│  ┌──────────────┐            │                            │
│  │   Agent 2    │────────────┘                            │
│  └──────────────┘            │                            │
│                              ▼                            │
│  ┌──────────────┐      ┌──────────────┐                   │
│  │   Agent N    │      │   Strategies │                   │
│  └──────────────┘      │  • RAG Poison│                   │
│                        │  • Swarm Disr│                   │
│                        │  • Protocol   │                   │
│                        │    Fuzzing    │                   │
│                        └──────────────┘                   │
│                                                             │
│  ┌──────────────┐      ┌──────────────┐                   │
│  │  Dashboard   │◄─────│  Observability│                   │
│  │  (WebSocket) │      │  (OTel/Jaeger)│                   │
│  └──────────────┘      └──────────────┘                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Project Structure

```
AgenticChaosMonkey/
├── agent_chaos_sdk/          # Core SDK package
│   ├── proxy/                # Chaos proxy (mitmproxy addon)
│   │   ├── addon.py          # Main proxy entry point
│   │   ├── classifier.py     # Traffic classifier
│   │   └── strategies/       # Chaos strategies
│   │       ├── rag.py        # RAG poisoning
│   │       ├── swarm.py      # Swarm disruption
│   │       ├── mcp.py        # Protocol fuzzing
│   │       └── ...
│   ├── storage/              # Record & Replay
│   │   └── tape.py           # VCR pattern implementation
│   ├── dashboard/            # Real-time visualization
│   │   ├── server.py         # WebSocket server
│   │   └── events.py         # Event models
│   ├── decorators.py         # Function-level chaos
│   └── swarm_runner.py       # Multi-agent swarm builder
├── src/
│   ├── tools/                # Mock external services
│   │   └── mock_server.py    # Flight booking API simulator
│   └── reporter/             # Resilience analysis
│       ├── scorecard.py      # Scorecard generator
│       └── generate.py       # Report generation CLI
├── examples/
│   ├── plans/                # Chaos plan examples
│   └── production_simulation/
│       └── travel_agent.py   # Test agent
├── docs/                      # Documentation
│   ├── markdown/             # Markdown docs
│   └── index.rst             # Sphinx API docs
├── pyproject.toml            # Modern Python config
└── setup.py                  # Compatibility layer
```

---

## 🎨 Example: Testing a Travel Agent

Let's test a travel booking agent's resilience:

```bash
# 1. Start the chaos platform
agent-chaos run examples/plans/travel_agent_chaos.yaml --mock-server

# 2. In another terminal, run your agent
export HTTP_PROXY=http://localhost:8080
python examples/production_simulation/travel_agent.py \
  --query "Book a flight from New York to Los Angeles on December 25th, 2025"

# 3. Watch the chaos unfold:
# - Dashboard: http://127.0.0.1:8081 (see live topology)
# - Logs: logs/proxy.log (structured JSON)
# - Report: reports/resilience_report.md (A-F grade)
```

**What happens:**
1. Agent calls `search_flights` → Proxy injects 5s delay
2. Agent calls `book_ticket` → Proxy injects 500 error (50% probability)
3. Agent receives fuzzed data → Invalid date format injected
4. Scorecard analyzes: Did agent retry? Did it recover? Did it crash?

**Result**: Resilience Scorecard with grade (A-F) and recommendations.

---

## 🔧 Configuration

Chaos experiments are defined in YAML files:

```yaml
version: "1.0"
metadata:
  name: "Travel Agent Chaos Test"
  experiment_id: "test_001"

targets:
  - name: "flight_api"
    type: "http_endpoint"
    pattern: ".*/search_flights.*"

scenarios:
  - name: "inject_delay"
    type: "latency"
    target_ref: "flight_api"
    enabled: true
    probability: 1.0
    params:
      delay: 5.0
  
  - name: "poison_rag"
    type: "phantom_document"
    target_ref: "rag_api"
    enabled: true
    params:
      target_json_path: "$.results[*].text"
      mode: "overwrite"
```

See [examples/plans/](examples/plans/) for more examples.

---

## 📊 Observability

### Real-Time Dashboard

Access the dashboard at `http://127.0.0.1:8081` when running experiments:

- **Live Topology**: See agent communication flow in real-time
- **Statistics**: Request counts, chaos injections, errors
- **Event Stream**: Real-time event feed with details

### Distributed Tracing

View complete request traces in Jaeger:

```bash
docker-compose up -d  # Starts Jaeger
# Access at http://localhost:16686
```

Traces show:
- Agent → Proxy → Tool/LLM flow
- Chaos injection points
- Agent role attribution
- Tool call nesting

### Metrics (Prometheus)

Query metrics by agent role:

```promql
# Requests by role
chaos_engineering_ai_requests_total{agent_role="TravelAgent"}

# Error rate by role
rate(chaos_engineering_ai_requests_total{status="error"}[5m])

# Token cost by role
chaos_engineering_ai_token_usage_total{agent_role="Developer"}
```

---

## ✅ Production Readiness Checklist

- **Dependencies pinned**: `pyproject.toml` uses upper bounds; use `requirements-lock.txt` for full pinning.
- **JWT strict mode**: set `CHAOS_JWT_STRICT=true` and install `pyjwt`.
- **Replay strict mode**: set `CHAOS_REPLAY_STRICT=true` and install `jsonpath-ng`.
- **Classifier strict mode**: set `CHAOS_CLASSIFIER_STRICT=true` and configure `classifier_rule_packs`.
- **Error code metrics**: monitor `chaos_error_codes_total` to catch strategy failures.
- **Encryption at rest**: set `CHAOS_TAPE_KEY` (Fernet key) for tape encryption.
- **PII redaction**: leave `PII_REDACTION_ENABLED=true` in production.
- **Audit log**: configure `CHAOS_AUDIT_LOG` and monitor for failures.
- **Tracing/metrics**: set `OTEL_EXPORTER_OTLP_ENDPOINT` and verify spans/metrics.
- **Dashboard isolation**: keep `NO_PROXY` configured for localhost.
- **Config integrity**: version/revision fields set in all chaos plans.
- **Load testing**: run `scripts/benchmark.sh` before rollout.

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=agent_chaos_sdk --cov-report=html

# Run specific test suite
pytest tests/unit/test_rag_strategy.py -v
```

**Test Coverage**: 127 tests, >80% coverage

See [docs/markdown/COMPREHENSIVE_TESTING_GUIDE.md](docs/markdown/COMPREHENSIVE_TESTING_GUIDE.md) for complete testing guide.

---

## 🛠️ SDK Usage

### As a Python Package

```python
from agent_chaos_sdk.decorators import simulate_chaos

@simulate_chaos(strategy="latency", probability=0.5, delay=2.0)
def my_agent_function():
    # This function may be delayed
    pass
```

### Proxy Mode (Recommended)

```python
from agent_chaos_sdk.proxy.addon import ChaosProxyAddon

# Used automatically by mitmproxy
addons = [ChaosProxyAddon()]
```

### Load Chaos Plans

```python
from agent_chaos_sdk.config_loader import load_chaos_plan

plan = load_chaos_plan("examples/plans/travel_agent_chaos.yaml")
print(f"Loaded: {plan.metadata.name}")
```

---

## 🎓 Advanced Features

### Multi-Agent Swarm Testing

Build and test complex agent swarms from YAML:

```yaml
name: "Enterprise Dev Team"
supervisor: "ProductManager"
agents:
  - name: "Dev_1"
    role: "PythonDeveloper"
    model: "llama3.2"
  - name: "QA_1"
    role: "QAEngineer"
    model: "llama3.2"
```

```python
from agent_chaos_sdk.swarm_runner import build_swarm_from_yaml

swarm = build_swarm_from_yaml("examples/scalable_swarm/software_house.yaml")
# All agents automatically route through chaos proxy
```

### Group-Based Chaos

Apply chaos to entire agent roles:

```yaml
scenarios:
  - name: "disable_qa"
    type: "group_failure"
    enabled: true
    params:
      target_role: "QAEngineer"
      probability: 1.0
```

This disables **all** QA engineers with one rule.

---

## 🏆 Comparison with Other Tools

| Feature | Agent Chaos Platform | Chaos Monkey | Toxiproxy | mitmproxy |
|---------|---------------------|--------------|-----------|-----------|
| Network Chaos | ✅ | ✅ | ✅ | ✅ |
| Protocol Fuzzing | ✅ | ❌ | ❌ | ❌ |
| RAG Poisoning | ✅ | ❌ | ❌ | ❌ |
| Swarm Disruption | ✅ | ❌ | ❌ | ❌ |
| Deterministic Replay | ✅ | ❌ | ❌ | ❌ |
| Agent-Native Observability | ✅ | ❌ | ❌ | ❌ |
| Race Condition Detection (Heuristic) | ✅ | ❌ | ❌ | ❌ |
| Configuration-Driven | ✅ | ❌ | ❌ | ❌ |

**Agent Chaos Platform is the only tool designed specifically for AI Agent systems.**

---

## 🛡️ Security

- **PII Redaction**: Automatically masks emails, API keys, tokens in logs
- **Authentication**: Optional `X-Chaos-Token` header for control plane security
- **Secure by Default**: No sensitive data in logs or traces

See [docs/troubleshooting/DASHBOARD_TROUBLESHOOTING.md](docs/troubleshooting/DASHBOARD_TROUBLESHOOTING.md) for security configuration.

---

## 🚦 Roadmap

- [ ] **gRPC Support**: Extend traffic classifier for gRPC
- [ ] **WebSocket Chaos**: Disrupt WebSocket connections
- [ ] **ML-Based Classification**: Auto-detect agent communication patterns
- [ ] **Chaos Scheduling**: Time-based chaos injection (e.g., "disable QA at 2pm")
- [ ] **Multi-Protocol Replay**: Support gRPC/WebSocket in tape replay

---

## 🤝 Contributing

We welcome contributions! Please see [docs/markdown/CONTRIBUTING.md](docs/markdown/CONTRIBUTING.md) for guidelines.

**Quick contribution steps:**
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

---

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Inspired by [Netflix Chaos Monkey](https://github.com/Netflix/chaosmonkey)
- Built on [mitmproxy](https://mitmproxy.org/) for HTTP interception
- Uses [OpenTelemetry](https://opentelemetry.io/) for observability

---

## 📚 Resources

- **[Quick Start Guide](docs/markdown/QUICK_START.md)** - Get started in 5 minutes
- **[API Documentation](docs/index.rst)** - Complete API reference
- **[Examples](examples/)** - Ready-to-use chaos plans
- **[Changelog](docs/markdown/CHANGELOG.md)** - Version history
- **[Configuration Reference](docs/CONFIGURATION_REFERENCE.md)** - Full schema and env vars
- **[Observability Reference](docs/OBSERVABILITY.md)** - Metrics and tracing
- **[Security Policy](SECURITY.md)** - Vulnerability reporting
- **[Support](SUPPORT.md)** - Support scope and guidance
- **[Versioning](VERSIONING.md)** - SemVer and release policy
- **[Code of Conduct](CODE_OF_CONDUCT.md)** - Community standards

---

<div align="center">

**Made with ❤️ for the AI Agent Community**

[⭐ Star us on GitHub](https://github.com/AgenticChaosMonkey/AgenticChaosMonkey) • [📖 Read the Docs](docs/markdown/QUICK_START.md) • [🐛 Report Issues](https://github.com/AgenticChaosMonkey/AgenticChaosMonkey/issues)

</div>
