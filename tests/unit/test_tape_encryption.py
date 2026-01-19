from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from agent_chaos_sdk.storage.tape import Tape, TapeEntry, RequestFingerprint, ResponseSnapshot, ChaosContext


def _sample_tape() -> Tape:
    entry = TapeEntry(
        fingerprint=RequestFingerprint(method="GET", url="http://example.com", body_hash=None, headers_hash=None),
        response=ResponseSnapshot(
            status_code=200,
            reason="OK",
            headers={"Content-Type": "application/json"},
            content=b'{"ok":true}',
            content_encoding=None,
        ),
        chaos_context=ChaosContext(applied_strategies=[], chaos_applied=False),
        timestamp="2025-01-01T00:00:00Z",
        sequence=0,
        redacted=True,
    )
    return Tape(entries=[entry])


def test_tape_encryption_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAOS_TAPE_KEY", Fernet.generate_key().decode("utf-8"))

    tape_path = tmp_path / "encrypted.tape"
    tape = _sample_tape()
    tape.save(tape_path)

    raw = tape_path.read_bytes()
    assert b"{\"version\"" not in raw  # Should not be plain JSON

    loaded = Tape.load(tape_path)
    assert len(loaded.entries) == 1
    assert loaded.entries[0].response.status_code == 200
