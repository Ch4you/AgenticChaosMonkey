import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from agent_chaos_sdk.proxy.addon import ChaosProxyAddon
from agent_chaos_sdk.storage.tape import TapeRecorder, ChaosContext


class _StubDashboardServer:
    def __init__(self) -> None:
        self.events = []

    async def broadcast_event(self, event) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_end_to_end_playback_with_dashboard(mock_flow, tmp_path, monkeypatch) -> None:
    # Ensure tape encryption works for test
    monkeypatch.setenv("CHAOS_TAPE_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CHAOS_REPLAY_STRICT", "false")

    tape_path = tmp_path / "session.tape"
    recorder = TapeRecorder(tape_path)

    chaos_context = ChaosContext(applied_strategies=[], chaos_applied=False)
    recorder.record(
        method=mock_flow.request.method,
        url=mock_flow.request.pretty_url,
        body=mock_flow.request.content,
        headers=dict(mock_flow.request.headers),
        response_status=200,
        response_reason="OK",
        response_headers={"Content-Type": "application/json"},
        response_content=b'{"status":"ok"}',
        response_encoding=None,
        chaos_context=chaos_context,
    )
    recorder.save()

    addon = ChaosProxyAddon(mode="PLAYBACK", tape_path=Path(tape_path))
    stub_dashboard = _StubDashboardServer()
    addon.set_dashboard_server(stub_dashboard)

    await addon.request(mock_flow)

    assert mock_flow.response is not None
    assert mock_flow.response.status_code == 200
    assert len(stub_dashboard.events) == 2
