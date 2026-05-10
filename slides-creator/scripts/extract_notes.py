#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Extract structured speaker notes from slide prompt files."""

import argparse
import re
from pathlib import Path


def find_prompt_file(slide_name: str, prompts_dir: Path) -> Path | None:
    """Find matching prompt .md for a slide name."""
    # Try flat structure first: 03-prompts/01-slide-cover.md
    flat = prompts_dir / f"{slide_name}.md"
    if flat.exists():
        return flat

    # Try versioned subdirectories: 03-prompts/v6/01-slide-cover.md
    for subdir in prompts_dir.iterdir():
        if subdir.is_dir():
            candidate = subdir / f"{slide_name}.md"
            if candidate.exists():
                return candidate

    return None


def extract_notes(prompt_text: str) -> dict:
    """Extract NARRATIVE GOAL and SPEAKER NOTES sections from prompt."""
    result = {}

    ng_match = re.search(
        r"// NARRATIVE GOAL\s*\n(.+?)(?=\n// |\n## |\Z)",
        prompt_text,
        re.DOTALL,
    )
    if ng_match:
        result["narrative_goal"] = ng_match.group(1).strip()

    sn_match = re.search(
        r"// SPEAKER NOTES\s*\n(.+?)(?=\n// |\n## |\Z)",
        prompt_text,
        re.DOTALL,
    )
    if sn_match:
        result["speaker_notes"] = sn_match.group(1).strip()

    # Fallback: KEY CONTENT
    if not result:
        kc_match = re.search(
            r"// KEY CONTENT\s*\n(.+?)(?=\n// |\n## |\Z)",
            prompt_text,
            re.DOTALL,
        )
        if kc_match:
            result["key_content"] = kc_match.group(1).strip()

    return result


def extract_all_notes(prompts_dir: str, output: str | None = None) -> str:
    """Extract notes from all prompt files and return as markdown."""
    prompts_path = Path(prompts_dir)
    if not prompts_path.exists():
        raise FileNotFoundError(f"Prompts directory not found: {prompts_dir}")

    # Find all slide prompt files
    prompt_files = []
    for path in prompts_path.rglob("*.md"):
        # Only match files like 01-slide-xxx.md (not README etc.)
        if re.match(r"\d+-slide-", path.name):
            prompt_files.append(path)

    # Sort by slide number extracted from filename
    def sort_key(p: Path) -> int:
        match = re.match(r"(\d+)-slide-", p.name)
        return int(match.group(1)) if match else 999

    prompt_files.sort(key=sort_key)

    lines = ["# Speaker Notes\n"]
    matched = 0

    for prompt_file in prompt_files:
        slide_name = prompt_file.stem  # e.g. "01-slide-cover"
        prompt_text = prompt_file.read_text(encoding="utf-8")
        notes = extract_notes(prompt_text)

        if notes:
            matched += 1
            lines.append(f"## {slide_name}")
            if "narrative_goal" in notes:
                lines.append(f"**Narrative Goal**: {notes['narrative_goal']}")
            if "speaker_notes" in notes:
                lines.append(f"**Speaker Notes**: {notes['speaker_notes']}")
            if "key_content" in notes:
                lines.append(f"**Key Content**: {notes['key_content']}")
            lines.append("")

    result = "\n".join(lines)

    if output:
        output_path = Path(output)
        output_path.write_text(result, encoding="utf-8")
        print(f"Wrote speaker notes to: {output}")
        print(f"Prompts scanned: {len(prompt_files)}")
        print(f"Slides with notes: {matched}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract speaker notes from prompts")
    parser.add_argument("--prompts", required=True, help="Directory containing per-slide prompt .md files")
    parser.add_argument("--output", help="Output markdown file path (default: print to stdout)")
    args = parser.parse_args()

    extract_all_notes(args.prompts, args.output)
