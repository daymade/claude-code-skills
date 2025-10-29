#!/usr/bin/env python3
"""
Security Utilities

CRITICAL FIX: Secure handling of sensitive data
ISSUE: Critical-2 in Engineering Excellence Plan

This module provides:
1. Secret masking for logs
2. Secure memory handling
3. API key validation
4. Input sanitization

Author: Chief Engineer
Date: 2025-10-28
Priority: P0 - Critical
"""

from __future__ import annotations

import re
import ctypes
import sys
from typing import Optional, Final

# Constants
MIN_API_KEY_LENGTH: Final[int] = 20  # Minimum reasonable API key length
MASK_PREFIX_LENGTH: Final[int] = 4   # Show first 4 chars
MASK_SUFFIX_LENGTH: Final[int] = 4   # Show last 4 chars


def mask_secret(secret: str, visible_chars: int = 4) -> str:
    """
    Safely mask secrets for logging.

    CRITICAL: Never log full secrets. Always use this function.

    Args:
        secret: The secret to mask (API key, token, password)
        visible_chars: Number of chars to show at start/end (default: 4)

    Returns:
        Masked string like "7fb3...DPRR"

    Examples:
        >>> mask_secret("7fb3ab7b186242288fe93a27227b7149.bJCOEAsUfejvWDPR")
        '7fb3...DPRR'

        >>> mask_secret("short")
        '***'

        >>> mask_secret("")
        '***'
    """
    if not secret:
        return "***"

    secret_len = len(secret)

    # Very short secrets: completely hide
    if secret_len < 2 * visible_chars:
        return "***"

    # Show prefix and suffix with ... in middle
    prefix = secret[:visible_chars]
    suffix = secret[-visible_chars:]

    return f"{prefix}...{suffix}"


def mask_secret_in_text(text: str, secret: str) -> str:
    """
    Replace all occurrences of secret in text with masked version.

    Useful for sanitizing error messages, logs, etc.

    Args:
        text: Text that might contain secrets
        secret: The secret to mask

    Returns:
        Text with secret masked

    Examples:
        >>> text = "API key example-fake-key-1234567890abcdef.test failed"
        >>> secret = "example-fake-key-1234567890abcdef.test"
        >>> mask_secret_in_text(text, secret)
        'API key exam...test failed'
    """
    if not secret or not text:
        return text

    masked = mask_secret(secret)
    return text.replace(secret, masked)


def validate_api_key(key: str) -> bool:
    """
    Validate API key format (basic checks).

    This doesn't verify if the key is valid with the API,
    just checks if it looks reasonable.

    Args:
        key: API key to validate

    Returns:
        True if key format is valid

    Checks:
    - Not empty
    - Minimum length (20 chars)
    - No suspicious patterns (only whitespace, etc.)
    """
    if not key:
        return False

    # Remove whitespace
    key_stripped = key.strip()

    # Check minimum length
    if len(key_stripped) < MIN_API_KEY_LENGTH:
        return False

    # Check it's not all spaces or special chars
    if key_stripped.isspace():
        return False

    # Check it contains some alphanumeric characters
    if not any(c.isalnum() for c in key_stripped):
        return False

    return True


def sanitize_for_logging(text: str, max_length: int = 200) -> str:
    """
    Sanitize text for safe logging.

    Prevents:
    - Log injection attacks
    - Excessively long log entries
    - Binary data in logs
    - Control characters

    Args:
        text: Text to sanitize
        max_length: Maximum length (default: 200)

    Returns:
        Safe text for logging
    """
    if not text:
        return ""

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length] + "... (truncated)"

    # Remove control characters (except newline, tab)
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')

    # Escape newlines to prevent log injection
    text = text.replace('\n', '\\n').replace('\r', '\\r')

    return text


