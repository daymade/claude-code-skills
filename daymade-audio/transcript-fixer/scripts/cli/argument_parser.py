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
        "--add-context-rule",
        nargs=2,
        metavar=("PATTERN", "REPLACEMENT"),
        dest="add_context_rule",
        help="Add a context-aware regex rule (PATTERN is a regex; --domain scopes it, omit for global)"
    )
    parser.add_argument(
        "--list-context-rules",
        action="store_true",
        dest="list_context_rules",
        help="List context rules (--domain filters to one domain plus globals)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all",
        help="With --list-context-rules: include disabled rules"
    )
    parser.add_argument(
        "--description",
        metavar="TEXT",
        default=None,
        help="Human-readable rule name for --add-context-rule"
    )
    parser.add_argument(
        "--priority",
        metavar="N",
        type=int,
        default=0,
        help="Priority for --add-context-rule (higher applies first)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force --add even when safety checks detect risks (common word, substring collision)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_corrections",
        help="List all corrections"
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        dest="audit_dictionary",
        help="Audit all active corrections for false positive risks (common words, short text, substring collisions)"
    )
    parser.add_argument(
        "--export",
        metavar="PATH",
        dest="export_path",
        help="Export corrections to a JSON file"
    )
    parser.add_argument(
        "--import",
        metavar="PATH",
        dest="import_path",
        help="Import corrections from a JSON file"
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        default=False,
        help="Merge imported corrections with existing rules instead of replacing matching entries"
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
        default=None,
        help="Correction domain (default: all domains). Accepts a comma-separated "
             "list (--domain huawei,huawei_lvdian): the rules of every listed domain "
             "load together, --apply-domain trusts all of them, and the FIRST entry "
             "is primary — it wins any cross-domain from_text collision. Write "
             "commands (--add, --approve) still require exactly one domain."
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="(Deprecated no-op — safe mode is the Stage 1 default; accepted but "
             "ignored for backward compatibility, slated for removal)"
    )
    parser.add_argument(
        "--apply-all",
        action="store_true",
        dest="apply_all",
        help="Opt OUT of the default safe mode: auto-apply ALL risk levels (low/medium/high) "
             "instead of only low-risk. Higher false-positive risk — use only when the dictionary "
             "domain matches the transcript and you've reviewed the rules."
    )
    parser.add_argument(
        "--apply-domain",
        action="store_true",
        dest="apply_domain",
        help="Trust the rules of the domain you explicitly passed via --domain: apply them at "
             "every risk level, while keeping safe-mode deferral for everything else (people "
             "roster, context rules). Rationale: rules added under a project domain were "
             "hand-confirmed for exactly this kind of transcript, so domain match = trust. "
             "Narrower than --apply-all; no-op without --domain. Batch workflows go from three "
             "passes (safe -> review sidecar -> --apply-all rerun) to one."
    )
    parser.add_argument(
        "--changes-file",
        action="store_true",
        dest="changes_file",
        help="Write *_changes.md with before/after/risk when a run applies or defers corrections (automatically on in safe mode, which is the default; a 0-change run writes no report)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit a machine-readable Stage 1 status object as the ONLY thing on stdout "
             "(the human-readable log is routed to stderr). Fields: applied, deferred, "
             "output_path, needs_review_path, input_unchanged, review_enqueued, "
             "stage1_only_incomplete, stage2_total_chunks, stage2_failed_chunks, "
             "stage2_degraded, boundary_refused. All eleven status fields are always present. Lets "
             "consumers stop inferring no-op vs failure from whether a *_stage1.md "
             "sidecar exists. Also applies to the review-queue commands "
             "(--enqueue-review/--list-review/--show-review/--resolve-review)."
    )

    # Evidence commands (advisory, read-only): turn the native pass's manual
    # grep loops into single invocations. Neither edits anything.
    parser.add_argument(
        "--scan-traps",
        action="store_true",
        dest="scan_traps",
        help="Scan --input for every trap documented in --context-file (a domain "
             "context markdown): parses each **误识 → 正确** entry (legacy ≈ "
             "accepted; quote exact multi-word variants), locates every "
             "variant with line number + context window, and lists no-hit entries "
             "so 'scanned and absent' is distinguishable from 'never scanned'. "
             "Replaces the manual per-trap grep loop in the native pass's "
             "trap-scan step."
    )
    parser.add_argument(
        "--context-file",
        metavar="PATH",
        dest="context_file",
        help="Domain context markdown for --scan-traps (e.g. "
             "~/.transcript-fixer/contexts/<domain>.md)"
    )
    parser.add_argument(
        "--probe",
        metavar="TERM",
        dest="probe_term",
        help="Measure TERM's real-meaning frequency across --corpus before "
             "deciding a dictionary rule: per-file counts + sampled context "
             "windows, with the verdict criterion attached. Advisory — the "
             "operator reads the samples and decides; the probe never blocks."
    )
    parser.add_argument(
        "--corpus",
        metavar="DIR",
        dest="corpus_dir",
        help="Transcript corpus directory for --probe / --check-corpus "
             "(searched recursively for *.md)"
    )
    parser.add_argument(
        "--check-corpus",
        action="store_true",
        dest="check_corpus",
        help="With --add: probe the FROM term against --corpus BEFORE writing "
             "the rule, so the in-corpus real-meaning frequency is on the "
             "record at decision time. Advisory (never blocks the add)."
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
        help="Approve a learned correction"
    )
    parser.add_argument(
        "--report-false-positive",
        nargs=2,
        metavar=("FROM", "TO"),
        dest="report_false_positive",
        help="Report a Stage 1 false positive to disable/downgrade the rule"
    )

    # Preset commands
    parser.add_argument(
        "--load-presets",
        metavar="DOMAIN",
        dest="load_presets",
        help="Load preset corrections for a domain (e.g. tech)"
    )

    # Uncertain extraction
    parser.add_argument(
        "--extract-uncertain",
        action="store_true",
        dest="extract_uncertain",
        help="Extract likely ASR errors into *_uncertain.md without applying corrections"
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

    # Review queue: persistent store for uncertain corrections awaiting a human
    # verdict (native-pass uncertain items, Stage 1 safe-mode deferrals).
    parser.add_argument(
        "--enqueue-review",
        metavar="JSON_PATH",
        dest="enqueue_review",
        help="Enqueue review items from a JSON file ('-' = stdin). Each item: "
             "{original, suggested?, file?, line?, context?, kind?, domain?, "
             "evidence?, actions?, priority?, source?}"
    )
    parser.add_argument(
        "--list-review",
        action="store_true",
        dest="list_review",
        help="List review-queue items (filter with --review-status/--domain/"
             "--review-source/--review-file)"
    )
    parser.add_argument(
        "--review-status",
        dest="review_status",
        choices=["pending", "accepted", "overridden", "kept_original", "skipped", "all"],
        default="pending",
        help="Status filter for --list-review (default: pending)"
    )
    parser.add_argument(
        "--review-source",
        dest="review_source",
        choices=["native_pass", "stage1_deferred", "learned_suggestion", "manual"],
        help="Source filter for --list-review"
    )
    parser.add_argument(
        "--review-file",
        metavar="FILE",
        dest="review_file",
        help="Exact transcript path for --list-review. Resolves to an absolute "
             "path and scopes both items and status totals to that one file."
    )
    parser.add_argument(
        "--close-sidecars",
        action="store_true",
        dest="close_sidecars",
        help="Decide whether the Stage 1/2 sidecars beside --input are closed (every "
             "*_changes/*_needs_review entry applied or decided, zero pending queue rows "
             "for that exact file) and remove them; --dry-run reports only. "
             "Exit 0 closed, 1 open, 2 blocked"
    )
    parser.add_argument(
        "--decide-raw",
        dest="decide_raw",
        choices=["kept_original", "skipped"],
        help="With --close-sidecars: record this verdict through the review queue for "
             "report entries that still read as the original and have no queue row "
             "(use --by/--note for provenance)"
    )
    parser.add_argument(
        "--discard-unpromoted",
        action="store_true",
        dest="discard_unpromoted",
        help="With --close-sidecars: also remove a *_stage2.md/*_dryrun.md that is newer "
             "than the transcript (unpromoted API/preview output)"
    )
    parser.add_argument(
        "--lookup",
        metavar="TERM",
        dest="lookup_term",
        help="Show every trace of TERM: dictionary rules where it is FROM or TO (active "
             "and disabled), context rules, roster-loaded name variants, review-queue "
             "rows; --domain narrows the dictionary and context-rule sections"
    )
    parser.add_argument(
        "--show-review",
        metavar="ID",
        type=int,
        dest="show_review",
        help="Show one review item in full (evidence + proposed action pack)"
    )
    parser.add_argument(
        "--reanchor-review",
        metavar="ID",
        type=int,
        nargs="+",
        dest="reanchor_review",
        help="Re-anchor pending item(s) whose transcript drifted or moved since "
             "enqueue: refresh line/context verbatim from the current file; when "
             "the file is gone, search --reanchor-root (and the recorded parent "
             "dir) for *.md containing the original text and re-point it"
    )
    parser.add_argument(
        "--reanchor-root",
        metavar="DIR",
        action="append",
        dest="reanchor_root",
        help="Extra search root(s) for --reanchor-review when the file is gone "
             "(repeatable; the recorded parent dir is always searched first)"
    )
    parser.add_argument(
        "--reanchor-to",
        metavar="FILE",
        dest="reanchor_to",
        help="Explicit re-point target for --reanchor-review when content search "
             "is ambiguous (the caller picks the file; refused if the original "
             "text is not in it)"
    )
    parser.add_argument(
        "--resolve-review",
        metavar="ID",
        type=int,
        dest="resolve_review",
        help="Record a verdict for a review item and execute its action pack "
             "(requires --decision)"
    )
    parser.add_argument(
        "--decision",
        dest="review_decision",
        choices=["accepted", "overridden", "kept_original", "skipped", "reopen"],
        help="Verdict for --resolve-review: accepted (apply suggestion, or record it "
             "if a hand edit already put it in place), overridden (apply --override-to "
             "text, or record it if already in place), kept_original (transcript is correct as spoken), skipped (can't "
             "judge, or the utterance is gone), reopen (undo a recorded verdict)"
    )
    parser.add_argument(
        "--override-to",
        dest="review_override_to",
        help="Replacement text when --decision overridden"
    )
    parser.add_argument(
        "--note",
        dest="review_note",
        help="Free-text note recorded with the verdict"
    )
    parser.add_argument(
        "--by",
        dest="review_by",
        help="Reviewer name recorded with the verdict"
    )

    return parser
