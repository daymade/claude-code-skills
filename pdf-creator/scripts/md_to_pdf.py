#!/usr/bin/env python3
"""
Markdown to PDF converter with Chinese font support and theme system.

Converts markdown files to PDF using:
  - pandoc (markdown → HTML)
  - weasyprint or headless Chrome (HTML → PDF), auto-detected

Usage:
    python md_to_pdf.py input.md output.pdf
    python md_to_pdf.py input.md --theme warm-terra
    python md_to_pdf.py input.md --theme default --backend chrome
    python md_to_pdf.py input.md  # outputs input.pdf, default theme, auto backend

Themes:
    Stored in ../themes/*.css. Built-in themes:
    - default:     Songti SC + black/grey, formal documents
    - warm-terra:  PingFang SC + terra cotta, training/workshop materials

Requirements:
    pandoc (system install, e.g. brew install pandoc)
    weasyprint (pip install weasyprint) OR Google Chrome (for --backend chrome)
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
THEMES_DIR = SCRIPT_DIR.parent / "themes"

# macOS ARM: auto-configure library path for weasyprint
if platform.system() == "Darwin":
    _homebrew_lib = "/opt/homebrew/lib"
    if Path(_homebrew_lib).is_dir():
        _cur = os.environ.get("DYLD_LIBRARY_PATH", "")
        if _homebrew_lib not in _cur:
            os.environ["DYLD_LIBRARY_PATH"] = (
                f"{_homebrew_lib}:{_cur}" if _cur else _homebrew_lib
            )


def _find_chrome() -> str | None:
    """Find Chrome/Chromium binary path."""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chrome"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return str(c)
    return None


def _has_weasyprint() -> bool:
    """Check if weasyprint is importable."""
    try:
        import weasyprint  # noqa: F401

        return True
    except ImportError:
        return False


def _detect_backend() -> str:
    """Auto-detect best available backend: weasyprint > chrome."""
    if _has_weasyprint():
        return "weasyprint"
    if _find_chrome():
        return "chrome"
    print(
        "Error: No PDF backend found. Install weasyprint (pip install weasyprint) "
        "or Google Chrome.",
        file=sys.stderr,
    )
    sys.exit(1)


def _load_theme(theme_name: str) -> str:
    """Load CSS from themes directory."""
    theme_file = THEMES_DIR / f"{theme_name}.css"
    if not theme_file.exists():
        available = [f.stem for f in THEMES_DIR.glob("*.css")]
        print(
            f"Error: Theme '{theme_name}' not found. Available: {available}",
            file=sys.stderr,
        )
        sys.exit(1)
    return theme_file.read_text(encoding="utf-8")


def _list_themes() -> list[str]:
    """List available theme names."""
    if not THEMES_DIR.exists():
        return []
    return sorted(f.stem for f in THEMES_DIR.glob("*.css"))


def _ensure_list_spacing(text: str) -> str:
    """Ensure blank lines before list items for proper markdown parsing.

    Both Python markdown library and pandoc require a blank line before a list
    when it follows a paragraph. Without it, list items render as plain text.
    """
    lines = text.split("\n")
    result = []
    list_re = re.compile(r"^(\s*)([-*+]|\d+\.)\s")
    for i, line in enumerate(lines):
        if i > 0 and list_re.match(line):
            prev = lines[i - 1]
            if prev.strip() and not list_re.match(prev):
                result.append("")
        result.append(line)
    return "\n".join(result)


_CJK_RANGE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
    r"\U00020000-\U0002a6df\U0002a700-\U0002ebef"
    r"\u3000-\u303f\uff00-\uffef]"
)


def _fix_cjk_code_blocks(html: str) -> str:
    """Replace <pre><code> blocks containing CJK with styled divs.

    weasyprint renders <pre> blocks using monospace fonts that lack CJK glyphs,
    causing garbled output. This converts CJK-heavy code blocks to styled divs
    that use the document's CJK font stack instead.
    """

    def _replace_if_cjk(match: re.Match) -> str:
        content = match.group(1)
        if _CJK_RANGE.search(content):
            return f'<div class="cjk-code-block">{content}</div>'
        return match.group(0)

    return re.sub(
        r"<pre><code(?:\s[^>]*)?>(.+?)</code></pre>",
        _replace_if_cjk,
        html,
        flags=re.DOTALL,
    )


def _md_to_html(md_file: str) -> str:
    """Convert markdown to HTML using pandoc with list spacing preprocessing."""
    if not shutil.which("pandoc"):
        print(
            "Error: pandoc not found. Install with: brew install pandoc",
            file=sys.stderr,
        )
        sys.exit(1)

    md_content = Path(md_file).read_text(encoding="utf-8")
    md_content = _ensure_list_spacing(md_content)

    result = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "html"],
        input=md_content,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error: pandoc failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    html = result.stdout
    html = _fix_cjk_code_blocks(html)
    return html


def _build_full_html(html_content: str, css: str, title: str) -> str:
    """Wrap HTML content in a full document with CSS."""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>{css}</style>
</head>
<body>
{html_content}
</body>
</html>"""


