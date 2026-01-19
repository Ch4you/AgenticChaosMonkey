"""
Structured logging utilities.

This module provides JSON logging capabilities for better observability
and log aggregation in production environments.
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime


class StructuredLogger:
    """
    Structured logger that outputs JSON-formatted logs.
    
    This enables better log aggregation and analysis in production systems.
    """
    
    def __init__(self, name: str, level: int = logging.INFO):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name.
            level: Logging level.
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # Add console handler if none exists
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(level)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _log(self, level: int, message: str, **kwargs) -> None:
        """
        Log a structured message.
        
        Args:
            level: Logging level.
            message: Log message.
            **kwargs: Additional structured fields.
        """
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            **kwargs
        }
        self.logger.log(level, json.dumps(log_data))
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message with structured data."""
        self._log(logging.INFO, message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message with structured data."""
        self._log(logging.ERROR, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message with structured data."""
        self._log(logging.WARNING, message, **kwargs)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message with structured data."""
        self._log(logging.DEBUG, message, **kwargs)


def get_logger(name: str) -> logging.Logger:
    """
    Get a standard Python logger.
    
    Args:
        name: Logger name.
        
    Returns:
        Logger instance.
    """
    return logging.getLogger(name)

