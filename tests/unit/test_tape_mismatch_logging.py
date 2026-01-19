import logging

from agent_chaos_sdk.storage.tape import (
    Tape,
    TapeEntry,
    RequestFingerprint,
    ResponseSnapshot,
    ChaosContext,
    TapePlayer,
)


def test_tape_mismatch_logs_diff(caplog) -> None:
    entry = TapeEntry(
        fingerprint=RequestFingerprint(
            method="POST",
            url="http://example.com/api",
            body_hash="recorded",
            headers_hash=None,
        ),
        response=ResponseSnapshot(
            status_code=200,
            reason="OK",
            headers={"Content-Type": "application/json"},
            content=b"{}",
            content_encoding=None,
        ),
        chaos_context=ChaosContext(applied_strategies=[], chaos_applied=False),
        timestamp="2025-01-01T00:00:00Z",
        sequence=0,
        redacted=True,
        request_body_redacted='{"id":1,"time":"10:00"}',
    )
    tape = Tape(entries=[entry])

    player = TapePlayer.__new__(TapePlayer)
    player.tape = tape
    player._index = {}

    with caplog.at_level(logging.DEBUG):
        player.find_match(
            method="POST",
            url="http://example.com/api",
            body=b'{"id":1,"time":"10:05"}',
            headers={"Content-Type": "application/json"},
        )

    assert any("Replay Mismatch!" in record.message for record in caplog.records)
