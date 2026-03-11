#!/usr/bin/env python3
"""
Markdown to PDF converter with Chinese font support.

Converts markdown files to PDF using pandoc (markdown→HTML) + weasyprint (HTML→PDF).
Designed for formal documents (trademark filings, legal documents, reports).

Usage:
    python md_to_pdf.py input.md output.pdf
    python md_to_pdf.py input.md  # outputs input.pdf

Requirements:
    pip install weasyprint
    pandoc (system install, e.g. brew install pandoc)

    macOS environment setup (if needed):
    export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"
"""

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Auto-configure library path on macOS ARM (Homebrew) — must be before weasyprint import
if platform.system() == 'Darwin':
    _homebrew_lib = '/opt/homebrew/lib'
    if Path(_homebrew_lib).is_dir():
        _cur = os.environ.get('DYLD_LIBRARY_PATH', '')
        if _homebrew_lib not in _cur:
            os.environ['DYLD_LIBRARY_PATH'] = f"{_homebrew_lib}:{_cur}" if _cur else _homebrew_lib

from weasyprint import CSS, HTML


# CSS with Chinese font support
CSS_STYLES = """
@page {
    size: A4;
    margin: 2.5cm 2cm;
}

body {
    font-family: 'Songti SC', 'SimSun', 'STSong', 'Noto Serif CJK SC', serif;
    font-size: 12pt;
    line-height: 1.8;
    color: #000;
    width: 100%;
}

h1 {
    font-family: 'Heiti SC', 'SimHei', 'STHeiti', 'Noto Sans CJK SC', sans-serif;
    font-size: 18pt;
    font-weight: bold;
    text-align: center;
    margin-top: 0;
    margin-bottom: 1.5em;
}

h2 {
    font-family: 'Heiti SC', 'SimHei', 'STHeiti', 'Noto Sans CJK SC', sans-serif;
    font-size: 14pt;
    font-weight: bold;
    margin-top: 1.5em;
    margin-bottom: 0.8em;
}

h3 {
    font-family: 'Heiti SC', 'SimHei', 'STHeiti', 'Noto Sans CJK SC', sans-serif;
    font-size: 12pt;
    font-weight: bold;
    margin-top: 1em;
    margin-bottom: 0.5em;
}

p {
    margin: 0.8em 0;
    text-align: justify;
}

ul, ol {
    margin: 0.8em 0;
    padding-left: 2em;
}

li {
    margin: 0.4em 0;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: 10pt;
    table-layout: fixed;
}

th, td {
    border: 1px solid #666;
    padding: 8px 6px;
    text-align: left;
    overflow-wrap: break-word;
    word-break: normal;
}

th {
    background-color: #f0f0f0;
    font-weight: bold;
}

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 1.5em 0;
}

strong {
    font-weight: bold;
}

code {
    font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
    font-size: 10pt;
    background-color: #f5f5f5;
    padding: 0.2em 0.4em;
    border-radius: 3px;
}

pre {
    background-color: #f5f5f5;
    padding: 1em;
    overflow-x: auto;
    font-size: 10pt;
    line-height: 1.4;
    border-radius: 4px;
}

blockquote {
    border-left: 3px solid #ccc;
    margin: 1em 0;
    padding-left: 1em;
    color: #555;
}
"""


def _ensure_list_spacing(text: str) -> str:
    """Ensure blank lines before list items for proper markdown parsing.

    Both Python markdown library and pandoc require a blank line before a list
    when it follows a paragraph. Without it, list items render as plain text.

    This preprocessor adds blank lines before list items when needed, without
    modifying the user's original markdown file.
    """
    lines = text.split('\n')
    result = []
    list_re = re.compile(r'^(\s*)([-*+]|\d+\.)\s')
    for i, line in enumerate(lines):
        if i > 0 and list_re.match(line):
            prev = lines[i - 1]
            if prev.strip() and not list_re.match(prev):
                result.append('')
        result.append(line)
    return '\n'.join(result)


def _md_to_html(md_file: str) -> str:
    """Convert markdown to HTML using pandoc with list spacing preprocessing.

    Reads the markdown file, preprocesses it to ensure proper list spacing,
    then passes the content to pandoc via stdin. The original file is not modified.
    """
    if not shutil.which('pandoc'):
        print("Error: pandoc not found. Install with: brew install pandoc", file=sys.stderr)
        sys.exit(1)

    # Read and preprocess markdown to ensure list spacing
    md_content = Path(md_file).read_text(encoding='utf-8')
    md_content = _ensure_list_spacing(md_content)

    result = subprocess.run(
        ['pandoc', '-f', 'markdown', '-t', 'html'],
        input=md_content, capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Error: pandoc failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    return result.stdout


def markdown_to_pdf(md_file: str, pdf_file: str | None = None) -> str:
    """
    Convert markdown file to PDF with Chinese font support.

    Args:
        md_file: Path to input markdown file
        pdf_file: Path to output PDF file (optional, defaults to same name as input)

    Returns:
        Path to generated PDF file
    """
    md_path = Path(md_file)

    if pdf_file is None:
        pdf_file = str(md_path.with_suffix('.pdf'))

    # Convert to HTML via pandoc
    html_content = _md_to_html(md_file)

    # Create full HTML document
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{md_path.stem}</title>
</head>
<body>
{html_content}
</body>
</html>"""

    # Generate PDF
    HTML(string=full_html).write_pdf(pdf_file, stylesheets=[CSS(string=CSS_STYLES)])

    return pdf_file


def main():
    if len(sys.argv) < 2:
        print("Usage: python md_to_pdf.py <input.md> [output.pdf]")
        print("\nConverts markdown to PDF with Chinese font support.")
        sys.exit(1)

    md_file = sys.argv[1]
    pdf_file = sys.argv[2] if len(sys.argv) > 2 else None

    if not Path(md_file).exists():
        print(f"Error: File not found: {md_file}")
        sys.exit(1)

    output = markdown_to_pdf(md_file, pdf_file)
    print(f"Generated: {output}")


if __name__ == "__main__":
    main()
