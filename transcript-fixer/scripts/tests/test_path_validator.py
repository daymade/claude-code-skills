#!/usr/bin/env python3
"""
Test Suite for Path Validator

CRITICAL FIX VERIFICATION: Tests for Critical-5
Purpose: Verify path traversal and symlink attack prevention

Test Coverage:
1. Path traversal prevention (../)
2. Symlink attack detection
3. Directory whitelist enforcement
4. File extension validation
5. Null byte injection prevention
6. Path canonicalization

Author: Chief Engineer
Priority: P0 - Critical
"""

import pytest
import os
import sys
from pathlib import Path
import tempfile

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.path_validator import (
    PathValidator,
    PathValidationError,
    validate_input_path,
    validate_output_path,
    ALLOWED_READ_EXTENSIONS,
    ALLOWED_WRITE_EXTENSIONS,
)


class TestPathTraversalPrevention:
    """Test path traversal attack prevention"""

    def test_parent_directory_traversal(self, tmp_path):
        """Test ../ path traversal is blocked"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        # Create a file outside allowed directory
        outside_dir = tmp_path.parent / "outside"
        outside_dir.mkdir(exist_ok=True)
        outside_file = outside_dir / "secret.md"
        outside_file.write_text("secret data")

        # Try to access it via ../
        malicious_path = str(tmp_path / ".." / "outside" / "secret.md")

        with pytest.raises(PathValidationError, match="Dangerous pattern"):
            validator.validate_input_path(malicious_path)

        # Cleanup
        outside_file.unlink()
        outside_dir.rmdir()

    def test_absolute_path_outside_whitelist(self, tmp_path):
        """Test absolute paths outside whitelist are blocked"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        # Try to access /etc/passwd
        with pytest.raises(PathValidationError, match="not under allowed directories"):
            validator.validate_input_path("/etc/passwd")

    def test_multiple_parent_traversals(self, tmp_path):
        """Test ../../ is blocked"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        with pytest.raises(PathValidationError, match="Dangerous pattern"):
            validator.validate_input_path("../../etc/passwd")


class TestSymlinkAttacks:
    """Test symlink attack prevention"""

    def test_direct_symlink_blocked(self, tmp_path):
        """Test direct symlink is blocked by default"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        # Create a real file
        real_file = tmp_path / "real.md"
        real_file.write_text("data")

        # Create symlink to it
        symlink = tmp_path / "link.md"
        symlink.symlink_to(real_file)

        with pytest.raises(PathValidationError, match="Symlink detected"):
            validator.validate_input_path(str(symlink))

        # Cleanup
        symlink.unlink()
        real_file.unlink()

    def test_symlink_allowed_when_configured(self, tmp_path):
        """Test symlinks can be allowed"""
        validator = PathValidator(
            allowed_base_dirs={tmp_path},
            allow_symlinks=True
        )

        # Create real file and symlink
        real_file = tmp_path / "real.md"
        real_file.write_text("data")

        symlink = tmp_path / "link.md"
        symlink.symlink_to(real_file)

        # Should succeed with allow_symlinks=True
        result = validator.validate_input_path(str(symlink))
        assert result.exists()

        # Cleanup
        symlink.unlink()
        real_file.unlink()

    def test_symlink_in_parent_directory(self, tmp_path):
        """Test symlink in parent path is blocked"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        # Create real directory
        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()

        # Create symlink to directory
        symlink_dir = tmp_path / "link_dir"
        symlink_dir.symlink_to(real_dir)

        # Create file inside real directory
        real_file = real_dir / "file.md"
        real_file.write_text("data")

        # Try to access via symlinked directory
        malicious_path = symlink_dir / "file.md"

        with pytest.raises(PathValidationError, match="Symlink"):
            validator.validate_input_path(str(malicious_path))

        # Cleanup
        real_file.unlink()
        symlink_dir.unlink()
        real_dir.rmdir()


class TestDirectoryWhitelist:
    """Test directory whitelist enforcement"""

    def test_file_in_allowed_directory(self, tmp_path):
        """Test file in allowed directory is accepted"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        test_file = tmp_path / "test.md"
        test_file.write_text("test data")

        result = validator.validate_input_path(str(test_file))
        assert result == test_file.resolve()

        test_file.unlink()

    def test_file_outside_allowed_directory(self, tmp_path):
        """Test file outside allowed directory is rejected"""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()

        validator = PathValidator(allowed_base_dirs={allowed_dir})

        # File in parent directory (not in whitelist)
        outside_file = tmp_path / "outside.md"
        outside_file.write_text("data")

        with pytest.raises(PathValidationError, match="not under allowed directories"):
            validator.validate_input_path(str(outside_file))

        outside_file.unlink()

    def test_add_allowed_directory(self, tmp_path):
        """Test dynamically adding allowed directories"""
        validator = PathValidator(allowed_base_dirs={tmp_path / "initial"})

        new_dir = tmp_path / "new"
        new_dir.mkdir()

        # Should fail initially
        test_file = new_dir / "test.md"
        test_file.write_text("data")

        with pytest.raises(PathValidationError):
            validator.validate_input_path(str(test_file))

        # Add directory to whitelist
        validator.add_allowed_directory(new_dir)

        # Should succeed now
        result = validator.validate_input_path(str(test_file))
        assert result.exists()

        test_file.unlink()


