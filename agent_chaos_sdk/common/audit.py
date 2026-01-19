"""
Audit logging for compliance.

Logs security-sensitive actions to a dedicated audit log file.
"""

import logging
import os
from datetime import datetime

_audit_logger: logging.Logger = logging.getLogger("agent_chaos_audit")
_initialized = False


def _init_audit_logger() -> None:
    global _initialized
    if _initialized:
        return

    log_path = os.getenv("CHAOS_AUDIT_LOG", "logs/audit.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    handler = logging.FileHandler(log_path)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)

    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False
    _audit_logger.addHandler(handler)

    _initialized = True


def log_audit(
    user_id: str,
    action: str,
    resource: str,
    outcome: str,
    details: dict | None = None,
) -> None:
    """
    Write an audit log entry.

    Format:
        [AUDIT] Timestamp | User/TokenID | Action | Resource | Outcome
    """
    _init_audit_logger()
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    line = f"[AUDIT] {timestamp} | User={user_id} | Action={action} | Resource={resource} | Outcome={outcome}"
    if details:
        line += f" | Details={details}"
    _audit_logger.info(line)