def detect_and_mask_api_keys(text: str) -> str:
    """
    Automatically detect and mask potential API keys in text.

    Patterns detected:
    - Typical API key formats (alphanumeric + special chars, 20+ chars)
    - Bearer tokens
    - Authorization headers

    Args:
        text: Text that might contain API keys

    Returns:
        Text with API keys masked

    Warning:
        This is heuristic-based and may have false positives/negatives.
        Best practice: Don't let keys get into logs in the first place.
    """
    # Pattern for typical API keys
    # Looks for: 20+ chars of alphanumeric, dots, dashes, underscores
    api_key_pattern = r'\b[A-Za-z0-9._-]{20,}\b'

    def replace_with_mask(match):
        potential_key = match.group(0)
        # Only mask if it looks like a real key
        if validate_api_key(potential_key):
            return mask_secret(potential_key)
        return potential_key

    # Replace potential keys
    text = re.sub(api_key_pattern, replace_with_mask, text)

    # Also mask Authorization headers
    text = re.sub(
        r'Authorization:\s*Bearer\s+([A-Za-z0-9._-]+)',
        lambda m: f'Authorization: Bearer {mask_secret(m.group(1))}',
        text,
        flags=re.IGNORECASE
    )

    return text


def zero_memory(data: str) -> None:
    """
    Attempt to overwrite sensitive data in memory.

    NOTE: This is best-effort in Python due to string immutability.
    Python strings cannot be truly zeroed. This is a defense-in-depth
    measure that may help in some scenarios but is not guaranteed.

    For truly secure secret handling, consider:
    - Using memoryview/bytearray for mutable secrets
    - Storing secrets in kernel memory (OS features)
    - Hardware security modules (HSM)

    Args:
        data: String to attempt to zero

    Limitations:
        - Python strings are immutable
        - GC may have already copied the data
        - This is NOT cryptographically secure erasure
    """
    try:
        # This is best-effort only
        # Python strings are immutable, so we can't truly zero them
        # But we can try to overwrite the memory location
        location = id(data) + sys.getsizeof('')
        size = len(data.encode('utf-8'))
        ctypes.memset(location, 0, size)
    except Exception:
        # Silently fail - this is best-effort
        pass


class SecretStr:
    """
    Wrapper for secrets that prevents accidental logging.

    Usage:
        api_key = SecretStr("7fb3ab7b186242288fe93a27227b7149.bJCOEAsUfejvWDPR")
        print(api_key)  # Prints: SecretStr(7fb3...DPRR)
        print(api_key.get())  # Get actual value when needed

    This prevents accidentally logging secrets:
        logger.info(f"Using key: {api_key}")  # Safe! Automatically masked
    """

    def __init__(self, secret: str):
        """
        Initialize with secret value.

        Args:
            secret: The secret to wrap
        """
        self._secret = secret

    def get(self) -> str:
        """
        Get the actual secret value.

        Use this only when you need the real value.
        Never log the result!

        Returns:
            The actual secret
        """
        return self._secret

    def __str__(self) -> str:
        """String representation (masked)"""
        return f"SecretStr({mask_secret(self._secret)})"

    def __repr__(self) -> str:
        """Repr (masked)"""
        return f"SecretStr({mask_secret(self._secret)})"

    def __del__(self):
        """Attempt to zero memory on deletion"""
        zero_memory(self._secret)


# Example usage and testing
if __name__ == "__main__":
    # Test masking (using fake example key for testing)
    api_key = "example-fake-key-for-testing-only-not-real"
    print(f"Original: {api_key}")
    print(f"Masked: {mask_secret(api_key)}")

    # Test in text
    text = f"Connection failed with key {api_key}"
    print(f"Sanitized: {mask_secret_in_text(text, api_key)}")

    # Test SecretStr
    secret = SecretStr(api_key)
    print(f"SecretStr: {secret}")  # Automatically masked

    # Test validation
    print(f"Valid: {validate_api_key(api_key)}")
    print(f"Invalid: {validate_api_key('short')}")

    # Test auto-detection
    log_text = f"ERROR: API request failed with key {api_key}"
    print(f"Auto-masked: {detect_and_mask_api_keys(log_text)}")
