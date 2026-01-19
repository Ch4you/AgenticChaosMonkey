# Cognitive Layer Attack Strategies

This document describes the advanced chaos strategies that target the **cognitive/logic layer** of AI agents, testing their ability to handle false data and context overflow.

## Overview

Traditional chaos engineering focuses on network and infrastructure failures. Cognitive attacks go deeper, testing:
- **Data Trust**: Does the agent blindly trust tool responses?
- **Context Limits**: Does the agent crash or forget instructions when context is overflowed?
- **Logic Resilience**: Can the agent detect and handle false but plausible data?

## Strategies

### 1. HallucinationStrategy

**Purpose**: Inject false but plausible data into tool responses to test if agents verify data.

**How it works**:
- Intercepts HTTP responses from tools/APIs
- Identifies entities: numbers, dates, prices, names
- Swaps them with plausible but incorrect values
- Example: `{"price": 99.99}` → `{"price": 149.99}`

**Configuration**:
```yaml
- name: "hallucinate_flight_prices"
  type: "hallucination"
  target_ref: "tool_responses"
  enabled: true
  probability: 0.8
  params:
    mode: "swap_entities"  # Options: "swap_entities", "invert_numbers", "shift_dates"
```

**Modes**:
- `swap_entities`: Replace numbers/dates with similar but different values (±20% variation)
- `invert_numbers`: Negate numeric values
- `shift_dates`: Shift dates by ±7 days

**Use Cases**:
- Test if agent verifies flight prices before booking
- Test if agent detects incorrect dates in responses
- Test if agent blindly trusts tool output

### 2. ContextOverflowStrategy

**Purpose**: Inject massive amounts of noise into prompts/contexts to test context window limits.

**How it works**:
- Intercepts HTTP requests to LLM APIs
- Appends 5k-10k tokens of garbage text to prompts
- Tests if agent crashes or forgets earlier instructions

**Configuration**:
```yaml
- name: "overflow_llm_context"
  type: "context_overflow"
  target_ref: "llm_requests"
  enabled: true
  probability: 1.0
  params:
    token_count: 7500  # ~30k characters, ~5k-10k tokens
    mode: "repeating_chars"  # Options: "repeating_chars", "random_words", "gibberish"
```

**Modes**:
- `repeating_chars`: Repeating alphanumeric characters (e.g., "ABCDEFG...")
- `random_words`: Random dictionary words
- `gibberish`: Random alphanumeric gibberish

**Use Cases**:
- Test if agent crashes when context exceeds limits
- Test if agent forgets earlier instructions
- Test if agent can filter out noise

## Target Matching

Both strategies use the **target-driven** approach from `ChaosPlan`:

1. **Define Targets**: What to attack (URLs, agent roles, etc.)
2. **Reference in Scenarios**: Strategies reference targets by name
3. **Automatic Matching**: Strategies automatically match flows to targets

Example:
```yaml
targets:
  - name: "tool_responses"
    type: "http_endpoint"
    pattern: ".*/search_flights.*|.*/book_ticket.*"

scenarios:
  - name: "hallucinate_flight_prices"
    type: "hallucination"
    target_ref: "tool_responses"  # References the target above
```

## Integration with BaseStrategy

The `BaseStrategy` class now includes:
- `should_trigger(flow)`: Automatically checks if flow matches configured targets
- Support for `target_ref`: References targets from `ChaosPlan`
- Backward compatibility: Still supports direct `url_pattern` parameter

## Example Plan

See `cognitive_attacks.yaml` for a complete example:

```yaml
version: "1.0"
metadata:
  name: "Cognitive Layer Attack Plan"
targets:
  - name: "tool_responses"
    type: "http_endpoint"
    pattern: ".*/search_flights.*|.*/book_ticket.*"
scenarios:
  - name: "hallucinate_flight_prices"
    type: "hallucination"
    target_ref: "tool_responses"
    enabled: true
    params:
      mode: "swap_entities"
```

## Testing

Run the test script to verify strategies work:

```bash
python test_cognitive_strategies.py
```

This tests:
- Hallucination data swapping
- Context overflow injection
- Target matching with ChaosPlan

## Usage in Proxy

The strategies are automatically registered in `StrategyFactory`:

- `hallucination` → `HallucinationStrategy`
- `context_overflow` → `ContextOverflowStrategy`

They can be used in both:
- Legacy `chaos_config.yaml` format
- New `ChaosPlan` YAML format

## Best Practices

1. **Start with Low Probability**: Use `probability: 0.3` initially to avoid overwhelming the agent
2. **Monitor Agent Behavior**: Watch for crashes, incorrect decisions, or forgotten instructions
3. **Gradual Escalation**: Increase `token_count` or `probability` gradually
4. **Target Specific Endpoints**: Use precise URL patterns to avoid affecting unrelated requests

## Limitations

- **HallucinationStrategy**: Only works with JSON or text responses
- **ContextOverflowStrategy**: May cause legitimate LLM APIs to reject requests if limits are exceeded
- **Target Matching**: Requires `ChaosPlan` to be loaded globally (via `set_global_plan()`)

