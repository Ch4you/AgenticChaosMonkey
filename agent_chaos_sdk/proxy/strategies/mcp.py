"""
MCP Protocol Fuzzing Strategy - Schema-Aware Fuzzing

This module provides advanced fuzzing capabilities for MCP (Model Context Protocol)
tool calls, with schema-aware introspection to inject intelligent faults.

Key Features:
- Schema-aware field detection (date, numeric, string)
- Intelligent fuzzing based on field types
- Configurable attack modes
- Logic error injection (not just network errors)
"""

import json
import random
import re
from typing import Optional, Dict, Any, List
from mitmproxy import http
import logging

from agent_chaos_sdk.proxy.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class SchemaAwareFuzzer:
    """
    Schema-aware fuzzer that intelligently injects faults based on field types.
    
    This fuzzer analyzes JSON request bodies and injects faults that target
    specific field types, causing logic errors rather than just network errors.
    """
    
    # Date-related field patterns
    DATE_FIELDS = ["date", "time", "datetime", "timestamp", "departure", "arrival", "checkin", "checkout"]
    
    # Numeric field patterns
    NUMERIC_FIELDS = ["price", "amount", "cost", "quantity", "count", "number", "id", "age", "seats"]
    
    # String field patterns
    STRING_FIELDS = ["name", "description", "message", "text", "content", "origin", "destination", "city"]
    
    # SQL injection payloads
    SQL_INJECTION_PAYLOADS = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "' UNION SELECT * FROM users --",
        "1' OR '1'='1",
        "admin'--",
        "' OR 1=1--",
        "1' UNION SELECT NULL--",
    ]
    
    # Buffer overflow payloads (various sizes)
    BUFFER_OVERFLOW_PAYLOADS = {
        "small": "A" * 1000,  # 1KB
        "medium": "A" * 10000,  # 10KB
        "large": "A" * 100000,  # 100KB
        "huge": "A" * 1000000,  # 1MB
        "massive": "A" * 10000000,  # 10MB
    }
    
    # Invalid date formats
    INVALID_DATE_FORMATS = [
        "2025/13/40",  # Invalid month/day
        "yesterday",  # Relative date
        "tomorrow",  # Relative date
        "2025-13-01",  # Invalid month
        "2025-02-30",  # Invalid day
        "2025-00-01",  # Zero month
        "2025-01-00",  # Zero day
        "13/40/2025",  # Wrong format
        "2025-1-1",  # Missing leading zeros
        "25-12-2025",  # Wrong order
    ]
    
    @classmethod
    def detect_field_type(cls, field_name: str, field_value: Any) -> str:
        """
        Detect the type of a field based on its name and value.
        
        Args:
            field_name: Name of the field
            field_value: Value of the field
            
        Returns:
            Field type: "date", "numeric", "string", or "unknown"
        """
        field_lower = field_name.lower()
        
        # Check date fields
        for pattern in cls.DATE_FIELDS:
            if pattern in field_lower:
                return "date"
        
        # Check numeric fields
        for pattern in cls.NUMERIC_FIELDS:
            if pattern in field_lower:
                return "numeric"
        
        # Check string fields
        for pattern in cls.STRING_FIELDS:
            if pattern in field_lower:
                return "string"
        
        # Infer from value type
        if isinstance(field_value, (int, float)):
            return "numeric"
        elif isinstance(field_value, str):
            # Try to detect date format
            if re.match(r'^\d{4}-\d{2}-\d{2}', field_value):
                return "date"
            return "string"
        
        return "unknown"
    
    @classmethod
    def fuzz_date_field(cls, field_name: str, original_value: Any, mode: str = "invalid_format") -> Any:
        """
        Fuzz a date field with various attack vectors.
        
        Args:
            field_name: Name of the field
            original_value: Original field value
            mode: Fuzzing mode ("invalid_format", "sql_injection", "random")
            
        Returns:
            Fuzzed value
        """
        if mode == "invalid_format":
            return random.choice(cls.INVALID_DATE_FORMATS)
        elif mode == "sql_injection":
            # Inject SQL injection payload into date field
            return random.choice(cls.SQL_INJECTION_PAYLOADS)
        elif mode == "relative_date":
            return random.choice(["yesterday", "tomorrow", "today", "next week"])
        else:  # random
            return random.choice([
                random.choice(cls.INVALID_DATE_FORMATS),
                random.choice(cls.SQL_INJECTION_PAYLOADS),
                "yesterday",
            ])
    
    @classmethod
    def fuzz_numeric_field(cls, field_name: str, original_value: Any, mode: str = "type_mismatch") -> Any:
        """
        Fuzz a numeric field with various attack vectors.
        
        Args:
            field_name: Name of the field
            original_value: Original field value
            mode: Fuzzing mode ("type_mismatch", "negative", "max_int", "random")
            
        Returns:
            Fuzzed value
        """
        if mode == "type_mismatch":
            # Convert to string (type mismatch)
            return str(original_value) + "abc"
        elif mode == "negative":
            # Inject negative number (if original was positive)
            if isinstance(original_value, (int, float)) and original_value > 0:
                return -abs(original_value)
            return -999999
        elif mode == "max_int":
            # Inject maximum integer
            return 2**31 - 1  # MAX_INT
        elif mode == "zero":
            return 0
        elif mode == "null":
            return None
        else:  # random
            return random.choice([
                str(original_value) + "abc",  # Type mismatch
                -999999,  # Negative
                2**31 - 1,  # MAX_INT
                0,  # Zero
                None,  # Null
            ])
    
    @classmethod
    def fuzz_string_field(cls, field_name: str, original_value: Any, mode: str = "buffer_overflow") -> Any:
        """
        Fuzz a string field with various attack vectors.
        
        Args:
            field_name: Name of the field
            original_value: Original field value
            mode: Fuzzing mode ("buffer_overflow", "empty", "sql_injection", "random")
            
        Returns:
            Fuzzed value
        """
        if mode == "buffer_overflow":
            # Inject large payload (buffer overflow simulation)
            size = random.choice(["medium", "large", "huge", "massive"])
            return cls.BUFFER_OVERFLOW_PAYLOADS[size]
        elif mode == "empty":
            return ""  # Empty string
        elif mode == "sql_injection":
            # Inject SQL injection payload
            return random.choice(cls.SQL_INJECTION_PAYLOADS)
        elif mode == "xss":
            # XSS payload
            return "<script>alert('XSS')</script>"
        else:  # random
            return random.choice([
                cls.BUFFER_OVERFLOW_PAYLOADS["large"],  # Buffer overflow
                "",  # Empty
                random.choice(cls.SQL_INJECTION_PAYLOADS),  # SQL injection
            ])
    
    @classmethod
    def fuzz_field(cls, field_name: str, field_value: Any, field_type: str, mode: str = "random") -> Any:
        """
        Fuzz a field based on its detected type.
        
        Args:
            field_name: Name of the field
            field_value: Original field value
            field_type: Detected field type
            mode: Fuzzing mode
            
        Returns:
            Fuzzed value
        """
        if field_type == "date":
            return cls.fuzz_date_field(field_name, field_value, mode)
        elif field_type == "numeric":
            return cls.fuzz_numeric_field(field_name, field_value, mode)
        elif field_type == "string":
            return cls.fuzz_string_field(field_name, field_value, mode)
        else:
            # Unknown type - try generic fuzzing
            if isinstance(field_value, str):
                return cls.fuzz_string_field(field_name, field_value, mode)
            elif isinstance(field_value, (int, float)):
                return cls.fuzz_numeric_field(field_name, field_value, mode)
            else:
                return None  # Null injection


