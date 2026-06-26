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

from core.defaults import API_PROVIDER, DEFAULT_MODEL, API_BASE_URL


def _check_system_config_consistency(repository) -> list[str]:
    """Compare DB system_config against canonical defaults."""
    expected = {
        "api_provider": API_PROVIDER,
        "api_model": DEFAULT_MODEL,
        "api_base_url": API_BASE_URL,
    }
    mismatches = []
    with repository._pool.get_connection() as conn:
        for key, expected_value in expected.items():
            cursor = conn.execute(
                "SELECT value FROM system_config WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            if row is None:
                mismatches.append(f"system_config missing '{key}'")
            elif row[0] != expected_value:
                mismatches.append(
                    f"system_config.{key}='{row[0]}' (expected '{expected_value}')"
                )
    return mismatches


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

            # Check system_config defaults match canonical values
            mismatches = _check_system_config_consistency(repository)
            if mismatches:
                errors.append(f"Default configuration drift: {'; '.join(mismatches)}")
                print(f"❌ {errors[-1]}")
            else:
                print("✅ Default configuration values consistent")

            service.close()

        except Exception as e:
            errors.append(f"Database validation failed: {e}")
            print(f"❌ {errors[-1]}")
    else:
        warnings.append("Database not found (will be created on first use)")
        print(f"⚠️  Database not found: {db_path}")

    # Check API key (canonical source: config directory)
    config_dir = Path.home() / ".transcript-fixer"
    try:
        from utils.config import get_config
        config = get_config()
        api_key = config.api.api_key
        config_dir = config.paths.config_dir
    except Exception as e:
        errors.append(f"Could not load configuration: {e}")
        print(f"❌ Could not load configuration: {e}")
        api_key = None

    if not api_key:
        warnings.append("API key not configured (required for Stage 2 AI corrections)")
        print(f"⚠️  API key not configured. Set it in {config_dir}/config.json (api.api_key)")
        print("   or via the GLM_API_KEY / ANTHROPIC_API_KEY environment variable.")
    else:
        print("✅ API key is configured")

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
