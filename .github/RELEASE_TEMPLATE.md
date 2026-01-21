## Release v0.2.0

### Highlights
- In-process SDK mode (`AgentChaosSDK`, `wrap_client`)
- JSONL tape recording with optional RAG poisoning
- OpenAI SDK hooks (`chat.completions` + `responses`)
- LangChain 2.x Runnable/ChatModel/Retriever hooks
- LlamaIndex + Haystack auto-detection

### Migration Notes
- Proxy mode remains available; SDK mode is recommended for zero-infra use.
- Tape format is JSONL (SDK). Proxy mode tapes remain encrypted `.tape`.

### Checklist
- [ ] Version bump in `pyproject.toml` and `agent_chaos_sdk/__init__.py`
- [ ] `CHANGELOG.md` updated
- [ ] Release tag created (`v0.2.0`)
