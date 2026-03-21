#!/usr/bin/env python3
"""
CLI Commands - Command Handler Functions

SINGLE RESPONSIBILITY: Handle CLI command execution

All cmd_* functions take parsed args and execute the requested operation.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from core import (
    CorrectionRepository,
    CorrectionService,
    DictionaryProcessor,
    AIProcessor,
    LearningEngine,
)
from utils import validate_configuration, print_validation_summary
from utils.health_check import HealthChecker, CheckLevel, format_health_output
from utils.metrics import get_metrics, format_metrics_summary
from utils.config import get_config
from utils.db_migrations_cli import create_migration_cli


def _get_service() -> CorrectionService:
    """Get configured CorrectionService instance."""
    # P1-5 FIX: Use centralized configuration
    config = get_config()
    repository = CorrectionRepository(config.database.path)
    return CorrectionService(repository)


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize ~/.transcript-fixer/ directory"""
    service = _get_service()
    service.initialize()


def cmd_add_correction(args: argparse.Namespace) -> None:
    """Add a single correction with safety checks"""
    service = _get_service()
    force = getattr(args, 'force', False)
    try:
        service.add_correction(
            args.from_text, args.to_text, args.domain, force=force,
        )
        print(f"Added: '{args.from_text}' -> '{args.to_text}' (domain: {args.domain})")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_audit(args: argparse.Namespace) -> None:
    """Audit all active corrections for false positive risks"""
    service = _get_service()
    domain = getattr(args, 'domain', None)

    print(f"\nAuditing corrections" + (f" (domain: {domain})" if domain else " (all domains)") + "...")
    print("=" * 70)

    issues = service.audit_dictionary(domain)

    if not issues:
        corrections = service.get_corrections(domain)
        print(f"\nAll {len(corrections)} corrections passed safety checks.")
        return

    # Categorize
    error_count = 0
    warning_count = 0
    for from_text, warnings in issues.items():
        for w in warnings:
            if w.level == "error":
                error_count += 1
            else:
                warning_count += 1

    corrections = service.get_corrections(domain)
    print(f"\nScanned {len(corrections)} corrections. "
          f"Found issues in {len(issues)} rules:")
    print(f"  Errors: {error_count} (should be removed or converted to context rules)")
    print(f"  Warnings: {warning_count} (review recommended)")
    print()

    # Print details grouped by severity
    for severity in ["error", "warning"]:
        label = "ERRORS" if severity == "error" else "WARNINGS"
        relevant = {
            ft: [w for w in ws if w.level == severity]
            for ft, ws in issues.items()
        }
        relevant = {ft: ws for ft, ws in relevant.items() if ws}

        if not relevant:
            continue

        print(f"--- {label} ({len(relevant)} rules) ---")
        for from_text, warnings in sorted(relevant.items()):
            to_text = corrections.get(from_text, "?")
            print(f"\n  '{from_text}' -> '{to_text}'")
            for w in warnings:
                print(f"    [{w.category}] {w.message}")
                print(f"    Suggestion: {w.suggestion}")
        print()

    if error_count > 0:
        print(
            f"ACTION REQUIRED: {error_count} error(s) found. These rules are "
            f"actively causing false positives and should be removed or "
            f"converted to context rules."
        )
        print(
            f"To remove a rule: "
            f"sqlite3 ~/.transcript-fixer/corrections.db "
            f"\"UPDATE corrections SET is_active=0 WHERE from_text='...';\""
        )


def cmd_list_corrections(args: argparse.Namespace) -> None:
    """List all corrections"""
    service = _get_service()
    corrections = service.get_corrections(args.domain)

    if args.domain:
        header = f"domain: {args.domain}, {len(corrections)} total"
    else:
        header = f"all domains, {len(corrections)} total"

    print(f"\n📋 Corrections ({header})")
    print("=" * 60)

    if args.domain:
        for wrong, correct in sorted(corrections.items()):
            print(f"  '{wrong}' → '{correct}'")
    else:
        all_corrections = service.repository.get_all_corrections(active_only=True)
        for c in all_corrections:
            print(f"  [{c.domain}]  '{c.from_text}' → '{c.to_text}'")
    print()


