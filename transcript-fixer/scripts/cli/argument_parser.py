#!/usr/bin/env python3
"""
Argument Parser - CLI Argument Configuration

SINGLE RESPONSIBILITY: Configure command-line argument parsing
"""

from __future__ import annotations

import argparse


def create_argument_parser() -> argparse.ArgumentParser:
    """
    Create and configure the argument parser for transcript-fixer CLI.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        description="Transcript Fixer - Iterative correction tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Setup commands
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize ~/.transcript-fixer/"
    )

    # Correction management
    parser.add_argument(
        "--add",
        nargs=2,
        metavar=("FROM", "TO"),
        dest="add_correction",
        help="Add correction"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_corrections",
        help="List all corrections"
    )

    # Correction workflow
    parser.add_argument(
        "--input", "-i",
        help="Input file"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output directory"
    )
    parser.add_argument(
        "--stage", "-s",
        type=int,
        choices=[1, 2, 3],
        default=3,
        help="Run stage (1=dict, 2=AI, 3=full)"
    )
    parser.add_argument(
        "--domain", "-d",
        default="general",
        help="Correction domain"
    )

    # Learning commands
    parser.add_argument(
        "--review-learned",
        action="store_true",
        help="Review learned suggestions"
    )
    parser.add_argument(
        "--approve",
        nargs=2,
        metavar=("FROM", "TO"),
        help="Approve suggestion"
    )

    # Utility commands
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate configuration and JSON files"
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Perform system health check (P1-4 fix)"
    )
    parser.add_argument(
        "--health-level",
        dest="health_level",
        choices=["basic", "standard", "deep"],
        default="standard",
        help="Health check thoroughness (default: standard)"
    )
    parser.add_argument(
        "--health-format",
        dest="health_format",
        choices=["text", "json"],
        default="text",
        help="Health check output format (default: text)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output (for health check)"
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Display collected metrics (P1-7 fix)"
    )
    parser.add_argument(
        "--metrics-format",
        dest="metrics_format",
        choices=["text", "json", "prometheus"],
        default="text",
        help="Metrics output format (default: text)"
    )

    # Configuration management (P1-5 fix)
    parser.add_argument(
        "--config",
        dest="config_action",
        choices=["show", "create-example", "validate", "set-env"],
        help="Configuration management (P1-5 fix)"
    )
    parser.add_argument(
        "--config-path",
        dest="config_path",
        help="Path for config file operations"
    )
    parser.add_argument(
        "--env",
        dest="config_env",
        choices=["development", "staging", "production", "test"],
        help="Set environment (with --config set-env)"
    )

    # Database migration commands (P1-6 fix)
    parser.add_argument(
        "--migration",
        dest="migration_action",
        choices=["status", "history", "migrate", "rollback", "plan", "validate", "create"],
        help="Database migration commands (P1-6 fix)"
    )
    parser.add_argument(
        "--migration-version",
        dest="migration_version",
        help="Target migration version (for migrate/rollback commands)"
    )
    parser.add_argument(
        "--migration-dry-run",
        dest="migration_dry_run",
        action="store_true",
        help="Dry run mode for migrations (no changes applied)"
    )
    parser.add_argument(
        "--migration-force",
        dest="migration_force",
        action="store_true",
        help="Force migration (bypass safety checks)"
    )
    parser.add_argument(
        "--migration-yes",
        dest="migration_yes",
        action="store_true",
        help="Skip confirmation prompts"
    )
    parser.add_argument(
        "--migration-history-format",
        dest="migration_history_format",
        choices=["text", "json"],
        default="text",
        help="Migration history output format (default: text)"
    )
    parser.add_argument(
        "--migration-name",
        dest="migration_name",
        help="Migration name (for create command)"
    )
    parser.add_argument(
        "--migration-description",
        dest="migration_description",
        help="Migration description (for create command)"
    )

    # Audit log retention commands (P1-11 fix)
    parser.add_argument(
        "--audit-retention",
        dest="audit_retention_action",
        choices=["cleanup", "report", "policies", "restore"],
        help="Audit log retention commands (P1-11 fix)"
    )
    parser.add_argument(
        "--entity-type",
        dest="entity_type",
        help="Entity type to operate on (for cleanup command)"
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Dry run mode (no actual changes)"
    )
    parser.add_argument(
        "--archive-file",
        dest="archive_file",
        help="Archive file path (for restore command)"
    )
    parser.add_argument(
        "--verify-only",
        dest="verify_only",
        action="store_true",
        help="Verify archive integrity without restoring (for restore command)"
    )

    return parser
