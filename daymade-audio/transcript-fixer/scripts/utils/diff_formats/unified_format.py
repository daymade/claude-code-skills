#!/usr/bin/env python3
"""
Unified diff format generator

SINGLE RESPONSIBILITY: Generate unified diff format output
"""

from __future__ import annotations

import difflib

from .text_splitter import split_into_words


def generate_unified_diff(
    original: str,
    fixed: str,
    original_label: str = "原始版本",
    fixed_label: str = "修复版本"
) -> str:
    """
    Generate unified format diff report

    Args:
        original: Original text
        fixed: Fixed text
        original_label: Label for original version
        fixed_label: Label for fixed version

    Returns:
        Unified diff format string
    """
    original_words = split_into_words(original)
    fixed_words = split_into_words(fixed)

    diff = difflib.unified_diff(
        original_words,
        fixed_words,
        fromfile=original_label,
        tofile=fixed_label,
        lineterm=''
    )

    return '\n'.join(diff)