class TestFileExtensionValidation:
    """Test file extension validation"""

    def test_allowed_read_extension(self, tmp_path):
        """Test allowed read extensions are accepted"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        for ext in ['.md', '.txt', '.html', '.json']:
            test_file = tmp_path / f"test{ext}"
            test_file.write_text("data")

            result = validator.validate_input_path(str(test_file))
            assert result.exists()

            test_file.unlink()

    def test_disallowed_read_extension(self, tmp_path):
        """Test disallowed extensions are rejected for reading"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        dangerous_files = [
            "script.sh",
            "executable.exe",
            "code.py",
            "binary.bin",
        ]

        for filename in dangerous_files:
            test_file = tmp_path / filename
            test_file.write_text("data")

            with pytest.raises(PathValidationError, match="not allowed for reading"):
                validator.validate_input_path(str(test_file))

            test_file.unlink()

    def test_allowed_write_extension(self, tmp_path):
        """Test allowed write extensions are accepted"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        for ext in ['.md', '.html', '.db', '.log']:
            test_file = tmp_path / f"output{ext}"

            result = validator.validate_output_path(str(test_file))
            assert result.parent.exists()

    def test_disallowed_write_extension(self, tmp_path):
        """Test disallowed extensions are rejected for writing"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        with pytest.raises(PathValidationError, match="not allowed for writing"):
            validator.validate_output_path(str(tmp_path / "output.exe"))


class TestNullByteInjection:
    """Test null byte injection prevention"""

    def test_null_byte_in_path(self, tmp_path):
        """Test null byte injection is blocked"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        malicious_paths = [
            "file.md\x00.exe",
            "file\x00.md",
            "\x00etc/passwd",
        ]

        for path in malicious_paths:
            with pytest.raises(PathValidationError, match="Dangerous pattern"):
                validator.validate_input_path(path)


class TestNewlineInjection:
    """Test newline injection prevention"""

    def test_newline_in_path(self, tmp_path):
        """Test newline injection is blocked"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        malicious_paths = [
            "file\n.md",
            "file.md\r\n",
            "file\r.md",
        ]

        for path in malicious_paths:
            with pytest.raises(PathValidationError, match="Dangerous pattern"):
                validator.validate_input_path(path)


class TestOutputPathValidation:
    """Test output path validation"""

    def test_output_path_creates_parent(self, tmp_path):
        """Test parent directory creation for output paths"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        output_path = tmp_path / "subdir" / "output.md"

        result = validator.validate_output_path(str(output_path), create_parent=True)

        assert result.parent.exists()
        assert result == output_path.resolve()

    def test_output_path_no_create_parent(self, tmp_path):
        """Test error when parent doesn't exist and create_parent=False"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        output_path = tmp_path / "nonexistent" / "output.md"

        with pytest.raises(PathValidationError, match="Parent directory does not exist"):
            validator.validate_output_path(str(output_path), create_parent=False)


class TestEdgeCases:
    """Test edge cases and corner scenarios"""

    def test_empty_path(self):
        """Test empty path is rejected"""
        validator = PathValidator()

        with pytest.raises(PathValidationError):
            validator.validate_input_path("")

    def test_directory_instead_of_file(self, tmp_path):
        """Test directory path is rejected (expect file)"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        test_dir = tmp_path / "testdir"
        test_dir.mkdir()

        with pytest.raises(PathValidationError, match="not a file"):
            validator.validate_input_path(str(test_dir))

        test_dir.rmdir()

    def test_nonexistent_file(self, tmp_path):
        """Test nonexistent file is rejected for reading"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        with pytest.raises(PathValidationError, match="does not exist"):
            validator.validate_input_path(str(tmp_path / "nonexistent.md"))

    def test_case_insensitive_extension(self, tmp_path):
        """Test extension matching is case-insensitive"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        test_file = tmp_path / "TEST.MD"  # Uppercase extension
        test_file.write_text("data")

        # Should succeed (case-insensitive)
        result = validator.validate_input_path(str(test_file))
        assert result.exists()

        test_file.unlink()


class TestGlobalValidator:
    """Test global validator convenience functions"""

    def test_global_validate_input_path(self, tmp_path):
        """Test global validate_input_path function"""
        from utils.path_validator import get_validator

        # Add tmp_path to global validator
        get_validator().add_allowed_directory(tmp_path)

        test_file = tmp_path / "test.md"
        test_file.write_text("data")

        result = validate_input_path(str(test_file))
        assert result.exists()

        test_file.unlink()

    def test_global_validate_output_path(self, tmp_path):
        """Test global validate_output_path function"""
        from utils.path_validator import get_validator

        get_validator().add_allowed_directory(tmp_path)

        output_path = tmp_path / "output.md"

        result = validate_output_path(str(output_path))
        assert result == output_path.resolve()


class TestSecurityScenarios:
    """Test realistic attack scenarios"""

    def test_zipslip_attack(self, tmp_path):
        """Test zipslip-style attack is blocked"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        # Zipslip: ../../../etc/passwd
        with pytest.raises(PathValidationError, match="Dangerous pattern"):
            validator.validate_input_path("../../../etc/passwd")

    def test_windows_path_traversal(self, tmp_path):
        """Test Windows-style path traversal is blocked"""
        validator = PathValidator(allowed_base_dirs={tmp_path})

        malicious_paths = [
            "..\\..\\..\\windows\\system32",
            "C:\\..\\..\\etc\\passwd",
        ]

        for path in malicious_paths:
            with pytest.raises(PathValidationError):
                validator.validate_input_path(path)

    def test_home_directory_expansion_safe(self, tmp_path):
        """Test home directory expansion works safely"""
        # Create test file in actual home directory
        home = Path.home()
        test_file = home / "Documents" / "test_path_validator.md"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("test")

        validator = PathValidator()  # Uses default whitelist including ~/Documents

        # Should work with ~ expansion
        result = validator.validate_input_path("~/Documents/test_path_validator.md")
        assert result.exists()

        # Cleanup
        test_file.unlink()


# Run tests with: pytest -v test_path_validator.py
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
