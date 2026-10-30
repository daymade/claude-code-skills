#!/usr/bin/env python3
"""
Quality validator for document-to-markdown conversion.

Compare original document with converted markdown to assess conversion quality.
Generates HTML quality report with detailed metrics.

Usage:
    uv run --with pymupdf python scripts/validate_output.py document.pdf output.md
    uv run --with pymupdf python scripts/validate_output.py document.pdf output.md --report report.html
"""

import argparse
import html
import json
from difflib import SequenceMatcher
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ValidationMetrics:
    """Quality metrics for conversion validation."""
    # Text metrics
    source_char_count: int = 0
    output_char_count: int = 0
    text_retention: float = 0.0  # character-count coverage, not accuracy
    text_similarity: float = 0.0
    text_equal: bool = False
    numeric_sequences_equal: Optional[bool] = None
    source_extracted: bool = False
    structure_verified: bool = False
    comparison_scope: str = "Extractable body text; whitespace ignored, punctuation retained"
    differences: list[dict] = field(default_factory=list)

    # Table metrics
    source_table_count: Optional[int] = None
    output_table_count: int = 0
    table_retention: Optional[float] = None

    # Image metrics
    source_image_count: Optional[int] = None
    output_image_count: int = 0
    image_retention: Optional[float] = None

    # Structure metrics
    heading_count: int = 0
    list_count: int = 0
    code_block_count: int = 0

    # Quality scores
    overall_score: Optional[float] = None
    status: str = "unknown"  # pass, warn, fail

    # Details
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def extract_text_from_pdf(pdf_path: Path) -> tuple[str, Optional[int], Optional[int]]:
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
        result = subprocess.run(
            ['pdftotext', '-layout', str(pdf_path), '-'],
            capture_output=True, text=True, timeout=60, check=True,
        )
        return result.stdout, None, None  # unavailable counts are not zero


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

                wordprocessing_ns = 'http' + '://schemas.openxmlformats.org/wordprocessingml/2006/main'
                ns = {'w': wordprocessing_ns}
                # Count tables
                tables = root.findall('.//w:tbl', ns)
                table_count = len(tables)

            # Count images
            image_count = sum(1 for name in z.namelist()
                            if name.startswith('word/media/'))

            # Word stores generated list labels outside w:t. Use the same
            # semantic parser as Markdown so faithful numbered lists compare.
            result = subprocess.run(
                ['pandoc', '-f', 'docx', '-t', 'json', str(docx_path)],
                capture_output=True, text=True, timeout=60, check=True,
            )
            ast = json.loads(result.stdout)
            return body_text(ast.get('blocks', [])), table_count, image_count

    except Exception as exc:
        raise ValueError(f"Cannot extract DOCX: {exc}") from exc


def body_text(node):
    """Flatten Pandoc body text while retaining numeric token boundaries."""
    if isinstance(node, list):
        return ''.join(body_text(child) for child in node)
    if not isinstance(node, dict):
        return ''
    kind, children = node.get('t'), node.get('c')
    if kind == 'Str':
        return children
    if kind in ('Space', 'SoftBreak', 'LineBreak'):
        return ' '
    if kind in ('Code', 'CodeBlock', 'Math'):
        return children[-1] + (' ' if kind == 'CodeBlock' else '')
    if kind == 'Image':
        return ''  # alt captions are not independent source body text
    if kind == 'Link':
        return body_text(children[1])
    if kind == 'OrderedList':
        start = children[0][0]
        return ' '.join(f'{i}. ' + body_text(item) for i, item in
                        enumerate(children[1], start=start)) + ' '
    if kind == 'BulletList':
        return ' '.join(body_text(item) for item in children) + ' '
    if kind in ('RawInline', 'RawBlock'):
        return ''  # raw markup is diagnosed separately below
    if kind == 'Quoted':
        quote = '“' if children[0]['t'] == 'DoubleQuote' else '‘'
        close = '”' if quote == '“' else '’'
        return quote + body_text(children[1]) + close
    text = body_text(children)
    return text + ' ' if kind in ('Para', 'Plain', 'Header') else text


