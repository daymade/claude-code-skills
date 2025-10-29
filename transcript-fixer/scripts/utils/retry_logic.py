#!/usr/bin/env python3
"""
Retry Logic with Exponential Backoff

CRITICAL FIX: Implements retry for transient failures
ISSUE: Critical-4 in Engineering Excellence Plan

This module provides:
1. Exponential backoff retry logic
2. Error categorization (transient vs permanent)
3. Configurable retry strategies
4. Async retry support

Author: Chief Engineer
Date: 2025-10-28
Priority: P0 - Critical
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TypeVar, Callable, Any, Optional, Set
from functools import wraps
from dataclasses import dataclass
import httpx

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class RetryConfig:
    """
    Configuration for retry behavior.

    Attributes:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay between retries in seconds (default: 1.0)
        max_delay: Maximum delay between retries in seconds (default: 60.0)
        exponential_base: Multiplier for exponential backoff (default: 2.0)
        jitter: Add randomness to avoid thundering herd (default: True)
    """
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


# Transient errors that should be retried
TRANSIENT_EXCEPTIONS: Set[type] = {
    # Network errors
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,

    # HTTP status codes (will check separately)
    # 408 Request Timeout
    # 429 Too Many Requests
    # 500 Internal Server Error
    # 502 Bad Gateway
    # 503 Service Unavailable
    # 504 Gateway Timeout
}

# Status codes that indicate transient failures
TRANSIENT_STATUS_CODES: Set[int] = {
    408,  # Request Timeout
    429,  # Too Many Requests
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}

# Permanent errors that should NOT be retried
PERMANENT_EXCEPTIONS: Set[type] = {
    # Authentication/Authorization
    httpx.HTTPStatusError,  # Will check status code

    # Validation errors
    ValueError,
    KeyError,
    TypeError,
}


def is_transient_error(exception: Exception) -> bool:
    """
    Determine if an exception represents a transient failure.

    Transient errors:
    - Network timeouts
    - Connection errors
    - Server overload (429, 503)
    - Temporary server errors (500, 502, 504)

    Permanent errors:
    - Authentication failures (401, 403)
    - Not found (404)
    - Validation errors (400, 422)

    Args:
        exception: Exception to categorize

    Returns:
        True if error is transient and should be retried
    """
    # Check exception type
    if type(exception) in TRANSIENT_EXCEPTIONS:
        return True

    # Check HTTP status codes
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code in TRANSIENT_STATUS_CODES

    # Default: treat as permanent
    return False


def calculate_delay(
    attempt: int,
    config: RetryConfig
) -> float:
    """
    Calculate delay for exponential backoff.

    Formula: min(base_delay * (exponential_base ** attempt), max_delay)
    With optional jitter to avoid thundering herd.

    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration

    Returns:
        Delay in seconds

    Example:
        >>> calculate_delay(0, RetryConfig(base_delay=1.0, exponential_base=2.0))
        1.0
        >>> calculate_delay(1, RetryConfig(base_delay=1.0, exponential_base=2.0))
        2.0
        >>> calculate_delay(2, RetryConfig(base_delay=1.0, exponential_base=2.0))
        4.0
    """
    delay = config.base_delay * (config.exponential_base ** attempt)
    delay = min(delay, config.max_delay)

    if config.jitter:
        import random
        # Add ±25% jitter
        jitter_amount = delay * 0.25
        delay = delay + random.uniform(-jitter_amount, jitter_amount)

    return max(0, delay)  # Ensure non-negative


def retry_sync(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorator for synchronous retry logic with exponential backoff.

    Args:
        config: Retry configuration (uses defaults if None)
        on_retry: Optional callback called on each retry attempt

    Example:
        >>> @retry_sync(RetryConfig(max_attempts=3))
        ... def fetch_data():
        ...     return call_api()

    Raises:
        Original exception if all retries exhausted
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # Check if error is transient
                    if not is_transient_error(e):
                        logger.error(
                            f"{func.__name__} failed with permanent error: {e}"
                        )
                        raise

                    # Last attempt?
                    if attempt >= config.max_attempts - 1:
                        logger.error(
                            f"{func.__name__} failed after {config.max_attempts} attempts: {e}"
                        )
                        raise

                    # Calculate delay
                    delay = calculate_delay(attempt, config)

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{config.max_attempts} "
                        f"failed with transient error: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )

                    # Call retry callback if provided
                    if on_retry:
                        on_retry(e, attempt)

                    # Wait before retry
                    time.sleep(delay)

            # Should never reach here, but satisfy type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic error")

        return wrapper
    return decorator


def retry_async(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorator for asynchronous retry logic with exponential backoff.

    Args:
        config: Retry configuration (uses defaults if None)
        on_retry: Optional callback called on each retry attempt

    Example:
        >>> @retry_async(RetryConfig(max_attempts=3))
        ... async def fetch_data():
        ...     return await call_api_async()

    Raises:
        Original exception if all retries exhausted
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None

            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    # Check if error is transient
                    if not is_transient_error(e):
                        logger.error(
                            f"{func.__name__} failed with permanent error: {e}"
                        )
                        raise

                    # Last attempt?
                    if attempt >= config.max_attempts - 1:
                        logger.error(
                            f"{func.__name__} failed after {config.max_attempts} attempts: {e}"
                        )
                        raise

                    # Calculate delay
                    delay = calculate_delay(attempt, config)

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{config.max_attempts} "
                        f"failed with transient error: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )

                    # Call retry callback if provided
                    if on_retry:
                        on_retry(e, attempt)

                    # Wait before retry (async)
                    await asyncio.sleep(delay)

            # Should never reach here, but satisfy type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic error")

        return wrapper
    return decorator


# Example usage and testing
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    # Test synchronous retry
    print("=== Testing Synchronous Retry ===")

    attempt_count = 0

    @retry_sync(RetryConfig(max_attempts=3, base_delay=0.1))
    def flaky_function():
        global attempt_count
        attempt_count += 1
        print(f"Attempt {attempt_count}")

        if attempt_count < 3:
            raise httpx.ConnectTimeout("Connection timeout")
        return "Success!"

    try:
        result = flaky_function()
        print(f"Result: {result}")
    except Exception as e:
        print(f"Failed: {e}")

    # Test async retry
    print("\n=== Testing Asynchronous Retry ===")

    async def test_async():
        attempt_count = 0

        @retry_async(RetryConfig(max_attempts=3, base_delay=0.1))
        async def async_flaky_function():
            nonlocal attempt_count
            attempt_count += 1
            print(f"Async attempt {attempt_count}")

            if attempt_count < 2:
                raise httpx.ReadTimeout("Read timeout")
            return "Async success!"

        try:
            result = await async_flaky_function()
            print(f"Result: {result}")
        except Exception as e:
            print(f"Failed: {e}")

    asyncio.run(test_async())

    # Test permanent error (should not retry)
    print("\n=== Testing Permanent Error (No Retry) ===")

    attempt_count = 0

    @retry_sync(RetryConfig(max_attempts=3, base_delay=0.1))
    def permanent_error_function():
        global attempt_count
        attempt_count += 1
        print(f"Attempt {attempt_count}")
        raise ValueError("Invalid input")  # Permanent error

    try:
        result = permanent_error_function()
    except ValueError as e:
        print(f"Correctly failed immediately: {e}")
        print(f"Attempts made: {attempt_count} (should be 1)")
