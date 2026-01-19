"""
Scorecard Generator - Resilience Analysis and Reporting

This module analyzes proxy logs and test run data to generate resilience scorecards,
measuring how well agents handle chaos injections and errors.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class ScorecardGenerator:
    """
    Generates resilience scorecards from chaos testing logs.
    
    Analyzes:
    - Total tool calls
    - Fuzzing success rate
    - System recovery rate (retries, error handling)
    - Final outcome (success vs crash)
    """
    
    def __init__(self, log_file: Optional[str] = None, log_dir: str = "logs"):
        """
        Initialize the scorecard generator.
        
        Args:
            log_file: Path to log file (if None, searches for proxy logs)
            log_dir: Directory containing log files
        """
        self.log_file = log_file
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Analysis results
        self.metrics = {
            "total_tool_calls": 0,
            "successful_tool_calls": 0,
            "failed_tool_calls": 0,
            "fuzzing_attempts": 0,
            "fuzzing_successful": 0,
            "retry_attempts": 0,
            "successful_retries": 0,
            "agent_crashes": 0,
            "agent_successful_completion": 0,
            "tool_call_errors": defaultdict(int),
            "fuzzing_types": defaultdict(int),
            "race_conditions_detected": 0,  # Parallel tool calls with dependencies
            "logic_errors": [],  # List of detected logic errors
            # Swarm communication metrics
            "swarm_communication_errors": defaultdict(int),  # By traffic type
            "agent_to_agent_disruptions": 0,
            "consensus_delays": 0,
            "message_mutations": 0,
            "agent_isolations": 0,
        }
        
        self.tool_calls: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.log_lines: List[str] = []  # Store all log lines for analysis
        self.json_log_entries: List[Dict[str, Any]] = []  # Store parsed JSON log entries
    
    def analyze(self) -> Dict[str, Any]:
        """
        Analyze logs and generate metrics.
        
        Returns:
            Dictionary with analysis results
        """
        logger.info("Starting log analysis...")
        
        # Find and read log file
        log_path = self._find_log_file()
        if not log_path:
            logger.warning("No log file found. Using empty results.")
            return self._generate_empty_results()
        
        # Read and parse logs
        self._parse_logs(log_path)
        
        # Calculate metrics
        self._calculate_metrics()
        
        # Generate scorecard
        scorecard = self._generate_scorecard()
        
        return scorecard
    
    def _find_log_file(self) -> Optional[Path]:
        """Find the log file to analyze."""
        if self.log_file:
            log_path = Path(self.log_file)
            if log_path.exists():
                return log_path
        
        # Search for proxy logs
        possible_names = [
            "proxy.log",
            "chaos_proxy.log",
            "proxy_logs.txt",
            "logs/proxy.log",
            "logs/chaos_proxy.log",
        ]
        
        for name in possible_names:
            log_path = Path(name)
            if log_path.exists():
                return log_path
        
        # Search in log directory
        if self.log_dir.exists():
            for log_file in self.log_dir.glob("*.log"):
                return log_file
        
        return None
    
    def _parse_logs(self, log_path: Path):
        """Parse log file and extract events."""
        logger.info(f"Parsing log file: {log_path}")
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                self.log_lines = f.readlines()
                
            # First pass: extract all events
            for line_num, line in enumerate(self.log_lines, 1):
                self._parse_log_line(line, line_num)
            
            # Second pass: detect retry success patterns
            self._detect_retry_success()
        except Exception as e:
            logger.error(f"Error parsing log file: {e}")
    
    def _extract_json_log_entry(self, line: str) -> Optional[Dict]:
        """
        Helper to safely parse a JSON log line.
        
        Args:
            line: Raw log line string
            
        Returns:
            Parsed JSON dictionary or None if parsing fails
        """
        try:
            line = line.strip()
            if not line:
                return None
            log_entry = json.loads(line)
            if isinstance(log_entry, dict):
                return log_entry
            return None
        except json.JSONDecodeError as e:
            logger.debug(f"Could not parse log line as JSON: {line[:50]}...")
            return None
        except Exception as e:
            logger.debug(f"Error parsing log line: {e}")
            return None
    
    def _parse_log_line(self, line: str, line_num: int):
        """Parse a single log line and extract events."""
        line = line.strip()
        if not line:
            return
        
        # Try to parse as JSON first (structured log format)
        log_entry = self._extract_json_log_entry(line)
        if log_entry and "timestamp" in log_entry:
            # This is a structured JSON log entry from the proxy
            self._parse_json_log_entry(log_entry, line_num)
            return
        
        # Track tool calls
        if "HTTP Tool" in line and "POST" in line:
            self._extract_tool_call(line, line_num)
        
        # Track fuzzing events
        if "Schema-aware fuzzing" in line or "MCP protocol fuzzing" in line:
            self._extract_fuzzing_event(line, line_num)
        
        # Track errors
        if "Error" in line or "ERROR" in line.upper():
            self._extract_error_event(line, line_num)
        
        # Track retries
        if "retry" in line.lower() or "Retry" in line or "Retry attempt" in line:
            self._extract_retry_event(line, line_num)
        
        # Track agent completion
        if "Agent processing complete" in line or "Workflow Complete" in line:
            self._extract_completion_event(line, line_num)
        
        # Track agent crashes
        if "Exception" in line or "Traceback" in line or "CRASH" in line.upper():
            self._extract_crash_event(line, line_num)
        
        # Track HTTP responses
        if "Response:" in line and ("200" in line or "400" in line or "500" in line):
            self._extract_response_event(line, line_num)
    
    def _extract_tool_call(self, line: str, line_num: int):
        """Extract tool call information from log line."""
        # Pattern: [HTTP Tool] POST http://...
        match = re.search(r'POST\s+([^\s]+)', line)
        if match:
            url = match.group(1)
            self.metrics["total_tool_calls"] += 1
            
            tool_call = {
                "line": line_num,
                "url": url,
                "timestamp": self._extract_timestamp(line),
                "type": self._classify_tool_call(url),
            }
            self.tool_calls.append(tool_call)
            
            self.events.append({
                "type": "tool_call",
                "line": line_num,
                "url": url,
                "timestamp": tool_call["timestamp"],
            })
    
    def _extract_fuzzing_event(self, line: str, line_num: int):
        """Extract fuzzing event from log line."""
        self.metrics["fuzzing_attempts"] += 1
        
        # Extract fuzzing type
        fuzz_type = "unknown"
        for f_type in ["schema_violation", "type_mismatch", "null_injection", "garbage_value"]:
            if f_type in line:
                fuzz_type = f_type
                break
        
        self.metrics["fuzzing_types"][fuzz_type] += 1
        
        # Extract fuzzed fields
        fields_fuzzed = 0
        match = re.search(r'(\d+)\s+fields?\s+fuzzed', line)
        if match:
            fields_fuzzed = int(match.group(1))
        
        if fields_fuzzed > 0:
            self.metrics["fuzzing_successful"] += 1
        
        self.events.append({
            "type": "fuzzing",
            "line": line_num,
            "fuzz_type": fuzz_type,
            "fields_fuzzed": fields_fuzzed,
            "timestamp": self._extract_timestamp(line),
        })
    
    def _extract_error_event(self, line: str, line_num: int):
        """Extract error event from log line."""
        error_type = "unknown"
        
        # Classify error
        if "400" in line or "Bad Request" in line:
            error_type = "validation_error"
        elif "404" in line or "Not Found" in line:
            error_type = "not_found"
        elif "500" in line or "Internal Server Error" in line:
            error_type = "server_error"
        elif "timeout" in line.lower():
            error_type = "timeout"
        elif "network" in line.lower():
            error_type = "network_error"
        
        self.metrics["tool_call_errors"][error_type] += 1
        self.metrics["failed_tool_calls"] += 1
        
        self.events.append({
            "type": "error",
            "line": line_num,
            "error_type": error_type,
            "message": line[:200],  # Truncate
            "timestamp": self._extract_timestamp(line),
        })
    
    def _extract_retry_event(self, line: str, line_num: int):
        """Extract retry event from log line."""
        self.metrics["retry_attempts"] += 1
        
        self.events.append({
            "type": "retry",
            "line": line_num,
            "timestamp": self._extract_timestamp(line),
        })
    
    def _detect_retry_success(self):
        """Detect successful retries by analyzing event patterns."""
        # Look for retry events followed by successful responses
        retry_lines = [e["line"] for e in self.events if e.get("type") == "retry"]
        
        for retry_line in retry_lines:
            # Look ahead for successful response within next 10 lines
            for i in range(retry_line, min(retry_line + 10, len(self.log_lines))):
                line = self.log_lines[i-1] if i > 0 else ""
                if "Response: 200" in line:
                    self.metrics["successful_retries"] += 1
                    break
    
    def _extract_completion_event(self, line: str, line_num: int):
        """Extract completion event from log line."""
        self.metrics["agent_successful_completion"] += 1
        
        self.events.append({
            "type": "completion",
            "line": line_num,
            "timestamp": self._extract_timestamp(line),
        })
    
    def _extract_crash_event(self, line: str, line_num: int):
        """Extract crash event from log line."""
        self.metrics["agent_crashes"] += 1
        
        self.events.append({
            "type": "crash",
            "line": line_num,
            "message": line[:200],
            "timestamp": self._extract_timestamp(line),
        })
    
    def _parse_json_log_entry(self, log_entry: Dict[str, Any], line_num: int):
        """
        Parse a structured JSON log entry from the proxy.
        
        Args:
            log_entry: Parsed JSON dictionary
            line_num: Line number in the log file
        """
        self.json_log_entries.append(log_entry)
        
        # Extract information from JSON log entry
        method = log_entry.get("method", "")
        url = log_entry.get("url", "")
        status_code = log_entry.get("status_code")
        tool_name = log_entry.get("tool_name")
        chaos_applied = log_entry.get("chaos_applied")
        fuzzed = log_entry.get("fuzzed", False)
        agent_role = log_entry.get("agent_role")
        traffic_type = log_entry.get("traffic_type", "UNKNOWN")
        traffic_subtype = log_entry.get("traffic_subtype")
        
        # Detect tool name from URL if not explicitly set
        if not tool_name and url:
            url_lower = url.lower()
            if "/search_flights" in url_lower:
                tool_name = "search_flights"
            elif "/book_ticket" in url_lower or "/book" in url_lower:
                tool_name = "book_ticket"
            elif "/api/" in url_lower or "/v1/chat" in url_lower:
                tool_name = "llm_request"
        
        # Track tool call (POST requests to tool endpoints)
        if tool_name and method == "POST":
            self.metrics["total_tool_calls"] += 1
            
            tool_call = {
                "line": line_num,
                "url": url,
                "timestamp": log_entry.get("timestamp"),
                "type": tool_name,
            }
            self.tool_calls.append(tool_call)
            
            self.events.append({
                "type": "tool_call",
                "line": line_num,
                "url": url,
                "tool_name": tool_name,
                "timestamp": log_entry.get("timestamp"),
            })
        
        # Track response
        if status_code is not None:
            if status_code == 200:
                self.metrics["successful_tool_calls"] += 1
            elif status_code >= 400:
                self.metrics["failed_tool_calls"] += 1
                # Classify error type
                error_type = "unknown"
                if status_code == 400:
                    error_type = "validation_error"
                elif status_code == 404:
                    error_type = "not_found"
                elif status_code >= 500:
                    error_type = "server_error"
                self.metrics["tool_call_errors"][error_type] += 1
            
            self.events.append({
                "type": "response",
                "line": line_num,
                "status_code": status_code,
                "timestamp": log_entry.get("timestamp"),
            })
        
        # Track fuzzing
        # Handle chaos_applied as either a list or string
        chaos_applied_str = ""
        if chaos_applied:
            if isinstance(chaos_applied, list):
                chaos_applied_str = ",".join(chaos_applied).lower()
            elif isinstance(chaos_applied, str):
                chaos_applied_str = chaos_applied.lower()
        
        if fuzzed or (chaos_applied_str and ("fuzzing" in chaos_applied_str or "mcp" in chaos_applied_str)):
            self.metrics["fuzzing_attempts"] += 1
            if fuzzed:
                self.metrics["fuzzing_successful"] += 1
            
            # Extract fuzzing type from chaos_applied
            fuzz_type = "unknown"
            if chaos_applied_str:
                if "schema_violation" in chaos_applied_str:
                    fuzz_type = "schema_violation"
                elif "type_mismatch" in chaos_applied_str:
                    fuzz_type = "type_mismatch"
                elif "null" in chaos_applied_str:
                    fuzz_type = "null_injection"
                elif "garbage" in chaos_applied_str:
                    fuzz_type = "garbage_value"
            
            self.metrics["fuzzing_types"][fuzz_type] += 1
            
            self.events.append({
                "type": "fuzzing",
                "line": line_num,
                "fuzz_type": fuzz_type,
                "fields_fuzzed": 1 if fuzzed else 0,  # Assume 1 if fuzzed is True
                "timestamp": log_entry.get("timestamp"),
            })
        
        # Track swarm communication errors
        if traffic_type == "AGENT_TO_AGENT":
            self.metrics["agent_to_agent_disruptions"] += 1
            
            # Categorize by subtype
            if traffic_subtype:
                error_key = f"swarm_{traffic_subtype}"
                self.metrics["swarm_communication_errors"][error_key] += 1
            
            # Track specific attack types
            if chaos_applied_str:
                if "swarm_disruption" in chaos_applied_str or "message_mutation" in chaos_applied_str:
                    self.metrics["message_mutations"] += 1
                if "consensus_delay" in chaos_applied_str:
                    self.metrics["consensus_delays"] += 1
                if "agent_isolation" in chaos_applied_str:
                    self.metrics["agent_isolations"] += 1
            
            # Track errors in agent-to-agent communication
            if status_code and status_code >= 400:
                error_type = f"swarm_error_{status_code}"
                self.metrics["swarm_communication_errors"][error_type] += 1
    
    def _extract_response_event(self, line: str, line_num: int):
        """Extract HTTP response event from log line."""
        # Pattern: Response: 200, Response: 400, etc.
        match = re.search(r'Response:\s*(\d+)', line)
        if match:
            status_code = int(match.group(1))
            
            if status_code == 200:
                self.metrics["successful_tool_calls"] += 1
            elif status_code >= 400:
                self.metrics["failed_tool_calls"] += 1
            
            self.events.append({
                "type": "response",
                "line": line_num,
                "status_code": status_code,
                "timestamp": self._extract_timestamp(line),
            })
    
    def _extract_timestamp(self, line: str) -> Optional[str]:
        """Extract timestamp from log line."""
        # Try various timestamp formats
        patterns = [
            r'(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})',
            r'(\d{2}/\d{2}/\d{4}[\s]\d{2}:\d{2}:\d{2})',
            r'\[(\d{2}:\d{2}:\d{2})\]',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(1)
        
        return None
    
    def _classify_tool_call(self, url: str) -> str:
        """Classify tool call by URL."""
        url_lower = url.lower()
        
        if "search_flights" in url_lower:
            return "search_flights"
        elif "book_ticket" in url_lower or "book" in url_lower:
            return "book_ticket"
        elif "flight" in url_lower:
            return "flight_related"
        else:
            return "unknown"
    
    def _calculate_metrics(self):
        """Calculate derived metrics."""
        # Calculate success rates
        if self.metrics["total_tool_calls"] > 0:
            self.metrics["tool_call_success_rate"] = (
                self.metrics["successful_tool_calls"] / self.metrics["total_tool_calls"]
            ) * 100
        else:
            self.metrics["tool_call_success_rate"] = 0.0
        
        if self.metrics["fuzzing_attempts"] > 0:
            self.metrics["fuzzing_success_rate"] = (
                self.metrics["fuzzing_successful"] / self.metrics["fuzzing_attempts"]
            ) * 100
        else:
            self.metrics["fuzzing_success_rate"] = 0.0
        
        # Calculate recovery rate
        # Recovery = (successful retries + successful completion) / total failures
        total_failures = self.metrics["failed_tool_calls"]
        if total_failures > 0:
            recovery_count = (
                self.metrics["successful_retries"] + 
                self.metrics["agent_successful_completion"]
            )
            self.metrics["system_recovery_rate"] = (recovery_count / total_failures) * 100
        else:
            self.metrics["system_recovery_rate"] = 100.0
        
        # Calculate retry success rate
        if self.metrics["retry_attempts"] > 0:
            # Estimate successful retries (retries that led to completion)
            self.metrics["retry_success_rate"] = (
                self.metrics["successful_retries"] / self.metrics["retry_attempts"]
            ) * 100
        else:
            self.metrics["retry_success_rate"] = 0.0
        
        # Detect race conditions and logic errors
        self._detect_race_conditions()
        
        # Overall resilience score
        self.metrics["resilience_score"] = self._calculate_resilience_score()
    
    def _detect_race_conditions(self):
        """
        Detect race conditions in tool calls.
        
        A race condition occurs when:
        1. Multiple tools are called in parallel (within a short time window)
        2. One tool (e.g., book_ticket) depends on another tool's result (e.g., search_flights)
        3. The dependent tool is called before the dependency completes or with invalid data
        """
        # Group tool calls by timestamp to find parallel executions
        
        # Find search_flights and book_ticket calls
        search_calls = []
        book_calls = []
        
        for entry in self.json_log_entries:
            tool_name = entry.get("tool_name")
            if not tool_name:
                url = entry.get("url", "").lower()
                if "/search_flights" in url:
                    tool_name = "search_flights"
                elif "/book_ticket" in url or "/book" in url:
                    tool_name = "book_ticket"
            
            timestamp_str = entry.get("timestamp")
            if timestamp_str and tool_name:
                try:
                    # Parse ISO format timestamp
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    status_code = entry.get("status_code")
                    
                    if tool_name == "search_flights":
                        search_calls.append({
                            "timestamp": timestamp,
                            "status_code": status_code,
                            "entry": entry,
                        })
                    elif tool_name == "book_ticket":
                        book_calls.append({
                            "timestamp": timestamp,
                            "status_code": status_code,
                            "entry": entry,
                        })
                except (ValueError, AttributeError):
                    # Skip if timestamp parsing fails
                    continue
        
        # Check for race conditions: book_ticket called before or simultaneously with search_flights
        for book_call in book_calls:
            book_time = book_call["timestamp"]
            book_status = book_call["status_code"]
            
            # Check if there's a search_flights call that happened after this book_ticket
            # or if book_ticket was called with invalid data (404, 400)
            race_condition_detected = False
            logic_error = None
            
            # Case 1: book_ticket called before any search_flights completes
            search_before_book = [
                s for s in search_calls 
                if s["timestamp"] < book_time and s["status_code"] == 200
            ]
            
            # Case 2: book_ticket called simultaneously (within 2 seconds) with search_flights
            simultaneous_searches = [
                s for s in search_calls
                if abs((s["timestamp"] - book_time).total_seconds()) < 2
            ]
            
            # Case 3: book_ticket failed with 404/400, suggesting invalid flight_id
            if book_status in [400, 404] and (not search_before_book or simultaneous_searches):
                race_condition_detected = True
                logic_error = {
                    "type": "race_condition",
                    "description": "book_ticket called before search_flights completed or with invalid flight_id",
                    "book_ticket_time": book_time.isoformat(),
                    "book_ticket_status": book_status,
                    "search_flights_available": len(search_before_book) > 0,
                    "simultaneous_calls": len(simultaneous_searches) > 0,
                }
            
            if race_condition_detected:
                self.metrics["race_conditions_detected"] += 1
                if logic_error:
                    self.metrics["logic_errors"].append(logic_error)
                    # Use debug level to avoid spam, summary will show the count
                    logger.debug(
                        f"Race condition detected: {logic_error['description']} "
                        f"(book_ticket at {book_time.isoformat()}, status {book_status})"
                    )
    
    def _calculate_resilience_score(self) -> float:
        """
        Calculate overall resilience score (0-100).
        
        Factors:
        - Tool call success rate (40%)
        - Recovery rate (40%)
        - Agent completion rate (20%)
        """
        tool_success_weight = 0.4
        recovery_weight = 0.4
        completion_weight = 0.2
        
        # Tool call success rate
        tool_score = min(self.metrics.get("tool_call_success_rate", 0), 100)
        
        # Recovery rate
        recovery_score = min(self.metrics.get("system_recovery_rate", 0), 100)
        
        # Completion rate (no crashes = 100)
        if self.metrics["agent_crashes"] == 0:
            completion_score = 100.0
        else:
            total_attempts = self.metrics["agent_successful_completion"] + self.metrics["agent_crashes"]
            if total_attempts > 0:
                completion_score = (
                    self.metrics["agent_successful_completion"] / total_attempts
                ) * 100
            else:
                completion_score = 0.0
        
        resilience_score = (
            (tool_score * tool_success_weight) +
            (recovery_score * recovery_weight) +
            (completion_score * completion_weight)
        )
        
        return round(resilience_score, 2)
    
    def _generate_scorecard(self) -> Dict[str, Any]:
        """Generate the complete scorecard."""
        grade = self._calculate_grade(self.metrics["resilience_score"])
        
        scorecard = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "analyzer_version": "1.0.0",
            },
            "metrics": self.metrics.copy(),
            "grade": grade,
            "summary": self._generate_summary(grade),
            "tool_calls": self.tool_calls[-10:],  # Last 10 tool calls
            "events": self.events[-20:],  # Last 20 events
        }
        
        return scorecard
    
    def _calculate_grade(self, score: float) -> str:
        """Calculate letter grade from resilience score."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"
    
    def _generate_summary(self, grade: str) -> Dict[str, str]:
        """Generate human-readable summary."""
        total_calls = self.metrics["total_tool_calls"]
        fuzzing_success = self.metrics["fuzzing_successful"]
        fuzzing_attempts = self.metrics["fuzzing_attempts"]
        recovery_rate = self.metrics.get("system_recovery_rate", 0)
        crashes = self.metrics["agent_crashes"]
        completions = self.metrics["agent_successful_completion"]
        
        summary = {
            "grade": grade,
            "resilience_score": f"{self.metrics['resilience_score']:.1f}/100",
            "tool_calls": f"Total: {total_calls}, Successful: {self.metrics['successful_tool_calls']}, Failed: {self.metrics['failed_tool_calls']}",
            "fuzzing": f"Attempted: {fuzzing_attempts}, Successful: {fuzzing_success}",
            "recovery": f"System recovered from {recovery_rate:.1f}% of failures",
            "outcome": f"Completions: {completions}, Crashes: {crashes}",
        }
        
        # Add protocol attack survival message
        if fuzzing_attempts > 0:
            survival_rate = (completions / (completions + crashes)) * 100 if (completions + crashes) > 0 else 0
            summary["protocol_attacks"] = f"System survived {survival_rate:.1f}% of protocol attacks"
        else:
            summary["protocol_attacks"] = "No protocol attacks detected"
        
        # Add race condition detection
        race_conditions = self.metrics.get("race_conditions_detected", 0)
        if race_conditions > 0:
            summary["race_conditions"] = f"⚠️ CRITICAL: {race_conditions} race condition(s) detected - Agent called dependent tools before dependencies completed"
            logic_errors = self.metrics.get("logic_errors", [])
            if logic_errors:
                error_descriptions = [e.get("description", "Unknown error") for e in logic_errors]
                summary["logic_errors"] = "; ".join(error_descriptions[:3])  # Show first 3 errors
        else:
            summary["race_conditions"] = "No race conditions detected"
        
        return summary
    
    def _generate_empty_results(self) -> Dict[str, Any]:
        """Generate empty results when no logs found."""
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "analyzer_version": "1.0.0",
                "warning": "No log file found",
            },
            "metrics": self.metrics.copy(),
            "grade": "N/A",
            "summary": {
                "grade": "N/A",
                "message": "No log data available for analysis",
            },
        }
    
    def generate_json_report(self, output_path: str = "resilience_report.json", scorecard: Optional[Dict[str, Any]] = None) -> Path:
        """
        Generate JSON report.
        
        Args:
            output_path: Path to output JSON file
            scorecard: Pre-analyzed scorecard (optional, to avoid re-analysis)
            
        Returns:
            Path to generated file
        """
        if scorecard is None:
            scorecard = self.analyze()
        
        output_file = Path(output_path)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(scorecard, f, indent=2, ensure_ascii=False)
        
        logger.info(f"JSON report generated: {output_file}")
        return output_file
    
    def generate_markdown_report(self, output_path: str = "resilience_report.md", scorecard: Optional[Dict[str, Any]] = None) -> Path:
        """
        Generate Markdown report.
        
        Args:
            output_path: Path to output Markdown file
            scorecard: Pre-analyzed scorecard (optional, to avoid re-analysis)
            
        Returns:
            Path to generated file
        """
        if scorecard is None:
            scorecard = self.analyze()
        
        output_file = Path(output_path)
        with open(output_file, 'w', encoding='utf-8') as f:
            self._write_markdown(f, scorecard)
        
        logger.info(f"Markdown report generated: {output_file}")
        return output_file
    
    def _write_markdown(self, f, scorecard: Dict[str, Any]):
        """Write markdown report content."""
        metadata = scorecard.get("metadata", {})
        metrics = scorecard.get("metrics", {})
        grade = scorecard.get("grade", "N/A")
        summary = scorecard.get("summary", {})
        
        # Header
        f.write("# Resilience Scorecard\n\n")
        f.write(f"**Generated:** {metadata.get('generated_at', 'Unknown')}\n\n")
        f.write(f"## Overall Grade: {grade}\n\n")
        f.write(f"**Resilience Score:** {metrics.get('resilience_score', 0):.1f}/100\n\n")
        
        # Summary
        f.write("## Summary\n\n")
        for key, value in summary.items():
            if key != "grade":
                f.write(f"- **{key.replace('_', ' ').title()}:** {value}\n")
        f.write("\n")
        
        # Metrics
        f.write("## Detailed Metrics\n\n")
        
        f.write("### Tool Calls\n\n")
        f.write(f"- Total Tool Calls: {metrics.get('total_tool_calls', 0)}\n")
        f.write(f"- Successful: {metrics.get('successful_tool_calls', 0)}\n")
        f.write(f"- Failed: {metrics.get('failed_tool_calls', 0)}\n")
        
        # Swarm Communication Errors
        swarm_errors = metrics.get('swarm_communication_errors', {})
        if swarm_errors:
            f.write(f"\n## Swarm Communication Errors\n\n")
            for error_type, count in swarm_errors.items():
                f.write(f"- {error_type}: {count}\n")
            
            f.write(f"\n### Swarm Disruption Summary\n\n")
            f.write(f"- Agent-to-Agent Disruptions: {metrics.get('agent_to_agent_disruptions', 0)}\n")
            f.write(f"- Message Mutations: {metrics.get('message_mutations', 0)}\n")
            f.write(f"- Consensus Delays: {metrics.get('consensus_delays', 0)}\n")
            f.write(f"- Agent Isolations: {metrics.get('agent_isolations', 0)}\n")
        f.write(f"- Success Rate: {metrics.get('tool_call_success_rate', 0):.1f}%\n\n")
        
        f.write("### Fuzzing\n\n")
        f.write(f"- Fuzzing Attempts: {metrics.get('fuzzing_attempts', 0)}\n")
        f.write(f"- Successful Injections: {metrics.get('fuzzing_successful', 0)}\n")
        f.write(f"- Fuzzing Success Rate: {metrics.get('fuzzing_success_rate', 0):.1f}%\n\n")
        
        if metrics.get('fuzzing_types'):
            f.write("**Fuzzing Types:**\n")
            for fuzz_type, count in metrics['fuzzing_types'].items():
                f.write(f"- {fuzz_type}: {count}\n")
            f.write("\n")
        
        f.write("### System Recovery\n\n")
        f.write(f"- Retry Attempts: {metrics.get('retry_attempts', 0)}\n")
        f.write(f"- Successful Retries: {metrics.get('successful_retries', 0)}\n")
        f.write(f"- Recovery Rate: {metrics.get('system_recovery_rate', 0):.1f}%\n\n")
        
        f.write("### Agent Outcome\n\n")
        f.write(f"- Successful Completions: {metrics.get('agent_successful_completion', 0)}\n")
        f.write(f"- Crashes: {metrics.get('agent_crashes', 0)}\n\n")
        
        # Race Conditions and Logic Errors
        race_conditions = metrics.get('race_conditions_detected', 0)
        if race_conditions > 0:
            f.write("### ⚠️ Race Conditions Detected\n\n")
            f.write(f"**Critical Issue**: {race_conditions} race condition(s) found!\n\n")
            f.write("**What this means**: The agent called dependent tools (e.g., `book_ticket`) ")
            f.write("before their dependencies (e.g., `search_flights`) completed, or with invalid data.\n\n")
            
            logic_errors = metrics.get('logic_errors', [])
            if logic_errors:
                f.write("**Details**:\n")
                for i, error in enumerate(logic_errors[:5], 1):  # Show first 5 errors
                    f.write(f"{i}. {error.get('description', 'Unknown error')}\n")
                    if error.get('book_ticket_time'):
                        f.write(f"   - Time: {error.get('book_ticket_time')}\n")
                    if error.get('book_ticket_status'):
                        f.write(f"   - Status: {error.get('book_ticket_status')}\n")
                f.write("\n")
        
        if metrics.get('tool_call_errors'):
            f.write("### Error Breakdown\n\n")
            for error_type, count in metrics['tool_call_errors'].items():
                f.write(f"- {error_type}: {count}\n")
            f.write("\n")
        
        # Recommendations
        f.write("## Recommendations\n\n")
        recommendations = self._generate_recommendations(scorecard)
        for rec in recommendations:
            f.write(f"- {rec}\n")
        f.write("\n")
    
    def _generate_recommendations(self, scorecard: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on scorecard."""
        recommendations = []
        metrics = scorecard.get("metrics", {})
        grade = scorecard.get("grade", "N/A")
        
        if grade in ["D", "F"]:
            recommendations.append("⚠️ **Critical**: System resilience is low. Implement error handling and retry logic.")
        
        if metrics.get("tool_call_success_rate", 100) < 70:
            recommendations.append("🔧 Improve tool call error handling. Many tool calls are failing.")
        
        if metrics.get("system_recovery_rate", 100) < 50:
            recommendations.append("🔄 Implement retry logic. System is not recovering from failures effectively.")
        
        if metrics.get("agent_crashes", 0) > 0:
            recommendations.append("💥 Add exception handling. Agent is crashing on errors.")
        
        if metrics.get("fuzzing_success_rate", 0) < 50:
            recommendations.append("🎯 Fuzzing is not being applied effectively. Check proxy configuration.")
        
        if metrics.get("retry_attempts", 0) == 0 and metrics.get("failed_tool_calls", 0) > 0:
            recommendations.append("🔁 No retry attempts detected. Consider implementing retry mechanisms.")
        
        # Race condition recommendations
        race_conditions = metrics.get("race_conditions_detected", 0)
        if race_conditions > 0:
            recommendations.append(
                "🚨 **CRITICAL**: Race condition detected! Agent is calling dependent tools before dependencies complete. "
                "Implement sequential tool execution or dependency validation before calling dependent tools."
            )
            recommendations.append(
                "💡 **Solution**: Ensure tools that depend on other tools' results wait for those results. "
                "For example, `book_ticket` should only be called after `search_flights` returns a valid `flight_id`."
            )
        
        if not recommendations:
            recommendations.append("✅ System shows good resilience. Continue monitoring and testing.")
        
        return recommendations

