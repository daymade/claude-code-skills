#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version
"""

import sys
import os
import re
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    print(
        "Missing dependency: PyYAML.\n"
        "Run validation with an explicit dependency declaration:\n"
        "  uv run --with PyYAML python skill-creator/scripts/quick_validate.py <skill_directory>\n"
        "Or from the skill-creator directory:\n"
        "  uv run --with PyYAML python -m scripts.quick_validate <skill_directory>\n"
        "For packaging from the skill-creator directory:\n"
        "  uv run --with PyYAML python -m scripts.package_skill <skill_directory>",
        file=sys.stderr,
    )
    sys.exit(2)


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


def find_internal_path_references(content: str) -> list[str]:
    """
    Extract skill-internal path references from SKILL.md content.
    Looks for patterns like scripts/xxx, references/xxx, assets/xxx

    Only returns paths that are clearly internal to the skill bundle.
    Filters out:
    - Placeholder paths (<path>, example, etc.)
    - Absolute paths (these are external by definition)
    - Paths in example contexts
    - External tool references
    """
    # Pattern: relative paths starting with scripts/, references/, or assets/
    # that do NOT start with / or ~ (absolute paths)
    pattern = r'(?<![A-Za-z0-9_/])(?:scripts|references|assets)/[\w./-]+'

    unique_paths = set()
    for line in content.split('\n'):
        line_lower = line.lower()
        if any(x in line_lower for x in [
            'example:', 'examples:', 'e.g.', 'for example',
            '- **example', '- example:', 'such as',
            'pattern:', 'usage:', '❌', '✅',
            '- **allowed', '- **best practice', 'would be helpful',
            'like `scripts/', 'like `references/', 'like `assets/',
        ]):
            continue

        matches = re.findall(pattern, line)
        for path in matches:
            # Skip placeholders
            if any(x in path.lower() for x in ['example', 'xxx', '<', '>', 'my-', 'my_']):
                continue
            # Skip absolute paths (they're external, not internal skill references)
            if path.startswith('/') or path.startswith('~'):
                continue
            # Skip false positives like "scripts/assets" / "references/scripts"
            parts = path.split('/')
            if len(parts) >= 2 and parts[1] in {'scripts', 'references', 'assets'}:
                continue
            unique_paths.add(path)

    return list(unique_paths)


def find_external_absolute_paths(content: str) -> list[tuple[int, str]]:
    """
    Find absolute paths that contain user home directories.
    These are personal data that won't work on other machines.
    Returns list of (line_number, path).
    """
    issues = []
    # Match /Users/<user>/ and /home/<user>/ patterns
    pattern = re.compile(r'(/[Uu]sers/[A-Za-z][A-Za-z0-9_-]+/[^\s,;"\']+|/home/[A-Za-z][A-Za-z0-9_-]+/[^\s,;"\']+|C:\\\\Users\\\\[A-Za-z][A-Za-z0-9_-]+\\[^\s,;"\']*)')

    for line_no, line in enumerate(content.split('\n'), 1):
        # Skip code blocks that are clearly examples/placeholders
        stripped = line.strip()
        if stripped.startswith('#') or '<path' in stripped or 'example' in stripped.lower():
            continue
        for match in pattern.finditer(line):
            path = match.group(0)
            # Skip obvious placeholders
            if '<' in path or 'username' in path.lower() or 'user' in path.lower():
                continue
            issues.append((line_no, path))

    return issues


def find_personal_identifiers(content: str) -> list[tuple[int, str, str]]:
    """
    Find personal identifiers that are likely project-specific:
    - Real-looking profile names (lark open_id `ou_*`, `<name>-personal`, etc.)
    - Long opaque tokens/IDs that look like real credentials
    - Person names in config-like contexts (CJK names caught structurally below)
    
    Returns list of (line_number, identifier, category).
    """
    issues = []
    lines = content.split('\n')
    
    # Patterns for personal identifiers
    # 1. Profile names with personal prefixes
    # Structural detection only — do NOT hardcode real profile/person names here:
    # this script ships in a PUBLIC skill, so a real name in the pattern is itself a leak.
    # Lark open_id (ou_ + long hash) and the `<name>-personal` profile suffix are generic
    # shapes; real CJK names are caught by cjk_name_pattern below, real tokens by token_pattern.
    profile_pattern = re.compile(r'\b(ou_[a-z0-9]{8,}|[a-z][a-z0-9]*-personal)\b', re.IGNORECASE)
    
    # 2. Long opaque tokens (16+ chars, not placeholders)
    token_pattern = re.compile(r'\b[a-z0-9]{20,}\b', re.IGNORECASE)
    
    # 3. Chinese names (2-4 chars, common name patterns) in non-comment lines
    cjk_name_pattern = re.compile(r'[一-鿿]{2,4}')
    
    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments, placeholders, and obvious examples
        if stripped.startswith('#') or stripped.startswith('```'):
            continue
        if '<' in stripped or 'example' in stripped.lower() or 'placeholder' in stripped.lower():
            continue
        
        # Check for profile names
        for match in profile_pattern.finditer(line):
            text = match.group(0)
            # Skip obvious non-personal patterns
            if text.lower() in {'self', 'me', 'example-profile'}:
                continue
            issues.append((line_no, text, 'profile_name'))
        
        # Check for long tokens
        for match in token_pattern.finditer(line):
            text = match.group(0)
            # Skip common non-token words
            if text.lower() in {'skill_version', 'lookback_days', 'relevance_keywords'}:
                continue
            issues.append((line_no, text, 'opaque_token'))
        
        # Check for CJK names (only in config-like contexts: after colon, in YAML values)
        # Simple heuristic: lines that look like YAML key: value where value is CJK
        if ':' in stripped and not stripped.startswith('#'):
            key_part, _, val_part = stripped.partition(':')
            val_part = val_part.strip()
            if cjk_name_pattern.match(val_part):
                # Could be a person name in config
                issues.append((line_no, val_part, 'cjk_identifier'))

    return issues


def validate_internal_paths(skill_path: Path, content: str) -> tuple[bool, list[str]]:
    """
    Verify skill-internal path references actually exist.
    Only checks relative paths within the skill bundle (scripts/, references/, assets/).
    Absolute paths are NOT checked here (they're external).
    """
    referenced_paths = find_internal_path_references(content)
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

    # Validate skill-internal path references exist
    # NOTE: Only checks relative paths within the skill bundle (scripts/, references/, assets/).
    # Absolute paths (e.g., /Users/<user>/...) are external and NOT checked here.
    paths_valid, missing_paths = validate_internal_paths(skill_path, content)
    if not paths_valid:
        return False, f"Missing internal skill files: {', '.join(missing_paths)}"

    # Warn about absolute user paths (personal data)
    abs_paths = find_external_absolute_paths(content)
    if abs_paths:
        path_list = "; ".join(f"line {ln}: {p}" for ln, p in abs_paths[:5])
        print(f"{__import__('os').linesep}{__import__('os').linesep}".join([
            f"{chr(9992)}  WARNING: Found absolute user paths in {skill_md.name}:",
            f"   {path_list}",
            f"   These won't work on other machines.",
            f"   Use relative paths or config placeholders instead.",
        ]))

    # Warn about personal identifiers (profiles, tokens, names)
    personal = find_personal_identifiers(content)
    if personal:
        personal_list = "; ".join(f"line {ln}: {cat}={val!r}" for ln, val, cat in personal[:5])
        print(f"{chr(9992)}  WARNING: Found personal/project-specific identifiers in {skill_md.name}:")
        print(f"   {personal_list}")
        print(f"   These are fine for private projects but should be reviewed before sharing.")

    return True, "Skill is valid!"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
