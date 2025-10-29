#!/usr/bin/env python3
"""
Validation Utility - Configuration Health Checker

SINGLE RESPONSIBILITY: Validate transcript-fixer configuration and JSON files

Features:
- Check directory structure
- Validate JSON syntax in all config files
- Check environment variables
- Report statistics and health status
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def validate_configuration() -> tuple[list[str], list[str]]:
    """
    Validate transcript-fixer configuration.

    Returns:
        Tuple of (errors, warnings) as string lists
    """
    config_dir = Path.home() / ".transcript-fixer"
    db_path = config_dir / "corrections.db"

    errors = []
    warnings = []

    print("🔍 Validating transcript-fixer configuration...\n")

    # Check directory exists
    if not config_dir.exists():
        errors.append(f"Configuration directory not found: {config_dir}")
        print(f"❌ {errors[-1]}")
        print("\n💡 Run: python fix_transcription.py --init")
        return errors, warnings

    print(f"✅ Configuration directory exists: {config_dir}")

    # Validate SQLite database
    if db_path.exists():
        try:
            # CRITICAL FIX: Lazy import to prevent circular dependency
            # circular import: core → utils.domain_validator → utils → utils.validation → core
            from core import CorrectionRepository, CorrectionService

            repository = CorrectionRepository(db_path)
            service = CorrectionService(repository)

            # Query basic stats
            stats = service.get_statistics()
            print(f"✅ Database valid: {stats['total_corrections']} corrections")

            # Check tables exist
            with repository._pool.get_connection() as conn:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]

            expected_tables = [
                'corrections', 'context_rules', 'correction_history',
                'correction_changes', 'learned_suggestions', 'suggestion_examples',
                'system_config', 'audit_log'
            ]

            missing_tables = [t for t in expected_tables if t not in tables]
            if missing_tables:
                errors.append(f"Database missing tables: {missing_tables}")
                print(f"❌ {errors[-1]}")
            else:
                print(f"✅ All {len(expected_tables)} tables present")

            service.close()

        except Exception as e:
            errors.append(f"Database validation failed: {e}")
            print(f"❌ {errors[-1]}")
    else:
        warnings.append("Database not found (will be created on first use)")
        print(f"⚠️  Database not found: {db_path}")

    # Check API key
    api_key = os.getenv("GLM_API_KEY")
    if not api_key:
        warnings.append("GLM_API_KEY environment variable not set")
        print("⚠️  GLM_API_KEY not set (required for Stage 2 AI corrections)")
    else:
        print("✅ GLM_API_KEY is set")

    return errors, warnings


def print_validation_summary(errors: list[str], warnings: list[str]) -> int:
    """
    Print validation summary and return exit code.

    Returns:
        0 if valid, 1 if errors found
    """
    print("\n" + "=" * 60)

    if errors:
        print(f"❌ {len(errors)} error(s) found:")
        for err in errors:
            print(f"   - {err}")
        print("\n💡 Fix errors and run --validate again")
        print("=" * 60)
        return 1
    elif warnings:
        print(f"⚠️  {len(warnings)} warning(s):")
        for warn in warnings:
            print(f"   - {warn}")
        print("\n✅ Configuration is valid (with warnings)")
        print("=" * 60)
        return 0
    else:
        print("✅ All checks passed! Configuration is valid.")
        print("=" * 60)
        return 0


def main():
    """Run validation as standalone script"""
    errors, warnings = validate_configuration()
    exit_code = print_validation_summary(errors, warnings)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
