#!/usr/bin/env python3
"""
Multi-tool document to markdown converter with intelligent orchestration.

Supports Quick Mode (fast, single tool) and Heavy Mode (best quality, multi-tool merge).

Usage:
    # Quick Mode (default) - fast, single best tool
    uv run --with pymupdf4llm --with markitdown scripts/convert.py document.pdf -o output.md

    # Heavy Mode - multi-tool parallel execution with merge
    uv run --with pymupdf4llm --with markitdown scripts/convert.py document.pdf -o output.md --heavy

    # With image extraction
    uv run --with pymupdf4llm scripts/convert.py document.pdf -o output.md --assets-dir ./images

Dependencies:
    - pymupdf4llm: PDF conversion (LLM-optimized)
    - markitdown: PDF/DOCX/PPTX conversion
    - pandoc: DOCX/PPTX conversion (system install: brew install pandoc)
"""

import argparse
import subprocess
import sys
import tempfile
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ConversionResult:
    """Result from a single tool conversion."""
    markdown: str
    tool: str
    images: list[str] = field(default_factory=list)
    success: bool = True
    error: str = ""


def check_tool_available(tool: str) -> bool:
    """Check if a conversion tool is available."""
    if tool == "pymupdf4llm":
        try:
            import pymupdf4llm
            return True
        except ImportError:
            return False
    elif tool == "markitdown":
        try:
            import markitdown
            return True
        except ImportError:
            return False
    elif tool == "pandoc":
        return shutil.which("pandoc") is not None
    return False


def select_tools(file_path: Path, mode: str) -> list[str]:
    """Select conversion tools based on file type and mode."""
    ext = file_path.suffix.lower()

    # Tool preferences by format
    tool_map = {
        ".pdf": {
            "quick": ["pymupdf4llm", "markitdown"],  # fallback order
            "heavy": ["pymupdf4llm", "markitdown"],
        },
        ".docx": {
            "quick": ["pandoc", "markitdown"],
            "heavy": ["pandoc", "markitdown"],
        },
        ".doc": {
            "quick": ["pandoc", "markitdown"],
            "heavy": ["pandoc", "markitdown"],
        },
        ".pptx": {
            "quick": ["markitdown", "pandoc"],
            "heavy": ["markitdown", "pandoc"],
        },
        ".xlsx": {
            "quick": ["markitdown"],
            "heavy": ["markitdown"],
        },
    }

    tools = tool_map.get(ext, {"quick": ["markitdown"], "heavy": ["markitdown"]})

    if mode == "quick":
        # Return first available tool
        for tool in tools["quick"]:
            if check_tool_available(tool):
                return [tool]
        return []
    else:  # heavy
        # Return all available tools
        return [t for t in tools["heavy"] if check_tool_available(t)]


def convert_with_pymupdf4llm(
    file_path: Path, assets_dir: Optional[Path] = None
) -> ConversionResult:
    """Convert using PyMuPDF4LLM (best for PDFs)."""
    try:
        import pymupdf4llm

        kwargs = {}
        images = []

        if assets_dir:
            assets_dir.mkdir(parents=True, exist_ok=True)
            kwargs["write_images"] = True
            kwargs["image_path"] = str(assets_dir)
            kwargs["dpi"] = 150

        # Use best table detection strategy
        kwargs["table_strategy"] = "lines_strict"

        md_text = pymupdf4llm.to_markdown(str(file_path), **kwargs)

        # Collect extracted images
        if assets_dir and assets_dir.exists():
            images = [str(p) for p in assets_dir.glob("*.png")]
            images.extend([str(p) for p in assets_dir.glob("*.jpg")])

        return ConversionResult(
            markdown=md_text, tool="pymupdf4llm", images=images, success=True
        )
    except Exception as e:
        return ConversionResult(
            markdown="", tool="pymupdf4llm", success=False, error=str(e)
        )