class MCPProtocolFuzzingStrategy(BaseStrategy):
    """
    Schema-aware MCP Protocol Fuzzing Strategy.
    
    This strategy intercepts tool calls (MCP protocol) and injects intelligent
    faults based on field types and schemas. It causes logic errors, not just
    network errors.
    
    Features:
    - Schema-aware field detection
    - Type-specific fuzzing (date, numeric, string)
    - Configurable attack modes
    - Logic error injection
    """
    
    def __init__(
        self,
        name: str = "mcp_fuzzing",
        enabled: bool = True,
        fuzz_type: str = "schema_violation",
        target_endpoint: Optional[str] = None,
        field_mode: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """
        Initialize the schema-aware MCP fuzzing strategy.
        
        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
            fuzz_type: Type of fuzzing ("schema_violation", "type_mismatch", "null_injection", "garbage_value", "random").
            target_endpoint: Optional target endpoint pattern (e.g., "/search_flights").
            field_mode: Optional dict mapping field types to fuzzing modes (e.g., {"date": "sql_injection", "numeric": "type_mismatch"}).
            **kwargs: Additional parameters.
        """
        super().__init__(name, enabled)
        self.fuzz_type = kwargs.get('fuzz_type', fuzz_type)
        self.target_endpoint = kwargs.get('target_endpoint', target_endpoint)
        self.field_mode = kwargs.get('field_mode', field_mode) or {}
        
        # Valid fuzz types
        valid_types = [
            "schema_violation",  # Schema-aware fuzzing (default)
            "type_mismatch",
            "null_injection",
            "garbage_value",
            "random"
        ]
        
        if self.fuzz_type not in valid_types:
            logger.warning(
                f"Invalid fuzz_type: {self.fuzz_type}. Using 'schema_violation'."
            )
            self.fuzz_type = "schema_violation"
        
        # Initialize schema-aware fuzzer
        self.fuzzer = SchemaAwareFuzzer()
        
        logger.info(
            f"MCPProtocolFuzzingStrategy initialized: "
            f"fuzz_type={self.fuzz_type}, target_endpoint={self.target_endpoint}"
        )
    
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Apply schema-aware fuzzing to the flow.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if fuzzing was applied, False otherwise.
        """
        if not self.enabled:
            return False
        
        # Check if this is a tool call request
        if not self._is_tool_call_request(flow):
            return False
        
        # Check target endpoint if specified
        if self.target_endpoint and self.target_endpoint not in flow.request.pretty_url:
            return False
        
        # Apply fuzzing based on type
        if self.fuzz_type == "schema_violation":
            return self._apply_schema_violation(flow)
        elif self.fuzz_type == "type_mismatch":
            return self._apply_type_mismatch(flow)
        elif self.fuzz_type == "null_injection":
            return self._apply_null_injection(flow)
        elif self.fuzz_type == "garbage_value":
            return self._apply_garbage_value(flow)
        elif self.fuzz_type == "random":
            # Randomly choose a fuzzing method
            method = random.choice([
                self._apply_schema_violation,
                self._apply_type_mismatch,
                self._apply_null_injection,
                self._apply_garbage_value,
            ])
            return method(flow)
        
        return False
    
    def _apply_schema_violation_to_body(self, body: Dict[str, Any]) -> bool:
        """
        Apply schema-aware fuzzing to a JSON body (direct API call format).
        
        This handles direct API calls like POST /search_flights with JSON body.
        
        Args:
            body: JSON body dictionary.
            
        Returns:
            True if fuzzing was applied.
        """
        # Track fuzzed fields for logging
        fuzzed_fields = []
        
        # Iterate through all fields and fuzz based on type
        for field_name, field_value in body.items():
            # Detect field type
            field_type = self.fuzzer.detect_field_type(field_name, field_value)
            
            if field_type == "unknown":
                continue
            
            # Get fuzzing mode for this field type
            mode = self.field_mode.get(field_type, "random")
            
            # Fuzz the field
            fuzzed_value = self.fuzzer.fuzz_field(
                field_name, field_value, field_type, mode
            )
            
            if fuzzed_value is not None:
                body[field_name] = fuzzed_value
                fuzzed_fields.append({
                    "field": field_name,
                    "type": field_type,
                    "original": field_value,
                    "fuzzed": str(fuzzed_value)[:100]  # Truncate for logging
                })
        
        if fuzzed_fields:
            logger.warning(
                f"Schema-aware fuzzing: {len(fuzzed_fields)} fields fuzzed"
            )
            for field_info in fuzzed_fields:
                logger.debug(
                    f"  - {field_info['field']} ({field_info['type']}): "
                    f"{field_info['original']} → {field_info['fuzzed']}"
                )
            return True
        
        return False
    
    def _is_tool_call_request(self, flow: http.HTTPFlow) -> bool:
        """
        Check if this is a tool call request (MCP protocol or direct API call).
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if this looks like a tool call request.
        """
        # Check if request has JSON body
        if not flow.request.content:
            return False
        
        # Check Content-Type (handle both bytes and str from mitmproxy)
        content_type_header = flow.request.headers.get("Content-Type", "")
        # Convert bytes to string if needed
        if isinstance(content_type_header, bytes):
            content_type = content_type_header.decode('utf-8', errors='ignore').lower()
        else:
            content_type = str(content_type_header).lower()
        if "application/json" not in content_type:
            return False
        
        try:
            body_text = flow.request.get_text()
            if not body_text:
                return False
            
            # Try to parse as JSON
            body = json.loads(body_text)
            
            if not isinstance(body, dict):
                return False
            
            # Check for tool call indicators in various formats:
            
            # 1. OpenAI format: {"tool_calls": [...]} or {"function_call": {...}}
            if "tool_calls" in body or "function_call" in body:
                return True
            
            # 2. Anthropic format: messages with tool_use blocks
            if "messages" in body:
                messages = body["messages"]
                if isinstance(messages, list):
                    for msg in messages:
                        if isinstance(msg, dict):
                            if "tool_calls" in msg or "function_call" in msg:
                                return True
                            if "content" in msg:
                                content = msg["content"]
                                if isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict) and block.get("type") == "tool_use":
                                            return True
            
            # 3. Direct API call format (our mock server):
            # POST to /search_flights with {"origin": "...", "destination": "...", "date": "..."}
            # POST to /book_ticket with {"flight_id": "..."}
            if flow.request.method == "POST":
                url = flow.request.pretty_url.lower()
                # Check if it's a tool/API endpoint (not just any POST)
                tool_indicators = [
                    "/search_flights", "/book_ticket",  # Our mock server
                    "/v1/chat/completions",  # OpenAI
                    "/v1/messages",  # Anthropic
                    "/api/chat",  # Generic chat API
                ]
                
                if any(indicator in url for indicator in tool_indicators):
                    # Check if body has structured data (looks like tool call parameters)
                    if any(key in body for key in [
                        "origin", "destination", "date",  # Flight search
                        "flight_id",  # Booking
                        "tool_calls", "function_call",  # Tool calls
                        "messages",  # Chat messages
                    ]):
                        return True
            
            return False
        
        except (json.JSONDecodeError, AttributeError):
            return False
    
    def _apply_schema_violation(self, flow: http.HTTPFlow) -> bool:
        """
        Apply schema-aware fuzzing (intelligent field-based fuzzing).
        
        This is the main schema-aware fuzzing method that detects field types
        and injects appropriate faults. It handles both:
        - Direct API calls (e.g., POST /search_flights with JSON body)
        - Tool call formats (OpenAI, Anthropic)
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if fuzzing was applied.
        """
        try:
            body_text = flow.request.get_text()
            if not body_text:
                return False
            
            body = json.loads(body_text)
            
            fuzzed = False
            
            # Check for direct API call format (our mock server)
            # Format: {"origin": "...", "destination": "...", "date": "..."}
            if isinstance(body, dict) and not any(key in body for key in ["tool_calls", "function_call", "messages"]):
                # Direct API call - fuzz the body directly
                if self._apply_schema_violation_to_body(body):
                    fuzzed = True
            
            # Check for OpenAI format: tool_calls in messages
            elif "messages" in body and isinstance(body["messages"], list):
                for message in body["messages"]:
                    if "tool_calls" in message and isinstance(message["tool_calls"], list):
                        for tool_call in message["tool_calls"]:
                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                try:
                                    args_str = tool_call["function"]["arguments"]
                                    if isinstance(args_str, str):
                                        args = json.loads(args_str)
                                    else:
                                        args = args_str
                                    
                                    if self._apply_schema_violation_to_body(args):
                                        tool_call["function"]["arguments"] = json.dumps(args, ensure_ascii=False)
                                        fuzzed = True
                                except (json.JSONDecodeError, KeyError):
                                    pass
                    
                    # Check for function_call format
                    if "function_call" in message:
                        try:
                            args_str = message["function_call"].get("arguments", "{}")
                            if isinstance(args_str, str):
                                args = json.loads(args_str)
                            else:
                                args = args_str
                            
                            if self._apply_schema_violation_to_body(args):
                                message["function_call"]["arguments"] = json.dumps(args, ensure_ascii=False)
                                fuzzed = True
                        except (json.JSONDecodeError, KeyError):
                            pass
            
            # Check for Anthropic format: tool_use blocks
            elif "messages" in body:
                for message in body.get("messages", []):
                    if isinstance(message, dict) and "content" in message:
                        content = message["content"]
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "tool_use":
                                    if "input" in block and isinstance(block["input"], dict):
                                        if self._apply_schema_violation_to_body(block["input"]):
                                            fuzzed = True
            
            if fuzzed:
                # Update request body
                flow.request.text = json.dumps(body, ensure_ascii=False)
                flow.request.headers["Content-Length"] = str(len(flow.request.text.encode('utf-8')))
                
                redacted_url = self._redact_url(flow.request.pretty_url)
                logger.warning(
                    f"Schema-aware fuzzing applied to {redacted_url}"
                )
                return True
            
            return False
        
        except (json.JSONDecodeError, AttributeError, Exception) as e:
            logger.error(f"Error in schema-aware fuzzing: {e}", exc_info=True)
            return False
    
    def _apply_type_mismatch(self, flow: http.HTTPFlow) -> bool:
        """
        Apply type mismatch fuzzing (legacy method).
        
        Handles both direct API calls and nested tool call formats.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if fuzzing was applied.
        """
        try:
            body_text = flow.request.get_text()
            if not body_text:
                return False
            
            body = json.loads(body_text)
            fuzzed = False
            
            # Handle nested tool call format (messages -> tool_calls -> function -> arguments)
            if "messages" in body and isinstance(body["messages"], list):
                for message in body["messages"]:
                    if "tool_calls" in message and isinstance(message["tool_calls"], list):
                        for tool_call in message["tool_calls"]:
                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                try:
                                    args_str = tool_call["function"]["arguments"]
                                    if isinstance(args_str, str):
                                        args = json.loads(args_str)
                                    else:
                                        args = args_str
                                    
                                    # Find a numeric field and convert to string
                                    for key, value in args.items():
                                        if isinstance(value, (int, float)):
                                            args[key] = str(value) + "abc"
                                            tool_call["function"]["arguments"] = json.dumps(args, ensure_ascii=False)
                                            fuzzed = True
                                            break
                                except (json.JSONDecodeError, KeyError):
                                    pass
            
            # Handle direct API call format
            if not fuzzed and isinstance(body, dict):
                for key, value in body.items():
                    if isinstance(value, (int, float)):
                        body[key] = str(value) + "abc"
                        fuzzed = True
                        break
            
            if fuzzed:
                flow.request.text = json.dumps(body, ensure_ascii=False)
                flow.request.headers["Content-Length"] = str(len(flow.request.text.encode('utf-8')))
                logger.warning(f"Type mismatch fuzzing applied")
                return True
            
            return False
        
        except (json.JSONDecodeError, AttributeError):
            return False
    
    def _apply_null_injection(self, flow: http.HTTPFlow) -> bool:
        """
        Apply null injection fuzzing (legacy method).
        
        Handles both direct API calls and nested tool call formats.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if fuzzing was applied.
        """
        try:
            body_text = flow.request.get_text()
            if not body_text:
                return False
            
            body = json.loads(body_text)
            fuzzed = False
            
            # Handle nested tool call format (messages -> tool_calls -> function -> arguments)
            if "messages" in body and isinstance(body["messages"], list):
                for message in body["messages"]:
                    if "tool_calls" in message and isinstance(message["tool_calls"], list):
                        for tool_call in message["tool_calls"]:
                            if "function" in tool_call and "arguments" in tool_call["function"]:
                                try:
                                    args_str = tool_call["function"]["arguments"]
                                    if isinstance(args_str, str):
                                        args = json.loads(args_str)
                                    else:
                                        args = args_str
                                    
                                    # Remove a required field (set to None)
                                    if args:
                                        key = random.choice(list(args.keys()))
                                        original_value = args[key]
                                        args[key] = None
                                        tool_call["function"]["arguments"] = json.dumps(args, ensure_ascii=False)
                                        fuzzed = True
                                        break
                                except (json.JSONDecodeError, KeyError):
                                    pass
            
            # Handle direct API call format
            if not fuzzed and isinstance(body, dict) and body:
                key = random.choice(list(body.keys()))
                original_value = body[key]
                body[key] = None
                fuzzed = True
            
            if fuzzed:
                flow.request.text = json.dumps(body, ensure_ascii=False)
                flow.request.headers["Content-Length"] = str(len(flow.request.text.encode('utf-8')))
                logger.warning(f"Null injection fuzzing applied")
                return True
            
            return False
        
        except (json.JSONDecodeError, AttributeError):
            return False
    
    def _apply_garbage_value(self, flow: http.HTTPFlow) -> bool:
        """
        Apply garbage value fuzzing (legacy method).
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if fuzzing was applied.
        """
        try:
            body_text = flow.request.get_text()
            if not body_text:
                return False
            
            body = json.loads(body_text)
            
            # Replace a value with garbage
            if body:
                key = random.choice(list(body.keys()))
                original_value = body[key]
                body[key] = "💥 CHAOS 💥"
                flow.request.text = json.dumps(body)
                flow.request.headers["Content-Length"] = str(len(flow.request.text))
                logger.warning(f"Garbage value: {key} = {original_value} → 💥 CHAOS 💥")
                return True
            
            return False
        
        except (json.JSONDecodeError, AttributeError):
            return False
