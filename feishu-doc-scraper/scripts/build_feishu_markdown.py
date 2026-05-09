#!/usr/bin/env python3
"""
Render a structured Feishu capture manifest into Markdown.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def to_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def yaml_lines(manifest):
    lines = ["---"]
    simple_fields = [
        "title",
        "source",
        "published",
        "created",
        "description",
    ]
    for field in simple_fields:
        value = manifest.get(field, "")
        lines.append(f'{field}: "{str(value).replace(chr(34), chr(39))}"' if value else f"{field}:")

    for key in ("author", "tags"):
        values = to_list(manifest.get(key))
        if values:
            lines.append(f"{key}:")
            for value in values:
                lines.append(f'  - "{value.replace(chr(34), chr(39))}"')
        else:
            lines.append(f"{key}:")

    lines.append("---")
    return lines


def normalize_body(body):
    if body is None:
        return []
    if isinstance(body, list):
        return [str(block).strip() for block in body if str(block).strip()]
    text = str(body).strip()
    return [text] if text else []


def section_lines(section):
    level = int(section.get("heading_level", 2))
    level = max(1, min(level, 6))
    heading = str(section.get("heading", "")).strip()
    if not heading:
        raise ValueError("Section heading is required")

    lines = [f'{"#" * level} {heading}']
    body_blocks = normalize_body(section.get("body"))
    if body_blocks:
        lines.append("")
        lines.extend(body_blocks)
    return lines


def render_markdown(manifest):
    title = str(manifest.get("title", "")).strip()
    if not title:
        raise ValueError("Manifest title is required")

    sections = manifest.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("Manifest sections must be a non-empty list")

    lines = yaml_lines(manifest)
    lines.extend(["", f"# {title}"])

    source = str(manifest.get("source", "")).strip()
    if source:
        lines.extend(["", f"Source: <{source}>"])

    for section in sections:
        lines.extend(["", *section_lines(section)])

    return "\n".join(lines).rstrip() + "\n"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to capture manifest JSON")
    parser.add_argument("--output", help="Optional output markdown path")
    return parser.parse_args()


def main():
    args = parse_args()
    manifest_path = Path(args.input)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    markdown = render_markdown(manifest)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(markdown, encoding="utf-8")
        print(f"Wrote {output_path}")
    else:
        sys.stdout.write(markdown)


if __name__ == "__main__":
    main()
