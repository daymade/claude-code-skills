#!/usr/bin/env python3
"""
Generate Word-Level Diff HTML Comparison

Creates an HTML file showing word-by-word differences between original and corrected transcripts.
This helps users review corrections more easily than character-level or line-level diffs.

Usage:
    python scripts/generate_word_diff.py <original_file> <corrected_file> [output_file]

Example:
    python scripts/generate_word_diff.py original.md corrected.md comparison.html
"""

import difflib
import html
import re
import sys
from pathlib import Path


def tokenize(text):
    """
    Split text into tokens (words) while preserving Chinese, English, numbers, and punctuation.

    Pattern explanation:
    - [\\u4e00-\\u9fff]+  : Chinese characters (one or more)
    - [a-zA-Z0-9]+        : English words and numbers (one or more)
    - [^\\u4e00-\\u9fffa-zA-Z0-9\\s] : Single punctuation/special chars
    - \\s+                : Whitespace sequences

    Returns:
        List of token strings
    """
    pattern = r'[\u4e00-\u9fff]+|[a-zA-Z0-9]+|[^\u4e00-\u9fffa-zA-Z0-9\s]|\s+'
    return re.findall(pattern, text)


def get_word_diff(old, new):
    """
    Generate word-level diff with HTML highlighting.

    Args:
        old: Original text line
        new: Corrected text line

    Returns:
        HTML string with word-level diff highlighting
    """
    old_tokens = tokenize(old)
    new_tokens = tokenize(new)

    s = difflib.SequenceMatcher(None, old_tokens, new_tokens)
    result = []

    for tag, i1, i2, j1, j2 in s.get_opcodes():
        old_part = ''.join(old_tokens[i1:i2])
        new_part = ''.join(new_tokens[j1:j2])

        if tag == 'equal':
            result.append(html.escape(old_part))
        elif tag == 'delete':
            result.append(f'<del class="word-del" title="删除: {html.escape(old_part)}">{html.escape(old_part)}</del>')
        elif tag == 'insert':
            result.append(f'<ins class="word-ins" title="添加: {html.escape(new_part)}">{html.escape(new_part)}</ins>')
        elif tag == 'replace':
            result.append(f'<span class="word-change"><del class="word-del" title="原文">{html.escape(old_part)}</del> → <ins class="word-ins" title="修正后">{html.escape(new_part)}</ins></span>')

    return ''.join(result)


