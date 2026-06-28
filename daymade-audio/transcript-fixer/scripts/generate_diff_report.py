#!/usr/bin/env python3
"""
Generate a full multi-format diff report for transcript corrections.

This is a thin CLI wrapper around utils.diff_generator.generate_full_report,
which coordinates four output formats:
    - Markdown summary report
    - Unified diff
    - HTML side-by-side comparison
    - Inline marked comparison

The internal diff generator is kept as a library module; this script makes it
directly executable via `uv run scripts/generate_diff_report.py`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.defaults import DEFAULT_MODEL
from utils.diff_generator import generate_full_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a multi-format comparison report for transcript corrections."
    )
    parser.add_argument(
        "original_file",
        help="Path to the original transcript file.",
    )
    parser.add_argument(
        "stage1_file",
        help="Path to the Stage 1 (dictionary) corrected file.",
    )
    parser.add_argument(
        "stage2_file",
        help="Path to the Stage 2 (AI) corrected file.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        dest="output_dir",
        default=None,
        help="Directory for output files (defaults to the original file's directory).",
    )
    parser.add_argument(
        "--model",
        dest="model",
        default=DEFAULT_MODEL,
        help=f"Model name to display in the Markdown report (default: {DEFAULT_MODEL}).",
    )

    args = parser.parse_args()

    for path in (args.original_file, args.stage1_file, args.stage2_file):
        if not Path(path).is_file():
            print(f"❌ File not found: {path}", file=sys.stderr)
            return 1

    generate_full_report(
        args.original_file,
        args.stage1_file,
        args.stage2_file,
        output_dir=args.output_dir,
        model=args.model,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
