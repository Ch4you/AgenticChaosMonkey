"""
Tape Storage for Deterministic Replay (VCR Pattern).

This module implements a "Record & Replay" system for HTTP interactions,
allowing developers to debug flaky Agent failures by replaying exact
network conditions that caused failures.

Key Features:
- Request fingerprinting (Method, URL, Body Hash)
- Response snapshot storage
- Chaos context preservation
- Deterministic replay
"""

from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from datetime import datetime
import hashlib
import json
import logging
from urllib.parse import urlparse, parse_qsl, urlencode
import os
import base64

from pydantic import BaseModel, Field

from agent_chaos_sdk.config_loader import get_global_plan, DEFAULT_REPLAY_IGNORE_PATHS
from cryptography.fernet import Fernet, InvalidToken

try:
    from jsonpath_ng import parse as jsonpath_parse
    JSONPATH_AVAILABLE = True
except ImportError:
    JSONPATH_AVAILABLE = False
from agent_chaos_sdk.common.security import PIIRedactor, get_redactor

logger = logging.getLogger(__name__)
_jsonpath_warned = False
def _is_replay_strict() -> bool:
    return os.getenv("CHAOS_REPLAY_STRICT", "true").lower() == "true"


def _require_jsonpath(ignore_paths: List[str]) -> None:
    if not ignore_paths:
        return
    if JSONPATH_AVAILABLE:
        return
    if _is_replay_strict():
        raise RuntimeError(
            "jsonpath-ng is required for replay masking. Install jsonpath-ng "
            "or set CHAOS_REPLAY_STRICT=false to allow limited fallback."
        )


def _get_fernet() -> Fernet:
    key = os.getenv("CHAOS_TAPE_KEY")
    if not key:
        raise ValueError("CHAOS_TAPE_KEY is required for tape encryption")

    try:
        if len(key) != 44:
            key_bytes = base64.urlsafe_b64encode(key.encode("utf-8"))
        else:
            key_bytes = key.encode("utf-8")
        return Fernet(key_bytes)
    except Exception as e:
        raise ValueError(f"Invalid CHAOS_TAPE_KEY: {e}") from e


def _encrypt_payload(payload: bytes) -> bytes:
    fernet = _get_fernet()
    return fernet.encrypt(payload)


def _decrypt_payload(payload: bytes) -> bytes:
    fernet = _get_fernet()
    try:
        return fernet.decrypt(payload)
    except InvalidToken as e:
        raise ValueError("Failed to decrypt tape: invalid key or corrupted tape") from e


def normalize_request(
    method: str,
    url: str,
    body: Optional[bytes],
    headers: Optional[Dict[str, Any]],
) -> Tuple[str, str, Optional[bytes], Dict[str, str]]:
    """
    Normalize request components for deterministic fingerprinting.

    - Method: uppercased
    - URL: query params sorted alphabetically
    - Body: if JSON, parse + re-dump with sort_keys=True
    - Headers: include only allowlist
    """
    normalized_method = (method or "").upper()

    parsed = urlparse(url)
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    ignore_params = _get_ignore_params()
    ignore_params_lower = {p.lower() for p in ignore_params}
    filtered_pairs = [(k, v) for k, v in query_pairs if k.lower() not in ignore_params_lower]
    sorted_query = urlencode(sorted(filtered_pairs), doseq=True)
    normalized_url = parsed._replace(query=sorted_query).geturl()

    headers = headers or {}
    allowlist = {"content-type"}
    normalized_headers: Dict[str, str] = {}
    for key, value in headers.items():
        key_lower = str(key).lower()
        if key_lower in allowlist:
            if isinstance(value, bytes):
                normalized_headers[key_lower] = value.decode("utf-8", errors="ignore")
            else:
                normalized_headers[key_lower] = str(value)

    normalized_body = body
    content_type = normalized_headers.get("content-type", "")
    content_type_lower = content_type.lower()
    if body and ("json" in content_type_lower):
        try:
            decoded = body.decode("utf-8", errors="ignore")
            parsed_json = json.loads(decoded)
            ignore_paths = _get_ignore_paths()
            _require_jsonpath(ignore_paths)
            masked_json = _apply_ignore_paths(parsed_json, ignore_paths, scope="body")
            normalized_body = json.dumps(masked_json, sort_keys=True, separators=(",", ":")).encode("utf-8")
        except Exception:
            normalized_body = body

    ignore_paths = _get_ignore_paths()
    _require_jsonpath(ignore_paths)
    masked_headers = _apply_ignore_paths(normalized_headers, ignore_paths, scope="headers")

    return normalized_method, normalized_url, normalized_body, masked_headers