def generate_html_header(total_lines, total_changes):
    """Generate HTML header with statistics and styling."""
    change_rate = total_changes / total_lines * 100 if total_lines > 0 else 0

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>录音转写修正对比（词语级别）</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            font-size: 16px;
            line-height: 2;
            max-width: 1400px;
            margin: 20px auto;
            padding: 20px;
            background: #f8f9fa;
        }}
        h1 {{
            color: #1a1a1a;
            border-bottom: 3px solid #007aff;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }}
        .summary {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 25px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .summary h2 {{
            margin: 0 0 15px 0;
            color: #007aff;
            font-size: 18px;
        }}
        .stat {{
            display: inline-block;
            margin-right: 25px;
            padding: 8px 15px;
            background: #f0f0f0;
            border-radius: 5px;
            font-weight: 500;
        }}
        .legend {{
            background: #fff9e6;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #ffc107;
        }}
        .legend-item {{
            display: inline-block;
            margin-right: 20px;
            margin-bottom: 5px;
        }}
        .diff-container {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .diff-line {{
            padding: 12px 15px;
            margin: 10px 0;
            border-left: 4px solid transparent;
            border-radius: 4px;
            background: #fafafa;
        }}
        .diff-line.changed {{
            background: #fff;
            border-left-color: #ff9800;
        }}
        .diff-line.unchanged {{
            opacity: 0.5;
            font-size: 14px;
        }}
        del.word-del {{
            background-color: #ffcdd2;
            color: #c62828;
            text-decoration: line-through;
            padding: 3px 6px;
            border-radius: 4px;
            font-weight: 700;
            margin: 0 2px;
        }}
        ins.word-ins {{
            background-color: #c8e6c9;
            color: #2e7d32;
            text-decoration: none;
            padding: 3px 6px;
            border-radius: 4px;
            font-weight: 700;
            margin: 0 2px;
        }}
        .word-change {{
            display: inline-block;
            background: #fff3e0;
            padding: 4px 8px;
            border-radius: 4px;
            margin: 0 2px;
        }}
        .line-number {{
            display: inline-block;
            min-width: 60px;
            color: #999;
            font-size: 13px;
            margin-right: 15px;
            user-select: none;
            font-family: 'SF Mono', 'Monaco', monospace;
        }}
    </style>
</head>
<body>
    <h1>🎙️ 录音转写修正对比（词语级别）</h1>

    <div class="summary">
        <h2>📊 修正统计</h2>
        <span class="stat">总行数: <strong>{total_lines}</strong></span>
        <span class="stat" style="color: #ff9800;">修改行数: <strong>{total_changes}</strong></span>
        <span class="stat" style="color: #4caf50;">修改率: <strong>{change_rate:.1f}%</strong></span>
    </div>

    <div class="legend">
        <strong>📖 图例说明：</strong><br>
        <span class="legend-item"><del class="word-del">删除的词</del> 原文中的错误</span>
        <span class="legend-item"><ins class="word-ins">添加的词</ins> 修正后的内容</span>
        <span class="legend-item"><span class="word-change"><del class="word-del">错误</del> → <ins class="word-ins">正确</ins></span> 词语替换</span>
    </div>

    <div class="diff-container">
'''


def generate_diff_content(original_lines, corrected_lines, context_lines=1):
    """
    Generate diff content HTML showing changed lines with context.

    Args:
        original_lines: List of original text lines
        corrected_lines: List of corrected text lines
        context_lines: Number of context lines to show around changes

    Returns:
        HTML string with diff content
    """
    html_parts = []
    last_change_idx = -999

    for i, (old_line, new_line) in enumerate(zip(original_lines, corrected_lines), 1):
        old_line = old_line.rstrip('\n')
        new_line = new_line.rstrip('\n')

        if old_line.strip() != new_line.strip():
            # Show separator if gap is large
            if i - last_change_idx > context_lines + 1:
                if last_change_idx > 0:
                    html_parts.append('<div style="text-align: center; color: #999; margin: 20px 0; font-size: 18px;">⋯ ⋯ ⋯</div>\n')

            # Show changed line
            diff_html = get_word_diff(old_line, new_line)
            html_parts.append(f'<div class="diff-line changed"><span class="line-number">第 {i} 行</span>{diff_html}</div>\n')
            last_change_idx = i
        elif abs(i - last_change_idx) <= context_lines and last_change_idx > 0:
            # Show context line
            escaped = html.escape(old_line)
            html_parts.append(f'<div class="diff-line unchanged"><span class="line-number">第 {i} 行</span>{escaped}</div>\n')

    return ''.join(html_parts)


def generate_html_footer():
    """Generate HTML footer."""
    return '''
    </div>
</body>
</html>
'''


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 3:
        print("Usage: python generate_word_diff.py <original_file> <corrected_file> [output_file]")
        print("\nExample:")
        print("  python generate_word_diff.py original.md corrected.md comparison.html")
        sys.exit(1)

    original_path = Path(sys.argv[1])
    corrected_path = Path(sys.argv[2])

    # Determine output path
    if len(sys.argv) >= 4:
        output_path = Path(sys.argv[3])
    else:
        # Default: save next to original file with _对比_词语级.html suffix
        output_path = original_path.parent / f"{original_path.stem}_对比_词语级.html"

    # Validate input files
    if not original_path.exists():
        print(f"❌ Error: Original file not found: {original_path}")
        sys.exit(1)

    if not corrected_path.exists():
        print(f"❌ Error: Corrected file not found: {corrected_path}")
        sys.exit(1)

    # Read files
    try:
        with open(original_path, 'r', encoding='utf-8') as f:
            original_lines = f.readlines()

        with open(corrected_path, 'r', encoding='utf-8') as f:
            corrected_lines = f.readlines()
    except Exception as e:
        print(f"❌ Error reading files: {e}")
        sys.exit(1)

    # Count changes
    total_changes = sum(1 for old, new in zip(original_lines, corrected_lines)
                       if old.strip() != new.strip())

    # Generate HTML
    html_content = generate_html_header(len(original_lines), total_changes)
    html_content += generate_diff_content(original_lines, corrected_lines)
    html_content += generate_html_footer()

    # Write output
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"✅ 词语级 diff HTML 已生成: {output_path}")
        print(f"📊 共修改了 {total_changes} 行，占总行数的 {total_changes/len(original_lines)*100:.1f}%")

        return 0
    except Exception as e:
        print(f"❌ Error writing output file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
