#!/usr/bin/env python3
"""
Domain Validation and Input Sanitization

CRITICAL FIX: Prevents SQL injection via domain parameter
ISSUE: Critical-3 in Engineering Excellence Plan

This module provides:
1. Domain whitelist validation
2. Input sanitization for text fields
3. SQL injection prevention helpers

Author: Chief Engineer
Date: 2025-10-28
Priority: P0 - Critical
"""

from __future__ import annotations

from typing import Final, Set
import re

# Predefined domains (for documentation/reference, not enforced as whitelist)
PREDEFINED_DOMAINS: Final[Set[str]] = {
    'general',
    'embodied_ai',
    'finance',
    'medical',
    'legal',
    'technical',
}

# Domain validation pattern - supports Chinese, Japanese, Korean characters
# \u4e00-\u9fff: CJK Unified Ideographs (Chinese)
# \u3040-\u309f: Hiragana, \u30a0-\u30ff: Katakana (Japanese)
# \uac00-\ud7af: Hangul Syllables (Korean)
DOMAIN_PATTERN: Final[str] = r'^[\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af-]+$'
MAX_DOMAIN_LENGTH: Final[int] = 50

# Keep VALID_DOMAINS as alias for backward compatibility
VALID_DOMAINS = PREDEFINED_DOMAINS

# Source whitelist
VALID_SOURCES: Final[Set[str]] = {
    'manual',
    'learned',
    'imported',
    'ai_suggested',
    'community',
}

# Maximum text lengths to prevent DoS
MAX_FROM_TEXT_LENGTH: Final[int] = 500
MAX_TO_TEXT_LENGTH: Final[int] = 500
MAX_NOTES_LENGTH: Final[int] = 2000
MAX_USER_LENGTH: Final[int] = 100


class ValidationError(Exception):
    """Input validation failed"""
    pass


def validate_domain(domain: str) -> str:
    """
    Validate domain name using pattern matching.

    CRITICAL: Prevents SQL injection via domain parameter.
    Domain is used in WHERE clauses - must match safe pattern.

    Supports:
    - Alphanumeric characters (a-z, A-Z, 0-9)
    - Underscores and hyphens
    - Chinese, Japanese, Korean characters

    Args:
        domain: Domain string to validate

    Returns:
        Validated domain (guaranteed to match safe pattern)

    Raises:
        ValidationError: If domain contains invalid characters

    Examples:
        >>> validate_domain('general')
        'general'

        >>> validate_domain('火星加速器')
        '火星加速器'

        >>> validate_domain('hacked"; DROP TABLE corrections--')
        ValidationError: Invalid domain
    """
    if not domain:
        raise ValidationError("Domain cannot be empty")

    domain = domain.strip()

    # Check again after stripping (whitespace-only input)
    if not domain:
        raise ValidationError("Domain cannot be empty")

    # Check length
    if len(domain) > MAX_DOMAIN_LENGTH:
        raise ValidationError(
            f"Domain name too long: {len(domain)} chars (max: {MAX_DOMAIN_LENGTH})"
        )

    # Check pattern (supports Chinese and other CJK characters)
    if not re.match(DOMAIN_PATTERN, domain):
        raise ValidationError(
            f"Domain name contains invalid characters: {domain}. "
            f"Allowed: alphanumeric, underscore, hyphen, Chinese/Japanese/Korean characters"
        )

    # Check for path traversal attempts
    if '..' in domain or '/' in domain or '\\' in domain:
        raise ValidationError(f"Domain name contains path traversal: {domain}")

    return domain


def validate_source(source: str) -> str:
    """
    Validate source against whitelist.

    Args:
        source: Source string to validate

    Returns:
        Validated source

    Raises:
        ValidationError: If source not in whitelist
    """
    if not source:
        raise ValidationError("Source cannot be empty")

    source = source.strip().lower()

    if source not in VALID_SOURCES:
        raise ValidationError(
            f"Invalid source: '{source}'. "
            f"Valid sources: {sorted(VALID_SOURCES)}"
        )

    return source


