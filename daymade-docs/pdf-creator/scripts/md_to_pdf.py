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
    # Chinese: CJK Unified Ideographs + Extension A + Compatibility + Extensions B-F
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
    r"\U00020000-\U0002a6df\U0002a700-\U0002ebef"
    # CJK Symbols and Punctuation + Halfwidth/Fullwidth Forms
    r"\u3000-\u303f\uff00-\uffef"
    # Japanese: Hiragana + Katakana + Katakana Phonetic Extensions
    r"\u3040-\u309f\u30a0-\u30ff\u31f0-\u31ff"
    # Korean: Hangul Syllables + Hangul Jamo + Hangul Compatibility Jamo
    r"\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]"
)

# Match <pre><code>…</code></pre> allowing attributes on both tags.
# Also handles pandoc's <div class="sourceCode"><pre class="..."><code class="...">
# syntax highlighting wrapper, by matching the inner <pre><code> structure.
_PRE_CODE_RE = re.compile(
    r"<pre[^>]*>\s*<code[^>]*>(.+?)</code>\s*</pre>",
    flags=re.DOTALL,
)


def _fix_cjk_code_blocks(html: str) -> str:
    """Replace <pre><code> blocks containing CJK with styled divs.

    weasyprint renders <pre> blocks using monospace fonts that lack CJK glyphs,
    causing garbled output. This converts CJK-heavy code blocks to styled divs
    that use the document's CJK font stack instead.

    Pure-ASCII code blocks (including pandoc-highlighted ones with language
    identifiers) are left untouched so syntax highlighting and monospace
    rendering are preserved.
    """

    def _replace_if_cjk(match: re.Match) -> str:
        content = match.group(1)
        if _CJK_RANGE.search(content):
            # Strip pandoc's <span> syntax-highlighting wrappers so the
            # content renders as plain text in the inherited body font.
            cleaned = re.sub(r"<span[^>]*>", "", content)
            cleaned = cleaned.replace("</span>", "")
            return f'<div class="cjk-code-block">{cleaned}</div>'
        return match.group(0)

    return _PRE_CODE_RE.sub(_replace_if_cjk, html)


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


# ---------------- Visual self-check (post-render PNG previews) ----------------
#
# Why: "PDF generated successfully" ≠ "PDF renders correctly". Common silent
# failures include paragraph collapsing (pseudo-list), table overflow, missing
# CJK / emoji glyphs, code block garbling. The author/AI must visually inspect
# the rendered output, not assume success from a clean exit code.
#
# Design: after PDF generation, automatically convert each page to PNG next to
# the PDF (via pdftoppm), and print a structured self-check checklist to stdout.
# This makes "Read each PNG and verify" the default contract of every PDF run,
# not an optional step that's easy to skip.
#
# Reference: CLAUDE.md "Self-Verification Protocol" + "Visual Verification" rules.


def _generate_pdf_previews(pdf_file: str, dpi: int = 130) -> list[Path]:
    """Convert each PDF page to PNG for visual inspection.

    Returns sorted list of PNG paths. Empty list if pdftoppm not available
    or no pages produced. Old previews in target dir are cleaned first.
    """
    if not shutil.which("pdftoppm"):
        return []

    pdf_path = Path(pdf_file).resolve()
    preview_dir = pdf_path.parent / f"{pdf_path.stem}-preview"
    preview_dir.mkdir(exist_ok=True)
    # Clean stale previews so old/extra pages don't linger after a shorter rerun
    for old in preview_dir.glob("page-*.png"):
        old.unlink()

    subprocess.run(
        [
            "pdftoppm",
            "-png",
            "-r",
            str(dpi),
            str(pdf_path),
            str(preview_dir / "page"),
        ],
        capture_output=True,
    )

    return sorted(preview_dir.glob("page-*.png"))


