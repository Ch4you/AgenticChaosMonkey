import importlib
from pathlib import Path


def test_audit_log_written(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "audit.log"
    monkeypatch.setenv("CHAOS_AUDIT_LOG", str(log_path))

    from agent_chaos_sdk.common import audit

    # Reload to pick up new env path
    audit = importlib.reload(audit)

    audit.log_audit(
        user_id="user-123",
        action="CONFIG_CHANGE",
        resource="chaos_plan.yaml",
        outcome="success",
        details={"revision": 1},
    )

    assert log_path.exists()
    contents = log_path.read_text(encoding="utf-8")
    assert "[AUDIT]" in contents
    assert "User=user-123" in contents
    assert "Action=CONFIG_CHANGE" in contents
    assert "Resource=chaos_plan.yaml" in contents
    assert "Outcome=success" in contents
