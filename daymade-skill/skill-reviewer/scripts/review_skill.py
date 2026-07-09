#!/usr/bin/env python3
"""
Validate a Claude Code skill against official best practices.

Usage:
    python3 review_skill.py <skill-path>
    python3 review_skill.py <skill-path> --json

Checks:
    - Frontmatter: name, description presence and quality
    - Structure: correct directory layout
    - Size: SKILL.md body under 500 lines
    - Privacy: no hardcoded user paths or secrets
    - Scripts: shebang, error handling
    - Tool usage: invented subagent types, wrong tool names
    - Content quality: excessive caps directives, non-imperative form

Exit codes:
    0 - all checks passed
    1 - warnings only
    2 - errors found
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path


# Subagent types that ship with Claude Code itself. Plugin agents
# (plugin-name:agent-name) are valid too but depend on what is installed,
# so unknown ones are reported as warnings/info rather than errors.
CORE_SUBAGENT_TYPES = {
    "general-purpose",
    "Explore",
    "Plan",
}

HARDCODED_PATH_PATTERNS = [
    r"/Users/\w+",
    r"/home/\w+",
    r"C:\\Users\\\w+",
]

SECRET_PATTERNS = [
    r"(?i)(api[_-]?key|secret[_-]?key|password|token)\s*[:=]\s*['\"][^'\"]{8,}",
    r"sk-[a-zA-Z0-9]{20,}",
    r"ghp_[a-zA-Z0-9]{36}",
]


def parse_frontmatter(content):
    """Extract YAML frontmatter from SKILL.md.

    Handles flat 'key: value' pairs, block scalars ('>', '>-', '|', '|-')
    and plain indented continuation lines, so multi-line descriptions
    are read as a single string instead of being lost.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return None, content

    fm_text = match.group(1)
    body = content[match.end():]
    fm = {}
    current_key = None

    for line in fm_text.split("\n"):
        if not line.strip():
            continue
        if not line[0].isspace() and ":" in line:
            key, _, val = line.partition(":")
            current_key = key.strip()
            val = val.strip()
            if val in {">", ">-", ">+", "|", "|-", "|+"}:
                val = ""
            fm[current_key] = val.strip('"').strip("'")
        elif current_key:
            extra = line.strip().strip('"').strip("'")
            if extra:
                fm[current_key] = (fm[current_key] + " " + extra).strip()

    return fm, body


def check_frontmatter(fm, issues):
    """Validate frontmatter fields."""
    if fm is None:
        issues.append(("error", "frontmatter", "YAML frontmatter is missing"))
        return

    if not fm.get("name"):
        issues.append(("error", "frontmatter", "'name' field is missing"))
    else:
        name = fm["name"]
        if len(name) > 64:
            issues.append(("warning", "frontmatter", f"'name' is {len(name)} chars (max 64)"))
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", name):
            issues.append(("warning", "frontmatter", "'name' should be lowercase letters, numbers, hyphens only"))

    if not fm.get("description"):
        issues.append(("error", "frontmatter", "'description' field is missing"))
    else:
        desc = fm["description"]
        if len(desc) > 1024:
            issues.append(("warning", "frontmatter", f"'description' is {len(desc)} chars (max 1024)"))
        if len(desc) < 50:
            issues.append(("warning", "frontmatter", "'description' is very short -- may not trigger reliably"))

        trigger_phrases = ["use when", "use this", "trigger", "when the user", "when you"]
        has_trigger = any(p in desc.lower() for p in trigger_phrases)
        if not has_trigger:
            issues.append(("warning", "frontmatter", "'description' has no trigger conditions (e.g. 'Use when...')"))


def check_structure(skill_path, issues):
    """Validate directory structure."""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        issues.append(("error", "structure", "SKILL.md not found"))
        return

    refs = skill_path / "references"
    scripts = skill_path / "scripts"

    has_refs = refs.is_dir() and any(refs.iterdir())
    has_scripts = scripts.is_dir() and any(scripts.iterdir())

    if not has_refs and not has_scripts:
        issues.append(("info", "structure", "No references/ or scripts/ -- consider adding for complex skills"))

    for item in skill_path.rglob("*"):
        if item.is_file() and item.name.startswith(".") and item.name not in {".gitkeep", ".security-scan-passed"}:
            issues.append(("info", "structure", f"Hidden file found: {item.relative_to(skill_path)}"))


def check_body_size(body, issues):
    """Check SKILL.md body length."""
    lines = body.strip().split("\n")
    line_count = len(lines)
    if line_count > 500:
        issues.append(("warning", "size", f"SKILL.md body is {line_count} lines (recommended: under 500). Move details to references/"))
    elif line_count > 400:
        issues.append(("info", "size", f"SKILL.md body is {line_count} lines -- approaching 500 limit"))


def check_privacy(skill_path, issues):
    """Check for hardcoded paths and secrets."""
    for fpath in skill_path.rglob("*"):
        if not fpath.is_file():
            continue
        if fpath.suffix in {".png", ".jpg", ".gif", ".ico", ".woff", ".woff2"}:
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        rel = fpath.relative_to(skill_path)

        for pattern in HARDCODED_PATH_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                issues.append(("warning", "privacy",
                               f"{rel}: hardcoded path found {len(matches)} time(s) (e.g. {matches[0]})"))

        for pattern in SECRET_PATTERNS:
            if re.search(pattern, text):
                issues.append(("error", "privacy", f"{rel}: possible secret/credential detected"))


