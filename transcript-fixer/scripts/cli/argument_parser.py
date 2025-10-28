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

    return parser
