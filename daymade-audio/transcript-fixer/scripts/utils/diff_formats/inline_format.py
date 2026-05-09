#!/usr/bin/env python3
"""
Inline diff format generator

SINGLE RESPONSIBILITY: Generate inline diff with change markers
"""

from __future__ import annotations

import difflib

from .text_splitter import split_into_words


def generate_inline_diff(original: str, fixed: str) -> str:
    """
    Generate inline diff marking deletions and additions

    Format:
        - Normal words: unchanged
        - Deletions: [-word-]
        - Additions: [+word+]

    Args:
        original: Original text
        fixed: Fixed text

    Returns:
        Inline diff string with markers
    """
    original_words = split_into_words(original)
    fixed_words = split_into_words(fixed)

    diff = difflib.ndiff(original_words, fixed_words)

    result = []
    result.append("=" * 80)
    result.append("行内词语级别对比 (- 删除, + 添加, ? 修改标记)")
    result.append("=" * 80)
    result.append("")

    current_line = []
    for item in diff:
        marker = item[0]
        word = item[2:]

        if marker == ' ':
            current_line.append(word)
        elif marker == '-':
            current_line.append(f"[-{word}-]")
        elif marker == '+':
            current_line.append(f"[+{word}+]")
        elif marker == '?':
            # Skip change marker lines
            continue

        # Wrap at 80 characters
        if len(''.join(current_line)) > 80:
            result.append(''.join(current_line))
            current_line = []

    if current_line:
        result.append(''.join(current_line))

    return '\n'.join(result)