def check_scripts(skill_path, issues):
    """Validate script files."""
    scripts_dir = skill_path / "scripts"
    if not scripts_dir.is_dir():
        return

    for script in sorted(scripts_dir.rglob("*")):
        if not script.is_file():
            continue
        rel = script.relative_to(skill_path)

        try:
            text = script.read_text(encoding="utf-8")
        except Exception:
            issues.append(("warning", "scripts", f"{rel}: cannot read file"))
            continue

        if script.suffix == ".py":
            if not text.startswith("#!/"):
                issues.append(("info", "scripts", f"{rel}: missing shebang (#!/usr/bin/env python3)"))

            if "except:" in text and "except Exception" not in text:
                issues.append(("warning", "scripts", f"{rel}: bare 'except:' found -- use specific exception types"))

            if re.search(r"^\s*import\s+requests\b", text, re.MULTILINE) or re.search(r"^\s*import\s+httpx\b", text, re.MULTILINE):
                issues.append(("info", "scripts", f"{rel}: uses external HTTP library -- document this dependency"))

        elif script.suffix == ".sh":
            if not text.startswith("#!/"):
                issues.append(("warning", "scripts", f"{rel}: missing shebang"))
            if "set -e" not in text and "set -euo" not in text:
                issues.append(("info", "scripts", f"{rel}: consider 'set -e' for fail-fast behavior"))


def check_tool_usage(body, issues):
    """Check for fake subagent types and wrong tool names."""
    for line in body.split("\n"):
        # Skip lines that explain the wrong name (e.g. "the correct name is Agent tool")
        if "Task tool" in line and "correct name" not in line.lower() and "wrong" not in line.lower():
            issues.append(("error", "tools", "'Task tool' referenced -- the correct name is 'Agent tool'"))
            break

    refs = set(re.findall(r'subagent_type\s*[=:]\s*["\']?([\w.:-]+)["\']?', body))
    for ref in sorted(refs):
        if "::" in ref:
            issues.append(("error", "tools",
                           f"subagent_type '{ref}' uses '::' which is never valid -- likely an invented type"))
        elif ref in CORE_SUBAGENT_TYPES:
            continue
        elif re.match(r"^[a-z0-9][\w.-]*:[\w.-]+$", ref):
            issues.append(("info", "tools",
                           f"subagent_type '{ref}' is a plugin agent -- verify the plugin is documented as a prerequisite"))
        else:
            issues.append(("warning", "tools",
                           f"subagent_type '{ref}' is not a core Claude Code type -- verify it exists in the target environment"))


def check_content_quality(body, issues):
    """Heuristic checks on instruction quality."""
    caps_directives = re.findall(r"\b(ALWAYS|NEVER|MUST|CRITICAL|IMPORTANT)\b", body)
    if len(caps_directives) > 5:
        issues.append(("warning", "quality",
                        f"{len(caps_directives)} capitalized directives (ALWAYS/NEVER/MUST/...) found. "
                        "Explain reasoning instead of rigid rules -- models follow 'why' better than 'must'."))

    you_should = re.findall(r"(?i)\byou should\b", body)
    if len(you_should) > 3:
        issues.append(("info", "quality", f"'You should' used {len(you_should)} times -- prefer imperative form ('Run...' not 'You should run...')"))


def run_review(skill_path):
    """Run all checks. Returns (issues, skill_name)."""
    issues = []
    skill_path = Path(skill_path).resolve()

    if not skill_path.is_dir():
        return [("error", "structure", f"Path is not a directory: {skill_path}")], None

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return [("error", "structure", "SKILL.md not found")], None

    content = skill_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)

    check_frontmatter(fm, issues)
    check_structure(skill_path, issues)
    check_body_size(body, issues)
    check_privacy(skill_path, issues)
    check_scripts(skill_path, issues)
    check_tool_usage(body, issues)
    check_content_quality(body, issues)

    skill_name = fm.get("name") if fm else None
    return issues, skill_name


def format_text(issues, skill_path, skill_name=None):
    """Format issues as readable text."""
    errors = [i for i in issues if i[0] == "error"]
    warnings = [i for i in issues if i[0] == "warning"]
    infos = [i for i in issues if i[0] == "info"]

    lines = [f"Skill Review: {skill_name or Path(skill_path).name}", "=" * 50]

    if errors:
        lines.append(f"\nErrors ({len(errors)}):")
        for _, cat, msg in errors:
            lines.append(f"  [x] [{cat}] {msg}")

    if warnings:
        lines.append(f"\nWarnings ({len(warnings)}):")
        for _, cat, msg in warnings:
            lines.append(f"  [!] [{cat}] {msg}")

    if infos:
        lines.append(f"\nInfo ({len(infos)}):")
        for _, cat, msg in infos:
            lines.append(f"  [-] [{cat}] {msg}")

    if not issues:
        lines.append("\nAll automated checks passed.")

    lines.append(f"\nSummary: {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info")
    return "\n".join(lines)


def format_json(issues, skill_path, skill_name=None):
    """Format issues as JSON."""
    return json.dumps({
        "skill": skill_name or Path(skill_path).name,
        "skill_path": str(skill_path),
        "issues": [{"level": lvl, "category": cat, "message": msg} for lvl, cat, msg in issues],
        "summary": {
            "errors": sum(1 for i in issues if i[0] == "error"),
            "warnings": sum(1 for i in issues if i[0] == "warning"),
            "info": sum(1 for i in issues if i[0] == "info"),
        },
    }, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Validate a Claude Code skill")
    parser.add_argument("skill_path", help="Path to skill directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    issues, skill_name = run_review(args.skill_path)

    if args.json:
        print(format_json(issues, args.skill_path, skill_name))
    else:
        print(format_text(issues, args.skill_path, skill_name))

    errors = sum(1 for i in issues if i[0] == "error")
    warnings = sum(1 for i in issues if i[0] == "warning")
    if errors:
        sys.exit(2)
    elif warnings:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