def _lint_pdf_typography(pdf_file: str) -> list[dict]:
    """Detect inappropriate Chinese line breaks in rendered PDF.

    Uses `pdftotext -layout` to preserve visual line structure, then scans
    each page for known typography anti-patterns per "中文文案排版指北":

      1. Single CJK character alone on a line (cell too narrow → forced break
         mid-word/mid-name)
      2. Line ending with 全角左括号 「（」 followed by content on next line
         (broken parenthesis pair: opener separated from content)
      3. Line starting with 全角右括号 「）」 (same as #2 from receiving end)
      4. Short line ending with mid-thought punctuation 「、，；：」 right
         before next CJK content (suggests forced break in narrow cell)

    Returns: list of dicts {page, line, kind, snippet, message}.
    Empty list if pdftotext unavailable or PDF clean.

    Note: this only catches obvious cases. Subtle typography issues (uneven
    line spacing, awkward breaks at safe points) require visual inspection.
    """
    if not shutil.which("pdftotext"):
        return []

    findings: list[dict] = []

    # Process each page separately to give accurate page numbers
    page_count_result = subprocess.run(
        ["pdfinfo", str(pdf_file)],
        capture_output=True,
        text=True,
    )
    page_count = 0
    if page_count_result.returncode == 0:
        for line in page_count_result.stdout.splitlines():
            if line.startswith("Pages:"):
                try:
                    page_count = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
                break

    if page_count == 0:
        return []

    cjk_re = re.compile(r"[一-鿿]")

    for page_num in range(1, page_count + 1):
        result = subprocess.run(
            [
                "pdftotext",
                "-layout",
                "-f",
                str(page_num),
                "-l",
                str(page_num),
                str(pdf_file),
                "-",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue

        lines = result.stdout.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            # Pattern 1: Single CJK character alone on a line
            if len(stripped) == 1 and cjk_re.match(stripped):
                findings.append({
                    "page": page_num,
                    "line": i + 1,
                    "kind": "single-cjk-char",
                    "snippet": stripped,
                    "message": (
                        f"Single CJK char 「{stripped}」 alone on a line — "
                        "cell width forced mid-word break"
                    ),
                })
                continue

            # Pattern 2: Line ends with 全角左括号 followed by content next line
            if stripped.endswith("（") and i + 1 < len(lines):
                next_stripped = lines[i + 1].strip()
                if next_stripped and not next_stripped.startswith("）"):
                    findings.append({
                        "page": page_num,
                        "line": i + 1,
                        "kind": "broken-bracket-open",
                        "snippet": stripped[-15:],
                        "message": (
                            "Line ends with 全角左括号「（」 and content "
                            "wraps to next line — broken bracket pair"
                        ),
                    })
                    continue

            # Pattern 3: Line starts with 全角右括号
            if stripped.startswith("）"):
                findings.append({
                    "page": page_num,
                    "line": i + 1,
                    "kind": "broken-bracket-close",
                    "snippet": stripped[:15],
                    "message": (
                        "Line starts with 全角右括号「）」 — "
                        "broken from previous line's bracket pair"
                    ),
                })
                continue

            # Pattern 4: Line ends with 中文标点 (suggests forced break)
            # This is informational — sometimes legitimate
            if stripped.endswith(("、", "，", "；", "：")) and i + 1 < len(lines):
                next_stripped = lines[i + 1].strip()
                # Only warn if next line continues with CJK content (not a new section)
                if next_stripped and cjk_re.match(next_stripped):
                    # Skip if this looks like end of a list item or paragraph (heuristic)
                    if len(stripped) < 30:  # short cell content suggests forced break
                        findings.append({
                            "page": page_num,
                            "line": i + 1,
                            "kind": "trailing-punctuation-break",
                            "snippet": stripped[-15:],
                            "message": (
                                f"Short line ends with 「{stripped[-1]}」 mid-thought — "
                                "may be forced break in narrow cell"
                            ),
                        })

    return findings


def _print_typography_findings(findings: list[dict]) -> None:
    """Print typography lint findings to stderr."""
    if not findings:
        return
    print("", file=sys.stderr)
    print(
        f"⚠️  Typography lint: {len(findings)} potential Chinese line-break issue(s)",
        file=sys.stderr,
    )
    print(
        "    Per 中文文案排版指北 — narrow cells / over-wide tables often force "
        "inappropriate breaks:",
        file=sys.stderr,
    )
    for f in findings[:20]:  # cap output
        print(
            f"  [page {f['page']} L{f['line']}] {f['kind']}: "
            f"{f['message']}",
            file=sys.stderr,
        )
        print(f"      snippet: 「{f['snippet']}」", file=sys.stderr)
    if len(findings) > 20:
        print(f"  ... ({len(findings) - 20} more)", file=sys.stderr)
    print(
        "    💡 Fix: reduce table column count, shorten cell content, or "
        "restructure as separate paragraph below the table.",
        file=sys.stderr,
    )
    print("", file=sys.stderr)


def _print_self_check_hint(pages: list[Path]) -> None:
    """Print a structured self-check checklist after PDF generation."""
    if not pages:
        print(
            "ℹ️  Visual self-check skipped: pdftoppm not found "
            "(install: brew install poppler).",
            file=sys.stderr,
        )
        return

    preview_dir = pages[0].parent
    print("")
    print(f"📋 Visual self-check required ({len(pages)} pages)")
    print(f"   Previews: {preview_dir}/page-NN.png")
    print("")
    print("   ⚠️  PDF generated cleanly does NOT mean rendering matches intent.")
    print("   Read each page PNG and verify against your markdown source:")
    print("")
    print("   [ ] Paragraphs render as separate blocks (NOT collapsed into one)")
    print("       ↳ Common issue: ≥2 consecutive `**xxx**：text` lines without")
    print("         blank lines collapse into one paragraph (CommonMark soft")
    print("         break = space). Fix in markdown: use `- ` real list, or")
    print("         insert blank lines between.")
    print("   [ ] Tables fit within page margins (no right-side text cut off)")
    print("   [ ] No inappropriate Chinese line breaks (per 中文文案排版指北)")
    print("       ↳ Symptoms: single CJK char alone on a line; broken bracket")
    print("         pairs (line ends with `（` while content wraps to next line,")
    print("         or line starts with `）`); short cells with mid-thought breaks.")
    print("       ↳ Cause: cell width too narrow / table has too many columns.")
    print("       ↳ Fix: reduce column count, shorten cell content, or move")
    print("         long content into a separate paragraph below the table.")
    print("   [ ] Lists keep nested indentation (sub-items visually nested)")
    print("   [ ] Emoji + CJK glyphs render correctly (no boxes / placeholders)")
    print("   [ ] Code blocks readable (monospace + CJK both visible)")
    print("   [ ] No content overflow / unexpected page breaks mid-table")
    print("   [ ] Last page ends naturally (no orphan title at top)")
    print("")


def markdown_to_pdf(
    md_file: str,
    pdf_file: str | None = None,
    theme: str = "default",
    backend: str | None = None,
    previews: bool = True,
) -> str:
    """
    Convert markdown file to PDF.

    Args:
        md_file: Path to input markdown file
        pdf_file: Path to output PDF (optional, defaults to same name as input)
        theme: Theme name (from themes/ directory)
        backend: 'weasyprint', 'chrome', or None (auto-detect)
        previews: If True (default), auto-generate per-page PNG previews next
                  to the PDF and print a visual self-check checklist. Disable
                  with --no-preview for batch / non-interactive runs.

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

    if previews:
        # Auto-run typography lint to catch obvious mid-word breaks in tables.
        # Findings go to stderr; do NOT block (warnings, not errors).
        typography_findings = _lint_pdf_typography(pdf_file)
        _print_typography_findings(typography_findings)

        pages = _generate_pdf_previews(pdf_file)
        _print_self_check_hint(pages)

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
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip per-page PNG preview generation and self-check hint",
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

    markdown_to_pdf(
        args.input,
        args.output,
        args.theme,
        args.backend,
        previews=not args.no_preview,
    )


if __name__ == "__main__":
    main()
