#!/usr/bin/env python3
"""
CLI Commands - Command Handler Functions

SINGLE RESPONSIBILITY: Handle CLI command execution

All cmd_* functions take parsed args and execute the requested operation.
"""

from __future__ import annotations

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


def _get_service():
    """Get configured CorrectionService instance."""
    config_dir = Path.home() / ".transcript-fixer"
    db_path = config_dir / "corrections.db"
    repository = CorrectionRepository(db_path)
    return CorrectionService(repository)


def cmd_init(args):
    """Initialize ~/.transcript-fixer/ directory"""
    service = _get_service()
    service.initialize()


def cmd_add_correction(args):
    """Add a single correction"""
    service = _get_service()
    try:
        service.add_correction(args.from_text, args.to_text, args.domain)
        print(f"✅ Added: '{args.from_text}' → '{args.to_text}' (domain: {args.domain})")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


def cmd_list_corrections(args):
    """List all corrections"""
    service = _get_service()
    corrections = service.get_corrections(args.domain)

    print(f"\n📋 Corrections (domain: {args.domain})")
    print("=" * 60)
    for wrong, correct in sorted(corrections.items()):
        print(f"  '{wrong}' → '{correct}'")
    print(f"\nTotal: {len(corrections)} corrections\n")


def cmd_run_correction(args):
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

    # Read input file
    print(f"📖 Reading: {input_path.name}")
    with open(input_path, 'r', encoding='utf-8') as f:
        original_text = f.read()
    print(f"   File size: {len(original_text):,} characters\n")

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
        print(f"💾 Saved: {stage1_file.name}\n")

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

        # TODO: Run learning engine
        # learning = LearningEngine(...)
        # suggestions = learning.analyze_and_suggest()
        # if suggestions:
        #     print(f"🎓 Learning: Found {len(suggestions)} new correction suggestions")
        #     print(f"   Run --review-learned to review them\n")

    # Stage 3: Generate diff report
    if args.stage >= 3:
        print("=" * 60)
        print("📊 Stage 3: Generating Diff Report")
        print("=" * 60)
        print("   Use diff_generator.py to create visual comparison\n")

    print("✅ Correction complete!")


def cmd_review_learned(args):
    """Review learned suggestions"""
    # TODO: Implement learning engine with SQLite backend
    print("⚠️  Learning engine not yet implemented with SQLite backend")
    print("   This feature will be added in a future update")


def cmd_approve(args):
    """Approve a learned suggestion"""
    # TODO: Implement learning engine with SQLite backend
    print("⚠️  Learning engine not yet implemented with SQLite backend")
    print("   This feature will be added in a future update")


def cmd_validate(args):
    """Validate configuration and JSON files"""
    errors, warnings = validate_configuration()
    exit_code = print_validation_summary(errors, warnings)
    if exit_code != 0:
        sys.exit(exit_code)
