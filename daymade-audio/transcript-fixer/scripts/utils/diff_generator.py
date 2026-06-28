#!/usr/bin/env python3
"""
Generate word-level correction comparison reports
Orchestrates multiple diff formats for visualization

This module is designed to be imported. To run it from the command line, use
the wrapper script at scripts/generate_diff_report.py:

    uv run scripts/generate_diff_report.py <orig> <stage1> <stage2> [-o <dir>]

SINGLE RESPONSIBILITY: Coordinate diff generation workflow
"""

from __future__ import annotations

from pathlib import Path

from core.defaults import DEFAULT_MODEL
from .diff_formats import (
    generate_unified_diff,
    generate_html_diff,
    generate_inline_diff,
    generate_markdown_report,
)
from .diff_formats.text_splitter import read_file


def generate_full_report(
    original_file: str,
    stage1_file: str,
    stage2_file: str,
    output_dir: str = None,
    model: str = DEFAULT_MODEL,
):
    """
    Generate comprehensive comparison report

    Creates 4 output files:
        1. Markdown format detailed report
        2. Unified diff format
        3. HTML side-by-side comparison
        4. Inline marked comparison

    Args:
        original_file: Path to original transcript
        stage1_file: Path to stage 1 (dictionary) corrected version
        stage2_file: Path to stage 2 (AI) corrected version
        output_dir: Optional output directory (defaults to original file location)
        model: Model name to display in the Markdown report (defaults to DEFAULT_MODEL)
    """
    original_path = Path(original_file)
    stage1_path = Path(stage1_file)
    stage2_path = Path(stage2_file)

    # Determine output directory
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = original_path.parent

    base_name = original_path.stem

    # Read files
    print(f"📖 读取文件...")
    original = read_file(original_file)
    stage1 = read_file(stage1_file)
    stage2 = read_file(stage2_file)

    # Generate reports
    print(f"📝 生成对比报告...")

    # 1. Markdown report
    print(f"   生成Markdown报告...")
    md_report = generate_markdown_report(
        original_file, stage1_file, stage2_file,
        original, stage1, stage2,
        model=model,
    )
    md_file = output_path / f"{base_name}_对比报告.md"
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(md_report)
    print(f"   ✓ Markdown报告: {md_file.name}")

    # 2. Unified Diff
    print(f"   生成Unified Diff...")
    unified_diff = generate_unified_diff(original, stage2)
    diff_file = output_path / f"{base_name}_unified.diff"
    with open(diff_file, 'w', encoding='utf-8') as f:
        f.write(unified_diff)
    print(f"   ✓ Unified Diff: {diff_file.name}")

    # 3. HTML comparison
    print(f"   生成HTML对比...")
    html_diff = generate_html_diff(original, stage2)
    html_file = output_path / f"{base_name}_对比.html"
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_diff)
    print(f"   ✓ HTML对比: {html_file.name}")

    # 4. Inline diff
    print(f"   生成行内diff...")
    inline_diff = generate_inline_diff(original, stage2)
    inline_file = output_path / f"{base_name}_行内对比.txt"
    with open(inline_file, 'w', encoding='utf-8') as f:
        f.write(inline_diff)
    print(f"   ✓ 行内对比: {inline_file.name}")

    # Summary
    print(f"\n✅ 对比报告生成完成!")
    print(f"📂 输出目录: {output_path}")
    print(f"\n生成的文件:")
    print(f"   1. {md_file.name} - Markdown格式详细报告")
    print(f"   2. {diff_file.name} - Unified Diff格式")
    print(f"   3. {html_file.name} - HTML并排对比")
    print(f"   4. {inline_file.name} - 行内标记对比")
