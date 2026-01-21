## Versioning & Release Policy

We follow **Semantic Versioning (SemVer)**: `MAJOR.MINOR.PATCH`.

### Version meanings
- **MAJOR**: backward-incompatible changes
- **MINOR**: backward-compatible features
- **PATCH**: backward-compatible bug fixes

### Deprecations
- Deprecations will be documented in the changelog.
- A deprecated feature will remain for at least one minor release cycle.

### Release cadence
## Current Release

Current SDK release: **v0.2.0**

Highlights:
- In-process SDK mode (`AgentChaosSDK`, `wrap_client`)
- JSONL tape recording
- SDK hooks for OpenAI / LangChain / LlamaIndex / Haystack
Releases are published when feature milestones are met or critical fixes are required.
