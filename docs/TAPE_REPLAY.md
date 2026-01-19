# Deterministic Replay System (VCR Pattern)

## Overview

The Deterministic Replay System allows developers to debug flaky Agent failures by recording HTTP interactions and replaying them exactly, even when the real API is down or unavailable.

## Architecture

### Storage Layer

**Location**: `agent_chaos_sdk/storage/tape.py`

**Components**:
- `RequestFingerprint`: Identifies requests (Method, URL, Body Hash, Headers Hash)
- `ResponseSnapshot`: Stores complete response (status, headers, body, encoding)
- `ChaosContext`: Records chaos that was applied during recording
- `TapeEntry`: Single request-response pair with fingerprint and context
- `Tape`: Complete session recording (list of entries)
- `TapeRecorder`: Records interactions to tape
- `TapePlayer`: Replays interactions from tape

### Proxy Modes

**Location**: `agent_chaos_sdk/proxy/addon.py`

The `ChaosProxyAddon` supports three modes:

1. **LIVE**: Normal pass-through + Chaos injection
2. **RECORD**: Pass-through + Chaos + Save to `.tape` file
3. **PLAYBACK**: No network access - intercept requests, match fingerprints, return recorded responses

## Request Fingerprinting

Fingerprints are computed based on:
- **Method**: HTTP method (GET, POST, etc.)
- **URL**: Normalized request URL
- **Body Hash**: SHA256 hash of request body (if present)
- **Headers Hash**: SHA256 hash of stable headers (excluding volatile ones)

**Volatile headers ignored**:
- `Date`, `If-Modified-Since`, `If-None-Match`
- `X-Request-ID`, `X-Correlation-ID`
- `User-Agent` (may vary)
- `Authorization` (excluded by default for security)

## Determinism

In `PLAYBACK` mode:
- The exact same chaos context is restored from the tape
- Traffic type and subtype are restored
- Agent role is restored
- The recorded "chaotic response" is returned directly

This ensures that if an Agent crashed due to a specific sequence of network packets yesterday, running `replay` will crash it in the exact same way today, even if the real API is down.

## Usage

### Recording

```bash
# Record interactions to a tape file
agent-chaos record examples/plans/payment_failure.yaml --tape tapes/payment_test.tape

# Auto-generate tape filename
agent-chaos record examples/plans/payment_failure.yaml
```

**What happens**:
1. Proxy starts in RECORD mode
2. All requests/responses are captured
3. Chaos is applied (if configured)
4. Request fingerprints and response snapshots are saved
5. Chaos context is preserved
6. Tape is saved on shutdown (Ctrl+C)

### Replaying

```bash
# Replay from a tape file
agent-chaos replay tapes/payment_test.tape --port 8080

# Replay with chaos plan (for metadata)
agent-chaos replay tapes/payment_test.tape --plan examples/plans/payment_failure.yaml
```

**What happens**:
1. Proxy starts in PLAYBACK mode
2. No network access (all requests intercepted)
3. Requests are matched against tape fingerprints
4. Recorded responses are returned
5. Chaos context is restored
6. Agent experiences exact same conditions as recording

## Tape File Format

Tape files are JSON with the following structure:

```json
{
  "version": "1.0",
  "metadata": {
    "created_at": "2025-01-15T10:30:00",
    "recorder_version": "1.0"
  },
  "entries": [
    {
      "fingerprint": {
        "method": "POST",
        "url": "http://localhost:8001/search_flights",
        "body_hash": "abc123...",
        "headers_hash": "def456..."
      },
      "response": {
        "status_code": 200,
        "reason": "OK",
        "headers": {"Content-Type": "application/json"},
        "content": "hex_encoded_bytes",
        "content_encoding": null
      },
      "chaos_context": {
        "applied_strategies": ["latency"],
        "chaos_applied": true,
        "traffic_type": "TOOL_CALL",
        "traffic_subtype": null,
        "agent_role": "TravelAgent"
      },
      "timestamp": "2025-01-15T10:30:01",
      "sequence": 0
    }
  ]
}
```

## Matching Algorithm

### Exact Match
1. Compute fingerprint for incoming request
2. Look up in tape index
3. If found, return corresponding response

### Partial Match (Fallback)
1. If exact match fails, try method + URL only
2. Ignore body and headers
3. Useful for GET requests or when body/headers vary slightly

### No Match
- Returns 404 response with error message
- Logs warning for debugging

## Integration

### CLI Commands

**Record**:
```bash
agent-chaos record <plan.yaml> [--tape <path>] [--port <port>]
```

**Replay**:
```bash
agent-chaos replay <tape.tape> [--plan <plan.yaml>] [--port <port>]
```

### Programmatic Usage

```python
from agent_chaos_sdk.proxy.addon import (
    ChaosProxyAddon, PROXY_MODE_RECORD, PROXY_MODE_PLAYBACK
)
from pathlib import Path

# Recording
addon = ChaosProxyAddon(
    config_path="config/chaos_config.yaml",
    mode=PROXY_MODE_RECORD,
    tape_path=Path("tapes/recording.tape")
)

# Playback
addon = ChaosProxyAddon(
    config_path="config/chaos_config.yaml",
    mode=PROXY_MODE_PLAYBACK,
    tape_path=Path("tapes/recording.tape")
)
```

## Use Cases

### 1. Debugging Flaky Failures

**Problem**: Agent crashes intermittently, hard to reproduce.

**Solution**:
1. Record session when failure occurs
2. Replay tape to reproduce exact failure
3. Debug with deterministic conditions

### 2. Offline Testing

**Problem**: Need to test Agent but API is down.

**Solution**:
1. Record interactions when API is up
2. Replay tape when API is down
3. Continue development/testing

### 3. Regression Testing

**Problem**: Need to verify Agent handles specific failure scenarios.

**Solution**:
1. Record failure scenario once
2. Replay tape in CI/CD pipeline
3. Verify Agent handles it correctly

### 4. Performance Testing

**Problem**: Need consistent network conditions for benchmarking.

**Solution**:
1. Record interactions with specific latency/errors
2. Replay tape for consistent test conditions
3. Compare Agent performance across versions

## Best Practices

1. **Name tapes descriptively**: `payment_failure_20250115.tape`
2. **Include metadata**: Use `--plan` option to preserve experiment context
3. **Version control**: Commit tapes for reproducible tests
4. **Clean up**: Remove old tapes periodically
5. **Document**: Add README explaining what each tape tests

## Limitations

1. **Stateful APIs**: Tapes don't capture server state changes
2. **Time-sensitive**: Timestamps in responses may be stale
3. **Dynamic Content**: Responses with timestamps/IDs may not match
4. **Compression**: Handles Gzip/Brotli, but encoding must match

## Future Enhancements

1. **Selective Recording**: Record only specific endpoints
2. **Tape Editing**: Modify recorded responses for testing
3. **Tape Merging**: Combine multiple tapes
4. **Tape Diffing**: Compare two tapes to find differences
5. **Tape Compression**: Compress large tapes

