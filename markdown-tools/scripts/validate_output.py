#!/usr/bin/env python3
"""
Quality validator for document-to-markdown conversion.

Compare original document with converted markdown to assess conversion quality.
Generates HTML quality report with detailed metrics.

Usage:
    uv run --with pymupdf scripts/validate_output.py document.pdf output.md
    uv run --with pymupdf scripts/validate_output.py document.pdf output.md --report report.html
"""

import argparse
import html
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ValidationMetrics:
    """Quality metrics for conversion validation."""
    # Text metrics
    source_char_count: int = 0
    output_char_count: int = 0
    text_retention: float = 0.0

    # Table metrics
    source_table_count: int = 0
    output_table_count: int = 0
    table_retention: float = 0.0

    # Image metrics
    source_image_count: int = 0
    output_image_count: int = 0
    image_retention: float = 0.0

    # Structure metrics
    heading_count: int = 0
    list_count: int = 0
    code_block_count: int = 0

    # Quality scores
    overall_score: float = 0.0
    status: str = "unknown"  # pass, warn, fail

    # Details
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def extract_text_from_pdf(pdf_path: Path) -> tuple[str, int, int]:
    """Extract text, table count, and image count from PDF."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        text_parts = []
        table_count = 0
        image_count = 0

        for page in doc:
            text_parts.append(page.get_text())
            # Count images
            image_count += len(page.get_images())
            # Estimate tables (look for grid-like structures)
            # This is approximate - tables are hard to detect in PDFs
            page_text = page.get_text()
            if re.search(r'(\t.*){2,}', page_text) or '│' in page_text:
                table_count += 1

        doc.close()
        return '\n'.join(text_parts), table_count, image_count

    except ImportError:
        # Fallback to pdftotext if available
        try:
            result = subprocess.run(
                ['pdftotext', '-layout', str(pdf_path), '-'],
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.stdout, 0, 0  # Can't count tables/images
        except Exception:
            return "", 0, 0


def extract_text_from_docx(docx_path: Path) -> tuple[str, int, int]:
    """Extract text, table count, and image count from DOCX."""
    try:
        import zipfile
        from xml.etree import ElementTree as ET

        with zipfile.ZipFile(docx_path, 'r') as z:
            # Extract main document text
            if 'word/document.xml' not in z.namelist():
                return "", 0, 0

            with z.open('word/document.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()

                # Extract text
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                text_parts = []
                for t in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                    if t.text:
                        text_parts.append(t.text)

                # Count tables
                tables = root.findall('.//w:tbl', ns)
                table_count = len(tables)

            # Count images
            image_count = sum(1 for name in z.namelist()
                            if name.startswith('word/media/'))

            return ' '.join(text_parts), table_count, image_count

    except Exception as e:
        return "", 0, 0


def analyze_markdown(md_path: Path) -> dict:
    """Analyze markdown file structure and content."""
    content = md_path.read_text()

    # Count tables (markdown tables with |)
    table_lines = [l for l in content.split('\n')
                   if re.match(r'^\s*\|.*\|', l)]
    # Group consecutive table lines
    table_count = 0
    in_table = False
    for line in content.split('\n'):
        if re.match(r'^\s*\|.*\|', line):
            if not in_table:
                table_count += 1
                in_table = True
        else:
            in_table = False

    # Count images
    images = re.findall(r'!\[.*?\]\(.*?\)', content)

    # Count headings
    headings = re.findall(r'^#{1,6}\s+.+$', content, re.MULTILINE)

    # Count lists
    list_items = re.findall(r'^[\s]*[-*+]\s+', content, re.MULTILINE)
    list_items += re.findall(r'^[\s]*\d+\.\s+', content, re.MULTILINE)

    # Count code blocks
    code_blocks = re.findall(r'```', content)

    # Clean text for comparison
    clean_text = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
    clean_text = re.sub(r'!\[.*?\]\(.*?\)', '', clean_text)
    clean_text = re.sub(r'\[.*?\]\(.*?\)', '', clean_text)
    clean_text = re.sub(r'[#*_`|>-]', '', clean_text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    return {
        'char_count': len(clean_text),
        'table_count': table_count,
        'image_count': len(images),
        'heading_count': len(headings),
        'list_count': len(list_items),
        'code_block_count': len(code_blocks) // 2,
        'raw_content': content,
        'clean_text': clean_text
    }


def validate_conversion(
    source_path: Path,
    output_path: Path
) -> ValidationMetrics:
    """Validate conversion quality by comparing source and output."""
    metrics = ValidationMetrics()

    # Analyze output markdown
    md_analysis = analyze_markdown(output_path)
    metrics.output_char_count = md_analysis['char_count']
    metrics.output_table_count = md_analysis['table_count']
    metrics.output_image_count = md_analysis['image_count']
    metrics.heading_count = md_analysis['heading_count']
    metrics.list_count = md_analysis['list_count']
    metrics.code_block_count = md_analysis['code_block_count']

    # Extract source content based on file type
    ext = source_path.suffix.lower()
    if ext == '.pdf':
        source_text, source_tables, source_images = extract_text_from_pdf(source_path)
    elif ext in ['.docx', '.doc']:
        source_text, source_tables, source_images = extract_text_from_docx(source_path)
    else:
        # For other formats, estimate from file size
        source_text = ""
        source_tables = 0
        source_images = 0
        metrics.warnings.append(f"Cannot analyze source format: {ext}")

    metrics.source_char_count = len(source_text.replace(' ', '').replace('\n', ''))
    metrics.source_table_count = source_tables
    metrics.source_image_count = source_images

    # Calculate retention rates
    if metrics.source_char_count > 0:
        # Use ratio of actual/expected, capped at 1.0
        metrics.text_retention = min(
            metrics.output_char_count / metrics.source_char_count,
            1.0
        )
    else:
        metrics.text_retention = 1.0 if metrics.output_char_count > 0 else 0.0

    if metrics.source_table_count > 0:
        metrics.table_retention = min(
            metrics.output_table_count / metrics.source_table_count,
            1.0
        )
    else:
        metrics.table_retention = 1.0  # No tables expected

    if metrics.source_image_count > 0:
        metrics.image_retention = min(
            metrics.output_image_count / metrics.source_image_count,
            1.0
        )
    else:
        metrics.image_retention = 1.0  # No images expected

    # Determine status based on thresholds
    if metrics.text_retention < 0.85:
        metrics.errors.append(f"Low text retention: {metrics.text_retention:.1%}")
    elif metrics.text_retention < 0.95:
        metrics.warnings.append(f"Text retention below optimal: {metrics.text_retention:.1%}")

    if metrics.source_table_count > 0 and metrics.table_retention < 0.9:
        metrics.errors.append(f"Tables missing: {metrics.table_retention:.1%} retained")
    elif metrics.source_table_count > 0 and metrics.table_retention < 1.0:
        metrics.warnings.append(f"Some tables may be incomplete: {metrics.table_retention:.1%}")

    if metrics.source_image_count > 0 and metrics.image_retention < 0.8:
        metrics.errors.append(f"Images missing: {metrics.image_retention:.1%} retained")
    elif metrics.source_image_count > 0 and metrics.image_retention < 1.0:
        metrics.warnings.append(f"Some images missing: {metrics.image_retention:.1%}")

    # Calculate overall score (0-100)
    metrics.overall_score = (
        metrics.text_retention * 50 +
        metrics.table_retention * 25 +
        metrics.image_retention * 25
    ) * 100

    # Determine status
    if metrics.errors:
        metrics.status = "fail"
    elif metrics.warnings:
        metrics.status = "warn"
    else:
        metrics.status = "pass"

    return metrics


def generate_html_report(
    metrics: ValidationMetrics,
    source_path: Path,
    output_path: Path
) -> str:
    """Generate HTML quality report."""
    status_colors = {
        "pass": "#28a745",
        "warn": "#ffc107",
        "fail": "#dc3545"
    }
    status_color = status_colors.get(metrics.status, "#6c757d")

    def metric_bar(value: float, thresholds: tuple) -> str:
        """Generate colored progress bar."""
        pct = int(value * 100)
        if value >= thresholds[0]:
            color = "#28a745"  # green
        elif value >= thresholds[1]:
            color = "#ffc107"  # yellow
        else:
            color = "#dc3545"  # red
        return f'''
        <div style="background: #e9ecef; border-radius: 4px; overflow: hidden; height: 20px;">
            <div style="background: {color}; width: {pct}%; height: 100%; transition: width 0.3s;"></div>
        </div>
        <span style="font-size: 14px; color: #666;">{pct}%</span>
        '''

    report = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Conversion Quality Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #eee; padding-bottom: 15px; }}
        .status {{ display: inline-block; padding: 8px 16px; border-radius: 4px; color: white; font-weight: bold; }}
        .metric {{ margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 4px; }}
        .metric-label {{ font-weight: bold; color: #333; margin-bottom: 8px; }}
        .metric-value {{ font-size: 24px; color: #333; }}
        .issues {{ margin-top: 20px; }}
        .error {{ background: #f8d7da; color: #721c24; padding: 10px; margin: 5px 0; border-radius: 4px; }}
        .warning {{ background: #fff3cd; color: #856404; padding: 10px; margin: 5px 0; border-radius: 4px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; }}
        .score {{ font-size: 48px; font-weight: bold; color: {status_color}; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Conversion Quality Report</h1>

        <div style="text-align: center; margin: 30px 0;">
            <div class="score">{metrics.overall_score:.0f}</div>
            <div style="color: #666;">Overall Score</div>
            <div class="status" style="background: {status_color}; margin-top: 10px;">
                {metrics.status.upper()}
            </div>
        </div>

        <h2>📄 File Information</h2>
        <table>
            <tr><th>Source</th><td>{html.escape(str(source_path))}</td></tr>
            <tr><th>Output</th><td>{html.escape(str(output_path))}</td></tr>
        </table>

        <h2>📏 Retention Metrics</h2>

        <div class="metric">
            <div class="metric-label">Text Retention (target: >95%)</div>
            {metric_bar(metrics.text_retention, (0.95, 0.85))}
            <div style="font-size: 12px; color: #666; margin-top: 5px;">
                Source: ~{metrics.source_char_count:,} chars | Output: {metrics.output_char_count:,} chars
            </div>
        </div>

        <div class="metric">
            <div class="metric-label">Table Retention (target: 100%)</div>
            {metric_bar(metrics.table_retention, (1.0, 0.9))}
            <div style="font-size: 12px; color: #666; margin-top: 5px;">
                Source: {metrics.source_table_count} tables | Output: {metrics.output_table_count} tables
            </div>
        </div>

        <div class="metric">
            <div class="metric-label">Image Retention (target: 100%)</div>
            {metric_bar(metrics.image_retention, (1.0, 0.8))}
            <div style="font-size: 12px; color: #666; margin-top: 5px;">
                Source: {metrics.source_image_count} images | Output: {metrics.output_image_count} images
            </div>
        </div>

        <h2>📊 Structure Analysis</h2>
        <table>
            <tr><th>Headings</th><td>{metrics.heading_count}</td></tr>
            <tr><th>List Items</th><td>{metrics.list_count}</td></tr>
            <tr><th>Code Blocks</th><td>{metrics.code_block_count}</td></tr>
        </table>

        {'<h2>⚠️ Issues</h2><div class="issues">' + ''.join(f'<div class="error">❌ {html.escape(e)}</div>' for e in metrics.errors) + ''.join(f'<div class="warning">⚠️ {html.escape(w)}</div>' for w in metrics.warnings) + '</div>' if metrics.errors or metrics.warnings else ''}

        <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; color: #666; font-size: 12px;">
            Generated by markdown-tools validate_output.py
        </div>
    </div>
</body>
</html>
'''
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Validate document-to-markdown conversion quality"
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Original document (PDF, DOCX, etc.)"
    )
    parser.add_argument(
        "output",
        type=Path,
        help="Converted markdown file"
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Generate HTML report at this path"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output metrics as JSON"
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.source.exists():
        print(f"Error: Source file not found: {args.source}", file=sys.stderr)
        sys.exit(1)
    if not args.output.exists():
        print(f"Error: Output file not found: {args.output}", file=sys.stderr)
        sys.exit(1)

    # Run validation
    metrics = validate_conversion(args.source, args.output)

    # Output results
    if args.json:
        import json
        print(json.dumps({
            'text_retention': metrics.text_retention,
            'table_retention': metrics.table_retention,
            'image_retention': metrics.image_retention,
            'overall_score': metrics.overall_score,
            'status': metrics.status,
            'warnings': metrics.warnings,
            'errors': metrics.errors
        }, indent=2))
    else:
        # Console output
        status_emoji = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(metrics.status, "❓")
        print(f"\n{status_emoji} Conversion Quality: {metrics.status.upper()}")
        print(f"   Overall Score: {metrics.overall_score:.0f}/100")
        print(f"\n   Text Retention:  {metrics.text_retention:.1%}")
        print(f"   Table Retention: {metrics.table_retention:.1%}")
        print(f"   Image Retention: {metrics.image_retention:.1%}")

        if metrics.errors:
            print("\n   Errors:")
            for e in metrics.errors:
                print(f"     ❌ {e}")

        if metrics.warnings:
            print("\n   Warnings:")
            for w in metrics.warnings:
                print(f"     ⚠️ {w}")

    # Generate HTML report
    if args.report:
        report_html = generate_html_report(metrics, args.source, args.output)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report_html)
        print(f"\n📊 HTML report: {args.report}")

    # Exit with appropriate code
    sys.exit(0 if metrics.status != "fail" else 1)


if __name__ == "__main__":
    main()
