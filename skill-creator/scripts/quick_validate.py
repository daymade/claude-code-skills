#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version
"""

import sys
import os
import re
import yaml
from pathlib import Path


def find_invalid_frontmatter_indentation(frontmatter: str) -> list[tuple[int, str]]:
    """
    Detect non-space indentation characters in YAML frontmatter.

    YAML indentation must use ASCII spaces. Tabs or non-ASCII whitespace
    (e.g., NBSP) can cause YAML parse errors.
    """
    issues = []
    for line_no, line in enumerate(frontmatter.splitlines(), start=1):
        # Scan leading whitespace only.
        for ch in line:
            if not ch.isspace():
                break
            if ch != ' ':
                issues.append((line_no, ch))
                break
    return issues


def describe_whitespace(ch: str) -> str:
    if ch == '\t':
        return "TAB"
    return f"U+{ord(ch):04X}"


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
            'pattern:', 'usage:', '\u274c', '\u2705',
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


# Define allowed properties (union of official and our extensions)
ALLOWED_PROPERTIES = {
    'name', 'description', 'license', 'allowed-tools', 'metadata',
    'compatibility', 'context', 'agent', 'disable-model-invocation',
    'user-invocable', 'model', 'argument-hint', 'hooks',
}


def validate_skill(skill_path):
    """Basic validation of a skill"""
    skill_path = Path(skill_path)

    # Check SKILL.md exists
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, "SKILL.md not found"

    # Read and validate frontmatter
    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith('---'):
        return False, "No YAML frontmatter found"

    # Extract frontmatter
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter_text = match.group(1)

    # Check for invalid indentation characters in frontmatter
    invalid_indent = find_invalid_frontmatter_indentation(frontmatter_text)
    if invalid_indent:
        samples = ", ".join(
            f"line {line_no} ({describe_whitespace(ch)})"
            for line_no, ch in invalid_indent[:3]
        )
        more = "" if len(invalid_indent) <= 3 else f" (+{len(invalid_indent) - 3} more)"
        return False, (
            "Invalid whitespace in frontmatter indentation; use ASCII spaces only. "
            f"Found: {samples}{more}"
        )

    # Parse YAML frontmatter
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter must be a YAML dictionary"
    except yaml.YAMLError as e:
        return False, f"Invalid YAML in frontmatter: {e}"

    # Check for unexpected properties
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected_keys:
        return False, (
            f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected_keys))}. "
            f"Allowed properties are: {', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    # Check required fields
    if 'description' not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    # Extract name for validation (optional per official spec, but validate if present)
    name = frontmatter.get('name', '')
    if isinstance(name, str):
        name = name.strip()
        if name:
            # Check naming convention (kebab-case: lowercase with hyphens)
            if not re.match(r'^[a-z0-9-]+$', name):
                return False, f"Name '{name}' should be kebab-case (lowercase letters, digits, and hyphens only)"
            if name.startswith('-') or name.endswith('-') or '--' in name:
                return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
            # Check name length (max 64 characters per spec)
            if len(name) > 64:
                return False, f"Name is too long ({len(name)} characters). Maximum is 64 characters."
    elif name is not None:
        return False, f"Name must be a string, got {type(name).__name__}"

    # Extract and validate description
    description = frontmatter.get('description', '')
    if not isinstance(description, str):
        return False, f"Description must be a string, got {type(description).__name__}"
    description = description.strip()
    if description:
        # Check for angle brackets
        if '<' in description or '>' in description:
            return False, "Description cannot contain angle brackets (< or >)"
        # Check description length (max 1024 characters per spec)
        if len(description) > 1024:
            return False, f"Description is too long ({len(description)} characters). Maximum is 1024 characters."

    # Validate compatibility field if present (optional)
    compatibility = frontmatter.get('compatibility', '')
    if compatibility:
        if not isinstance(compatibility, str):
            return False, f"Compatibility must be a string, got {type(compatibility).__name__}"
        if len(compatibility) > 500:
            return False, f"Compatibility is too long ({len(compatibility)} characters). Maximum is 500 characters."

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