def _render_weasyprint(full_html: str, pdf_file: str, css: str) -> None:
    """Render PDF using weasyprint."""
    from weasyprint import CSS, HTML

    HTML(string=full_html).write_pdf(pdf_file, stylesheets=[CSS(string=css)])


def _render_chrome(full_html: str, pdf_file: str) -> None:
    """Render PDF using headless Chrome."""
    chrome = _find_chrome()
    if not chrome:
        print("Error: Chrome not found.", file=sys.stderr)
        sys.exit(1)

    with tempfile.NamedTemporaryFile(
        suffix=".html", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(full_html)
        html_path = f.name

    try:
        result = subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_file}",
                html_path,
            ],
            capture_output=True,
            text=True,
        )
        if not Path(pdf_file).exists():
            print(
                f"Error: Chrome failed to generate PDF. stderr: {result.stderr}",
                file=sys.stderr,
            )
            sys.exit(1)
    finally:
        Path(html_path).unlink(missing_ok=True)


def markdown_to_pdf(
    md_file: str,
    pdf_file: str | None = None,
    theme: str = "default",
    backend: str | None = None,
) -> str:
    """
    Convert markdown file to PDF.

    Args:
        md_file: Path to input markdown file
        pdf_file: Path to output PDF (optional, defaults to same name as input)
        theme: Theme name (from themes/ directory)
        backend: 'weasyprint', 'chrome', or None (auto-detect)

    Returns:
        Path to generated PDF file
    """
    md_path = Path(md_file)
    if pdf_file is None:
        pdf_file = str(md_path.with_suffix(".pdf"))

    if backend is None:
        backend = _detect_backend()

    css = _load_theme(theme)
    html_content = _md_to_html(md_file)
    full_html = _build_full_html(html_content, css, md_path.stem)

    if backend == "weasyprint":
        _render_weasyprint(full_html, pdf_file, css)
    elif backend == "chrome":
        _render_chrome(full_html, pdf_file)
    else:
        print(f"Error: Unknown backend '{backend}'", file=sys.stderr)
        sys.exit(1)

    size_kb = Path(pdf_file).stat().st_size / 1024
    print(f"Generated: {pdf_file} ({size_kb:.0f}KB, theme={theme}, backend={backend})")
    return pdf_file


def main():
    available_themes = _list_themes()

    parser = argparse.ArgumentParser(
        description="Markdown to PDF with Chinese font support and themes."
    )
    parser.add_argument("input", help="Input markdown file")
    parser.add_argument("output", nargs="?", help="Output PDF file (optional)")
    parser.add_argument(
        "--theme",
        default="default",
        choices=available_themes or ["default"],
        help=f"CSS theme (available: {', '.join(available_themes) or 'default'})",
    )
    parser.add_argument(
        "--backend",
        choices=["weasyprint", "chrome"],
        default=None,
        help="PDF rendering backend (default: auto-detect)",
    )
    parser.add_argument(
        "--list-themes",
        action="store_true",
        help="List available themes and exit",
    )

    args = parser.parse_args()

    if args.list_themes:
        for t in available_themes:
            marker = " (default)" if t == "default" else ""
            css_file = THEMES_DIR / f"{t}.css"
            first_line = ""
            for line in css_file.read_text().splitlines():
                line = line.strip()
                if line.startswith("*") and "—" in line:
                    first_line = line.lstrip("* ").strip()
                    break
            print(f"  {t}{marker}: {first_line}")
        sys.exit(0)

    if not Path(args.input).exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    markdown_to_pdf(args.input, args.output, args.theme, args.backend)


if __name__ == "__main__":
    main()
