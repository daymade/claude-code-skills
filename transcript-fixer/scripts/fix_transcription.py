#!/usr/bin/env python3
"""
Transcript Fixer - Main Entry Point

SINGLE RESPONSIBILITY: Route CLI commands to handlers

This is the main entry point for the transcript-fixer tool.
It parses arguments and dispatches to appropriate command handlers.

Usage:
    # Setup
    python fix_transcription.py --init

    # Correction workflow
    python fix_transcription.py --input file.md --stage 3

    # Manage corrections
    python fix_transcription.py --add "错误" "正确"
    python fix_transcription.py --list

    # Review learned suggestions
    python fix_transcription.py --review-learned
    python fix_transcription.py --approve "错误" "正确"

    # Validate configuration
    python fix_transcription.py --validate
"""

from __future__ import annotations

from cli import (
    cmd_init,
    cmd_add_correction,
    cmd_list_corrections,
    cmd_run_correction,
    cmd_review_learned,
    cmd_approve,
    cmd_validate,
    cmd_health,
    cmd_metrics,
    cmd_config,
    cmd_migration,
    cmd_audit_retention,
    create_argument_parser,
)


def main() -> None:
    """Main entry point - parse arguments and dispatch to commands"""
    parser = create_argument_parser()
    args = parser.parse_args()

    # Dispatch commands
    if args.init:
        cmd_init(args)
    elif args.health:
        # Map argument names for health command
        args.level = args.health_level
        args.format = args.health_format
        cmd_health(args)
    elif args.metrics:
        # Map argument names for metrics command
        args.format = args.metrics_format
        cmd_metrics(args)
    elif args.config_action:
        # Map argument names for config command (P1-5 fix)
        args.action = args.config_action
        args.path = args.config_path
        args.env = args.config_env
        cmd_config(args)
    elif args.migration_action:
        # Map argument names for migration command (P1-6 fix)
        args.action = args.migration_action
        args.version = args.migration_version
        args.dry_run = args.migration_dry_run
        args.force = args.migration_force
        args.yes = args.migration_yes
        args.format = args.migration_history_format
        args.name = args.migration_name
        args.description = args.migration_description
        cmd_migration(args)
    elif args.audit_retention_action:
        # Map argument names for audit-retention command (P1-11 fix)
        args.action = args.audit_retention_action
        # Other arguments (entity_type, dry_run, archive_file, verify_only) already have correct names
        cmd_audit_retention(args)
    elif args.validate:
        cmd_validate(args)
    elif args.add_correction:
        args.from_text, args.to_text = args.add_correction
        cmd_add_correction(args)
    elif args.list_corrections:
        cmd_list_corrections(args)
    elif args.review_learned:
        cmd_review_learned(args)
    elif args.approve:
        args.from_text, args.to_text = args.approve
        cmd_approve(args)
    elif args.input:
        cmd_run_correction(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
