#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version
"""

import sys
import os
import re
from pathlib import Path


def find_path_references(content: str) -> list[str]:
    """
    Extract path references from SKILL.md content.
    Looks for patterns like scripts/xxx, references/xxx, assets/xxx

    Filters out:
    - Placeholder paths (xxx, example, etc.)
    - Paths in example contexts (lines containing "Example:", "e.g.", etc.)
    - Generic documentation examples
    - Paths prefixed with file:// (e.g., file://scripts/xxx) - these are external tool references, not skill-internal paths
    """
    # Pattern to match bundled resource paths (scripts/, references/, assets/)
    # Use negative lookbehind to exclude file:// prefixed paths
    pattern = r'(?<!file://)(?:scripts|references|assets)/[\w./-]+'

    # Find all matches with their line context
    unique_paths = set()
    for line in content.split('\n'):
        # Skip lines that are clearly examples or documentation
        line_lower = line.lower()
        if any(x in line_lower for x in [
            'example:', 'examples:', 'e.g.', 'for example',
            '- **example', '- example:', 'such as',
            'pattern:', 'usage:', '❌', '✅',
            '- **allowed', '- **best practice', 'would be helpful',
            'like `scripts/', 'like `references/', 'like `assets/',
        ]):
            continue

        # Find paths in this line
        matches = re.findall(pattern, line)
        for path in matches:
            # Skip obvious placeholders
            if any(x in path.lower() for x in ['example', 'xxx', '<', '>', 'my-', 'my_']):
                continue
            unique_paths.add(path)

    return list(unique_paths)


def validate_path_references(skill_path: Path, content: str) -> tuple[bool, list[str]]:
    """
    Verify all path references in SKILL.md actually exist.

    Returns:
        (all_exist, missing_paths)
    """
    referenced_paths = find_path_references(content)
    missing = []

    for ref_path in referenced_paths:
        full_path = skill_path / ref_path
        if not full_path.exists():
            missing.append(ref_path)

    return len(missing) == 0, missing


def validate_skill(skill_path):
    """Basic validation of a skill"""
    skill_path = Path(skill_path)

    # Check SKILL.md exists
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, "SKILL.md not found"

    # Read and validate frontmatter
    content = skill_md.read_text()
    if not content.startswith('---'):
        return False, "No YAML frontmatter found"

    # Extract frontmatter
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter = match.group(1)

    # Check required fields
    if 'name:' not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if 'description:' not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    # Extract name for validation
    name_match = re.search(r'name:\s*(.+)', frontmatter)
    if name_match:
        name = name_match.group(1).strip()
        # Check naming convention (hyphen-case: lowercase with hyphens)
        if not re.match(r'^[a-z0-9-]+$', name):
            return False, f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)"
        if name.startswith('-') or name.endswith('-') or '--' in name:
            return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"

    # Extract and validate description
    desc_match = re.search(r'description:\s*(.+)', frontmatter)
    if desc_match:
        description = desc_match.group(1).strip()
        # Check for angle brackets
        if '<' in description or '>' in description:
            return False, "Description cannot contain angle brackets (< or >)"

    # Validate path references exist
    paths_valid, missing_paths = validate_path_references(skill_path, content)
    if not paths_valid:
        return False, f"Missing referenced files: {', '.join(missing_paths)}"

    return True, "Skill is valid!"

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)
    
    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)