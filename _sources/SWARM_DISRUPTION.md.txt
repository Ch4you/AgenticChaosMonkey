# Multi-Agent Swarm Disruption

## Overview

The Swarm Disruption feature enables targeted chaos engineering for multi-agent systems (AutoGen, OpenAI Swarm, etc.) by identifying and disrupting inter-agent communication specifically.

## Architecture

### Traffic Classifier

**Location**: `agent_chaos_sdk/proxy/classifier.py`

The `TrafficClassifier` analyzes HTTP requests to categorize traffic into:

- **TOOL_CALL**: Agent calling external tools/APIs
- **LLM_API**: Agent calling LLM services (OpenAI, Anthropic, etc.)
- **AGENT_TO_AGENT**: Inter-agent communication (AutoGen, OpenAI Swarm, etc.)
- **UNKNOWN**: Unclassified traffic

**Classification Methods**:

1. **URL Pattern Matching**: Fast pattern-based classification
2. **Header Analysis**: Checks for agent-specific headers (`X-Agent-To-Agent`, `X-Swarm-Message`)
3. **Body Structure Analysis**: Analyzes JSON body structure for agent communication patterns

**Subtype Detection**:

The classifier also identifies specific subtypes of agent-to-agent communication:
- `supervisor_to_worker`: Supervisor delegating tasks
- `consensus_vote`: Consensus/voting phases
- `worker_communication`: Worker-to-worker communication
- `autogen_message`: AutoGen-specific format
- `swarm_message`: OpenAI Swarm format

**Extensibility**:

- Configurable via ChaosPlan targets
- Protocol-agnostic design (HTTP now, gRPC/WebSocket ready)
- Pattern-based and ML-ready architecture

### Swarm Disruption Strategy

**Location**: `agent_chaos_sdk/proxy/strategies/swarm.py`

The `SwarmDisruptionStrategy` specifically targets `AGENT_TO_AGENT` traffic with three attack types:

#### 1. Message Mutation

Modifies messages between agents:
- Flips boolean flags (e.g., `priority: "high"` → `priority: "low"`)
- Modifies numeric values (±20% or ±1)
- Applies custom mutation rules from config

**Example**:
```json
// Original
{"instruction": "Process this task", "priority": "high", "enabled": true}

// Mutated
{"instruction": "Process this task", "priority": "low", "enabled": false}
```

#### 2. Consensus Delay

Injects high latency during consensus/voting phases:
- Only triggers on `consensus_vote` subtype
- Configurable delay (default: 5.0s)
- Tests swarm's ability to handle slow consensus

#### 3. Agent Isolation

Blocks communication from specific agents:
- Returns 503 error for isolated agents
- Configurable agent list
- Tests swarm's resilience to agent failures

## Integration

### Addon Integration

**Location**: `agent_chaos_sdk/proxy/addon.py`

The classifier is integrated into the request hook **before** strategies are applied:

```python
# CRITICAL: Classify traffic BEFORE applying strategies
classifier = get_classifier()
traffic_type = classifier.classify(flow)

# Traffic type is stored in flow.metadata
# Strategies can check flow.metadata[METADATA_TRAFFIC_TYPE]
```

**OpenTelemetry Integration**:
- `traffic.type` attribute added to spans
- `traffic.subtype` attribute for detailed classification
- Enables filtering and analysis in Jaeger/Grafana

**Logging Integration**:
- `traffic_type` and `traffic_subtype` added to structured JSON logs
- Enables scorecard analysis by traffic type

### Scorecard Integration

**Location**: `agent_chaos_sdk/reporter/scorecard.py`

The scorecard now tracks swarm-specific metrics:

```python
"swarm_communication_errors": defaultdict(int),  # By traffic type
"agent_to_agent_disruptions": 0,
"consensus_delays": 0,
"message_mutations": 0,
"agent_isolations": 0,
```

**Report Sections**:
- Swarm Communication Errors (by type)
- Swarm Disruption Summary
- Agent-to-Agent Disruptions count
- Message Mutations count
- Consensus Delays count
- Agent Isolations count

## Configuration

### Example YAML Configuration

**Location**: `examples/plans/swarm_disruption.yaml`