def _get_ignore_paths() -> List[str]:
    plan = get_global_plan()
    if not plan:
        return list(DEFAULT_REPLAY_IGNORE_PATHS)
    return plan.replay_config.ignore_paths or list(DEFAULT_REPLAY_IGNORE_PATHS)


def _get_ignore_params() -> List[str]:
    plan = get_global_plan()
    if not plan:
        return []
    return plan.replay_config.ignore_params or []


def _apply_ignore_paths(data: Any, ignore_paths: List[str], scope: str) -> Any:
    """
    Mask fields in data using JSONPath ignore paths.

    scope:
        - "body": apply paths without prefix or with $.body
        - "headers": apply paths with $.headers
    """
    if not ignore_paths:
        return data
    if not JSONPATH_AVAILABLE:
        if _is_replay_strict():
            raise RuntimeError(
                "jsonpath-ng is required for replay masking. Install jsonpath-ng "
                "or set CHAOS_REPLAY_STRICT=false to allow limited fallback."
            )
        masked = _apply_ignore_paths_fallback(data, ignore_paths, scope)
        return masked

    masked = data
    for path in ignore_paths:
        if scope == "headers":
            if not path.startswith("$.headers."):
                continue
            jsonpath_expr = jsonpath_parse(path.replace("$.headers.", "$."))
        else:
            # body scope
            if path.startswith("$.headers."):
                continue
            if path.startswith("$.body."):
                jsonpath_expr = jsonpath_parse(path.replace("$.body.", "$."))
            else:
                jsonpath_expr = jsonpath_parse(path)

        try:
            for match in jsonpath_expr.find(masked):
                match.full_path.update(masked, "<IGNORED>")
        except Exception as e:
            logger.debug(f"Failed to apply ignore path {path}: {e}")
            continue

    return masked


def _apply_ignore_paths_fallback(data: Any, ignore_paths: List[str], scope: str) -> Any:
    """
    Best-effort ignore path masking when jsonpath-ng is unavailable.

    Supports simple dot paths like "$.timestamp" or "$.headers.Date".
    """
    if not ignore_paths:
        return data

    masked = data
    for path in ignore_paths:
        if scope == "headers":
            if not path.startswith("$.headers."):
                continue
            simple_path = path.replace("$.headers.", "$.")
        else:
            if path.startswith("$.headers."):
                continue
            simple_path = path.replace("$.body.", "$.")

        parts = [p for p in simple_path.strip().split(".") if p and p != "$"]
        if not parts:
            continue
        if any(part.endswith("]") or part == "*" for part in parts):
            # Skip complex paths in fallback mode
            continue

        try:
            current = masked
            for key in parts[:-1]:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    current = None
                    break
            if isinstance(current, dict) and parts[-1] in current:
                current[parts[-1]] = "<IGNORED>"
        except Exception:
            continue

    global _jsonpath_warned
    if not JSONPATH_AVAILABLE and not _jsonpath_warned:
        logger.warning("jsonpath-ng not available; applying limited ignore_paths fallback")
        _jsonpath_warned = True
    return masked


def _decode_text_if_possible(data: bytes) -> Optional[str]:
    if not data:
        return None
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return None


def _redact_body_bytes(body: Optional[bytes], headers: Dict[str, Any]) -> bytes:
    redactor = get_redactor()
    if not body:
        return b""

    content_type = headers.get("Content-Type") or headers.get("content-type") or ""
    if isinstance(content_type, bytes):
        content_type = content_type.decode("utf-8", errors="ignore")
    content_type = str(content_type).lower()

    text_like = any(
        marker in content_type
        for marker in ["application/json", "text/", "application/xml", "application/x-www-form-urlencoded"]
    )
    if not text_like:
        return body

    try:
        decoded = body.decode("utf-8", errors="ignore")
        redacted_text = redactor.redact(decoded)
        return redacted_text.encode("utf-8")
    except Exception:
        return body