def sanitize_text_field(text: str, max_length: int, field_name: str = "field") -> str:
    """
    Sanitize text input with length validation.

    Prevents:
    - Excessively long inputs (DoS)
    - Binary data
    - Control characters (except whitespace)

    Args:
        text: Text to sanitize
        max_length: Maximum allowed length
        field_name: Field name for error messages

    Returns:
        Sanitized text

    Raises:
        ValidationError: If validation fails
    """
    if not text:
        raise ValidationError(f"{field_name} cannot be empty")

    if not isinstance(text, str):
        raise ValidationError(f"{field_name} must be a string")

    # Check length
    if len(text) > max_length:
        raise ValidationError(
            f"{field_name} too long: {len(text)} chars "
            f"(max: {max_length})"
        )

    # Check for null bytes (can break SQLite)
    if '\x00' in text:
        raise ValidationError(f"{field_name} contains null bytes")

    # Remove other control characters except tab, newline, carriage return
    sanitized = ''.join(
        char for char in text
        if ord(char) >= 32 or char in '\t\n\r'
    )

    if not sanitized.strip():
        raise ValidationError(f"{field_name} is empty after sanitization")

    return sanitized


def validate_correction_inputs(
    from_text: str,
    to_text: str,
    domain: str,
    source: str,
    notes: str | None = None,
    added_by: str | None = None
) -> tuple[str, str, str, str, str | None, str | None]:
    """
    Validate all inputs for correction creation.

    Comprehensive validation in one function.
    Call this before any database operation.

    Args:
        from_text: Original text
        to_text: Corrected text
        domain: Domain name
        source: Source type
        notes: Optional notes
        added_by: Optional user

    Returns:
        Tuple of (sanitized from_text, to_text, domain, source, notes, added_by)

    Raises:
        ValidationError: If any validation fails

    Example:
        >>> validate_correction_inputs(
        ...     "teh", "the", "general", "manual", None, "user123"
        ... )
        ('teh', 'the', 'general', 'manual', None, 'user123')
    """
    # Validate domain and source (whitelist)
    domain = validate_domain(domain)
    source = validate_source(source)

    # Sanitize text fields
    from_text = sanitize_text_field(from_text, MAX_FROM_TEXT_LENGTH, "from_text")
    to_text = sanitize_text_field(to_text, MAX_TO_TEXT_LENGTH, "to_text")

    # Optional fields
    if notes is not None:
        notes = sanitize_text_field(notes, MAX_NOTES_LENGTH, "notes")

    if added_by is not None:
        added_by = sanitize_text_field(added_by, MAX_USER_LENGTH, "added_by")

    return from_text, to_text, domain, source, notes, added_by


def validate_confidence(confidence: float) -> float:
    """
    Validate confidence score is in valid range.

    Args:
        confidence: Confidence score

    Returns:
        Validated confidence

    Raises:
        ValidationError: If out of range
    """
    if not isinstance(confidence, (int, float)):
        raise ValidationError("Confidence must be a number")

    if not 0.0 <= confidence <= 1.0:
        raise ValidationError(
            f"Confidence must be between 0.0 and 1.0, got: {confidence}"
        )

    return float(confidence)


def is_safe_sql_identifier(identifier: str) -> bool:
    """
    Check if string is a safe SQL identifier.

    Safe identifiers:
    - Only alphanumeric and underscores
    - Start with letter or underscore
    - Max 64 chars

    Use this for table/column names if dynamically constructing SQL.
    (Though we should avoid this entirely - use parameterized queries!)

    Args:
        identifier: String to check

    Returns:
        True if safe to use as SQL identifier
    """
    if not identifier:
        return False

    if len(identifier) > 64:
        return False

    # Must match: ^[a-zA-Z_][a-zA-Z0-9_]*$
    pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*$'
    return bool(re.match(pattern, identifier))


# Example usage and testing
if __name__ == "__main__":
    print("Testing domain_validator.py")
    print("=" * 60)

    # Test valid domain
    try:
        result = validate_domain("general")
        print(f"✓ Valid domain: {result}")
    except ValidationError as e:
        print(f"✗ Unexpected error: {e}")

    # Test invalid domain
    try:
        result = validate_domain("hacked'; DROP TABLE--")
        print(f"✗ Should have failed: {result}")
    except ValidationError as e:
        print(f"✓ Correctly rejected: {e}")

    # Test text sanitization
    try:
        result = sanitize_text_field("hello\x00world", 100, "test")
        print(f"✗ Should have rejected null byte")
    except ValidationError as e:
        print(f"✓ Correctly rejected null byte: {e}")

    # Test full validation
    try:
        result = validate_correction_inputs(
            from_text="teh",
            to_text="the",
            domain="general",
            source="manual",
            notes="Typo fix",
            added_by="test_user"
        )
        print(f"✓ Full validation passed: {result[0]} → {result[1]}")
    except ValidationError as e:
        print(f"✗ Unexpected error: {e}")

    print("=" * 60)
    print("✅ All validation tests completed")
