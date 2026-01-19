"""
Security utilities for PII redaction and authentication.

This module provides critical security features to prevent sensitive data
from being logged and to authenticate chaos control plane access.
"""

import re
import os
import logging
import json
import hashlib
from dataclasses import dataclass
from typing import Dict, Optional, List, Any
from urllib.parse import urlparse, parse_qs, urlencode

try:
    import jwt
    from jwt import InvalidIssuerError, ExpiredSignatureError, InvalidAudienceError, InvalidTokenError
    JWT_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    jwt = None

    class InvalidIssuerError(Exception):
        pass

    class ExpiredSignatureError(Exception):
        pass

    class InvalidAudienceError(Exception):
        pass

    class InvalidTokenError(Exception):
        pass

    JWT_AVAILABLE = False
from agent_chaos_sdk.common.logger import get_logger

logger = get_logger(__name__)


class PIIRedactor:
    """
    PII (Personally Identifiable Information) redaction utility.
    
    This class provides methods to identify and mask sensitive data patterns
    in text, URLs, headers, and request/response bodies to prevent PII leakage
    in logs and observability systems.
    """
    
    # Regex patterns for sensitive data
    PATTERNS = {
        "email": re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            re.IGNORECASE
        ),
        "credit_card": re.compile(
            r'\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{13,19}\b'
        ),
        "ssn": re.compile(
            r'\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b'
        ),
        "phone": re.compile(
            r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b'
        ),
        "api_key_anthropic": re.compile(
            r'\bsk-ant-[a-zA-Z0-9\-_]{10,}\b',
            re.IGNORECASE
        ),
        "api_key_openai": re.compile(
            r'\bsk-(?!ant-)[a-zA-Z0-9\-_]{10,}\b',  # Negative lookahead to exclude "sk-ant-"
            re.IGNORECASE
        ),
        "api_key_generic": re.compile(
            r'\b(?:api[_-]?key|apikey|access[_-]?token|secret[_-]?key)\s*[:=]\s*([a-zA-Z0-9_\-]{20,})\b',
            re.IGNORECASE
        ),
        "bearer_token": re.compile(
            r'\bBearer\s+([a-zA-Z0-9_\-\.]+)\b',
            re.IGNORECASE
        ),
        "jwt_token": re.compile(
            r'\beyJ[A-Za-z0-9-_=]+\.eyJ[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*\b'
        ),
        "password": re.compile(
            r'\b(?:password|passwd|pwd)\s*[:=]\s*([^\s"\'<>]+)\b',
            re.IGNORECASE
        ),
    }
    
    # Redaction placeholders
    REDACTIONS = {
        "email": "[REDACTED_EMAIL]",
        "credit_card": "[REDACTED_CC]",
        "ssn": "[REDACTED_SSN]",
        "phone": "[REDACTED_PHONE]",
        "api_key_openai": "[REDACTED_OPENAI_KEY]",
        "api_key_anthropic": "[REDACTED_ANTHROPIC_KEY]",
        "api_key_generic": "[REDACTED_API_KEY]",
        "bearer_token": "[REDACTED_BEARER_TOKEN]",
        "jwt_token": "[REDACTED_JWT]",
        "password": "[REDACTED_PASSWORD]",
    }
    
    def __init__(self, enabled: bool = True):
        """
        Initialize PII redactor.
        
        Args:
            enabled: Whether redaction is enabled (can be disabled for debugging).
        """
        self.enabled = enabled
        if not enabled:
            logger.warning("PII redaction is DISABLED - sensitive data may be logged!")
    
    def redact(self, text: str) -> str:
        """
        Redact all PII patterns from text.
        
        This method applies all redaction patterns in order, ensuring that
        sensitive data is masked before logging or storage.
        
        Args:
            text: Input text that may contain PII.
            
        Returns:
            Text with all PII patterns replaced with redaction placeholders.
        """
        if not self.enabled or not text:
            return text
        
        redacted = text
        
        # Apply redaction patterns in order of specificity
        # (More specific patterns first to avoid false positives)
        
        # 1. API Keys (most specific patterns first)
        # Anthropic keys must be checked before OpenAI (both start with "sk-")
        redacted = self.PATTERNS["api_key_anthropic"].sub(
            self.REDACTIONS["api_key_anthropic"],
            redacted
        )
        redacted = self.PATTERNS["api_key_openai"].sub(
            self.REDACTIONS["api_key_openai"],
            redacted
        )
        
        # 2. Bearer tokens and JWTs
        redacted = self.PATTERNS["bearer_token"].sub(
            f'Bearer {self.REDACTIONS["bearer_token"]}',
            redacted
        )
        redacted = self.PATTERNS["jwt_token"].sub(
            self.REDACTIONS["jwt_token"],
            redacted
        )
        
        # 3. Generic API keys (catch-all)
        redacted = self.PATTERNS["api_key_generic"].sub(
            lambda m: f'{m.group(0).split("=")[0]}={self.REDACTIONS["api_key_generic"]}',
            redacted
        )
        
        # 4. Passwords
        redacted = self.PATTERNS["password"].sub(
            lambda m: f'{m.group(0).split("=")[0]}={self.REDACTIONS["password"]}',
            redacted
        )
        
        # 5. Credit cards
        redacted = self.PATTERNS["credit_card"].sub(
            self.REDACTIONS["credit_card"],
            redacted
        )
        
        # 6. SSN
        redacted = self.PATTERNS["ssn"].sub(
            self.REDACTIONS["ssn"],
            redacted
        )
        
        # 7. Phone numbers
        redacted = self.PATTERNS["phone"].sub(
            self.REDACTIONS["phone"],
            redacted
        )
        
        # 8. Email addresses (last, as they're common and less sensitive)
        redacted = self.PATTERNS["email"].sub(
            self.REDACTIONS["email"],
            redacted
        )
        
        return redacted
    
    def redact_url(self, url: str) -> str:
        """
        Redact sensitive data from URLs (query parameters, paths).
        
        Args:
            url: URL string that may contain sensitive data.
            
        Returns:
            URL with sensitive query parameters redacted.
        """
        if not self.enabled or not url:
            return url
        
        try:
            url = str(url)
            parsed = urlparse(url)
            
            # Redact sensitive query parameters
            if parsed.query:
                query_params = parse_qs(parsed.query, keep_blank_values=True)
                sensitive_params = [
                    "api_key", "apikey", "token", "access_token", "secret",
                    "password", "passwd", "pwd", "auth", "authorization"
                ]
                
                redacted_params = {}
                for key, values in query_params.items():
                    if any(sensitive in key.lower() for sensitive in sensitive_params):
                        redacted_params[key] = ["[REDACTED]"]
                    else:
                        # Still redact values that look like tokens
                        redacted_values = []
                        for value in values:
                            redacted_values.append(self.redact(value))
                        redacted_params[key] = redacted_values
                
                # Reconstruct query string
                redacted_query = urlencode(redacted_params, doseq=True)
                parsed = parsed._replace(query=redacted_query)
            
            # Redact path if it contains sensitive patterns
            redacted_path = self.redact(parsed.path)
            parsed = parsed._replace(path=redacted_path)
            
            return parsed.geturl()
        
        except Exception as e:
            logger.warning(f"Error redacting URL: {e}, returning original")
            return self.redact(str(url))  # Fallback to simple text redaction
    
    def redact_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Redact sensitive headers.
        
        Args:
            headers: Dictionary of HTTP headers.
            
        Returns:
            Dictionary with sensitive header values redacted.
        """
        if not self.enabled or not headers:
            return headers
        
        redacted = {}
        sensitive_headers = [
            "authorization", "x-api-key", "x-auth-token", "cookie",
            "set-cookie", "x-chaos-token", "api-key", "access-token"
        ]
        
        for key, value in headers.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_headers):
                redacted[key] = "[REDACTED]"
            else:
                # Still check value for PII
                redacted[key] = self.redact(str(value))
        
        return redacted
    
    def redact_dict(self, data: Dict) -> Dict:
        """
        Recursively redact sensitive fields in a dictionary.
        
        Useful for redacting JSON request/response bodies.
        
        Args:
            data: Dictionary that may contain sensitive data.
            
        Returns:
            Dictionary with sensitive values redacted.
        """
        if not self.enabled or not data:
            return data
        
        redacted = {}
        sensitive_keys = [
            "password", "passwd", "pwd", "token", "api_key", "apikey",
            "secret", "access_token", "authorization", "auth", "ssn",
            "credit_card", "cc_number", "email"
        ]
        
        for key, value in data.items():
            key_lower = str(key).lower()
            
            # Check if key itself is sensitive
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                redacted[key] = "[REDACTED]"
            elif isinstance(value, dict):
                redacted[key] = self.redact_dict(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self.redact_dict(item) if isinstance(item, dict)
                    else self.redact(str(item)) if isinstance(item, str)
                    else item
                    for item in value
                ]
            elif isinstance(value, str):
                redacted[key] = self.redact(value)
            else:
                redacted[key] = value
        
        return redacted


class ChaosAuth:
    """
    Authentication middleware for chaos control plane.
    
    Validates that only authorized users can trigger chaos injection
    via the proxy.
    """
    
    def __init__(self, token: Optional[str] = None, config: Optional["ChaosAuthConfig"] = None):
        """
        Initialize authentication.
        
        Args:
            token: Admin token for validation. If None, reads from
                  CHAOS_ADMIN_TOKEN environment variable.
        """
        if config is None:
            # Scope-based API keys
            read_keys = _split_keys(os.getenv("READ_KEY") or os.getenv("CHAOS_READ_KEYS"))
            admin_keys = _split_keys(os.getenv("ADMIN_KEY") or os.getenv("CHAOS_ADMIN_KEYS"))
            config = ChaosAuthConfig(
                admin_token=token or os.getenv("CHAOS_ADMIN_TOKEN"),
                jwt_secret=os.getenv("CHAOS_JWT_SECRET"),
                jwt_issuer=os.getenv("CHAOS_JWT_ISSUER"),
                jwt_audience=os.getenv("CHAOS_JWT_AUDIENCE"),
                read_keys=read_keys,
                admin_keys=admin_keys,
            )

        self.config = config
        self.token = self.config.admin_token
        self._jwt_strict = os.getenv("CHAOS_JWT_STRICT", "true").lower() == "true"

        if self.config.jwt_secret and not JWT_AVAILABLE and self._jwt_strict:
            logger.error(
                "CHAOS_JWT_SECRET is set but pyjwt is not installed. "
                "Install pyjwt or set CHAOS_JWT_STRICT=false."
            )

        self._api_key_scopes: Dict[str, List[str]] = {}
        for key in self.config.read_keys:
            self._api_key_scopes[key] = ["READ"]
        for key in self.config.admin_keys:
            self._api_key_scopes[key] = ["ADMIN", "READ"]

        if not self.config.admin_token and not self._api_key_scopes and not self.config.jwt_secret:
            logger.warning(
                "No auth configured (CHAOS_ADMIN_TOKEN / READ_KEY / ADMIN_KEY / CHAOS_JWT_SECRET). "
                "Authentication is DISABLED. This is a security risk in production!"
            )
            self.enabled = False
        else:
            self.enabled = True
            logger.info("Chaos authentication enabled")
    
    def validate(self, flow, required_scope: str = "READ") -> bool:
        """
        Validate request authentication.
        
        Checks for Authorization Bearer or X-Chaos-Token and validates
        against scope-based API keys or JWT.
        
        Args:
            flow: HTTP flow object.
            
        Returns:
            True if authenticated with required scope, False otherwise.
        """
        auth = self.authenticate(flow, required_scope=required_scope)
        return auth.allowed

    def authenticate(self, flow, required_scope: str = "READ") -> "AuthContext":
        """
        Authenticate request and return auth context.

        Args:
            flow: HTTP flow object.
            required_scope: Required scope (READ or ADMIN).

        Returns:
            AuthContext with allowed flag and identity details.
        """
        if not self.enabled:
            return AuthContext(allowed=True, user_id="auth_disabled", scopes=["READ", "ADMIN"])

        token = _extract_token(flow)
        if not token:
            redacted_url = get_redactor().redact_url(flow.request.pretty_url)
            logger.warning(
                f"Unauthorized access attempt: Missing token for {redacted_url}"
            )
            return AuthContext(allowed=False, user_id="missing_token", scopes=[])

        # API key authentication
        if token in self._api_key_scopes:
            scopes = self._api_key_scopes[token]
            if _has_scope(scopes, required_scope):
                return AuthContext(allowed=True, user_id=_token_id(token), scopes=scopes)
            return AuthContext(allowed=False, user_id=_token_id(token), scopes=scopes)

        # Legacy admin token
        if self.config.admin_token and token == self.config.admin_token:
            scopes = ["ADMIN", "READ"]
            if _has_scope(scopes, required_scope):
                return AuthContext(allowed=True, user_id=_token_id(token), scopes=scopes)
            return AuthContext(allowed=False, user_id=_token_id(token), scopes=scopes)

        # JWT authentication
        if _looks_like_jwt(token):
            jwt_ctx = self.validate_token(token)
            if jwt_ctx is None:
                return AuthContext(allowed=False, user_id="invalid_jwt", scopes=[])

            scopes = jwt_ctx.get("scopes", [])
            user_id = jwt_ctx.get("user_id", "jwt_user")
            if _has_scope(scopes, required_scope):
                return AuthContext(allowed=True, user_id=user_id, scopes=scopes)
            return AuthContext(allowed=False, user_id=user_id, scopes=scopes)

        redacted_url = get_redactor().redact_url(flow.request.pretty_url)
        logger.warning(
            f"Unauthorized access attempt: Invalid token for {redacted_url}"
        )
        return AuthContext(allowed=False, user_id=_token_id(token), scopes=[])

    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        if not JWT_AVAILABLE:
            if self._jwt_strict:
                logger.warning("JWT validation requested but pyjwt is not installed (strict mode)")
            else:
                logger.warning("JWT validation skipped because pyjwt is not installed (non-strict)")
            return None
        if not self.config.jwt_secret:
            logger.warning("JWT provided but CHAOS_JWT_SECRET not set")
            return None

        if not self.config.jwt_issuer or not self.config.jwt_audience:
            logger.warning("JWT issuer/audience not configured; rejecting JWT")
            return None

        try:
            payload = jwt.decode(
                token,
                self.config.jwt_secret,
                algorithms=["HS256", "RS256"],
                options={"verify_exp": True, "verify_iss": True, "verify_aud": True},
                issuer=self.config.jwt_issuer,
                audience=self.config.jwt_audience,
            )
            scopes = _extract_scopes(payload)
            user_id = payload.get("sub") or payload.get("user_id") or payload.get("uid") or "jwt_user"
            return {"scopes": scopes, "user_id": f"jwt:{user_id}"}
        except InvalidIssuerError:
            logger.warning("JWT invalid issuer")
        except InvalidAudienceError:
            logger.warning("JWT invalid audience")
        except ExpiredSignatureError:
            logger.warning("JWT expired")
        except InvalidTokenError as e:
            logger.warning(f"Invalid JWT: {e}")
        return None
    
    def create_unauthorized_response(self, flow, required_scope: str = "READ") -> None:
        """
        Create a 401 Unauthorized response.
        
        Args:
            flow: HTTP flow object to modify.
        """
        message = (
            f"Invalid or missing credentials. Required scope: {required_scope}. "
            f"Provide Authorization: Bearer <token> or X-Chaos-Token."
        )
        flow.response = flow.request.make_response(
            json.dumps({"error": "Unauthorized", "message": message}).encode("utf-8"),
            status_code=401,
            headers={"Content-Type": "application/json"}
        )


@dataclass
class AuthContext:
    allowed: bool
    user_id: str
    scopes: List[str]


@dataclass
class ChaosAuthConfig:
    admin_token: Optional[str]
    jwt_secret: Optional[str]
    jwt_issuer: Optional[str]
    jwt_audience: Optional[str]
    read_keys: List[str]
    admin_keys: List[str]


def _split_keys(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _extract_token(flow) -> Optional[str]:
    auth_header = flow.request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return flow.request.headers.get("X-Chaos-Token")


def _has_scope(scopes: List[str], required_scope: str) -> bool:
    required = required_scope.upper()
    normalized = {s.upper() for s in scopes}
    return required in normalized


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2


def _token_id(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"token:{digest[:12]}"


def _extract_scopes(payload: Dict[str, Any]) -> List[str]:
    if "scopes" in payload and isinstance(payload["scopes"], list):
        return [str(s).upper() for s in payload["scopes"]]
    if "scope" in payload and isinstance(payload["scope"], str):
        return [s.upper() for s in payload["scope"].split() if s]
    return []


# Global instances
_redactor: Optional[PIIRedactor] = None
_auth: Optional[ChaosAuth] = None


def get_redactor() -> PIIRedactor:
    """Get global PII redactor instance."""
    global _redactor
    if _redactor is None:
        enabled = os.getenv("PII_REDACTION_ENABLED", "true").lower() == "true"
        _redactor = PIIRedactor(enabled=enabled)
    return _redactor


def get_auth() -> ChaosAuth:
    """Get global authentication instance."""
    global _auth
    if _auth is None:
        _auth = ChaosAuth()
    return _auth

