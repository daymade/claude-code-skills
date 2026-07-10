#!/usr/bin/env python3
"""
Review a Claude Code skill against official best practices.

Usage:
    uv run --with PyYAML python review_skill.py <skill-path>
    uv run --with PyYAML python review_skill.py <skill-path> --json

Checks:
    - Canonical validation: YAML frontmatter, schema, internal paths
    - Frontmatter quality: name, description, trigger conditions
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
    3 - invocation or runtime failure
"""

import ast
import re
import sys
import json
import argparse
import subprocess
from pathlib import Path


# Subagent types that ship with Claude Code itself. Plugin agents
# (plugin-name:agent-name) are valid too but depend on what is installed,
# so unknown ones are reported as warnings/info rather than errors.
CORE_SUBAGENT_TYPES = {
    "general-purpose",
    "Explore",
    "Plan",
}

EXIT_CLEAN = 0
EXIT_WARNINGS = 1
EXIT_FINDINGS = 2
EXIT_OPERATIONAL = 3

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}

BINARY_SUFFIXES = {
    ".gif", ".ico", ".jpeg", ".jpg", ".mov", ".mp3", ".mp4",
    ".otf", ".pdf", ".png", ".ttf", ".wav", ".webp", ".woff",
    ".woff2", ".zip",
}

PATH_PATTERNS = [
    re.compile(r"/Users/(?P<user>[A-Za-z][A-Za-z0-9._-]*)(?=/|[\s`'\"),;:]|$)"),
    re.compile(r"/home/(?P<user>[A-Za-z][A-Za-z0-9._-]*)(?=/|[\s`'\"),;:]|$)"),
    re.compile(r"C:\\Users\\(?P<user>[A-Za-z][A-Za-z0-9._-]*)(?=\\|[\s`'\"),;:]|$)"),
]

PLACEHOLDER_USERNAMES = {
    "example",
    "example-user",
    "name",
    "user",
    "username",
    "your-name",
    "yourname",
}

SECRET_PATTERNS = [
    re.compile(
        r"\b(?:api[_-]?key|secret[_-]?key|password|token)\b"
        r"\s*[:=]\s*['\"](?P<value>[^'\"]{8,})['\"]",
        re.IGNORECASE,
    ),
    re.compile(r"(?P<value>sk-[A-Za-z0-9]{20,})"),
    re.compile(r"(?P<value>ghp_[A-Za-z0-9]{36})"),
]

PLACEHOLDER_SECRET_PATTERNS = [
    re.compile(r"^<[^>\r\n]+>$"),
    re.compile(
        r"^(?:your|example|sample|dummy|fake|test)[-_]"
        r"(?:(?:api|secret)[-_])?"
        r"(?:key|token|password|secret)"
        r"(?:[-_]here)?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:sk|ghp)[-_](?:test|example|sample|dummy|fake|placeholder|redacted)"
        r"(?:[-_].*)?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:change[-_]?me|replace[-_]?me|redacted|placeholder|x{3,})$",
        re.IGNORECASE,
    ),
]


class ReviewRuntimeError(Exception):
    """Raised when the reviewer cannot complete a trustworthy review."""


class ReviewArgumentParser(argparse.ArgumentParser):
    """Keep invocation failures distinct from review findings."""

    def error(self, message):
        if "--json" in sys.argv[1:]:
            print(json.dumps({
                "status": "operational_error",
                "error": {
                    "category": "invocation",
                    "message": message,
                },
            }, indent=2))
            self.exit(EXIT_OPERATIONAL)
        self.print_usage(sys.stderr)
        self.exit(EXIT_OPERATIONAL, f"{self.prog}: error: {message}\n")


def load_yaml_module():
    """Load the canonical YAML parser or fail with an actionable message."""
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ReviewRuntimeError(
            "Missing dependency: PyYAML. Run with: "
            "uv run --with PyYAML python review_skill.py <skill-path>"
        ) from exc
    return yaml


def canonical_validator_path():
    """Resolve skill-creator's validator from the explicit suite layout."""
    validator = (
        Path(__file__).resolve().parents[2]
        / "skill-creator"
        / "scripts"
        / "quick_validate.py"
    )
    if not validator.is_file():
        raise ReviewRuntimeError(
            "Canonical validator not found at the expected daymade-skill suite path: "
            f"{validator}"
        )
    return validator


