#!/usr/bin/env python3
"""
Text splitter utility for word-level diff generation

SINGLE RESPONSIBILITY: Split text into words while preserving structure
"""

from __future__ import annotations

import re


def split_into_words(text: str) -> list[str]:
    """
    Split text into words, preserving whitespace and punctuation

    This enables word-level diff generation for Chinese and English text

    Args:
        text: Input text to split

    Returns:
        List of word tokens (Chinese words, English words, numbers, punctuation)
    """
    # Pattern: Chinese chars, English words, numbers, non-alphanumeric chars
    pattern = r'[\u4e00-\u9fff]+|[a-zA-Z]+|[0-9]+|[^\u4e00-\u9fffa-zA-Z0-9]'
    return re.findall(pattern, text)


def read_file(file_path: str) -> str:
    """Read file contents"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()