def analyze_markdown(md_path: Path) -> dict:
    """Analyze markdown file structure and content."""
    content = md_path.read_text(encoding="utf-8")

    # A missing parser is an explicit prerequisite failure, never a regex PASS.
    result = subprocess.run(
        ['pandoc', '-f', 'gfm', '-t', 'json'], input=content,
        capture_output=True, text=True, timeout=60, check=True,
    )
    ast = json.loads(result.stdout)

    clean_text = body_text(ast.get('blocks', []))
    counts = {'Table': 0, 'Image': 0, 'Header': 0, 'CodeBlock': 0, 'list_items': 0}
    raw_markup = False

    def count_nodes(node):
        nonlocal raw_markup
        if isinstance(node, list):
            for child in node:
                count_nodes(child)
        elif isinstance(node, dict):
            kind, children = node.get('t'), node.get('c')
            if kind in counts:
                counts[kind] += 1
            if kind in ('RawInline', 'RawBlock'):
                raw_markup |= bool(re.search(r'<(?![!/?])[^>]+>', children[-1]))
            if kind == 'OrderedList':
                counts['list_items'] += len(children[1])
            elif kind == 'BulletList':
                counts['list_items'] += len(children)
            count_nodes(children)

    count_nodes(ast.get('blocks', []))
    return {
        'char_count': len(normalize_text(clean_text)),
        'table_count': counts['Table'],
        'image_count': counts['Image'],
        'heading_count': counts['Header'],
        'list_count': counts['list_items'],
        'code_block_count': counts['CodeBlock'],
        'raw_content': content,
        'clean_text': clean_text,
        'raw_markup': raw_markup,
    }


def normalize_text(text):
    """Ignore layout whitespace only; never delete signs, units or punctuation."""
    return re.sub(r'\s+', '', text)


def numeric_sequences(text):
    """Preserve ordered signed decimals, grouping separators and percentages."""
    return re.findall(r'[-+−]?\d+(?:[,，]\d{3})*(?:[.．]\d+)?[%％]?', text)


