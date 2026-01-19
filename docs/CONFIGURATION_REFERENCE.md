## Configuration Reference

This document reflects the **current** ChaosPlan schema and required production settings.

### ChaosPlan (YAML)

```yaml
version: "1.0"
revision: 0
metadata:
  name: "Experiment Name"
  description: "What this experiment tests"
  experiment_id: "unique_id"

# Optional enterprise overrides
classifier_rules:
  llm_patterns: ["openai\\.com.*/v1/(chat|completions)"]
  tool_patterns: ["example\\.internal/tools/"]
  agent_patterns: [".*agent-[a-z0-9]+.*"]

# Production-required rule packs (when CHAOS_CLASSIFIER_STRICT=true)
classifier_rule_packs:
  - name: "prod-default"
    rules:
      llm_patterns: ["openai\\.com.*/v1/(chat|completions)"]
      tool_patterns: ["example\\.internal/tools/"]
      agent_patterns: [".*agent-[a-z0-9]+.*"]

replay_config:
  ignore_paths:
    - "$.timestamp"
    - "$.trace_id"
  ignore_params:
    - "request_id"

targets:
  - name: "flight_search_api"
    type: "http_endpoint"
    pattern: ".*/search_flights.*"

scenarios:
  - name: "inject_delay"
    type: "latency"
    target_ref: "flight_search_api"
    enabled: true
    probability: 1.0
    params:
      delay: 2.0
```

### TargetConfig
- `name`: unique identifier
- `type`: `http_endpoint | llm_input | tool_call | agent_role | custom`
- `pattern`: regex string
- `description`: optional

### StrategyConfig
- `name`: unique identifier
- `type`: strategy type (e.g., `latency`, `error`, `mcp_fuzzing`, `phantom_document`)
- `target_ref`: must reference a target
- `enabled`: boolean
- `probability`: 0.0–1.0
- `params`: strategy-specific config

### ReplayConfig
- `ignore_paths`: JSONPath list to mask volatile fields
- `ignore_params`: query params to ignore

### Production Env Vars
- `CHAOS_CLASSIFIER_STRICT=true` → requires `classifier_rule_packs`
- `CHAOS_REPLAY_STRICT=true` → requires `jsonpath-ng` for masking
- `CHAOS_JWT_STRICT=true` + `CHAOS_JWT_SECRET` → requires `pyjwt`
- `CHAOS_TAPE_KEY` → required for record/replay (Fernet key)