def _compute_json_diff(recorded: Optional[str], live: Optional[str]) -> str:
    if not recorded or not live:
        return "missing_body"
    try:
        rec_obj = json.loads(recorded)
        live_obj = json.loads(live)
        diffs = _diff_keys(rec_obj, live_obj)
        return "; ".join(diffs) if diffs else "no_diff"
    except Exception:
        return "non_json_or_unparseable"


def _diff_keys(rec_obj: Any, live_obj: Any, path: str = "$") -> List[str]:
    diffs: List[str] = []
    if isinstance(rec_obj, dict) and isinstance(live_obj, dict):
        keys = set(rec_obj.keys()) | set(live_obj.keys())
        for key in keys:
            new_path = f"{path}.{key}"
            if key not in rec_obj:
                diffs.append(f"{new_path}: missing_in_recorded")
            elif key not in live_obj:
                diffs.append(f"{new_path}: missing_in_live")
            else:
                diffs.extend(_diff_keys(rec_obj[key], live_obj[key], new_path))
    elif isinstance(rec_obj, list) and isinstance(live_obj, list):
        if len(rec_obj) != len(live_obj):
            diffs.append(f"{path}: length {len(rec_obj)} != {len(live_obj)}")
    else:
        if rec_obj != live_obj:
            diffs.append(f"{path}: {rec_obj} != {live_obj}")
    return diffs


