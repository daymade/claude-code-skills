#!/usr/bin/env python3
"""
Test Suite for Domain Validator

CRITICAL FIX VERIFICATION: Tests for Critical-3
Purpose: Verify SQL injection prevention and input validation

Test Coverage:
1. Domain whitelist validation
2. Source whitelist validation
3. Text sanitization
4. Confidence validation
5. SQL injection attack prevention
6. DoS prevention (length limits)

Author: Chief Engineer
Priority: P0 - Critical
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.domain_validator import (
    validate_domain,
    validate_source,
    sanitize_text_field,
    validate_correction_inputs,
    validate_confidence,
    is_safe_sql_identifier,
    ValidationError,
    VALID_DOMAINS,
    VALID_SOURCES,
    MAX_FROM_TEXT_LENGTH,
    MAX_TO_TEXT_LENGTH,
)


class TestDomainValidation:
    """Test domain pattern validation"""

    def test_valid_domains(self):
        """Test predefined domains are accepted"""
        for domain in VALID_DOMAINS:
            result = validate_domain(domain)
            assert result == domain

    def test_custom_domains(self):
        """Test custom domain names are accepted"""
        assert validate_domain("my_custom_domain") == "my_custom_domain"
        assert validate_domain("test-domain-123") == "test-domain-123"
        assert validate_domain("domain1") == "domain1"
        assert validate_domain("export_test") == "export_test"

    def test_chinese_domains(self):
        """Test Chinese domain names are accepted"""
        assert validate_domain("火星加速器") == "火星加速器"
        assert validate_domain("具身智能") == "具身智能"
        assert validate_domain("中文域名") == "中文域名"
        assert validate_domain("混合domain中文") == "混合domain中文"

    def test_whitespace_trimmed(self):
        """Test whitespace is trimmed"""
        assert validate_domain("  general  ") == "general"
        assert validate_domain("\ngeneral\t") == "general"

    def test_sql_injection_domain(self):
        """CRITICAL: Test SQL injection is rejected"""
        malicious_inputs = [
            "general'; DROP TABLE corrections--",
            "general' OR '1'='1",
            "'; DELETE FROM corrections WHERE '1'='1",
            "general\"; DROP TABLE--",
            "1' UNION SELECT * FROM corrections--",
        ]

        for malicious in malicious_inputs:
            with pytest.raises(ValidationError):
                validate_domain(malicious)

    def test_empty_domain(self):
        """Test empty domain is rejected"""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_domain("")

        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_domain("   ")

    def test_domain_too_long(self):
        """Test domain length limit"""
        long_domain = "a" * 51
        with pytest.raises(ValidationError, match="too long"):
            validate_domain(long_domain)


class TestSourceValidation:
    """Test source whitelist validation"""

    def test_valid_sources(self):
        """Test all valid sources are accepted"""
        for source in VALID_SOURCES:
            result = validate_source(source)
            assert result == source

    def test_invalid_source(self):
        """Test invalid source is rejected"""
        with pytest.raises(ValidationError, match="Invalid source"):
            validate_source("hacked")

        with pytest.raises(ValidationError, match="Invalid source"):
            validate_source("'; DROP TABLE--")


class TestTextSanitization:
    """Test text field sanitization"""

    def test_valid_text(self):
        """Test normal text passes"""
        text = "Hello world!"
        result = sanitize_text_field(text, 100, "test")
        assert result == text

    def test_length_limit(self):
        """Test length limit is enforced"""
        long_text = "a" * 1000
        with pytest.raises(ValidationError, match="too long"):
            sanitize_text_field(long_text, 100, "test")

    def test_null_byte_rejection(self):
        """CRITICAL: Test null bytes are rejected (can break SQLite)"""
        malicious = "hello\x00world"
        with pytest.raises(ValidationError, match="null bytes"):
            sanitize_text_field(malicious, 100, "test")

    def test_control_characters(self):
        """Test control characters are removed"""
        text_with_controls = "hello\x01\x02world\x1f"
        result = sanitize_text_field(text_with_controls, 100, "test")
        assert result == "helloworld"

    def test_whitespace_preserved(self):
        """Test normal whitespace is preserved"""
        text = "hello\tworld\ntest\r\nline"
        result = sanitize_text_field(text, 100, "test")
        assert "\t" in result
        assert "\n" in result

    def test_empty_after_sanitization(self):
        """Test rejects text that becomes empty after sanitization"""
        with pytest.raises(ValidationError, match="empty after sanitization"):
            sanitize_text_field("   ", 100, "test")


class TestCorrectionInputsValidation:
    """Test full correction validation"""

    def test_valid_inputs(self):
        """Test valid inputs pass"""
        result = validate_correction_inputs(
            from_text="teh",
            to_text="the",
            domain="general",
            source="manual",
            notes="Typo fix",
            added_by="test_user"
        )

        assert result[0] == "teh"
        assert result[1] == "the"
        assert result[2] == "general"
        assert result[3] == "manual"
        assert result[4] == "Typo fix"
        assert result[5] == "test_user"

    def test_invalid_domain_in_full_validation(self):
        """Test invalid domain is rejected in full validation"""
        with pytest.raises(ValidationError):
            validate_correction_inputs(
                from_text="test",
                to_text="test",
                domain="hacked'; DROP--",
                source="manual"
            )

    def test_text_too_long(self):
        """Test excessively long text is rejected"""
        long_text = "a" * (MAX_FROM_TEXT_LENGTH + 1)

        with pytest.raises(ValidationError, match="too long"):
            validate_correction_inputs(
                from_text=long_text,
                to_text="test",
                domain="general",
                source="manual"
            )

    def test_optional_fields_none(self):
        """Test optional fields can be None"""
        result = validate_correction_inputs(
            from_text="test",
            to_text="test",
            domain="general",
            source="manual",
            notes=None,
            added_by=None
        )

        assert result[4] is None  # notes
        assert result[5] is None  # added_by


class TestConfidenceValidation:
    """Test confidence score validation"""

    def test_valid_confidence(self):
        """Test valid confidence values"""
        assert validate_confidence(0.0) == 0.0
        assert validate_confidence(0.5) == 0.5
        assert validate_confidence(1.0) == 1.0

    def test_confidence_out_of_range(self):
        """Test out-of-range confidence is rejected"""
        with pytest.raises(ValidationError, match="between 0.0 and 1.0"):
            validate_confidence(-0.1)

        with pytest.raises(ValidationError, match="between 0.0 and 1.0"):
            validate_confidence(1.1)

        with pytest.raises(ValidationError, match="between 0.0 and 1.0"):
            validate_confidence(100.0)

    def test_confidence_type_check(self):
        """Test non-numeric confidence is rejected"""
        with pytest.raises(ValidationError, match="must be a number"):
            validate_confidence("high")  # type: ignore


class TestSQLIdentifierValidation:
    """Test SQL identifier safety checks"""

    def test_safe_identifiers(self):
        """Test valid SQL identifiers"""
        assert is_safe_sql_identifier("table_name")
        assert is_safe_sql_identifier("_private")
        assert is_safe_sql_identifier("Column123")

    def test_unsafe_identifiers(self):
        """Test unsafe SQL identifiers are rejected"""
        assert not is_safe_sql_identifier("table-name")  # Hyphen
        assert not is_safe_sql_identifier("123table")    # Starts with number
        assert not is_safe_sql_identifier("table name")  # Space
        assert not is_safe_sql_identifier("table; DROP") # Semicolon
        assert not is_safe_sql_identifier("table' OR")   # Quote

    def test_empty_identifier(self):
        """Test empty identifier is rejected"""
        assert not is_safe_sql_identifier("")

    def test_too_long_identifier(self):
        """Test excessively long identifier is rejected"""
        long_id = "a" * 65
        assert not is_safe_sql_identifier(long_id)


class TestSecurityScenarios:
    """Test realistic attack scenarios"""

    def test_sql_injection_via_from_text(self):
        """Test SQL injection via from_text is handled safely"""
        # These should be sanitized, not cause SQL injection
        malicious_from = "test'; DROP TABLE corrections--"

        # Should NOT raise exception - text fields allow any content
        # They're protected by parameterized queries
        result = validate_correction_inputs(
            from_text=malicious_from,
            to_text="safe",
            domain="general",
            source="manual"
        )

        assert result[0] == malicious_from  # Text preserved as-is

    def test_dos_via_long_input(self):
        """Test DoS prevention via length limits"""
        # Attempt to create extremely long input
        dos_text = "a" * 10000

        with pytest.raises(ValidationError, match="too long"):
            validate_correction_inputs(
                from_text=dos_text,
                to_text="test",
                domain="general",
                source="manual"
            )

    def test_domain_bypass_attempts(self):
        """Test various domain bypass attempts"""
        bypass_attempts = [
            "general\nmalicious",    # Newline injection
            "general -- comment",    # SQL comment (space is invalid)
            "general' UNION",        # SQL union (quote is invalid)
            "../etc/passwd",         # Path traversal
        ]

        for attempt in bypass_attempts:
            with pytest.raises(ValidationError):
                validate_domain(attempt)


# Run tests with: pytest -v test_domain_validator.py
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
