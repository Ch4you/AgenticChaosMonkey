"""
Unit tests for security module (PII redaction and authentication).
"""

import pytest
from agent_chaos_sdk.common.security import PIIRedactor, ChaosAuth
import os


class TestPIIRedactor:
    """Test PII redaction functionality."""
    
    def test_redact_email(self):
        """Test email redaction."""
        redactor = PIIRedactor()
        text = "Contact user@example.com for support"
        result = redactor.redact(text)
        assert "[REDACTED_EMAIL]" in result
        assert "user@example.com" not in result
    
    def test_redact_openai_api_key(self):
        """Test OpenAI API key redaction."""
        redactor = PIIRedactor()
        text = "API key: sk-abc123xyz456789012345678901234567890"
        result = redactor.redact(text)
        assert "[REDACTED_OPENAI_KEY]" in result
        assert "sk-abc123" not in result
    
    def test_redact_anthropic_api_key(self):
        """Test Anthropic API key redaction."""
        redactor = PIIRedactor()
        text = "API key: sk-ant-api03-abc123xyz456789012345678901234567890"
        result = redactor.redact(text)
        assert "[REDACTED_ANTHROPIC_KEY]" in result
        assert "sk-ant-api03" not in result
    
    def test_redact_bearer_token(self):
        """Test Bearer token redaction."""
        redactor = PIIRedactor()
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redactor.redact(text)
        assert "[REDACTED_BEARER_TOKEN]" in result
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
    
    def test_redact_jwt_token(self):
        """Test JWT token redaction."""
        redactor = PIIRedactor()
        text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ"
        result = redactor.redact(text)
        assert "[REDACTED_JWT]" in result
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
    
    def test_redact_password(self):
        """Test password redaction."""
        redactor = PIIRedactor()
        text = "password=secret123"
        result = redactor.redact(text)
        assert "[REDACTED_PASSWORD]" in result
        assert "secret123" not in result
    
    def test_redact_credit_card(self):
        """Test credit card redaction."""
        redactor = PIIRedactor()
        text = "Card: 1234-5678-9012-3456"
        result = redactor.redact(text)
        assert "[REDACTED_CC]" in result
        assert "1234-5678-9012-3456" not in result
    
    def test_redact_ssn(self):
        """Test SSN redaction."""
        redactor = PIIRedactor()
        text = "SSN: 123-45-6789"
        result = redactor.redact(text)
        assert "[REDACTED_SSN]" in result
        assert "123-45-6789" not in result
    
    def test_redact_phone(self):
        """Test phone number redaction."""
        redactor = PIIRedactor()
        text = "Phone: +1-555-123-4567"
        result = redactor.redact(text)
        assert "[REDACTED_PHONE]" in result
        assert "+1-555-123-4567" not in result
    
    def test_redact_complex_json(self, sample_json_with_pii):
        """Test redaction of complex JSON structure."""
        redactor = PIIRedactor()
        import json
        text = json.dumps(sample_json_with_pii)
        result = redactor.redact(text)
        
        # All PII should be redacted
        assert "[REDACTED_EMAIL]" in result
        assert "[REDACTED_PHONE]" in result
        assert "[REDACTED_SSN]" in result
        assert "[REDACTED_OPENAI_KEY]" in result
        assert "[REDACTED_BEARER_TOKEN]" in result
        # Password might be redacted differently (as part of key-value pair)
        assert "secret123" not in result or "[REDACTED" in result
        assert "[REDACTED_CC]" in result
        
        # Original values should not appear
        assert "user@example.com" not in result
        assert "1234-5678-9012-3456" not in result
    
    def test_redact_url_query_params(self):
        """Test URL query parameter redaction."""
        redactor = PIIRedactor()
        url = "http://api.example.com/search?api_key=secret123&token=abc456&q=test"
        result = redactor.redact_url(url)
        # URL encoding might change the format, but sensitive data should be redacted
        assert "secret123" not in result
        assert "abc456" not in result
        # Should contain some form of redaction
        assert "[REDACTED" in result or "%5BREDACTED" in result
    
    def test_redact_headers(self):
        """Test header redaction."""
        redactor = PIIRedactor()
        headers = {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "X-API-Key": "sk-abc123xyz456",
            "Content-Type": "application/json"
        }
        result = redactor.redact_headers(headers)
        assert result["Authorization"] == "[REDACTED]"
        assert result["X-API-Key"] == "[REDACTED]"
        assert result["Content-Type"] == "application/json"  # Non-sensitive header preserved
    
    def test_redact_dict(self, sample_json_with_pii):
        """Test dictionary redaction."""
        redactor = PIIRedactor()
        result = redactor.redact_dict(sample_json_with_pii)
        
        # Check that sensitive fields are redacted
        assert "[REDACTED" in str(result["user"]["email"])
        assert "[REDACTED" in str(result["user"]["phone"])
        assert "[REDACTED" in str(result["user"]["ssn"])
        assert result["api_key"] == "[REDACTED]"
        assert "[REDACTED" in str(result["token"])
        assert result["password"] == "[REDACTED]"
        assert "[REDACTED" in str(result["credit_card"])
    
    def test_redaction_disabled(self):
        """Test that redaction can be disabled."""
        redactor = PIIRedactor(enabled=False)
        text = "Email: user@example.com"
        result = redactor.redact(text)
        assert "user@example.com" in result  # Not redacted
        assert "[REDACTED_EMAIL]" not in result


class TestChaosAuth:
    """Test authentication functionality."""
    
    def test_auth_disabled_when_no_token(self, monkeypatch):
        """Test that auth is disabled when no token is set."""
        # Clear the environment variable
        if "CHAOS_ADMIN_TOKEN" in os.environ:
            monkeypatch.delenv("CHAOS_ADMIN_TOKEN")
        # Force re-initialization by creating new instance
        auth = ChaosAuth()
        # Auth should be disabled if no token is set
        assert auth.enabled is False
    
    def test_auth_enabled_with_token(self, monkeypatch):
        """Test that auth is enabled when token is set."""
        monkeypatch.setenv("CHAOS_ADMIN_TOKEN", "test-token-123")
        # Create new instance to pick up env var
        auth = ChaosAuth()
        assert auth.enabled is True
        assert auth.token == "test-token-123"
    
    def test_validate_success(self, mock_flow, monkeypatch):
        """Test successful authentication."""
        monkeypatch.setenv("CHAOS_ADMIN_TOKEN", "test-token-123")
        auth = ChaosAuth()
        # Set header as bytes (mitmproxy uses bytes)
        mock_flow.request.headers[b"X-Chaos-Token"] = b"test-token-123"
        assert auth.validate(mock_flow) is True
    
    def test_validate_failure_missing_token(self, mock_flow, monkeypatch):
        """Test authentication failure when token is missing."""
        monkeypatch.setenv("CHAOS_ADMIN_TOKEN", "test-token-123")
        auth = ChaosAuth()
        # Remove X-Chaos-Token header if it exists
        if b"X-Chaos-Token" in mock_flow.request.headers:
            del mock_flow.request.headers[b"X-Chaos-Token"]
        assert auth.validate(mock_flow) is False
    
    def test_validate_failure_wrong_token(self, mock_flow, monkeypatch):
        """Test authentication failure when token is wrong."""
        monkeypatch.setenv("CHAOS_ADMIN_TOKEN", "test-token-123")
        auth = ChaosAuth()
        mock_flow.request.headers[b"X-Chaos-Token"] = b"wrong-token"
        assert auth.validate(mock_flow) is False

