#!/usr/bin/env python3
"""Unmix a repomix file to restore original file structure.

Supports XML, Markdown, and JSON repomix output formats.
"""

import re
import os
import sys
import json
from pathlib import Path, PureWindowsPath


def checked_destination(root, file_path):
    """Reject archive paths that are not plain, contained relative file paths."""
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError(f"Rejected archive path {file_path!r}: expected a file path")
    if ('\x00' in file_path or '\\' in file_path
            or PureWindowsPath(file_path).drive
            or Path(file_path).is_absolute()
            or '..' in file_path.split('/')):
        raise ValueError(f"Rejected archive path {file_path!r}: unsafe relative path")

    destination = root / file_path
    if destination == root or not destination.resolve().is_relative_to(root):
        raise ValueError(f"Rejected archive path {file_path!r}: outside output directory")

    current = root
    for part in Path(file_path).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Rejected archive path {file_path!r}: symbolic link")
        if current != destination and current.exists() and not current.is_dir():
            raise ValueError(f"Rejected archive path {file_path!r}: parent is not a directory")
    if destination.exists() and not destination.is_file():
        raise ValueError(f"Rejected archive path {file_path!r}: not a regular file")
    return destination


def extract_files(entries, output_dir):
    """Validate every entry before creating directories or writing archive content."""
    output = Path(output_dir)
    if output.is_symlink():
        raise ValueError(f"Rejected output directory {str(output)!r}: symbolic link")
    root = output.resolve()
    if root.exists() and not root.is_dir():
        raise ValueError(f"Rejected output directory {str(output)!r}: not a directory")

    entries = list(entries)
    errors = []
    for file_path, file_content in entries:
        try:
            checked_destination(root, file_path)
            if not isinstance(file_content, str):
                raise ValueError(f"Rejected archive content for {file_path!r}: expected text")
        except (ValueError, OSError, RuntimeError) as error:
            errors.append(str(error))
    if errors:
        raise ValueError('\n'.join(errors))

    extracted_files = []
    for file_path, file_content in entries:
        full_path = checked_destination(root, file_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        # Recheck after directory creation, including the output root itself.
        if root.is_symlink():
            raise ValueError(f"Rejected output directory {str(root)!r}: symbolic link")
        checked_destination(root, file_path)
        with open(full_path, 'w', encoding='utf-8') as stream:
            stream.write(file_content)
        extracted_files.append(file_path)
        print(f"✓ Extracted: {file_path}")
    return extracted_files


def unmix_xml(content, output_dir):
    """Extract files from repomix XML format."""
    # Pattern: <file path="...">content</file>
    file_pattern = r'<file path="([^"]*)">\n(.*?)\n</file>'
    matches = re.finditer(file_pattern, content, re.DOTALL)

    return extract_files(((match.group(1), match.group(2)) for match in matches), output_dir)


def unmix_markdown(content, output_dir):
    """Extract files from repomix Markdown format."""
    # Pattern: ## File: path\n```\ncontent\n```
    file_pattern = r'## File: ([^\n]*)\n```[^\n]*\n(.*?)\n```'
    matches = re.finditer(file_pattern, content, re.DOTALL)

    return extract_files(
        ((match.group(1).strip(), match.group(2)) for match in matches), output_dir
    )


def unmix_json(content, output_dir):
    """Extract files from repomix JSON format."""
    try:
        data = json.loads(content)
        files = data.get('files', [])

        return extract_files(
            ((entry.get('path'), entry.get('content', '')) for entry in files), output_dir
        )
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
    try:
        extracted = unmix_repomix(repomix_file, output_dir)
    except (ValueError, OSError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    if not extracted:
        print("\n⚠️  No files extracted!")
        print("Check that the input file is a valid repomix output file.")
        sys.exit(1)

    print(f"\n✅ Successfully extracted {len(extracted)} files!")
    print(f"\nExtracted files are in: {output_dir}")


if __name__ == "__main__":
    main()