def cmd_run_correction(args: argparse.Namespace) -> None:
    """Run the correction workflow"""
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Error: File not found: {input_path}")
        sys.exit(1)

    # Setup output directory
    output_dir = Path(args.output) if args.output else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize service
    service = _get_service()

    # Load corrections and rules
    corrections = service.get_corrections(args.domain)
    context_rules = service.load_context_rules()
    domain_stats = service.get_domain_stats()

    # Read input file
    print(f"📖 Reading: {input_path.name}")
    with open(input_path, 'r', encoding='utf-8') as f:
        original_text = f.read()
    print(f"   File size: {len(original_text):,} characters")

    # Show domain loading info
    if args.domain:
        print(f"📚 Loaded {len(corrections)} corrections (domain: {args.domain})")
    elif domain_stats:
        parts = ", ".join(f"{d}: {n}" for d, n in sorted(domain_stats.items()))
        print(f"📚 Loaded {len(corrections)} corrections ({parts})")
    else:
        print(f"📚 No corrections in database")
    print()

    # Stage 1: Dictionary corrections
    stage1_changes = []
    stage1_text = original_text
    if args.stage >= 1:
        print("=" * 60)
        print("🔧 Stage 1: Dictionary Corrections")
        print("=" * 60)

        processor = DictionaryProcessor(corrections, context_rules)
        stage1_text, stage1_changes = processor.process(original_text)

        summary = processor.get_summary(stage1_changes)
        print(f"✓ Applied {summary['total_changes']} corrections")
        print(f"  - Dictionary: {summary['dictionary_changes']}")
        print(f"  - Context rules: {summary['context_rule_changes']}")

        stage1_file = output_dir / f"{input_path.stem}_stage1.md"
        with open(stage1_file, 'w', encoding='utf-8') as f:
            f.write(stage1_text)
        print(f"💾 Saved: {stage1_file.name}")

        # Hint when 0 corrections and other domains have rules
        if summary['total_changes'] == 0 and args.domain and domain_stats:
            other = {d: n for d, n in domain_stats.items() if d != args.domain}
            if other:
                parts = ", ".join(f"{d} ({n})" for d, n in sorted(other.items()))
                total = sum(other.values())
                print(f"hint: no rules in domain '{args.domain}'. Available: {parts}")
                print(f"hint: run without --domain to use all {total} rules")
        print()

    # Stage 2: AI corrections
    stage2_changes = []
    stage2_text = stage1_text
    if args.stage >= 2:
        print("=" * 60)
        print("🤖 Stage 2: AI Corrections")
        print("=" * 60)

        # Check API key
        api_key = os.environ.get("GLM_API_KEY")
        if not api_key:
            print("❌ Error: GLM_API_KEY environment variable not set")
            print("   Set it with: export GLM_API_KEY='your-key'")
            sys.exit(1)

        ai_processor = AIProcessor(api_key)
        stage2_text, stage2_changes = ai_processor.process(stage1_text)

        print(f"✓ Processed {len(stage2_changes)} chunks\n")

        stage2_file = output_dir / f"{input_path.stem}_stage2.md"
        with open(stage2_file, 'w', encoding='utf-8') as f:
            f.write(stage2_text)
        print(f"💾 Saved: {stage2_file.name}\n")

        # Save history for learning
        service.save_history(
            filename=str(input_path),
            domain=args.domain,
            original_length=len(original_text),
            stage1_changes=len(stage1_changes),
            stage2_changes=len(stage2_changes),
            model="GLM-4.6",
            changes=stage1_changes + stage2_changes
        )

        # Run learning engine - AUTO-LEARN from AI results!
        if stage2_changes:
            print("=" * 60)
            print("🎓 Learning System: Analyzing AI Corrections")
            print("=" * 60)

            config_dir = Path.home() / ".transcript-fixer"
            learning = LearningEngine(
                history_dir=config_dir / "history",
                learned_dir=config_dir / "learned",
                correction_service=service
            )

            stats = learning.analyze_and_auto_approve(stage2_changes, args.domain)

            print(f"📊 Analysis Results:")
            print(f"   Total changes: {stats['total_changes']}")
            print(f"   Unique patterns: {stats['unique_patterns']}")

            if stats['auto_approved'] > 0:
                print(f"   ✅ Auto-approved: {stats['auto_approved']} patterns")
                print(f"      (Added to dictionary for next run)")

            if stats['pending_review'] > 0:
                print(f"   ⏳ Pending review: {stats['pending_review']} patterns")
                print(f"      (Run --review-learned to approve manually)")

            if stats.get('savings_potential'):
                print(f"\n   💰 {stats['savings_potential']}")

            print()

    # Stage 3: Generate diff report
    if args.stage >= 3:
        print("=" * 60)
        print("📊 Stage 3: Generating Diff Report")
        print("=" * 60)
        print("   Use diff_generator.py to create visual comparison\n")

    print("✅ Correction complete!")


def cmd_review_learned(args: argparse.Namespace) -> None:
    """Review learned suggestions"""
    # TODO: Implement learning engine with SQLite backend
    print("⚠️  Learning engine not yet implemented with SQLite backend")
    print("   This feature will be added in a future update")


