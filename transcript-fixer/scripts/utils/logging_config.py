#!/usr/bin/env python3
"""
Logging Configuration for Transcript Fixer

Provides structured logging with rotation, levels, and audit trails.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    log_dir: Optional[Path] = None,
    level: str = "INFO",
    enable_console: bool = True,
    enable_file: bool = True,
    enable_audit: bool = True
) -> None:
    """
    Configure logging for the application.

    Args:
        log_dir: Directory for log files (default: ~/.transcript-fixer/logs)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_console: Enable console output
        enable_file: Enable file logging
        enable_audit: Enable audit logging

    Example:
        >>> setup_logging(level="DEBUG")
        >>> logger = logging.getLogger(__name__)
        >>> logger.info("Application started")
    """
    # Default log directory
    if log_dir is None:
        log_dir = Path.home() / ".transcript-fixer" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all, filter by handler

    # Clear existing handlers
    root_logger.handlers.clear()

    # Formatters
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    simple_formatter = logging.Formatter(
        fmt='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        console_handler.setFormatter(simple_formatter)
        root_logger.addHandler(console_handler)

    # File handler (rotating)
    if enable_file:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_dir / "transcript-fixer.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)

    # Error file handler (only errors)
    if enable_file:
        error_handler = logging.handlers.RotatingFileHandler(
            filename=log_dir / "errors.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(error_handler)

    # Audit handler (separate audit trail)
    if enable_audit:
        audit_handler = logging.handlers.RotatingFileHandler(
            filename=log_dir / "audit.log",
            maxBytes=50 * 1024 * 1024,  # 50MB
            backupCount=10,
            encoding='utf-8'
        )
        audit_handler.setLevel(logging.INFO)
        audit_handler.setFormatter(detailed_formatter)

        # Create audit logger
        audit_logger = logging.getLogger('audit')
        audit_logger.setLevel(logging.INFO)
        audit_logger.addHandler(audit_handler)
        audit_logger.propagate = False  # Don't propagate to root

    logging.info(f"Logging configured: level={level}, log_dir={log_dir}")


def get_audit_logger() -> logging.Logger:
    """Get the dedicated audit logger."""
    return logging.getLogger('audit')


# Example usage
if __name__ == "__main__":
    setup_logging(level="DEBUG")
    logger = logging.getLogger(__name__)

    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    audit_logger = get_audit_logger()
    audit_logger.info("User 'admin' added correction: '错误' → '正确'")
