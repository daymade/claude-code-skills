#!/usr/bin/env python3
"""
Verify that a repo no longer contains sensitive strings after a history rewrite.

Re-runs gitleaks and greps all commits for the original sensitive strings.
The original strings are extracted from the same replacements file that was
passed to rewrite_history.py, so verification is precise and not confused by
a rewritten `.pii-patterns` file.

Usage:
    uv run --with gitpython scripts/verify_cleanup.py \
      --repo /path/to/repo \
      --replacements /tmp/sensitive-replacements.txt
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def extract_patterns_from_replacements(replacements_path: Path) -> list[str]:
    """
    Parse a git-filter-repo --replace-text file and return the search sides.

    Supports:
        literal:old==>new
        regex:old==>new
    """
    patterns = []
    for line in replacements_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "==>" not in line:
            continue
        left, _ = line.split("==>", 1)
        left = left.strip()
        if not left:
            continue
        if left.startswith("literal:"):
            patterns.append(left[len("literal:"):])
        elif left.startswith("regex:"):
            patterns.append(left[len("regex:"):])
        else:
            # Bare string, treat as literal.
            patterns.append(left)
    return patterns


def load_extra_patterns(patterns_path: Path | None) -> list[str]:
    if not patterns_path:
        return []
    patterns = []
    for line in patterns_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def check_pattern_in_history(repo_path: Path, pattern: str) -> list[str]:
    """Return commits that still contain the pattern."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "log",
            "--all",
            "--pickaxe-regex",
            "-S",
            pattern,
            "--pretty=format:%H",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return [c for c in result.stdout.splitlines() if c.strip()]


def run_gitleaks(repo_path: Path) -> list[dict]:
    gitleaks_bin = shutil.which("gitleaks")
    if not gitleaks_bin:
        return [{"tool": "gitleaks", "error": "gitleaks not found on PATH"}]

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    cmd = [
        gitleaks_bin,
        "detect",
        "--source",
        str(repo_path),
        "--report-format",
        "json",
        "--report-path",
        str(tmp_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=False)

    findings = []
    if tmp_path.exists():
        try:
            with tmp_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            findings = data if isinstance(data, list) else data.get("findings", [])
        except json.JSONDecodeError:
            pass
        finally:
            tmp_path.unlink(missing_ok=True)
    return findings


def main():
    parser = argparse.ArgumentParser(description="Verify a repo is clean of sensitive data.")
    parser.add_argument("--repo", required=True, help="Path to the git repository.")
    parser.add_argument(
        "--replacements",
        help="Path to the git-filter-repo replacements file used for the rewrite.",
    )
    parser.add_argument(
        "--patterns",
        help="Optional path to an extra patterns file to also check.",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not (repo_path / ".git").is_dir():
        print(f"Not a git repository: {repo_path}", file=sys.stderr)
        sys.exit(1)

    patterns = []
    if args.replacements:
        replacements_path = Path(args.replacements).resolve()
        if not replacements_path.is_file():
            print(f"Replacements file not found: {replacements_path}", file=sys.stderr)
            sys.exit(1)
        patterns.extend(extract_patterns_from_replacements(replacements_path))

    if args.patterns:
        patterns.extend(load_extra_patterns(Path(args.patterns).resolve()))

    if not patterns:
        print(
            "No patterns to verify. Provide --replacements or --patterns.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Re-running gitleaks...")
    gitleaks_findings = run_gitleaks(repo_path)

    print("Checking for remaining sensitive patterns in history...")
    remaining = []
    for pattern in patterns:
        commits = check_pattern_in_history(repo_path, pattern)
        if commits:
            remaining.append({"pattern": pattern, "commits": commits[:10]})

    report = {
        "repo": str(repo_path),
        "patterns_checked": len(patterns),
        "gitleaks_findings": gitleaks_findings,
        "remaining_patterns": remaining,
        "ai_semantic_review_required": True,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if gitleaks_findings or remaining:
        print("\nVERIFICATION FAILED: sensitive data still present.", file=sys.stderr)
        sys.exit(1)

    print("\nVERIFICATION PASSED: no known sensitive patterns remain in history.")
    print("Remember to do an AI semantic review before pushing.")


if __name__ == "__main__":
    main()
