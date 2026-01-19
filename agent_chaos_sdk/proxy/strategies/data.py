"""
Data Layer Attack Strategies.

This module contains strategies that target the data/content layer:
- JSON response corruption
- Data truncation
- Malformed response injection
"""

from typing import Optional, Dict, Any
from mitmproxy import http
import logging
import json
import random

from agent_chaos_sdk.proxy.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class JSONCorruptionStrategy(BaseStrategy):
    """
    Strategy that corrupts JSON response data.
    
    This attack simulates data corruption by randomly modifying JSON values
    in API responses, which can cause parsing errors or unexpected behavior.
    """
    
    def __init__(
        self,
        name: str = "json_corruption",
        enabled: bool = True,
        corruption_text: str = "💥 CHAOS 💥",
        **kwargs
    ):
        """
        Initialize the JSON corruption strategy.
        
        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
            corruption_text: Text to inject into corrupted JSON values.
            **kwargs: Additional parameters (for dynamic config loading).
        """
        super().__init__(name, enabled)
        self.corruption_text = kwargs.get('corruption_text', corruption_text)
        logger.info(f"JSONCorruptionStrategy initialized: corruption_text={self.corruption_text}")
    
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Corrupt JSON data in the response.
        
        Handles both standard JSON and streaming JSON (NDJSON - Newline Delimited JSON).
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if data was corrupted, False otherwise.
        """
        if not self.enabled:
            return False
        
        # Only corrupt responses
        if not flow.response:
            return False
        
        # Check if response is JSON
        content_type = flow.response.headers.get("Content-Type", "").lower()
        if "json" not in content_type:
            logger.debug(f"Skipping non-JSON response: {content_type}")
            return False
        
        try:
            # Get response text
            response_text = flow.response.text
            
            if not response_text:
                logger.debug("Response text is empty, skipping corruption")
                return False
            
            # Try standard JSON first
            try:
                data = json.loads(response_text)
                # Standard JSON - corrupt and return
                corrupted_data = self._corrupt_json(data)
                corrupted_text = json.dumps(corrupted_data, ensure_ascii=False)
                
                flow.response.text = corrupted_text
                flow.response.headers["Content-Type"] = "application/json"
                
                redacted_url = self._redact_url(flow.request.pretty_url)
                logger.info(f"Injecting JSON corruption (standard JSON) for {redacted_url}")
                return True
            
            except json.JSONDecodeError:
                # Not standard JSON - try streaming JSON (NDJSON)
                logger.debug("Standard JSON parse failed, trying streaming JSON (NDJSON)")
                return self._corrupt_streaming_json(flow, response_text)
        
        except Exception as e:
            from agent_chaos_sdk.common.errors import ErrorCode
            from agent_chaos_sdk.common.telemetry import record_error_code
            record_error_code(ErrorCode.MUTATION_FAILED, strategy=self.name)
            logger.error(f"[{ErrorCode.MUTATION_FAILED}] Error corrupting JSON response: {e}", exc_info=True)
            return False
    
    def _corrupt_streaming_json(self, flow: http.HTTPFlow, text: str) -> bool:
        """
        Corrupt streaming JSON (NDJSON - Newline Delimited JSON).
        
        NDJSON format has one JSON object per line. We'll:
        1. Split by newlines
        2. Find valid JSON lines
        3. Randomly select one line to corrupt
        4. Corrupt that line's JSON
        5. Reassemble all lines
        
        Args:
            flow: The HTTP flow object.
            text: The response text (NDJSON format).
            
        Returns:
            True if corruption was successful, False otherwise.
        """
        try:
            # Split by newlines
            lines = text.split('\n')
            
            # Filter out empty lines and find valid JSON lines
            valid_json_lines = []
            line_indices = []
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # Check if line looks like JSON (starts with { or [)
                if line.startswith('{') or line.startswith('['):
                    try:
                        # Try to parse as JSON to validate
                        json.loads(line)
                        valid_json_lines.append(line)
                        line_indices.append(i)
                    except json.JSONDecodeError:
                        # Not valid JSON, skip
                        continue
            
            if not valid_json_lines:
                logger.debug("No valid JSON lines found in streaming response")
                return False
            
            # Randomly select one line to corrupt
            selected_index = random.randint(0, len(valid_json_lines) - 1)
            selected_line = valid_json_lines[selected_index]
            original_line_index = line_indices[selected_index]
            
            logger.debug(f"Corrupting line {original_line_index} of {len(valid_json_lines)} valid JSON lines")
            
            # Parse the selected line
            try:
                data = json.loads(selected_line)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse selected JSON line: {e}")
                return False
            
            # Corrupt the data
            corrupted_data = self._corrupt_json(data)
            
            # Serialize back to JSON
            corrupted_line = json.dumps(corrupted_data, ensure_ascii=False)
            
            # Replace the original line with corrupted line
            lines[original_line_index] = corrupted_line
            
            # Reassemble all lines
            corrupted_text = '\n'.join(lines)
            
            # Update response
            flow.response.text = corrupted_text
            flow.response.headers["Content-Type"] = "application/json"
            
            redacted_url = self._redact_url(flow.request.pretty_url)
            logger.info(
                f"Injecting JSON corruption (streaming JSON, line {original_line_index}) "
                f"for {redacted_url}"
            )
            return True
        
        except Exception as e:
            from agent_chaos_sdk.common.errors import ErrorCode
            from agent_chaos_sdk.common.telemetry import record_error_code
            record_error_code(ErrorCode.MUTATION_FAILED, strategy=self.name)
            logger.error(f"[{ErrorCode.MUTATION_FAILED}] Error corrupting streaming JSON: {e}", exc_info=True)
            return False
    
    def _corrupt_json(self, data: Any) -> Any:
        """
        Recursively corrupt JSON data by randomly selecting keys and replacing values.
        
        Args:
            data: JSON data (dict, list, or primitive).
            
        Returns:
            Corrupted JSON data.
        """
        if isinstance(data, dict):
            if not data:
                return data
            
            # Randomly select a key to corrupt
            keys = list(data.keys())
            key_to_corrupt = random.choice(keys)
            
            # Recursively corrupt nested structures
            corrupted = data.copy()
            corrupted[key_to_corrupt] = self._corrupt_json(data[key_to_corrupt])
            
            return corrupted
        
        elif isinstance(data, list):
            if not data:
                return data
            
            # Randomly select an index to corrupt
            index_to_corrupt = random.randint(0, len(data) - 1)
            
            # Recursively corrupt nested structures
            corrupted = data.copy()
            corrupted[index_to_corrupt] = self._corrupt_json(data[index_to_corrupt])
            
            return corrupted
        
        else:
            # Replace primitive value with corruption text
            return self.corruption_text