def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a learned suggestion"""
    # TODO: Implement learning engine with SQLite backend
    print("⚠️  Learning engine not yet implemented with SQLite backend")
    print("   This feature will be added in a future update")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate configuration and JSON files"""
    errors, warnings = validate_configuration()
    exit_code = print_validation_summary(errors, warnings)
    if exit_code != 0:
        sys.exit(exit_code)


def cmd_health(args: argparse.Namespace) -> None:
    """
    Perform system health check

    CRITICAL FIX (P1-4): Production-grade health monitoring
    """
    # Parse check level
    level_map = {
        'basic': CheckLevel.BASIC,
        'standard': CheckLevel.STANDARD,
        'deep': CheckLevel.DEEP
    }
    level = level_map.get(args.level, CheckLevel.STANDARD)

    # Run health check
    checker = HealthChecker()
    health = checker.check_health(level=level)

    # Output format
    if args.format == 'json':
        print(health.to_json())
    else:
        output = format_health_output(health, verbose=args.verbose)
        print(output)

    # Exit with appropriate code
    if health.status.value == 'unhealthy':
        sys.exit(1)
    elif health.status.value == 'degraded':
        sys.exit(2)
    else:
        sys.exit(0)


def cmd_metrics(args: argparse.Namespace) -> None:
    """
    Display collected metrics

    CRITICAL FIX (P1-7): Production-grade metrics and observability
    """
    metrics = get_metrics()

    # Output format
    if args.format == 'json':
        print(metrics.to_json())
    elif args.format == 'prometheus':
        print(metrics.to_prometheus())
    else:
        # Text summary
        summary = metrics.get_summary()
        output = format_metrics_summary(summary)
        print(output)


def cmd_config(args: argparse.Namespace) -> None:
    """
    Configuration management commands

    CRITICAL FIX (P1-5): Production-grade configuration management
    """
    from utils.config import create_example_config, Environment

    if args.action == 'show':
        # Display current configuration
        config = get_config()
        output = {
            'environment': config.environment.value,
            'database_path': str(config.database.path),
            'config_dir': str(config.paths.config_dir),
            'api_key_set': config.api.api_key is not None,
            'debug': config.debug,
            'features': {
                'learning': config.features.enable_learning,
                'metrics': config.features.enable_metrics,
                'health_checks': config.features.enable_health_checks,
                'rate_limiting': config.features.enable_rate_limiting,
                'caching': config.features.enable_caching,
                'auto_approval': config.features.enable_auto_approval,
            }
        }
        print('Current Configuration:')
        for key, value in output.items():
            print(f'  {key}: {value}')

    elif args.action == 'create-example':
        # Create example config file
        output_path = Path(args.path) if args.path else get_config().paths.config_dir / 'config.json'
        create_example_config(output_path)
        print(f'Example config created: {output_path}')

    elif args.action == 'validate':
        # Validate configuration
        config = get_config()
        errors, warnings = config.validate()

        print('Configuration Validation:')
        if errors:
            print('  Errors:')
            for error in errors:
                print(f'    ❌ {error}')
            sys.exit(1)
        if warnings:
            print('  Warnings:')
            for warning in warnings:
                print(f'    ⚠️  {warning}')
        if not errors and not warnings:
            print('  ✅ Configuration is valid')
        sys.exit(0 if not errors else 1)

    elif args.action == 'set-env':
        # Set environment
        if args.env not in [e.value for e in Environment]:
            print(f'Invalid environment: {args.env}')
            print(f'Valid environments: {", ".join(e.value for e in Environment)}')
            sys.exit(1)

        print(f'Environment set to: {args.env}')
        print('To make this permanent, set TRANSCRIPT_FIXER_ENV environment variable:')


def cmd_migration(args: argparse.Namespace) -> None:
    """
    Database migration commands (P1-6 fix)

    CRITICAL FIX (P1-6): Production database migration system
    """
    migration_cli = create_migration_cli()

    if args.action == 'status':
        migration_cli.cmd_status(args)
    elif args.action == 'history':
        migration_cli.cmd_history(args)
    elif args.action == 'migrate':
        migration_cli.cmd_migrate(args)
    elif args.action == 'rollback':
        migration_cli.cmd_rollback(args)
    elif args.action == 'plan':
        migration_cli.cmd_plan(args)
    elif args.action == 'validate':
        migration_cli.cmd_validate(args)
    elif args.action == 'create':
        migration_cli.cmd_create_migration(args)
    else:
        print("Unknown migration action")
        sys.exit(1)


