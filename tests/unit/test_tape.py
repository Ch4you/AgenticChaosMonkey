from pathlib import Path

from agent_chaos_sdk.storage.tape import TapeRecorder


def test_fingerprint_json_key_order_is_deterministic(tmp_path: Path) -> None:
    recorder = TapeRecorder(tape_path=tmp_path / "test.tape")
    headers = {"Content-Type": "application/json"}
    body_a = b'{"a":1,"b":2}'
    body_b = b'{"b":2,"a":1}'

    fp_a = recorder._create_fingerprint("POST", "http://example.com/api", body_a, headers)
    fp_b = recorder._create_fingerprint("POST", "http://example.com/api", body_b, headers)

    assert fp_a.body_hash == fp_b.body_hash
    assert fp_a == fp_b