```yaml
targets:
  - name: "agent_to_agent_traffic"
    type: "custom"
    pattern: ".*agent-[a-z0-9]+.*|.*/api/agent/.*"
    description: "Inter-agent communication endpoints"

scenarios:
  - name: "mutate_supervisor_messages"
    type: "swarm_disruption"
    target_ref: "agent_to_agent_traffic"
    enabled: true
    probability: 0.5
    params:
      attack_type: "message_mutation"
      target_subtype: "supervisor_to_worker"
      mutation_rules:
        priority: "low"
        enabled: false
```

### Strategy Parameters

**attack_type**: `"message_mutation"` | `"consensus_delay"` | `"agent_isolation"`

**target_subtype** (optional): Specific agent communication subtype to target

**probability**: 0.0-1.0, probability of applying the attack

**mutation_rules** (for message_mutation): Dictionary of field mutations

**consensus_delay** (for consensus_delay): Delay in seconds (default: 5.0)

**isolated_agents** (for agent_isolation): List of agent IDs to isolate

## Usage

### Basic Usage

```python
from agent_chaos_sdk.proxy.strategies.swarm import SwarmDisruptionStrategy

strategy = SwarmDisruptionStrategy(
    name="swarm_attack",
    attack_type="message_mutation",
    target_subtype="supervisor_to_worker",
    probability=0.5,
    mutation_rules={"priority": "low", "enabled": False}
)
```

### With ChaosPlan

```yaml
scenarios:
  - name: "disrupt_swarm"
    type: "swarm_disruption"
    enabled: true
    params:
      attack_type: "consensus_delay"
      consensus_delay: 10.0
```

## Testing

### Manual Testing

1. Start a multi-agent system (AutoGen, OpenAI Swarm, etc.)
2. Configure proxy with swarm disruption strategy
3. Send requests through the proxy
4. Verify:
   - Traffic is correctly classified as `AGENT_TO_AGENT`
   - Messages are mutated (if message_mutation enabled)
   - Consensus delays are applied (if consensus_delay enabled)
   - Isolated agents are blocked (if agent_isolation enabled)

### Verification

Check logs for:
- `traffic_type: "AGENT_TO_AGENT"` in JSON logs
- `chaos_applied: ["swarm_disruption"]` in logs
- Scorecard shows swarm communication errors

## Design Principles

### Decoupling

- **Classifier** is independent of strategies
- **Strategies** check traffic type from metadata
- **Addon** orchestrates classification and strategy application
- **Scorecard** analyzes logs without knowing implementation details

### Extensibility

- **New Protocols**: Add patterns to classifier (gRPC, WebSocket ready)
- **New Attack Types**: Extend `SwarmDisruptionStrategy` or create new strategy
- **New Subtypes**: Add detection logic to `_detect_agent_subtype()`

### Performance

- **Pattern Compilation**: Patterns compiled once at initialization
- **Metadata Storage**: Classification stored in flow.metadata (no re-classification)
- **Async**: All operations are async for high concurrency

## Future Enhancements

1. **gRPC Support**: Extend classifier for gRPC inter-agent communication
2. **WebSocket Support**: Real-time agent communication classification
3. **ML-Based Classification**: Use ML models for more accurate traffic classification
4. **Protocol-Specific Attacks**: Attacks tailored to specific swarm protocols (AutoGen, OpenAI Swarm)
5. **Consensus Manipulation**: Modify consensus votes, not just delay

## Troubleshooting

### Traffic Not Classified as AGENT_TO_AGENT

1. Check URL patterns in classifier
2. Verify headers (`X-Agent-To-Agent`, `X-Swarm-Message`)
3. Check body structure matches agent communication format
4. Add custom patterns to ChaosPlan targets

### Strategy Not Triggering

1. Verify `traffic_type == "AGENT_TO_AGENT"` in logs
2. Check `target_subtype` matches (if specified)
3. Verify `probability` is high enough
4. Check strategy is enabled in config

### Scorecard Not Showing Swarm Errors

1. Verify logs contain `traffic_type: "AGENT_TO_AGENT"`
2. Check `chaos_applied` contains `"swarm_disruption"`
3. Ensure scorecard reads from correct log file

