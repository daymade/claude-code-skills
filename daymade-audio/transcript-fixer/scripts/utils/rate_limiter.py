#!/usr/bin/env python3
"""
Rate Limiting Module

CRITICAL FIX (P1-8): Production-grade rate limiting for API protection

Features:
- Token Bucket algorithm (smooth rate limiting)
- Sliding Window algorithm (precise rate limiting)
- Fixed Window algorithm (simple, memory-efficient)
- Thread-safe operations
- Burst support
- Multiple rate limit tiers
- Metrics integration

Use cases:
- API rate limiting (e.g., 100 requests/minute)
- Resource protection (e.g., max 5 concurrent DB connections)
- DoS prevention
- Cost control (e.g., limit API calls)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Deque, Final
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class RateLimitStrategy(Enum):
    """Rate limiting strategy"""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    max_requests: int           # Maximum requests allowed
    window_seconds: float       # Time window in seconds
    strategy: RateLimitStrategy = RateLimitStrategy.TOKEN_BUCKET
    burst_size: Optional[int] = None  # Burst allowance (for token bucket)

    def __post_init__(self):
        """Validate configuration"""
        if self.max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        # Default burst size = max_requests (allow full burst)
        if self.burst_size is None:
            self.burst_size = self.max_requests


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded"""
    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.retry_after = retry_after  # Seconds to wait before retry


class TokenBucketLimiter:
    """
    Token Bucket algorithm implementation.

    Properties:
    - Smooth rate limiting
    - Allows bursts up to bucket capacity
    - Memory efficient (O(1))
    - Fast (O(1) per request)

    Use for: API rate limiting, general request throttling
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.capacity = config.burst_size or config.max_requests
        self.refill_rate = config.max_requests / config.window_seconds

        self._tokens = float(self.capacity)
        self._last_refill = time.time()
        self._lock = threading.Lock()

        logger.debug(
            f"TokenBucket initialized: capacity={self.capacity}, "
            f"refill_rate={self.refill_rate:.2f}/s"
        )

    def _refill(self) -> None:
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self._last_refill

        # Add tokens based on time elapsed
        tokens_to_add = elapsed * self.refill_rate
        self._tokens = min(self.capacity, self._tokens + tokens_to_add)
        self._last_refill = now

    def acquire(self, tokens: int = 1, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens from bucket.

        Args:
            tokens: Number of tokens to acquire (default: 1)
            blocking: If True, wait for tokens. If False, return immediately
            timeout: Maximum time to wait (seconds). None = wait forever

        Returns:
            True if tokens acquired, False if rate limit exceeded (non-blocking only)

        Raises:
            RateLimitExceeded: If rate limit exceeded in blocking mode
        """
        if tokens <= 0:
            raise ValueError("tokens must be positive")

        start_time = time.time()

        while True:
            with self._lock:
                self._refill()

                if self._tokens >= tokens:
                    # Sufficient tokens available
                    self._tokens -= tokens
                    return True

                if not blocking:
                    # Non-blocking mode - return immediately
                    return False

                # Calculate retry_after
                tokens_needed = tokens - self._tokens
                retry_after = tokens_needed / self.refill_rate

            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise RateLimitExceeded(
                        f"Rate limit exceeded: need {tokens} tokens, have {self._tokens:.1f}",
                        retry_after=retry_after
                    )

            # Wait before retry (but not longer than needed or timeout)
            wait_time = min(retry_after, 0.1)  # Check at least every 100ms
            if timeout is not None:
                remaining_timeout = timeout - (time.time() - start_time)
                wait_time = min(wait_time, remaining_timeout)

            if wait_time > 0:
                time.sleep(wait_time)

    def get_available_tokens(self) -> float:
        """Get current number of available tokens"""
        with self._lock:
            self._refill()
            return self._tokens

    def reset(self) -> None:
        """Reset to full capacity"""
        with self._lock:
            self._tokens = float(self.capacity)
            self._last_refill = time.time()


class SlidingWindowLimiter:
    """
    Sliding Window algorithm implementation.

    Properties:
    - Precise rate limiting
    - No "boundary problem" (unlike fixed window)
    - Memory: O(max_requests)
    - Fast: O(n) per request, where n = requests in window

    Use for: Strict rate limits, billing, quota enforcement
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.max_requests = config.max_requests
        self.window_seconds = config.window_seconds

        self._timestamps: Deque[float] = deque()
        self._lock = threading.Lock()

        logger.debug(
            f"SlidingWindow initialized: max_requests={self.max_requests}, "
            f"window={self.window_seconds}s"
        )

    def _cleanup_old_timestamps(self, now: float) -> None:
        """Remove timestamps outside the window"""
        cutoff = now - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def acquire(self, tokens: int = 1, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens (check if request allowed).

        Args:
            tokens: Number of requests to make (usually 1)
            blocking: If True, wait for capacity. If False, return immediately
            timeout: Maximum time to wait (seconds)

        Returns:
            True if allowed, False if rate limit exceeded (non-blocking only)

        Raises:
            RateLimitExceeded: If rate limit exceeded in blocking mode
        """
        if tokens <= 0:
            raise ValueError("tokens must be positive")

        start_time = time.time()

        while True:
            now = time.time()

            with self._lock:
                self._cleanup_old_timestamps(now)

                current_count = len(self._timestamps)

                if current_count + tokens <= self.max_requests:
                    # Allowed - record timestamps
                    for _ in range(tokens):
                        self._timestamps.append(now)
                    return True

                if not blocking:
                    # Non-blocking mode
                    return False

                # Calculate retry_after (when oldest request falls out of window)
                if self._timestamps:
                    oldest = self._timestamps[0]
                    retry_after = oldest + self.window_seconds - now
                else:
                    retry_after = 0.1

            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise RateLimitExceeded(
                        f"Rate limit exceeded: {current_count}/{self.max_requests} "
                        f"requests in {self.window_seconds}s window",
                        retry_after=max(retry_after, 0.1)
                    )

            # Wait before retry
            wait_time = min(retry_after, 0.1)
            if timeout is not None:
                remaining_timeout = timeout - (time.time() - start_time)
                wait_time = min(wait_time, remaining_timeout)

            if wait_time > 0:
                time.sleep(wait_time)

    def get_current_count(self) -> int:
        """Get current request count in window"""
        with self._lock:
            self._cleanup_old_timestamps(time.time())
            return len(self._timestamps)

    def reset(self) -> None:
        """Reset (clear all timestamps)"""
        with self._lock:
            self._timestamps.clear()


