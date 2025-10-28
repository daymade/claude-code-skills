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
    create_argument_parser,
)


def main():
    """Main entry point - parse arguments and dispatch to commands"""
    parser = create_argument_parser()
    args = parser.parse_args()

    # Dispatch commands
    if args.init:
        cmd_init(args)
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
