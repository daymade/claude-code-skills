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
)
from utils.config import get_config

# Heavy command-specific imports are deferred to the functions that use them
# to keep CLI startup fast for simple operations like --list / --add / --stage 1.


def _get_service() -> CorrectionService:
    """Get configured CorrectionService instance."""
    # P1-5 FIX: Use centralized configuration
    config = get_config()
    repository = CorrectionRepository(config.database.path)
    return CorrectionService(repository)


def _format_changes_report(
    changes,
    original_text: str,
    title: str = "Stage 1 Correction Report"
) -> str:
    """Format a list of Change objects into a markdown report with risk levels."""
    if not changes:
        return f"# {title}\n\nNo Stage 1 corrections applied.\n"

    lines = [f"# {title}", ""]
    lines.append(f"Total changes: {len(changes)}\n")

    # Summary by risk
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    for c in changes:
        risk_counts[c.risk] = risk_counts.get(c.risk, 0) + 1
    lines.append("| Risk | Count |")
    lines.append("|------|-------|")
    for risk in ("low", "medium", "high"):
        lines.append(f"| {risk} | {risk_counts.get(risk, 0)} |")
    lines.append("")

    # Group by risk
    by_risk = {"low": [], "medium": [], "high": []}
    for c in changes:
        by_risk.setdefault(c.risk, []).append(c)

    original_lines = original_text.split("\n")
    idx = 1
    for risk in ("high", "medium", "low"):
        group = by_risk.get(risk, [])
        if not group:
            continue
        lines.append(f"## {risk.upper()} Risk ({len(group)})")
        for c in group:
            context = original_lines[c.line_number - 1] if 1 <= c.line_number <= len(original_lines) else ""
            lines.append(f"### {idx}. Line {c.line_number}")
            lines.append(f"- **From**: `{c.from_text}`")
            lines.append(f"- **To**: `{c.to_text}`")
            lines.append(f"- **Type**: {c.rule_type}")
            lines.append(f"- **Context**: {context}")
            lines.append("")
            idx += 1

    return "\n".join(lines)


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
    """Run the correction workflow.

    Heavy imports (AIProcessor, diff generator) are loaded only when Stage 2/3
    is requested, keeping --stage 1 startup fast.
    """
    from core import AIProcessor, LearningEngine
    from core.defaults import API_BASE_URL
    from utils.diff_generator import generate_full_report

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
    corrections, correction_meta = service.get_corrections_with_metadata(args.domain)
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

    dry_run = getattr(args, 'dry_run', False)
    # Stage 1 defaults to conservative "safe mode": only auto-apply low-risk
    # (non-word, high-confidence) corrections. Medium/high-risk rules — common
    # words, <=2-char, real-word fragments — are tracked to *_needs_review.md for
    # AI/human confirmation rather than applied silently.
    #
    # Why the default flipped: _assess_risk() always classified risk correctly
    # (e.g. 多深→high, 小龙虾→medium), but review_mode defaulting to False meant
    # every level got applied anyway — the guard was computed and then ignored.
    # On a clean transcript from a strong ASR engine, cross-domain dictionary
    # rules are the main false-positive source, so applying only low-risk by
    # default is the safe choice. --apply-all opts back into apply-everything.
    review_mode = not getattr(args, 'apply_all', False)
    changes_file = getattr(args, 'changes_file', False) or review_mode

    # Stage 1: Dictionary corrections
    stage1_changes = []
    stage1_text = original_text
    if args.stage >= 1:
        print("=" * 60)
        print("🔧 Stage 1: Dictionary Corrections")
        if dry_run:
            print("   (DRY RUN — no files will be written)")
        elif review_mode:
            print("   (SAFE MODE [default] — only low-risk auto-applied; medium/high → *_needs_review.md. Pass --apply-all to apply every level.)")
        else:
            print("   (APPLY-ALL — every risk level applied; higher false-positive risk)")
        print("=" * 60)

        processor = DictionaryProcessor(corrections, context_rules, correction_meta)
        stage1_text, stage1_changes = processor.process(original_text, review_mode=review_mode)

        summary = processor.get_summary(stage1_changes)
        risk_counts = {"low": 0, "medium": 0, "high": 0}
        for c in stage1_changes:
            risk_counts[c.risk] = risk_counts.get(c.risk, 0) + 1

        applied_count = sum(1 for c in stage1_changes if c.risk == "low" or not review_mode)
        skipped_count = sum(1 for c in stage1_changes if c.risk in ("medium", "high") and review_mode)

        print(f"✓ Found {summary['total_changes']} corrections")
        print(f"  - Dictionary: {summary['dictionary_changes']}")
        print(f"  - Context rules: {summary['context_rule_changes']}")
        print(f"  - Risk: low={risk_counts['low']}, medium={risk_counts['medium']}, high={risk_counts['high']}")
        if review_mode:
            print(f"  - Applied (low risk): {applied_count}")
            print(f"  - Skipped for review: {skipped_count}")

        if not dry_run:
            stage1_file = output_dir / f"{input_path.stem}_stage1.md"
            with open(stage1_file, 'w', encoding='utf-8') as f:
                f.write(stage1_text)
            print(f"💾 Saved: {stage1_file.name}")

            # Write changes report
            if changes_file:
                changes_report = _format_changes_report(stage1_changes, original_text)
                changes_file_path = output_dir / f"{input_path.stem}_changes.md"
                with open(changes_file_path, 'w', encoding='utf-8') as f:
                    f.write(changes_report)
                print(f"📋 Changes report: {changes_file_path.name}")

            # Write needs-review file
            if review_mode and skipped_count > 0:
                needs_review = [c for c in stage1_changes if c.risk in ("medium", "high")]
                review_report = _format_changes_report(needs_review, original_text, title="Needs Review")
                review_file_path = output_dir / f"{input_path.stem}_needs_review.md"
                with open(review_file_path, 'w', encoding='utf-8') as f:
                    f.write(review_report)
                print(f"🟡 Needs review: {review_file_path.name}")

        else:
            # Dry run: write a changes report so the user can preview. Mark which
            # risk levels a real run would actually apply, so the preview matches
            # the default (safe) run instead of implying every listed change applies.
            mode_note = (" (SAFE MODE — only LOW-risk auto-applied; MEDIUM/HIGH shown for reference)"
                         if review_mode else
                         " (APPLY-ALL — every listed change will be applied)")
            preview_report = _format_changes_report(stage1_changes, original_text, title="Dry Run Preview" + mode_note)
            preview_path = output_dir / f"{input_path.stem}_dryrun.md"
            with open(preview_path, 'w', encoding='utf-8') as f:
                f.write(preview_report)
            print(f"🔍 Dry-run preview: {preview_path.name}")

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
    stage2_file = None
    if args.stage >= 2 and not dry_run:
        print("=" * 60)
        print("🤖 Stage 2: AI Corrections")
        print("=" * 60)

        # Check API key from config directory (canonical source)
        config = get_config()
        api_key = config.api.api_key
        if not api_key:
            print("❌ Error: API key not configured")
            config_dir = config.paths.config_dir
            print(f"   Add it to {config_dir}/config.json under api.api_key,")
            print("   or set GLM_API_KEY or ANTHROPIC_API_KEY environment variable.")
            sys.exit(1)

        ai_processor = AIProcessor(
            api_key,
            base_url=config.api.base_url or API_BASE_URL
        )
        stage2_text, stage2_changes = ai_processor.process(stage1_text)

        print(f"✓ Processed {len(stage2_changes)} chunks\n")

        stage2_file = output_dir / f"{input_path.stem}_stage2.md"
        with open(stage2_file, 'w', encoding='utf-8') as f:
            f.write(stage2_text)
        print(f"💾 Saved: {stage2_file.name}\n")

        # Save history for learning — only the Stage 1 changes that were
        # ACTUALLY applied. In safe mode (review_mode=True) medium/high-risk
        # changes are tracked but not applied, so recording them here would
        # inflate the history count and persist edits that never reached the
        # output. This applied set mirrors the applied_count condition above.
        applied_stage1 = [c for c in stage1_changes if c.risk == "low" or not review_mode]
        service.save_history(
            filename=str(input_path),
            domain=args.domain,
            original_length=len(original_text),
            stage1_changes=len(applied_stage1),
            stage2_changes=len(stage2_changes),
            model=ai_processor.model,
            changes=applied_stage1 + stage2_changes
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
    if args.stage >= 3 and not dry_run:
        print("=" * 60)
        print("📊 Stage 3: Generating Diff Report")
        print("=" * 60)

        if stage2_file is not None and stage2_file.exists():
            try:
                generate_full_report(
                    original_file=str(input_path),
                    stage1_file=str(stage1_file),
                    stage2_file=str(stage2_file),
                    output_dir=str(output_dir),
                    model=ai_processor.model,
                )
            except Exception as e:
                print(f"⚠️  Diff report generation failed: {e}", file=sys.stderr)
        else:
            print("   Skipped: Stage 2 output required for diff report\n")

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
    from utils import validate_configuration, print_validation_summary

    errors, warnings = validate_configuration()
    exit_code = print_validation_summary(errors, warnings)
    if exit_code != 0:
        sys.exit(exit_code)


def cmd_health(args: argparse.Namespace) -> None:
    """
    Perform system health check

    CRITICAL FIX (P1-4): Production-grade health monitoring
    """
    from utils.health_check import HealthChecker, CheckLevel, format_health_output

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
    from utils.metrics import get_metrics, format_metrics_summary

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
    from utils.db_migrations_cli import create_migration_cli

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


def cmd_extract_uncertain(args: argparse.Namespace) -> None:
    """Extract uncertain ASR tokens from a transcript file."""
    from core import UncertainExtractor

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Error: File not found: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output) if args.output else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Extracting uncertain items from: {input_path.name}")
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()

    extractor = UncertainExtractor()
    items = extractor.extract(text)

    from core.uncertain_extractor import format_uncertain_report
    report = format_uncertain_report(items)

    output_path = output_dir / f"{input_path.stem}_uncertain.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"   Found {len(items)} uncertain item(s)")
    print(f"💾 Saved: {output_path.name}")


def cmd_report_false_positive(args: argparse.Namespace) -> None:
    """Report a false-positive correction and disable it."""
    service = _get_service()
    domain = getattr(args, 'domain', None) or "general"
    success = service.report_false_positive(args.from_text, args.to_text, domain)
    if success:
        print(f"🚫 Reported false positive: '{args.from_text}' -> '{args.to_text}' (domain: {domain})")
        print("   The rule has been disabled and confidence lowered.")
    else:
        print(f"❌ No active rule matching '{args.from_text}' -> '{args.to_text}' (domain: {domain})")
        sys.exit(1)


def cmd_load_presets(args: argparse.Namespace) -> None:
    """Load preset correction rules for a domain."""
    service = _get_service()
    domain = args.load_presets
    count = service.load_presets(domain)
    print(f"✅ Loaded {count} preset rule(s) for domain: {domain}")


def get_available_presets() -> list:
    """Return available preset domain names."""
    from data.tech_presets import get_preset_names
    return get_preset_names()