class RequestFingerprint(BaseModel):
    """
    Fingerprint for matching requests during replay.
    
    Uses Method, URL, and Body Hash to identify requests,
    ignoring volatile headers like Date, Nonce, etc.
    """
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    url: str = Field(..., description="Request URL (normalized)")
    body_hash: Optional[str] = Field(None, description="SHA256 hash of request body")
    headers_hash: Optional[str] = Field(None, description="SHA256 hash of stable headers (excluding volatile ones)")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for hashing."""
        return {
            "method": self.method,
            "url": self.url,
            "body_hash": self.body_hash,
            "headers_hash": self.headers_hash,
        }
    
    def __hash__(self) -> int:
        """Hash for use in dictionaries."""
        return hash((self.method, self.url, self.body_hash, self.headers_hash))
    
    def __eq__(self, other) -> bool:
        """Equality comparison."""
        if not isinstance(other, RequestFingerprint):
            return False
        return (
            self.method == other.method
            and self.url == other.url
            and self.body_hash == other.body_hash
            and self.headers_hash == other.headers_hash
        )


class ResponseSnapshot(BaseModel):
    """
    Snapshot of HTTP response for replay.
    
    Stores all necessary information to reconstruct the exact response,
    including status code, headers, and body.
    """
    status_code: int = Field(..., description="HTTP status code")
    reason: str = Field(..., description="HTTP reason phrase")
    headers: Dict[str, str] = Field(..., description="Response headers")
    content: bytes = Field(..., description="Response body (bytes)")
    content_encoding: Optional[str] = Field(None, description="Content-Encoding if compressed")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status_code": self.status_code,
            "reason": self.reason,
            "headers": self.headers,
            "content": self.content.hex(),  # Convert bytes to hex string
            "content_encoding": self.content_encoding,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResponseSnapshot":
        """Create from dictionary."""
        content_hex = data.get("content", "")
        content = bytes.fromhex(content_hex) if content_hex else b""
        return cls(
            status_code=data["status_code"],
            reason=data.get("reason", "OK"),
            headers=data.get("headers", {}),
            content=content,
            content_encoding=data.get("content_encoding"),
        )


class ChaosContext(BaseModel):
    """
    Context about chaos that was applied during recording.
    
    This ensures deterministic replay - the same chaos is applied
    or the recorded "chaotic response" is returned directly.
    """
    applied_strategies: List[str] = Field(default_factory=list, description="List of strategy names applied")
    chaos_applied: bool = Field(False, description="Whether any chaos was applied")
    traffic_type: Optional[str] = Field(None, description="Traffic type from classifier")
    traffic_subtype: Optional[str] = Field(None, description="Traffic subtype from classifier")
    agent_role: Optional[str] = Field(None, description="Agent role if available")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "applied_strategies": self.applied_strategies,
            "chaos_applied": self.chaos_applied,
            "traffic_type": self.traffic_type,
            "traffic_subtype": self.traffic_subtype,
            "agent_role": self.agent_role,
        }


class TapeEntry(BaseModel):
    """
    Single entry in a tape (one request-response pair).
    
    Contains the request fingerprint, response snapshot, and chaos context.
    """
    fingerprint: RequestFingerprint = Field(..., description="Request fingerprint")
    response: ResponseSnapshot = Field(..., description="Response snapshot")
    chaos_context: ChaosContext = Field(..., description="Chaos context")
    timestamp: str = Field(..., description="ISO timestamp of recording")
    sequence: int = Field(..., description="Sequence number in tape")
    redacted: bool = Field(True, description="Whether request/response were redacted before saving")
    request_body_redacted: Optional[str] = Field(
        None,
        description="Redacted request body (text only) for debugging replay mismatches",
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "fingerprint": self.fingerprint.to_dict(),
            "response": self.response.to_dict(),
            "chaos_context": self.chaos_context.to_dict(),
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "redacted": self.redacted,
            "request_body_redacted": self.request_body_redacted,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TapeEntry":
        """Create from dictionary."""
        return cls(
            fingerprint=RequestFingerprint(**data["fingerprint"]),
            response=ResponseSnapshot.from_dict(data["response"]),
            chaos_context=ChaosContext(**data["chaos_context"]),
            timestamp=data["timestamp"],
            sequence=data["sequence"],
            redacted=data.get("redacted", True),
            request_body_redacted=data.get("request_body_redacted"),
        )


class Tape(BaseModel):
    """
    Complete tape (session recording) containing multiple entries.
    
    A tape represents a complete session of HTTP interactions that can be
    replayed deterministically.
    """
    version: str = Field("1.0", description="Tape format version")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata about the recording")
    entries: List[TapeEntry] = Field(default_factory=list, description="List of recorded entries")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "metadata": self.metadata,
            "entries": [entry.to_dict() for entry in self.entries],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Tape":
        """Create from dictionary."""
        return cls(
            version=data.get("version", "1.0"),
            metadata=data.get("metadata", {}),
            entries=[TapeEntry.from_dict(entry) for entry in data.get("entries", [])],
        )
    
    def save(self, path: Path) -> None:
        """Save tape to file."""
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False).encode("utf-8")
        encrypted = _encrypt_payload(payload)
        with open(path, 'wb') as f:
            f.write(encrypted)
        logger.info(f"Tape saved to {path} ({len(self.entries)} entries)")
    
    @classmethod
    def load(cls, path: Path) -> "Tape":
        """Load tape from file."""
        with open(path, 'rb') as f:
            raw = f.read()
        payload = _decrypt_payload(raw)
        data = json.loads(payload.decode("utf-8"))
        tape = cls.from_dict(data)
        logger.info(f"Tape loaded from {path} ({len(tape.entries)} entries)")
        return tape


class TapeRecorder:
    """
    Records HTTP interactions to a tape.
    
    Creates fingerprints for requests and snapshots for responses,
    storing them along with chaos context.
    """
    
    def __init__(self, tape_path: Optional[Path] = None):
        """
        Initialize the tape recorder.
        
        Args:
            tape_path: Path to save the tape file. If None, uses default.
        """
        self.tape_path = tape_path or Path("tapes") / f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tape"
        self.tape_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.tape = Tape(
            metadata={
                "created_at": datetime.now().isoformat(),
                "recorder_version": "1.0",
            }
        )
        self.sequence = 0
        self._redactor: PIIRedactor = get_redactor()
        
        logger.info(f"TapeRecorder initialized: {self.tape_path}")
    
    def _compute_body_hash(self, body: Optional[bytes]) -> Optional[str]:
        """Compute SHA256 hash of request body."""
        if not body:
            return None
        return hashlib.sha256(body).hexdigest()
    
    def _compute_headers_hash(self, headers: Dict[str, str]) -> Optional[str]:
        """Compute hash of normalized allowlist headers."""
        if not headers:
            return None
        sorted_headers = sorted(headers.items())
        headers_str = json.dumps(sorted_headers, sort_keys=True)
        return hashlib.sha256(headers_str.encode("utf-8")).hexdigest()
    
    def _create_fingerprint(
        self,
        method: str,
        url: str,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, Any]] = None
    ) -> RequestFingerprint:
        """
        Create request fingerprint.
        
        Args:
            method: HTTP method.
            url: Request URL (should be normalized).
            body: Request body.
            headers: Request headers.
            
        Returns:
            RequestFingerprint instance.
        """
        normalized_method, normalized_url, normalized_body, normalized_headers = normalize_request(
            method, url, body, headers or {}
        )
        body_hash = self._compute_body_hash(normalized_body)
        headers_hash = self._compute_headers_hash(normalized_headers)
        
        return RequestFingerprint(
            method=normalized_method,
            url=normalized_url,
            body_hash=body_hash,
            headers_hash=headers_hash,
        )
    
    def record(
        self,
        method: str,
        url: str,
        body: Optional[bytes],
        headers: Dict[str, Any],
        response_status: int,
        response_reason: str,
        response_headers: Dict[str, str],
        response_content: bytes,
        response_encoding: Optional[str],
        chaos_context: ChaosContext,
    ) -> None:
        """
        Record a request-response pair.
        
        Args:
            method: HTTP method.
            url: Request URL.
            body: Request body.
            headers: Request headers.
            response_status: Response status code.
            response_reason: Response reason phrase.
            response_headers: Response headers.
            response_content: Response body.
            response_encoding: Content-Encoding if compressed.
            chaos_context: Chaos context.
        """
        fingerprint = self._create_fingerprint(method, url, body, headers)
        redacted_request_body = self._redact_body(body, headers)
        _ = redacted_request_body  # Redacted request body is not stored, but is computed for compliance
        redacted_headers = self._redactor.redact_headers(headers)
        redacted_response_headers = self._redactor.redact_headers(response_headers)
        redacted_response_content = self._redact_body(response_content, response_headers)
        request_body_text = _decode_text_if_possible(redacted_request_body)
        
        response_snapshot = ResponseSnapshot(
            status_code=response_status,
            reason=response_reason,
            headers=redacted_response_headers,
            content=redacted_response_content,
            content_encoding=response_encoding,
        )
        
        entry = TapeEntry(
            fingerprint=fingerprint,
            response=response_snapshot,
            chaos_context=chaos_context,
            timestamp=datetime.now().isoformat(),
            sequence=self.sequence,
            redacted=True,
            request_body_redacted=request_body_text,
        )
        
        self.tape.entries.append(entry)
        self.sequence += 1
        
        logger.debug(
            f"Recorded entry {self.sequence}: {method} {url} -> {response_status} "
            f"(chaos: {chaos_context.chaos_applied})"
        )
    
    def save(self) -> Path:
        """
        Save the tape to file.
        
        Returns:
            Path to saved tape file.
        """
        self.tape.save(self.tape_path)
        return self.tape_path

    def _redact_body(self, body: Optional[bytes], headers: Dict[str, Any]) -> bytes:
        """
        Redact PII from request/response bodies if they are text-like.
        """
        if not body:
            return b""

        content_type = headers.get("Content-Type") or headers.get("content-type") or ""
        if isinstance(content_type, bytes):
            content_type = content_type.decode("utf-8", errors="ignore")
        content_type = str(content_type).lower()

        text_like = any(
            marker in content_type
            for marker in ["application/json", "text/", "application/xml", "application/x-www-form-urlencoded"]
        )
        if not text_like:
            return body

        try:
            decoded = body.decode("utf-8", errors="ignore")
            redacted_text = self._redactor.redact(decoded)
            return redacted_text.encode("utf-8")
        except Exception:
            return body


class TapePlayer:
    """
    Plays back recorded HTTP interactions from a tape.
    
    Matches incoming requests against recorded fingerprints and returns
    the corresponding response snapshots.
    """
    
    def __init__(self, tape_path: Path):
        """
        Initialize the tape player.
        
        Args:
            tape_path: Path to the tape file to replay.
        """
        self.tape = Tape.load(tape_path)
        self.tape_path = tape_path
        
        # Build index for fast lookup
        self._index: Dict[RequestFingerprint, TapeEntry] = {}
        for entry in self.tape.entries:
            self._index[entry.fingerprint] = entry
        
        logger.info(
            f"TapePlayer initialized: {self.tape_path} "
            f"({len(self.tape.entries)} entries, {len(self._index)} unique fingerprints)"
        )
    
    def _compute_body_hash(self, body: Optional[bytes]) -> Optional[str]:
        """Compute SHA256 hash of request body."""
        if not body:
            return None
        return hashlib.sha256(body).hexdigest()
    
    def _compute_headers_hash(self, headers: Dict[str, str]) -> Optional[str]:
        """Compute hash of normalized allowlist headers (same logic as recorder)."""
        if not headers:
            return None
        sorted_headers = sorted(headers.items())
        headers_str = json.dumps(sorted_headers, sort_keys=True)
        return hashlib.sha256(headers_str.encode("utf-8")).hexdigest()
    
    def _create_fingerprint(
        self,
        method: str,
        url: str,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, Any]] = None
    ) -> RequestFingerprint:
        """Create request fingerprint (same logic as recorder)."""
        normalized_method, normalized_url, normalized_body, normalized_headers = normalize_request(
            method, url, body, headers or {}
        )
        body_hash = self._compute_body_hash(normalized_body)
        headers_hash = self._compute_headers_hash(normalized_headers)
        
        return RequestFingerprint(
            method=normalized_method,
            url=normalized_url,
            body_hash=body_hash,
            headers_hash=headers_hash,
        )
    
    def find_match(
        self,
        method: str,
        url: str,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, Any]] = None
    ) -> Optional[TapeEntry]:
        """
        Find matching entry in tape.
        
        Args:
            method: HTTP method.
            url: Request URL.
            body: Request body.
            headers: Request headers.
            
        Returns:
            Matching TapeEntry or None if not found.
        """
        fingerprint = self._create_fingerprint(method, url, body, headers)
        
        # Exact match
        if fingerprint in self._index:
            entry = self._index[fingerprint]
            logger.debug(f"Found exact match for {method} {url} (sequence {entry.sequence})")
            return entry

        # Debug mismatch with partial matches (same method/url)
        normalized_method, normalized_url, normalized_body, normalized_headers = normalize_request(
            method, url, body, headers or {}
        )
        live_body_hash = self._compute_body_hash(normalized_body)
        live_body_text = _decode_text_if_possible(_redact_body_bytes(normalized_body, headers or {}))
        
        # Try partial match (method + URL only, ignore body/headers)
        # This is useful for GET requests or when body/headers vary slightly
        partial_fingerprint = RequestFingerprint(
            method=method,
            url=url,
            body_hash=None,
            headers_hash=None,
        )
        
        for entry in self.tape.entries:
            if (
                entry.fingerprint.method == partial_fingerprint.method
                and entry.fingerprint.url == partial_fingerprint.url
            ):
                recorded_hash = entry.fingerprint.body_hash
                diff = _compute_json_diff(entry.request_body_redacted, live_body_text)
                logger.debug(
                    f"Replay Mismatch! Recorded Body Hash: {recorded_hash}, "
                    f"Live Body Hash: {live_body_hash}. Diff: {diff}"
                )
                logger.debug(
                    f"Found partial match for {method} {url} "
                    f"(sequence {entry.sequence}, ignoring body/headers)"
                )
                return entry
        
        logger.warning(f"No match found for {method} {url}")
        return None
    
    def get_chaos_context(self, entry: TapeEntry) -> ChaosContext:
        """
        Get chaos context from entry.
        
        Args:
            entry: TapeEntry instance.
            
        Returns:
            ChaosContext from the entry.
        """
        return entry.chaos_context

