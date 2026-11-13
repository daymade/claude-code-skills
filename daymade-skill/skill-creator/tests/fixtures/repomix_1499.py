#!/usr/bin/env python3
"""Unmix a repomix file to restore original file structure.

Supports XML, Markdown, and JSON repomix output formats.
"""

import re
import os
import sys
import json
from pathlib import Path


def unmix_xml(content, output_dir):
    """Extract files from repomix XML format."""
    # Pattern: <file path="...">content</file>
    file_pattern = r'<file path="([^"]+)">\n(.*?)\n</file>'
    matches = re.finditer(file_pattern, content, re.DOTALL)

    extracted_files = []
    for match in matches:
        file_path = match.group(1)
        file_content = match.group(2)

        # Create full output path
        full_path = Path(output_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(file_content)

        extracted_files.append(file_path)
        print(f"✓ Extracted: {file_path}")

    return extracted_files


def unmix_markdown(content, output_dir):
    """Extract files from repomix Markdown format."""
    # Pattern: ## File: path\n```\ncontent\n```
    file_pattern = r'## File: ([^\n]+)\n```[^\n]*\n(.*?)\n```'
    matches = re.finditer(file_pattern, content, re.DOTALL)

    extracted_files = []
    for match in matches:
        file_path = match.group(1).strip()
        file_content = match.group(2)

        # Create full output path
        full_path = Path(output_dir) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(file_content)

        extracted_files.append(file_path)
        print(f"✓ Extracted: {file_path}")

    return extracted_files


def unmix_json(content, output_dir):
    """Extract files from repomix JSON format."""
    try:
        data = json.loads(content)
        files = data.get('files', [])

        extracted_files = []
        for file_entry in files:
            file_path = file_entry.get('path')
            file_content = file_entry.get('content', '')

            if not file_path:
                continue

            # Create full output path
            full_path = Path(output_dir) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the file
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(file_content)

            extracted_files.append(file_path)
            print(f"✓ Extracted: {file_path}")

        return extracted_files
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON: {e}")
        return []


def detect_format(content):
    """Detect the repomix file format."""
    # Check for XML format
    if '<file path=' in content and '</file>' in content:
        return 'xml'

    # Check for JSON format
    if content.strip().startswith('{') and '"files"' in content:
        return 'json'

    # Check for Markdown format
    if '## File:' in content:
        return 'markdown'

    return None


def unmix_repomix(repomix_file, output_dir):
    """Extract files from a repomix file (auto-detects format)."""

    # Read the repomix file
    with open(repomix_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Detect format
    format_type = detect_format(content)

    if format_type is None:
        print("Error: Could not detect repomix format")
        print("Expected XML (<file path=...>), Markdown (## File:), or JSON format")
        return []

    print(f"Detected format: {format_type.upper()}")

    # Extract based on format
    if format_type == 'xml':
        return unmix_xml(content, output_dir)
    elif format_type == 'markdown':
        return unmix_markdown(content, output_dir)
    elif format_type == 'json':
        return unmix_json(content, output_dir)

    return []


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: unmix_repomix.py <repomix_file> [output_directory]")
        print()
        print("Arguments:")
        print("  repomix_file       Path to the repomix output file (XML, Markdown, or JSON)")
        print("  output_directory   Optional: Directory to extract files to (default: ./extracted)")
        print()
        print("Examples:")
        print("  unmix_repomix.py skills.xml /tmp/extracted-skills")
        print("  unmix_repomix.py repo-output.md")
        sys.exit(1)

    repomix_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./extracted"

    # Validate input file exists
    if not os.path.exists(repomix_file):
        print(f"Error: File not found: {repomix_file}")
        sys.exit(1)

    print(f"Unmixing {repomix_file}...")
    print(f"Output directory: {output_dir}\n")

    # Extract files
    extracted = unmix_repomix(repomix_file, output_dir)

    if not extracted:
        print("\n⚠️  No files extracted!")
        print("Check that the input file is a valid repomix output file.")
        sys.exit(1)

    print(f"\n✅ Successfully extracted {len(extracted)} files!")
    print(f"\nExtracted files are in: {output_dir}")


if __name__ == "__main__":
    main()
