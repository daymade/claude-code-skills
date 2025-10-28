#!/usr/bin/env python3
"""
Change extraction and summarization

SINGLE RESPONSIBILITY: Extract and summarize changes between text versions
"""

from __future__ import annotations

import difflib

from .text_splitter import split_into_words


def extract_changes(original: str, fixed: str) -> list[dict]:
    """
    Extract all changes and return change list

    Args:
        original: Original text
        fixed: Fixed text

    Returns:
        List of change dictionaries with type, context, and content
    """
    original_words = split_into_words(original)
    fixed_words = split_into_words(fixed)

    diff = difflib.SequenceMatcher(None, original_words, fixed_words)
    changes = []

    for tag, i1, i2, j1, j2 in diff.get_opcodes():
        if tag == 'replace':
            original_text = ''.join(original_words[i1:i2])
            fixed_text = ''.join(fixed_words[j1:j2])
            changes.append({
                'type': 'replace',
                'original': original_text,
                'fixed': fixed_text,
                'context_before': ''.join(original_words[max(0, i1-5):i1]),
                'context_after': ''.join(original_words[i2:min(len(original_words), i2+5)])
            })
        elif tag == 'delete':
            original_text = ''.join(original_words[i1:i2])
            changes.append({
                'type': 'delete',
                'original': original_text,
                'fixed': '',
                'context_before': ''.join(original_words[max(0, i1-5):i1]),
                'context_after': ''.join(original_words[i2:min(len(original_words), i2+5)])
            })
        elif tag == 'insert':
            fixed_text = ''.join(fixed_words[j1:j2])
            changes.append({
                'type': 'insert',
                'original': '',
                'fixed': fixed_text,
                'context_before': ''.join(fixed_words[max(0, j1-5):j1]) if j1 > 0 else '',
                'context_after': ''.join(fixed_words[j2:min(len(fixed_words), j2+5)])
            })

    return changes


def generate_change_summary(changes: list[dict]) -> str:
    """
    Generate change summary

    Args:
        changes: List of change dictionaries

    Returns:
        Formatted summary string
    """
    result = []
    result.append("=" * 80)
    result.append(f"修改摘要 (共 {len(changes)} 处修改)")
    result.append("=" * 80)
    result.append("")

    for i, change in enumerate(changes, 1):
        change_type = {
            'replace': '替换',
            'delete': '删除',
            'insert': '添加'
        }[change['type']]

        result.append(f"[{i}] {change_type}")

        if change['original']:
            result.append(f"  原文: {change['original']}")
        if change['fixed']:
            result.append(f"  修复: {change['fixed']}")

        # Show context
        context = change['context_before'] + "【修改处】" + change['context_after']
        if context.strip():
            result.append(f"  上下文: ...{context}...")

        result.append("")

    return '\n'.join(result)
