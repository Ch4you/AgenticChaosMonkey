# Chaos Plan Examples

This directory contains example chaos plans demonstrating the configuration-driven approach to chaos engineering.

## What is a Chaos Plan?

A chaos plan is a YAML file that defines:
- **Targets**: What to attack (HTTP endpoints, agent roles, tool calls, etc.)
- **Scenarios**: How to attack them (network delays, errors, fuzzing, etc.)

This allows you to define complex chaos experiments without writing Python code.

## Example Plans

### `payment_failure.yaml`
Simulates network failures for payment processing:
- Targets Stripe API endpoints
- Injects 503 errors and timeouts
- Tests payment agent resilience

### `travel_agent_chaos.yaml`
Chaos scenarios for travel booking agents:
- Targets flight search and booking APIs
- Applies delays, errors, and protocol fuzzing
- Tests agent recovery from failures

## Usage

```python
from agent_chaos_sdk import load_chaos_plan, set_global_plan

# Load a chaos plan
plan = load_chaos_plan("examples/plans/payment_failure.yaml")

# Set as global plan (for proxy addon to use)
set_global_plan(plan)

# Access targets and scenarios
for target in plan.targets:
    print(f"Target: {target.name} ({target.type})")

for scenario in plan.scenarios:
    if scenario.enabled:
        print(f"Scenario: {scenario.name} -> {scenario.target_ref}")
```

## Plan Schema

```yaml
version: "1.0"
metadata:
  name: "Experiment Name"
  description: "What this experiment tests"
  experiment_id: "unique_id"
  # Optional enterprise classifier overrides
  classifier_rules:
    llm_patterns: ["openai\\.com.*/v1/(chat|completions)"]
    tool_patterns: ["example\\.internal/tools/"]
    agent_patterns: [".*agent-[a-z0-9]+.*"]

classifier_rule_packs:
  - name: "prod-default"
    rules:
      llm_patterns: ["openai\\.com.*/v1/(chat|completions)"]
      tool_patterns: ["example\\.internal/tools/"]
      agent_patterns: [".*agent-[a-z0-9]+.*"]

targets:
  - name: "target_name"
    type: "http_endpoint"  # or "llm_input", "tool_call", "agent_role"
    pattern: ".*regex.*"   # Pattern to match
    description: "Optional description"

scenarios:
  - name: "scenario_name"
    type: "latency"        # Strategy type
    target_ref: "target_name"  # Must match a target name
    enabled: true
    probability: 0.8
    params:
      delay: 5.0           # Strategy-specific params
```

## Converting to Legacy Format

The plan can be converted to the legacy `ChaosConfig` format for backward compatibility:

```python
legacy_config = plan.to_legacy_config()
# Use with existing proxy addon code
```

