#!/usr/bin/env python3
"""
Logging Configuration for Transcript Fixer

CRITICAL FIX: Enhanced with structured logging and error tracking
ISSUE: Critical-4 in Engineering Excellence Plan

Provides structured logging with rotation, levels, and audit trails.
Added: Error rate monitoring, performance tracking, context enrichment

Author: Chief Engineer
Date: 2025-10-28
Priority: P0 - Critical
"""

import logging
import logging.handlers
import sys
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager
from datetime import datetime


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


class ErrorCounter:
    """
    Track error rates for failure threshold monitoring.

    CRITICAL FIX: Added for Critical-4
    Prevents silent failures by monitoring error rates.

    Usage:
        counter = ErrorCounter(threshold=0.3)
        for item in items:
            try:
                process(item)
                counter.success()
            except Exception:
                counter.failure()
                if counter.should_abort():
                    logger.error("Error rate too high, aborting")
                    break
    """

    def __init__(self, threshold: float = 0.3, window_size: int = 100):
        """
        Initialize error counter.

        Args:
            threshold: Failure rate threshold (0.3 = 30%)
            window_size: Number of recent operations to track
        """
        self.threshold = threshold
        self.window_size = window_size
        self.results: list[bool] = []  # True = success, False = failure
        self.total_successes = 0
        self.total_failures = 0

    def success(self) -> None:
        """Record a successful operation"""
        self.results.append(True)
        self.total_successes += 1
        if len(self.results) > self.window_size:
            self.results.pop(0)

    def failure(self) -> None:
        """Record a failed operation"""
        self.results.append(False)
        self.total_failures += 1
        if len(self.results) > self.window_size:
            self.results.pop(0)

    def failure_rate(self) -> float:
        """Calculate current failure rate (rolling window)"""
        if not self.results:
            return 0.0
        failures = sum(1 for r in self.results if not r)
        return failures / len(self.results)

    def should_abort(self) -> bool:
        """Check if failure rate exceeds threshold"""
        # Need minimum sample size before aborting
        if len(self.results) < 10:
            return False
        return self.failure_rate() > self.threshold

    def get_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        window_total = len(self.results)
        window_failures = sum(1 for r in self.results if not r)
        window_successes = window_total - window_failures

        return {
            "window_total": window_total,
            "window_successes": window_successes,
            "window_failures": window_failures,
            "window_failure_rate": self.failure_rate(),
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "threshold": self.threshold,
            "should_abort": self.should_abort(),
        }

    def reset(self) -> None:
        """Reset counters"""
        self.results.clear()
        self.total_successes = 0
        self.total_failures = 0


class TimedLogger:
    """
    Logger wrapper with automatic performance tracking.

    CRITICAL FIX: Added for Critical-4
    Automatically logs execution time for operations.

    Usage:
        logger = TimedLogger(logging.getLogger(__name__))
        with logger.timed("chunk_processing", chunk_id=5):
            process_chunk()
        # Automatically logs: "chunk_processing completed in 123ms"
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize with a logger instance.

        Args:
            logger: Logger to wrap
        """
        self.logger = logger

    @contextmanager
    def timed(self, operation_name: str, **context: Any):
        """
        Context manager for timing operations.

        Args:
            operation_name: Name of operation
            **context: Additional context to log

        Yields:
            None

        Example:
            >>> with logger.timed("api_call", chunk_id=5):
            ...     call_api()
            # Logs: "api_call completed in 123ms (chunk_id=5)"
        """
        start_time = time.time()

        # Format context for logging
        context_str = ", ".join(f"{k}={v}" for k, v in context.items())
        if context_str:
            context_str = f" ({context_str})"

        self.logger.info(f"{operation_name} started{context_str}")

        try:
            yield
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error(
                f"{operation_name} failed in {duration_ms:.1f}ms{context_str}: {e}"
            )
            raise
        else:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.info(
                f"{operation_name} completed in {duration_ms:.1f}ms{context_str}"
            )


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

    # Test ErrorCounter
    print("\n--- Testing ErrorCounter ---")
    counter = ErrorCounter(threshold=0.3)
    for i in range(20):
        if i % 4 == 0:
            counter.failure()
        else:
            counter.success()

    stats = counter.get_stats()
    print(f"Stats: {json.dumps(stats, indent=2)}")

    # Test TimedLogger
    print("\n--- Testing TimedLogger ---")
    timed_logger = TimedLogger(logger)
    with timed_logger.timed("test_operation", item_count=100):
        time.sleep(0.1)