def cmd_audit_retention(args: argparse.Namespace) -> None:
    """
    Audit log retention management commands (P1-11 fix)

    CRITICAL FIX (P1-11): Production-grade audit log retention and compliance
    """
    from utils.audit_log_retention import get_retention_manager
    import json

    # Get retention manager with configured database path
    config = get_config()
    manager = get_retention_manager(config.database.path)

    if args.action == 'cleanup':
        # Clean up expired audit logs
        entity_type = getattr(args, 'entity_type', None)
        dry_run = getattr(args, 'dry_run', False)

        if dry_run:
            print("🔍 DRY RUN MODE - No actual changes will be made\n")

        print("🧹 Cleaning up expired audit logs...")
        results = manager.cleanup_expired_logs(entity_type=entity_type, dry_run=dry_run)

        if not results:
            print("ℹ️  No cleanup operations performed (permanent retention or no expired logs)")
            return

        print("\n📊 Cleanup Results:")
        print("=" * 70)

        for result in results:
            status = "✅ Success" if result.success else "❌ Failed"
            print(f"\n{result.entity_type}: {status}")
            print(f"  Scanned: {result.records_scanned}")
            print(f"  Deleted: {result.records_deleted}")
            print(f"  Archived: {result.records_archived}")
            print(f"  Anonymized: {result.records_anonymized}")
            print(f"  Execution time: {result.execution_time_ms}ms")

            if result.errors:
                print(f"  Errors: {', '.join(result.errors)}")

        print()

    elif args.action == 'report':
        # Generate compliance report
        print("📋 Generating compliance report...\n")
        report = manager.generate_compliance_report()

        print("=" * 70)
        print("AUDIT LOG COMPLIANCE REPORT")
        print("=" * 70)
        print(f"Report Date: {report.report_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Compliance Status: {'✅ COMPLIANT' if report.is_compliant else '❌ NON-COMPLIANT'}")
        print(f"\nTotal Audit Logs: {report.total_audit_logs:,}")

        if report.oldest_log_date:
            print(f"Oldest Log: {report.oldest_log_date.strftime('%Y-%m-%d %H:%M:%S')}")
        if report.newest_log_date:
            print(f"Newest Log: {report.newest_log_date.strftime('%Y-%m-%d %H:%M:%S')}")

        print(f"\nStorage: {report.storage_size_mb:.2f} MB")
        print(f"Archived Files: {report.archived_logs_count}")

        print("\nLogs by Entity Type:")
        for entity_type, count in sorted(report.logs_by_entity_type.items()):
            print(f"  {entity_type}: {count:,}")

        if report.retention_violations:
            print("\n⚠️  Retention Violations:")
            for violation in report.retention_violations:
                print(f"  • {violation}")
            print("\nRun 'audit-retention cleanup' to resolve violations")

        print()

        # JSON output option
        if getattr(args, 'format', 'text') == 'json':
            print(json.dumps(report.to_dict(), indent=2))

    elif args.action == 'policies':
        # Show retention policies
        print("📜 Retention Policies:")
        print("=" * 70)

        policies = manager.load_retention_policies()

        for entity_type, policy in sorted(policies.items()):
            status = "✅ Active" if policy.is_active else "❌ Inactive"
            days_str = "PERMANENT" if policy.retention_days == -1 else f"{policy.retention_days} days"

            print(f"\n{entity_type}: {status}")
            print(f"  Retention: {days_str}")
            print(f"  Strategy: {policy.strategy.value.upper()}")

            if policy.critical_action_retention_days:
                crit_days = policy.critical_action_retention_days
                print(f"  Critical Actions: {crit_days} days (extended)")

            if policy.description:
                print(f"  Description: {policy.description}")

        print()

    elif args.action == 'restore':
        # Restore from archive
        archive_file = Path(getattr(args, 'archive_file', ''))

        if not archive_file:
            print("❌ Error: --archive-file required for restore action")
            sys.exit(1)

        if not archive_file.exists():
            print(f"❌ Error: Archive file not found: {archive_file}")
            sys.exit(1)

        verify_only = getattr(args, 'verify_only', False)

        if verify_only:
            print(f"🔍 Verifying archive: {archive_file.name}")
            count = manager.restore_from_archive(archive_file, verify_only=True)
            print(f"✅ Archive is valid: contains {count} log entries")
        else:
            print(f"📦 Restoring from archive: {archive_file.name}")
            count = manager.restore_from_archive(archive_file, verify_only=False)
            print(f"✅ Restored {count} log entries")

        print()

    else:
        print(f"❌ Unknown audit-retention action: {args.action}")
        print("Valid actions: cleanup, report, policies, restore")
        sys.exit(1)
