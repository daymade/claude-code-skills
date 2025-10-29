#!/usr/bin/env python3
"""
Path Validation and Security

CRITICAL FIX: Prevents path traversal and symlink attacks
ISSUE: Critical-5 in Engineering Excellence Plan

This module provides:
1. Path whitelist validation
2. Path traversal prevention (../)
3. Symlink attack detection
4. File extension validation
5. Directory containment checks

Author: Chief Engineer
Date: 2025-10-28
Priority: P0 - Critical
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Set, Optional, Final, List
import logging

logger = logging.getLogger(__name__)

# Allowed base directories (whitelist)
# Only files under these directories can be accessed
ALLOWED_BASE_DIRS: Final[Set[Path]] = {
    Path.home() / ".transcript-fixer",  # Config/data directory
    Path.home() / "Downloads",           # Common download location
    Path.home() / "Documents",           # Common documents location
    Path.home() / "Desktop",             # Desktop files
    Path("/tmp"),                        # Temporary files
}

# Allowed file extensions for reading
ALLOWED_READ_EXTENSIONS: Final[Set[str]] = {
    '.md',      # Markdown
    '.txt',     # Text
    '.html',    # HTML output
    '.json',    # JSON config
    '.sql',     # SQL schema
}

# Allowed file extensions for writing
ALLOWED_WRITE_EXTENSIONS: Final[Set[str]] = {
    '.md',      # Markdown output
    '.html',    # HTML diff
    '.db',      # SQLite database
    '.log',     # Log files
}

# Dangerous patterns to reject
DANGEROUS_PATTERNS: Final[List[str]] = [
    '..',      # Parent directory traversal
    '\x00',    # Null byte
    '\n',      # Newline injection
    '\r',      # Carriage return injection
]


class PathValidationError(Exception):
    """Path validation failed"""
    pass


class PathValidator:
    """
    Validates file paths for security.

    Prevents:
    - Path traversal attacks (../)
    - Symlink attacks
    - Access outside whitelisted directories
    - Dangerous file types
    - Null byte injection

    Usage:
        validator = PathValidator()
        safe_path = validator.validate_input_path("/path/to/file.md")
        safe_output = validator.validate_output_path("/path/to/output.md")
    """

    def __init__(
        self,
        allowed_base_dirs: Optional[Set[Path]] = None,
        allowed_read_extensions: Optional[Set[str]] = None,
        allowed_write_extensions: Optional[Set[str]] = None,
        allow_symlinks: bool = False
    ):
        """
        Initialize path validator.

        Args:
            allowed_base_dirs: Whitelist of allowed base directories
            allowed_read_extensions: Allowed file extensions for reading
            allowed_write_extensions: Allowed file extensions for writing
            allow_symlinks: Allow symlinks (default: False for security)
        """
        self.allowed_base_dirs = allowed_base_dirs or ALLOWED_BASE_DIRS
        self.allowed_read_extensions = allowed_read_extensions or ALLOWED_READ_EXTENSIONS
        self.allowed_write_extensions = allowed_write_extensions or ALLOWED_WRITE_EXTENSIONS
        self.allow_symlinks = allow_symlinks

    def _check_dangerous_patterns(self, path_str: str) -> None:
        """
        Check for dangerous patterns in path string.

        Args:
            path_str: Path string to check

        Raises:
            PathValidationError: If dangerous pattern found
        """
        for pattern in DANGEROUS_PATTERNS:
            if pattern in path_str:
                raise PathValidationError(
                    f"Dangerous pattern '{pattern}' detected in path: {path_str}"
                )

    def _is_under_allowed_directory(self, path: Path) -> bool:
        """
        Check if path is under any allowed base directory.

        Args:
            path: Resolved path to check

        Returns:
            True if path is under allowed directory
        """
        for allowed_dir in self.allowed_base_dirs:
            try:
                # Check if path is relative to allowed_dir
                path.relative_to(allowed_dir)
                return True
            except ValueError:
                # Not relative to this allowed_dir
                continue

        return False

    def _check_symlink(self, path: Path) -> None:
        """
        Check for symlink attacks.

        Args:
            path: Path to check

        Raises:
            PathValidationError: If symlink detected and not allowed
        """
        if not self.allow_symlinks and path.is_symlink():
            raise PathValidationError(
                f"Symlink detected and not allowed: {path}"
            )

        # Check parent directories for symlinks (but stop at system dirs)
        if not self.allow_symlinks:
            current = path.parent

            # Stop checking at common system directories (they may be symlinks on macOS)
            system_dirs = {Path('/'), Path('/usr'), Path('/etc'), Path('/var')}

            while current != current.parent:  # Until root
                if current in system_dirs:
                    break

                if current.is_symlink():
                    raise PathValidationError(
                        f"Symlink in path hierarchy detected: {current}"
                    )
                current = current.parent

    def _validate_extension(
        self,
        path: Path,
        allowed_extensions: Set[str],
        operation: str
    ) -> None:
        """
        Validate file extension.

        Args:
            path: Path to validate
            allowed_extensions: Set of allowed extensions
            operation: Operation name (for error message)

        Raises:
            PathValidationError: If extension not allowed
        """
        extension = path.suffix.lower()

        if extension not in allowed_extensions:
            raise PathValidationError(
                f"File extension '{extension}' not allowed for {operation}. "
                f"Allowed: {sorted(allowed_extensions)}"
            )

    def validate_input_path(self, path_str: str) -> Path:
        """
        Validate an input file path for reading.

        Security checks:
        1. No dangerous patterns (.., null bytes, etc.)
        2. Path resolves to absolute path
        3. No symlinks (unless explicitly allowed)
        4. Under allowed base directory
        5. Allowed file extension for reading
        6. File exists

        Args:
            path_str: Path string to validate

        Returns:
            Validated, resolved Path object

        Raises:
            PathValidationError: If validation fails

        Example:
            >>> validator = PathValidator()
            >>> safe_path = validator.validate_input_path("~/Documents/file.md")
            >>> # Returns: Path('/home/username/Documents/file.md') or similar
        """
        # Check dangerous patterns in raw string
        self._check_dangerous_patterns(path_str)

        # Convert to Path (but don't resolve yet - need to check symlinks first)
        try:
            path = Path(path_str).expanduser().absolute()
        except Exception as e:
            raise PathValidationError(f"Invalid path format: {path_str}") from e

        # Check if file exists
        if not path.exists():
            raise PathValidationError(f"File does not exist: {path}")

        # Check if it's a file (not directory)
        if not path.is_file():
            raise PathValidationError(f"Path is not a file: {path}")

        # CRITICAL: Check for symlinks BEFORE resolving
        self._check_symlink(path)

        # Now resolve to get canonical path
        path = path.resolve()

        # Check if under allowed directory
        if not self._is_under_allowed_directory(path):
            raise PathValidationError(
                f"Path not under allowed directories: {path}\n"
                f"Allowed directories: {[str(d) for d in self.allowed_base_dirs]}"
            )

        # Check file extension
        self._validate_extension(path, self.allowed_read_extensions, "reading")

        logger.info(f"Input path validated: {path}")
        return path

    def validate_output_path(self, path_str: str, create_parent: bool = True) -> Path:
        """
        Validate an output file path for writing.

        Security checks:
        1. No dangerous patterns
        2. Path resolves to absolute path
        3. No symlinks in path hierarchy
        4. Under allowed base directory
        5. Allowed file extension for writing
        6. Parent directory exists or can be created

        Args:
            path_str: Path string to validate
            create_parent: Create parent directory if it doesn't exist

        Returns:
            Validated, resolved Path object

        Raises:
            PathValidationError: If validation fails

        Example:
            >>> validator = PathValidator()
            >>> safe_path = validator.validate_output_path("~/Documents/output.md")
            >>> # Returns: Path('/home/username/Documents/output.md') or similar
        """
        # Check dangerous patterns
        self._check_dangerous_patterns(path_str)

        # Convert to Path and resolve
        try:
            path = Path(path_str).expanduser().resolve()
        except Exception as e:
            raise PathValidationError(f"Invalid path format: {path_str}") from e

        # Check parent directory exists
        parent = path.parent
        if not parent.exists():
            if create_parent:
                # Validate parent directory first
                if not self._is_under_allowed_directory(parent):
                    raise PathValidationError(
                        f"Parent directory not under allowed directories: {parent}"
                    )
                try:
                    parent.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created parent directory: {parent}")
                except Exception as e:
                    raise PathValidationError(
                        f"Failed to create parent directory: {parent}"
                    ) from e
            else:
                raise PathValidationError(f"Parent directory does not exist: {parent}")

        # Check for symlinks in path hierarchy (but file itself doesn't exist yet)
        if not self.allow_symlinks:
            current = parent
            while current != current.parent:
                if current.is_symlink():
                    raise PathValidationError(
                        f"Symlink in path hierarchy: {current}"
                    )
                current = current.parent

        # Check if under allowed directory
        if not self._is_under_allowed_directory(path):
            raise PathValidationError(
                f"Path not under allowed directories: {path}\n"
                f"Allowed directories: {[str(d) for d in self.allowed_base_dirs]}"
            )

        # Check file extension
        self._validate_extension(path, self.allowed_write_extensions, "writing")

        logger.info(f"Output path validated: {path}")
        return path

    def add_allowed_directory(self, directory: str | Path) -> None:
        """
        Add a directory to the whitelist.

        Args:
            directory: Directory path to add

        Example:
            >>> validator.add_allowed_directory("/home/username/Projects")
        """
        dir_path = Path(directory).expanduser().resolve()
        self.allowed_base_dirs.add(dir_path)
        logger.info(f"Added allowed directory: {dir_path}")

    def is_path_safe(self, path_str: str, for_writing: bool = False) -> bool:
        """
        Check if a path is safe without raising exceptions.

        Args:
            path_str: Path to check
            for_writing: Check for writing (vs reading)

        Returns:
            True if path is safe

        Example:
            >>> if validator.is_path_safe("~/Documents/file.md"):
            ...     process_file()
        """
        try:
            if for_writing:
                self.validate_output_path(path_str, create_parent=False)
            else:
                self.validate_input_path(path_str)
            return True
        except PathValidationError:
            return False


# Global validator instance
_global_validator: Optional[PathValidator] = None


def get_validator() -> PathValidator:
    """
    Get global validator instance.

    Returns:
        Global PathValidator instance

    Example:
        >>> validator = get_validator()
        >>> safe_path = validator.validate_input_path("file.md")
    """
    global _global_validator
    if _global_validator is None:
        _global_validator = PathValidator()
    return _global_validator


# Convenience functions
def validate_input_path(path_str: str) -> Path:
    """Validate input path using global validator"""
    return get_validator().validate_input_path(path_str)


def validate_output_path(path_str: str, create_parent: bool = True) -> Path:
    """Validate output path using global validator"""
    return get_validator().validate_output_path(path_str, create_parent)


def add_allowed_directory(directory: str | Path) -> None:
    """Add allowed directory to global validator"""
    get_validator().add_allowed_directory(directory)


# Example usage and testing
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    print("=== Testing PathValidator ===\n")

    validator = PathValidator()

    # Test 1: Valid input path (create a test file first)
    print("Test 1: Valid input path")
    test_file = Path.home() / "Documents" / "test.md"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("test")

    try:
        result = validator.validate_input_path(str(test_file))
        print(f"✓ Valid: {result}\n")
    except PathValidationError as e:
        print(f"✗ Failed: {e}\n")

    # Test 2: Path traversal attack
    print("Test 2: Path traversal attack")
    try:
        result = validator.validate_input_path("../../etc/passwd")
        print(f"✗ Should have failed: {result}\n")
    except PathValidationError as e:
        print(f"✓ Correctly rejected: {e}\n")

    # Test 3: Invalid extension
    print("Test 3: Invalid extension")
    dangerous_file = Path.home() / "Documents" / "script.sh"
    dangerous_file.write_text("#!/bin/bash")

    try:
        result = validator.validate_input_path(str(dangerous_file))
        print(f"✗ Should have failed: {result}\n")
    except PathValidationError as e:
        print(f"✓ Correctly rejected: {e}\n")

    # Test 4: Valid output path
    print("Test 4: Valid output path")
    try:
        result = validator.validate_output_path(str(Path.home() / "Documents" / "output.html"))
        print(f"✓ Valid: {result}\n")
    except PathValidationError as e:
        print(f"✗ Failed: {e}\n")

    # Test 5: Null byte injection
    print("Test 5: Null byte injection")
    try:
        result = validator.validate_input_path("file.md\x00.txt")
        print(f"✗ Should have failed: {result}\n")
    except PathValidationError as e:
        print(f"✓ Correctly rejected: {e}\n")

    # Cleanup
    test_file.unlink(missing_ok=True)
    dangerous_file.unlink(missing_ok=True)

    print("=== All tests completed ===")