def run_canonical_validation(skill_path, issues):
    """Delegate structural validity to skill-creator's canonical validator."""
    validator = canonical_validator_path()
    try:
        result = subprocess.run(
            [sys.executable, str(validator), str(skill_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except OSError as exc:
        raise ReviewRuntimeError(
            f"Could not start canonical validator: {exc}"
        ) from exc

    stdout = " ".join(result.stdout.split())
    stderr = " ".join(result.stderr.split())
    if result.returncode == 0:
        return True
    if result.returncode == 1 and not stderr:
        issues.append((
            "error",
            "validation",
            stdout or "Canonical skill validation failed",
        ))
        return False

    output = " ".join(part for part in (stdout, stderr) if part)
    raise ReviewRuntimeError(
        "Canonical validator could not complete"
        + (f": {output}" if output else f" (exit {result.returncode})")
    )


def parse_frontmatter(content, yaml_module):
    """Parse YAML frontmatter with PyYAML after canonical validation."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return None, content

    fm_text = match.group(1)
    body = content[match.end():]
    try:
        fm = yaml_module.safe_load(fm_text)
    except yaml_module.YAMLError:
        return None, body
    return (fm if isinstance(fm, dict) else None), body


def check_frontmatter(fm, issues):
    """Apply reviewer-specific quality checks to valid YAML frontmatter."""
    if fm is None:
        return

    if not fm.get("name"):
        issues.append(("error", "frontmatter", "'name' field is missing"))
    else:
        name = fm["name"]
        if not isinstance(name, str):
            return
        if len(name) > 64:
            issues.append(("warning", "frontmatter", f"'name' is {len(name)} chars (max 64)"))
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", name):
            issues.append(("warning", "frontmatter", "'name' should be lowercase letters, numbers, hyphens only"))

    if not fm.get("description"):
        issues.append(("error", "frontmatter", "'description' field is missing"))
    else:
        desc = fm["description"]
        if not isinstance(desc, str):
            return
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
        rel = fpath.relative_to(skill_path)
        if any(part in IGNORED_DIRECTORY_NAMES for part in rel.parts):
            continue
        if fpath.name == ".security-scan-passed":
            continue
        if fpath.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = fpath.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ReviewRuntimeError(
                f"Cannot review {rel}: file is not valid UTF-8"
            ) from exc
        except OSError as exc:
            raise ReviewRuntimeError(f"Cannot read {rel}: {exc}") from exc

        for pattern in PATH_PATTERNS:
            matches = [
                match.group(0)
                for match in pattern.finditer(text)
                if match.group("user").lower() not in PLACEHOLDER_USERNAMES
            ]
            if matches:
                issues.append(("warning", "privacy",
                               f"{rel}: hardcoded path found {len(matches)} time(s) (e.g. {matches[0]})"))

        for pattern in SECRET_PATTERNS:
            matches = [
                match.group("value")
                for match in pattern.finditer(text)
                if not is_placeholder_secret(match.group("value"))
            ]
            if matches:
                issues.append(("error", "privacy", f"{rel}: possible secret/credential detected"))
                break


def is_placeholder_secret(value):
    """Recognize explicit documentation/test placeholders, not real values."""
    normalized = value.strip()
    return any(pattern.fullmatch(normalized) for pattern in PLACEHOLDER_SECRET_PATTERNS)


def check_scripts(skill_path, issues):
    """Validate script files."""
    scripts_dir = skill_path / "scripts"
    if not scripts_dir.is_dir():
        return

    for script in sorted(scripts_dir.rglob("*")):
        if not script.is_file():
            continue
        rel = script.relative_to(skill_path)
        if any(part in IGNORED_DIRECTORY_NAMES for part in rel.parts):
            continue
        if script.suffix.lower() in BINARY_SUFFIXES or script.suffix == ".pyc":
            continue

        try:
            text = script.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ReviewRuntimeError(
                f"Cannot review {rel}: script is not valid UTF-8"
            ) from exc
        except OSError as exc:
            raise ReviewRuntimeError(f"Cannot read {rel}: {exc}") from exc

        if script.suffix == ".py":
            if not text.startswith("#!/"):
                issues.append(("info", "scripts", f"{rel}: missing shebang (#!/usr/bin/env python3)"))

            try:
                syntax_tree = ast.parse(text, filename=str(rel))
            except SyntaxError as exc:
                issues.append((
                    "warning",
                    "scripts",
                    f"{rel}: Python syntax error at line {exc.lineno}: {exc.msg}",
                ))
            else:
                for node in ast.walk(syntax_tree):
                    if isinstance(node, ast.ExceptHandler) and node.type is None:
                        issues.append((
                            "warning",
                            "scripts",
                            f"{rel}:{node.lineno}: bare 'except:' found -- use specific exception types",
                        ))

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
        raise ReviewRuntimeError(f"Path is not a directory: {skill_path}")

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return [("error", "structure", "SKILL.md not found")], None

    try:
        content = skill_md.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ReviewRuntimeError("SKILL.md is not valid UTF-8") from exc
    except OSError as exc:
        raise ReviewRuntimeError(f"Cannot read SKILL.md: {exc}") from exc

    yaml_module = load_yaml_module()
    run_canonical_validation(skill_path, issues)
    fm, body = parse_frontmatter(content, yaml_module)

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


def format_operational_error(message, as_json=False):
    """Format a reviewer failure without misclassifying it as a finding."""
    if as_json:
        return json.dumps({
            "status": "operational_error",
            "error": {
                "category": "runtime",
                "message": message,
            },
        }, indent=2)
    return f"Reviewer could not complete: {message}"


def main():
    parser = ReviewArgumentParser(description="Review a Claude Code skill")
    parser.add_argument("skill_path", help="Path to skill directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    try:
        issues, skill_name = run_review(args.skill_path)
    except ReviewRuntimeError as exc:
        output = format_operational_error(str(exc), as_json=args.json)
        print(output, file=sys.stdout if args.json else sys.stderr)
        return EXIT_OPERATIONAL

    if args.json:
        print(format_json(issues, args.skill_path, skill_name))
    else:
        print(format_text(issues, args.skill_path, skill_name))

    errors = sum(1 for i in issues if i[0] == "error")
    warnings = sum(1 for i in issues if i[0] == "warning")
    if errors:
        return EXIT_FINDINGS
    if warnings:
        return EXIT_WARNINGS
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