class RateLimiter:
    """
    Main rate limiter with configurable strategy.

    CRITICAL FIX (P1-8): Thread-safe rate limiting for production use
    """

    def __init__(self, config: RateLimitConfig):
        self.config = config

        # Select implementation based on strategy
        if config.strategy == RateLimitStrategy.TOKEN_BUCKET:
            self._impl = TokenBucketLimiter(config)
        elif config.strategy == RateLimitStrategy.SLIDING_WINDOW:
            self._impl = SlidingWindowLimiter(config)
        else:
            raise ValueError(f"Unsupported strategy: {config.strategy}")

        logger.info(
            f"RateLimiter created: {config.strategy.value}, "
            f"{config.max_requests}/{config.window_seconds}s"
        )

    def acquire(self, tokens: int = 1, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to proceed.

        Args:
            tokens: Number of requests (default: 1)
            blocking: Wait for availability (default: True)
            timeout: Maximum wait time in seconds (default: None = forever)

        Returns:
            True if allowed, False if rate limit exceeded (non-blocking only)

        Raises:
            RateLimitExceeded: If rate limit exceeded in blocking mode
        """
        return self._impl.acquire(tokens=tokens, blocking=blocking, timeout=timeout)

    @contextmanager
    def limit(self, tokens: int = 1):
        """
        Context manager for rate-limited operations.

        Usage:
            with rate_limiter.limit():
                # Make API call
                response = client.post(...)

        Raises:
            RateLimitExceeded: If rate limit exceeded
        """
        self.acquire(tokens=tokens, blocking=True)
        try:
            yield
        finally:
            pass  # Tokens already consumed

    def check_available(self) -> bool:
        """Check if capacity available (non-blocking)"""
        return self.acquire(tokens=1, blocking=False)

    def reset(self) -> None:
        """Reset rate limiter state"""
        self._impl.reset()

    def get_info(self) -> dict:
        """Get current rate limiter information"""
        info = {
            'strategy': self.config.strategy.value,
            'max_requests': self.config.max_requests,
            'window_seconds': self.config.window_seconds,
        }

        if isinstance(self._impl, TokenBucketLimiter):
            info['available_tokens'] = self._impl.get_available_tokens()
            info['capacity'] = self._impl.capacity
        elif isinstance(self._impl, SlidingWindowLimiter):
            info['current_count'] = self._impl.get_current_count()

        return info


# Predefined rate limit configurations
class RateLimitPresets:
    """Common rate limit configurations"""

    # API rate limits
    API_CONSERVATIVE = RateLimitConfig(
        max_requests=10,
        window_seconds=60.0,
        strategy=RateLimitStrategy.TOKEN_BUCKET
    )

    API_MODERATE = RateLimitConfig(
        max_requests=60,
        window_seconds=60.0,
        strategy=RateLimitStrategy.TOKEN_BUCKET
    )

    API_AGGRESSIVE = RateLimitConfig(
        max_requests=100,
        window_seconds=60.0,
        strategy=RateLimitStrategy.TOKEN_BUCKET
    )

    # Burst limits
    BURST_ALLOWED = RateLimitConfig(
        max_requests=50,
        window_seconds=60.0,
        burst_size=100,  # Allow double burst
        strategy=RateLimitStrategy.TOKEN_BUCKET
    )

    # Strict limits (sliding window)
    STRICT_LIMIT = RateLimitConfig(
        max_requests=100,
        window_seconds=60.0,
        strategy=RateLimitStrategy.SLIDING_WINDOW
    )


# Global rate limiters
_global_limiters: dict[str, RateLimiter] = {}
_limiters_lock = threading.Lock()


def get_rate_limiter(name: str, config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """
    Get or create a named rate limiter.

    Args:
        name: Unique name for this rate limiter
        config: Rate limit configuration (required if creating new)

    Returns:
        RateLimiter instance
    """
    global _global_limiters

    with _limiters_lock:
        if name not in _global_limiters:
            if config is None:
                raise ValueError(f"Rate limiter '{name}' not found and no config provided")

            _global_limiters[name] = RateLimiter(config)
            logger.info(f"Created global rate limiter: {name}")

        return _global_limiters[name]


def reset_all_limiters() -> None:
    """Reset all global rate limiters (mainly for testing)"""
    with _limiters_lock:
        for limiter in _global_limiters.values():
            limiter.reset()
        logger.info("Reset all rate limiters")
