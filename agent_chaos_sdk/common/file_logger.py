"""
File Logger - Structured logging to file for analysis.

This module provides file-based logging that can be analyzed by the scorecard generator.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional
import json
from datetime import datetime


class StructuredFileHandler(logging.Handler):
    """
    Custom logging handler that writes structured logs to file.

    Logs are written in a format that can be easily parsed by the scorecard generator.
    """

    def __init__(self, filename: str, mode: str = "a"):
        """
        Initialize the file handler.

        Args:
            filename: Log file path
            mode: File mode ('a' for append, 'w' for write)
        """
        super().__init__()
        self.filename = filename
        self.mode = mode

        # Ensure directory exists
        log_path = Path(filename)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create file handler
        self.file_handler = logging.FileHandler(filename, mode=mode, encoding="utf-8")
        self.file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord):
        """Emit a log record to file."""
        try:
            self.file_handler.emit(record)
        except Exception:
            self.handleError(record)

    def close(self):
        """Close the file handler."""
        self.file_handler.close()
        super().close()


def setup_file_logger(
    name: str = "chaos_proxy", log_file: Optional[str] = None, level: int = logging.INFO
) -> logging.Logger:
    """
    Set up a file logger for proxy logs.

    Args:
        name: Logger name
        log_file: Path to log file (default: logs/proxy.log)
        level: Logging level

    Returns:
        Configured logger
    """
    if log_file is None:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        log_file = str(log_dir / "proxy.log")

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers
    logger.handlers.clear()

    # Add file handler
    file_handler = StructuredFileHandler(log_file)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    # Also add console handler for visibility
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(console_handler)

    return logger


def log_tool_call(logger: logging.Logger, url: str, method: str = "POST", **kwargs):
    """
    Log a tool call event.

    Args:
        logger: Logger instance
        url: Tool URL
        method: HTTP method
        **kwargs: Additional context
    """
    logger.info(f"[HTTP Tool] {method} {url} {json.dumps(kwargs) if kwargs else ''}")


def log_fuzzing(
    logger: logging.Logger,
    strategy: str,
    fuzz_type: str,
    fields_fuzzed: int = 0,
    **kwargs,
):
    """
    Log a fuzzing event.

    Args:
        logger: Logger instance
        strategy: Strategy name
        fuzz_type: Type of fuzzing
        fields_fuzzed: Number of fields fuzzed
        **kwargs: Additional context
    """
    logger.warning(
        f"Schema-aware fuzzing applied by {strategy}: "
        f"type={fuzz_type}, fields_fuzzed={fields_fuzzed}"
    )


def log_response(logger: logging.Logger, status_code: int, url: str, **kwargs):
    """
    Log an HTTP response.

    Args:
        logger: Logger instance
        status_code: HTTP status code
        url: Request URL
        **kwargs: Additional context
    """
    level = logging.INFO if status_code < 400 else logging.ERROR
    logger.log(level, f"Response: {status_code} for {url}")


def log_error(logger: logging.Logger, error_type: str, message: str, **kwargs):
    """
    Log an error event.

    Args:
        logger: Logger instance
        error_type: Type of error
        message: Error message
        **kwargs: Additional context
    """
    logger.error(f"Error [{error_type}]: {message}")


def log_retry(logger: logging.Logger, attempt: int, url: str, **kwargs):
    """
    Log a retry attempt.

    Args:
        logger: Logger instance
        attempt: Retry attempt number
        url: Request URL
        **kwargs: Additional context
    """
    logger.info(f"Retry attempt {attempt} for {url}")


def log_completion(logger: logging.Logger, success: bool = True, **kwargs):
    """
    Log agent completion.

    Args:
        logger: Logger instance
        success: Whether completion was successful
        **kwargs: Additional context
    """
    if success:
        logger.info("Agent processing complete")
    else:
        logger.error("Agent processing failed or crashed")