def validate_conversion(
    source_path: Path,
    output_path: Path
) -> ValidationMetrics:
    """Validate conversion quality by comparing source and output."""
    metrics = ValidationMetrics()

    try:
        md_analysis = analyze_markdown(output_path)
        ext = source_path.suffix.lower()
        if ext == '.pdf':
            source_text, source_tables, source_images = extract_text_from_pdf(source_path)
        elif ext == '.docx':
            source_text, source_tables, source_images = extract_text_from_docx(source_path)
        else:
            raise ValueError(f"Unsupported source format: {ext}; use PDF or DOCX")
    except Exception as exc:
        metrics.errors.append(f"Comparison unavailable: {exc}")
        metrics.status = 'fail'
        return metrics

    metrics.output_char_count = md_analysis['char_count']
    metrics.output_table_count = md_analysis['table_count']
    metrics.output_image_count = md_analysis['image_count']
    metrics.heading_count = md_analysis['heading_count']
    metrics.list_count = md_analysis['list_count']
    metrics.code_block_count = md_analysis['code_block_count']
    metrics.source_table_count = source_tables
    metrics.source_image_count = source_images
    source = normalize_text(source_text)
    output = normalize_text(md_analysis['clean_text'])
    metrics.source_char_count = len(source)
    if not source:
        metrics.errors.append('No source text extracted; OCR or a scoped source check is required')
        metrics.status = 'fail'
        return metrics
    metrics.source_extracted = True
    metrics.text_retention = min(len(output) / len(source), 1.0)
    metrics.text_equal = source == output
    matcher = SequenceMatcher(None, source, output, autojunk=False)
    metrics.text_similarity = 1.0 if metrics.text_equal else matcher.ratio()
    metrics.numeric_sequences_equal = (
        numeric_sequences(source_text) == numeric_sequences(md_analysis['clean_text'])
    )
    if not metrics.text_equal:
        for tag, i, j, a, b in matcher.get_opcodes():
            if tag != 'equal' and len(metrics.differences) < 10:
                metrics.differences.append({
                    'kind': tag, 'source_offset': i, 'output_offset': a,
                    'source': source[i:j][:80], 'output': output[a:b][:80],
                })
        if metrics.text_similarity < 0.85:
            metrics.errors.append(f'Low ordered text similarity: {metrics.text_similarity:.1%}')
        else:
            metrics.warnings.append('Text differs; inspect bounded difference samples and source scope')
    if not metrics.numeric_sequences_equal:
        metrics.errors.append('Ordered numeric sequences differ; inspect values, signs and units')
    if md_analysis['raw_markup']:
        metrics.warnings.append('Raw HTML may carry visible text; verify it in the actual reader')

    for name, expected, actual, fail_below in (
        ('table', source_tables, metrics.output_table_count, 0.9),
        ('image', source_images, metrics.output_image_count, 0.8),
    ):
        if expected is None:
            metrics.warnings.append(f'Source {name} count unavailable')
            continue
        retention = min(actual / expected, 1.0) if expected else 1.0
        setattr(metrics, name + '_retention', retention)
        if retention < fail_below:
            metrics.errors.append(f'{name.title()} count coverage low: {retention:.1%}')
        elif retention < 1.0:
            metrics.warnings.append(f'{name.title()} count coverage incomplete: {retention:.1%}')

    if metrics.table_retention is not None and metrics.image_retention is not None:
        metrics.overall_score = (
            metrics.text_similarity * 50 + metrics.table_retention * 25 +
            metrics.image_retention * 25
        )  # diagnostic 0–100; never an overall accuracy certification
    metrics.status = 'fail' if metrics.errors else 'warn' if metrics.warnings else 'pass'

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

    def metric_bar(value: Optional[float], thresholds: tuple) -> str:
        """Generate colored progress bar or an explicit unavailable marker."""
        if value is None:
            return '<span>Not measured</span>'
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

    score = f'{metrics.overall_score:.0f}/100' if metrics.overall_score is not None else 'Not measured'
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
            <div class="score">{score}</div>
            <div style="color: #666;">Diagnostic score; not accuracy</div>
            <div class="status" style="background: {status_color}; margin-top: 10px;">
                {metrics.status.upper()}
            </div>
        </div>

        <h2>📄 File Information</h2>
        <table>
            <tr><th>Source</th><td>{html.escape(str(source_path))}</td></tr>
            <tr><th>Output</th><td>{html.escape(str(output_path))}</td></tr>
        </table>

        <p>Mechanical comparison only. Structure, question ownership, warnings,
        image identity and recipient navigation are not certified.</p>
        <p>Text equal (whitespace ignored): {metrics.text_equal};
        ordered similarity: {metrics.text_similarity:.1%};
        numeric sequences equal: {metrics.numeric_sequences_equal}</p>
        <pre>{html.escape(json.dumps(metrics.differences, ensure_ascii=False, indent=2))}</pre>
        <h2>📏 Count Coverage</h2>

        <div class="metric">
            <div class="metric-label">Text character-count coverage (not content equality)</div>
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
            Generated by doc-to-markdown validate_output.py
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
        help="Original PDF or DOCX (extractable text required)"
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
        print(json.dumps(asdict(metrics), ensure_ascii=False, indent=2))
    else:
        # Console output
        status_emoji = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(metrics.status, "❓")
        print(f"\n{status_emoji} Conversion Quality: {metrics.status.upper()}")
        score = f'{metrics.overall_score:.0f}/100' if metrics.overall_score is not None else 'not measured'
        print(f"   Diagnostic score (not accuracy): {score}")
        print(f"   Text equal: {metrics.text_equal}; similarity: {metrics.text_similarity:.1%}")
        print(f"   Numeric sequences equal: {metrics.numeric_sequences_equal}")
        print("   Structure and recipient handoff: not verified")
        print(f"\n   Text character-count coverage: {metrics.text_retention:.1%}")
        for label, value in [('Table', metrics.table_retention), ('Image', metrics.image_retention)]:
            print(f"   {label} count coverage: " + (f'{value:.1%}' if value is not None else 'not measured'))
        for difference in metrics.differences:
            print('   Difference: ' + json.dumps(difference, ensure_ascii=False))

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
        print(f"HTML report: {args.report}", file=sys.stderr if args.json else sys.stdout)

    # Exit with appropriate code
    sys.exit(0 if metrics.status != "fail" else 1)


if __name__ == "__main__":
    main()
