"""
Cognitive Layer Attack Strategies.

This module contains strategies that target the cognitive/logic layer of AI agents:
- Hallucination: Inject false but plausible data into tool responses
- Context Overflow: Inject massive amounts of noise into prompts/contexts
"""

from typing import Optional, Dict, Any, List
from mitmproxy import http
import logging
import json
import re
import random
from datetime import datetime, timedelta

from agent_chaos_sdk.proxy.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class HallucinationStrategy(BaseStrategy):
    """
    Strategy that injects false but plausible data into tool responses.
    
    This cognitive attack tests if agents blindly trust tool responses or
    verify the data they receive. It swaps entities (numbers, dates, names)
    with plausible but incorrect values.
    
    Example:
        Original: {"price": 99.99, "date": "2025-12-25"}
        Hallucinated: {"price": 149.99, "date": "2025-12-26"}
    """
    
    def __init__(
        self,
        name: str = "hallucination",
        enabled: bool = True,
        mode: str = "swap_entities",
        probability: float = 1.0,
        **kwargs
    ):
        """
        Initialize the hallucination strategy.
        
        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
            mode: Attack mode ("swap_entities", "invert_numbers", "shift_dates").
            probability: Probability (0.0-1.0) of applying the attack.
            **kwargs: Additional parameters (for dynamic config loading).
        """
        super().__init__(name, enabled, **kwargs)
        self.mode = kwargs.get('mode', mode)
        self.probability = kwargs.get('probability', probability)
        
        # Entity patterns for detection
        self.number_pattern = re.compile(r'\b\d+\.?\d*\b')
        self.date_pattern = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
        self.price_pattern = re.compile(r'\$?\d+\.\d{2}\b')
        
        logger.info(f"HallucinationStrategy initialized: mode={self.mode}, probability={self.probability}")
    
    def _swap_number(self, value: str) -> str:
        """Swap a number with a plausible but different value."""
        try:
            num = float(value)
            # Swap with ±20% variation or ±10, whichever is larger
            variation = max(abs(num * 0.2), 10)
            new_num = num + random.choice([-1, 1]) * random.uniform(variation * 0.5, variation)
            # Preserve decimal places
            if '.' in value:
                decimals = len(value.split('.')[1])
                return f"{new_num:.{decimals}f}"
            else:
                return str(int(new_num))
        except ValueError:
            return value
    
    def _swap_date(self, value: str) -> str:
        """Swap a date with a nearby but different date."""
        try:
            date_obj = datetime.strptime(value, "%Y-%m-%d")
            # Shift by ±7 days
            days_shift = random.choice([-7, -5, -3, 3, 5, 7])
            new_date = date_obj + timedelta(days=days_shift)
            return new_date.strftime("%Y-%m-%d")
        except ValueError:
            return value
    
    def _swap_price(self, value: str) -> str:
        """Swap a price with a different but plausible price."""
        # Remove $ if present
        clean_value = value.replace('$', '')
        try:
            price = float(clean_value)
            # Swap with ±30% variation
            variation = price * 0.3
            new_price = price + random.choice([-1, 1]) * random.uniform(variation * 0.5, variation)
            # Format as price
            formatted = f"${new_price:.2f}"
            # Preserve original format
            if '$' not in value:
                formatted = formatted.replace('$', '')
            return formatted
        except ValueError:
            return value
    
    def _hallucinate_json(self, data: Any, depth: int = 0) -> Any:
        """
        Recursively hallucinate entities in JSON data.
        
        Args:
            data: JSON data (dict, list, or primitive).
            depth: Current recursion depth (to prevent infinite loops).
            
        Returns:
            Hallucinated data with swapped entities.
        """
        if depth > 10:  # Safety limit
            return data
        
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                # Check if value is a number, date, or price
                if isinstance(value, (int, float)):
                    # Swap numeric values
                    if self.mode == "swap_entities":
                        result[key] = float(self._swap_number(str(value)))
                    elif self.mode == "invert_numbers":
                        result[key] = -value if isinstance(value, (int, float)) else value
                    else:
                        result[key] = value
                elif isinstance(value, str):
                    # Check for dates
                    if self.date_pattern.match(value):
                        result[key] = self._swap_date(value) if self.mode == "swap_entities" else value
                    # Check for prices
                    elif self.price_pattern.search(value):
                        result[key] = self._swap_price(value) if self.mode == "swap_entities" else value
                    # Check for embedded numbers
                    elif self.number_pattern.search(value) and self.mode == "swap_entities":
                        # Replace numbers in string
                        result[key] = self.number_pattern.sub(
                            lambda m: self._swap_number(m.group()),
                            value
                        )
                    else:
                        result[key] = self._hallucinate_json(value, depth + 1)
                else:
                    result[key] = self._hallucinate_json(value, depth + 1)
            return result
        elif isinstance(data, list):
            return [self._hallucinate_json(item, depth + 1) for item in data]
        else:
            return data
    
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Apply hallucination attack to response.
        
        Only modifies responses (not requests) to inject false data.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if attack was applied, False otherwise.
        """
        if not self.should_trigger(flow):
            return False
        
        if not flow.response:
            return False
        
        # Only apply to responses
        if not hasattr(flow.response, 'content') or not flow.response.content:
            return False
        
        # Check probability
        if random.random() >= self.probability:
            return False
        
        try:
            # Get response text
            response_text = flow.response.get_text()
            if not response_text:
                return False
            
            # Try to parse as JSON
            try:
                data = json.loads(response_text)
                
                # Hallucinate the data
                hallucinated_data = self._hallucinate_json(data)
                
                # Serialize back
                new_text = json.dumps(hallucinated_data, ensure_ascii=False)
                flow.response.text = new_text
                flow.response.headers["Content-Length"] = str(len(new_text.encode('utf-8')))
                
                redacted_url = self._redact_url(flow.request.pretty_url)
                logger.warning(
                    f"HallucinationStrategy '{self.name}' injected false data into response "
                    f"for {redacted_url}"
                )
                return True
            except json.JSONDecodeError:
                # Not JSON, try to hallucinate text directly
                if self.mode == "swap_entities":
                    # Replace numbers in text
                    hallucinated_text = self.number_pattern.sub(
                        lambda m: self._swap_number(m.group()),
                        response_text
                    )
                    # Replace dates
                    hallucinated_text = self.date_pattern.sub(
                        lambda m: self._swap_date(m.group()),
                        hallucinated_text
                    )
                    
                    if hallucinated_text != response_text:
                        flow.response.text = hallucinated_text
                        flow.response.headers["Content-Length"] = str(len(hallucinated_text.encode('utf-8')))
                        redacted_url = self._redact_url(flow.request.pretty_url)
                        logger.warning(
                            f"HallucinationStrategy '{self.name}' injected false data into text response "
                            f"for {redacted_url}"
                        )
                        return True
            
            return False
        except Exception as e:
            from agent_chaos_sdk.common.errors import ErrorCode
            from agent_chaos_sdk.common.telemetry import record_error_code
            record_error_code(ErrorCode.MUTATION_FAILED, strategy=self.name)
            logger.error(f"[{ErrorCode.MUTATION_FAILED}] Error applying hallucination strategy: {e}", exc_info=True)
            return False


class ContextOverflowStrategy(BaseStrategy):
    """
    Strategy that injects massive amounts of noise into prompts/contexts.
    
    This safety attack tests if agents crash or forget earlier instructions
    due to context window limits. It appends 5k-10k tokens of garbage text
    to request bodies.
    
    Example:
        Original prompt: "Search for flights"
        Overflow: "Search for flights [5k tokens of garbage]"
    """
    
    def __init__(
        self,
        name: str = "context_overflow",
        enabled: bool = True,
        token_count: int = 7500,
        mode: str = "repeating_chars",
        probability: float = 1.0,
        **kwargs
    ):
        """
        Initialize the context overflow strategy.
        
        Args:
            name: Strategy name identifier.
            enabled: Whether this strategy is enabled.
            token_count: Number of tokens to inject (default: 7500, ~30k chars).
            mode: Overflow mode ("repeating_chars", "random_words", "gibberish").
            probability: Probability (0.0-1.0) of applying the attack.
            **kwargs: Additional parameters (for dynamic config loading).
        """
        super().__init__(name, enabled, **kwargs)
        self.token_count = kwargs.get('token_count', token_count)
        self.mode = kwargs.get('mode', mode)
        self.probability = kwargs.get('probability', probability)
        
        # Generate overflow content
        self._overflow_content = self._generate_overflow()
        
        logger.info(
            f"ContextOverflowStrategy initialized: "
            f"token_count={self.token_count}, mode={self.mode}, probability={self.probability}"
        )
    
    def _generate_overflow(self) -> str:
        """Generate overflow content based on mode."""
        # Estimate: ~4 characters per token
        char_count = self.token_count * 4
        
        if self.mode == "repeating_chars":
            # Repeat characters
            chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            return (chars * (char_count // len(chars) + 1))[:char_count]
        
        elif self.mode == "random_words":
            # Random words
            words = [
                "lorem", "ipsum", "dolor", "sit", "amet", "consectetur",
                "adipiscing", "elit", "sed", "do", "eiusmod", "tempor",
                "incididunt", "ut", "labore", "et", "dolore", "magna"
            ]
            overflow = []
            while len(' '.join(overflow)) < char_count:
                overflow.append(random.choice(words))
            return ' '.join(overflow)[:char_count]
        
        elif self.mode == "gibberish":
            # Random alphanumeric gibberish
            import string
            chars = string.ascii_letters + string.digits + " \n\t"
            return ''.join(random.choice(chars) for _ in range(char_count))
        
        else:
            # Default: repeating chars
            return "X" * char_count
    
    def _inject_into_json(self, data: Any, field_names: List[str] = None) -> Any:
        """
        Recursively inject overflow into JSON fields.
        
        Args:
            data: JSON data (dict, list, or primitive).
            field_names: Field names to target (e.g., ["prompt", "description", "content"]).
            
        Returns:
            Modified data with overflow injected.
        """
        if field_names is None:
            field_names = ["prompt", "description", "content", "message", "input", "text"]
        
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if key.lower() in [f.lower() for f in field_names] and isinstance(value, str):
                    # Inject overflow into this field
                    result[key] = value + "\n\n" + self._overflow_content
                else:
                    result[key] = self._inject_into_json(value, field_names)
            return result
        elif isinstance(data, list):
            return [self._inject_into_json(item, field_names) for item in data]
        else:
            return data
    
    async def _intercept_impl(self, flow: http.HTTPFlow) -> Optional[bool]:
        """
        Apply context overflow attack to request.
        
        Only modifies requests (not responses) to inject noise into prompts.
        
        Args:
            flow: The HTTP flow object.
            
        Returns:
            True if attack was applied, False otherwise.
        """
        if not self.should_trigger(flow):
            return False
        
        if not flow.request or not flow.request.content:
            return False
        
        # Only apply to requests
        if flow.request.method not in ["POST", "PUT", "PATCH"]:
            return False
        
        # Check probability
        if random.random() >= self.probability:
            return False
        
        try:
            # Get request text
            request_text = flow.request.get_text()
            if not request_text:
                return False
            
            # Try to parse as JSON
            try:
                data = json.loads(request_text)
                
                # Inject overflow
                overflow_data = self._inject_into_json(data)
                
                # Serialize back
                new_text = json.dumps(overflow_data, ensure_ascii=False)
                flow.request.text = new_text
                flow.request.headers["Content-Length"] = str(len(new_text.encode('utf-8')))
                
                redacted_url = self._redact_url(flow.request.pretty_url)
                logger.warning(
                    f"ContextOverflowStrategy '{self.name}' injected {self.token_count} tokens "
                    f"into request for {redacted_url}"
                )
                return True
            except json.JSONDecodeError:
                # Not JSON, append to text directly
                new_text = request_text + "\n\n" + self._overflow_content
                flow.request.text = new_text
                flow.request.headers["Content-Length"] = str(len(new_text.encode('utf-8')))
                
                redacted_url = self._redact_url(flow.request.pretty_url)
                logger.warning(
                    f"ContextOverflowStrategy '{self.name}' injected {self.token_count} tokens "
                    f"into text request for {redacted_url}"
                )
                return True
            
        except Exception as e:
            from agent_chaos_sdk.common.errors import ErrorCode
            from agent_chaos_sdk.common.telemetry import record_error_code
            record_error_code(ErrorCode.MUTATION_FAILED, strategy=self.name)
            logger.error(f"[{ErrorCode.MUTATION_FAILED}] Error applying context overflow strategy: {e}", exc_info=True)
            return False