def convert_with_markitdown(
    file_path: Path, assets_dir: Optional[Path] = None
) -> ConversionResult:
    """Convert using markitdown."""
    try:
        # markitdown CLI approach
        result = subprocess.run(
            ["markitdown", str(file_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            return ConversionResult(
                markdown="",
                tool="markitdown",
                success=False,
                error=result.stderr,
            )

        return ConversionResult(
            markdown=result.stdout, tool="markitdown", success=True
        )
    except FileNotFoundError:
        # Try Python API
        try:
            from markitdown import MarkItDown

            md = MarkItDown()
            result = md.convert(str(file_path))
            return ConversionResult(
                markdown=result.text_content, tool="markitdown", success=True
            )
        except Exception as e:
            return ConversionResult(
                markdown="", tool="markitdown", success=False, error=str(e)
            )
    except Exception as e:
        return ConversionResult(
            markdown="", tool="markitdown", success=False, error=str(e)
        )


def convert_with_pandoc(
    file_path: Path, assets_dir: Optional[Path] = None
) -> ConversionResult:
    """Convert using pandoc."""
    try:
        cmd = ["pandoc", str(file_path), "-t", "markdown", "--wrap=none"]

        if assets_dir:
            assets_dir.mkdir(parents=True, exist_ok=True)
            cmd.extend(["--extract-media", str(assets_dir)])

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            return ConversionResult(
                markdown="", tool="pandoc", success=False, error=result.stderr
            )

        images = []
        if assets_dir and assets_dir.exists():
            images = [str(p) for p in assets_dir.rglob("*.png")]
            images.extend([str(p) for p in assets_dir.rglob("*.jpg")])

        return ConversionResult(
            markdown=result.stdout, tool="pandoc", images=images, success=True
        )
    except Exception as e:
        return ConversionResult(
            markdown="", tool="pandoc", success=False, error=str(e)
        )


def convert_single(
    file_path: Path, tool: str, assets_dir: Optional[Path] = None
) -> ConversionResult:
    """Run a single conversion tool."""
    converters = {
        "pymupdf4llm": convert_with_pymupdf4llm,
        "markitdown": convert_with_markitdown,
        "pandoc": convert_with_pandoc,
    }

    converter = converters.get(tool)
    if not converter:
        return ConversionResult(
            markdown="", tool=tool, success=False, error=f"Unknown tool: {tool}"
        )

    return converter(file_path, assets_dir)


def merge_results(results: list[ConversionResult]) -> ConversionResult:
    """Merge results from multiple tools, selecting best segments."""
    if not results:
        return ConversionResult(markdown="", tool="none", success=False)

    # Filter successful results
    successful = [r for r in results if r.success and r.markdown.strip()]
    if not successful:
        # Return first error
        return results[0] if results else ConversionResult(
            markdown="", tool="none", success=False
        )

    if len(successful) == 1:
        return successful[0]

    # Multiple successful results - merge them
    # Strategy: Compare key metrics and select best
    best = successful[0]
    best_score = score_markdown(best.markdown)

    for result in successful[1:]:
        score = score_markdown(result.markdown)
        if score > best_score:
            best = result
            best_score = score

    # Merge images from all results
    all_images = []
    seen = set()
    for result in successful:
        for img in result.images:
            if img not in seen:
                all_images.append(img)
                seen.add(img)

    best.images = all_images
    best.tool = f"merged({','.join(r.tool for r in successful)})"

    return best


def score_markdown(md: str) -> float:
    """Score markdown quality for comparison."""
    score = 0.0

    # Length (more content is generally better)
    score += min(len(md) / 10000, 5.0)  # Cap at 5 points

    # Tables (proper markdown tables)
    table_count = md.count("|---|") + md.count("| ---")
    score += min(table_count * 0.5, 3.0)

    # Images (referenced images)
    image_count = md.count("![")
    score += min(image_count * 0.3, 2.0)

    # Headings (proper hierarchy)
    h1_count = md.count("\n# ")
    h2_count = md.count("\n## ")
    h3_count = md.count("\n### ")
    if h1_count > 0 and h2_count >= h1_count:
        score += 1.0  # Good hierarchy

    # Lists (structured content)
    list_count = md.count("\n- ") + md.count("\n* ") + md.count("\n1. ")
    score += min(list_count * 0.1, 2.0)

    return score


def main():
    parser = argparse.ArgumentParser(
        description="Convert documents to markdown with multi-tool orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Quick mode (default)
    python convert.py document.pdf -o output.md

    # Heavy mode (best quality)
    python convert.py document.pdf -o output.md --heavy

    # With custom assets directory
    python convert.py document.pdf -o output.md --assets-dir ./images
        """,
    )
    parser.add_argument("input", type=Path, help="Input document path")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output markdown file"
    )
    parser.add_argument(
        "--heavy",
        action="store_true",
        help="Enable Heavy Mode (multi-tool, best quality)",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=None,
        help="Directory for extracted images (default: <output>_assets/)",
    )
    parser.add_argument(
        "--tool",
        choices=["pymupdf4llm", "markitdown", "pandoc"],
        help="Force specific tool (overrides auto-selection)",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List available tools and exit",
    )

    args = parser.parse_args()

    # List tools mode
    if args.list_tools:
        tools = ["pymupdf4llm", "markitdown", "pandoc"]
        print("Available conversion tools:")
        for tool in tools:
            status = "✓" if check_tool_available(tool) else "✗"
            print(f"  {status} {tool}")
        sys.exit(0)

    # Validate input
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    output_path = args.output or args.input.with_suffix(".md")

    # Determine assets directory
    assets_dir = args.assets_dir
    if assets_dir is None and args.heavy:
        assets_dir = output_path.parent / f"{output_path.stem}_assets"

    # Select tools
    mode = "heavy" if args.heavy else "quick"
    if args.tool:
        tools = [args.tool] if check_tool_available(args.tool) else []
    else:
        tools = select_tools(args.input, mode)

    if not tools:
        print("Error: No conversion tools available.", file=sys.stderr)
        print("Install with:", file=sys.stderr)
        print("  pip install pymupdf4llm", file=sys.stderr)
        print("  uv tool install markitdown[pdf]", file=sys.stderr)
        print("  brew install pandoc", file=sys.stderr)
        sys.exit(1)

    print(f"Converting: {args.input}")
    print(f"Mode: {mode.upper()}")
    print(f"Tools: {', '.join(tools)}")

    # Run conversions
    results = []
    for tool in tools:
        print(f"  Running {tool}...", end=" ", flush=True)

        # Use separate assets dirs for each tool in heavy mode
        tool_assets = None
        if assets_dir and mode == "heavy" and len(tools) > 1:
            tool_assets = assets_dir / tool
        elif assets_dir:
            tool_assets = assets_dir

        result = convert_single(args.input, tool, tool_assets)
        results.append(result)

        if result.success:
            print(f"✓ ({len(result.markdown):,} chars, {len(result.images)} images)")
        else:
            print(f"✗ ({result.error[:50]}...)")

    # Merge results if heavy mode
    if mode == "heavy" and len(results) > 1:
        print("  Merging results...", end=" ", flush=True)
        final = merge_results(results)
        print(f"✓ (using {final.tool})")
    else:
        final = merge_results(results)

    if not final.success:
        print(f"Error: Conversion failed: {final.error}", file=sys.stderr)
        sys.exit(1)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(final.markdown)

    print(f"\nOutput: {output_path}")
    print(f"  Size: {len(final.markdown):,} characters")
    if final.images:
        print(f"  Images: {len(final.images)} extracted")


if __name__ == "__main__":
    main()
