#!/usr/bin/env python3
"""
Scan a git repository for sensitive data.

Combines gitleaks (secrets) with a custom bash/grep layer for private domains,
internal IPs, and other context that gitleaks does not cover.

Outputs a JSON report.

Usage:
    uv run --with gitpython scripts/scan_repo.py --repo /path/to/repo --output /tmp/report.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Default custom patterns for context that gitleaks may miss.
# Add repo-specific patterns in a .pii-patterns file next to the repo root.
# Do NOT hardcode real private domains here; distribute them via .pii-patterns.
DEFAULT_PATTERNS = [
    # Internal IP ranges
    r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    r"\b172\.(1[6-9]|2[0-9]|3[01])\.\d{1,3}\.\d{1,3}\b",
    r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
    # Chinese mobile phone numbers (approximate; adjust strictness as needed)
    r"\b1[3-9]\d{9}\b",
]


def run_gitleaks(repo_path: Path, output_path: Path) -> dict:
    """Run gitleaks and return parsed findings."""
    gitleaks_bin = shutil.which("gitleaks")
    if not gitleaks_bin:
        return {
            "tool": "gitleaks",
            "error": "gitleaks not found on PATH; install with `brew install gitleaks`",
            "findings": [],
        }

    # Write gitleaks JSON to a temp file so we can parse it even if it exits 1.
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
        "--verbose",
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as e:
        return {
            "tool": "gitleaks",
            "error": f"failed to run gitleaks: {e}",
            "findings": [],
        }

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

    return {
        "tool": "gitleaks",
        "error": None,
        "findings": findings,
    }


def load_custom_patterns(repo_path: Path) -> list[str]:
    """Load custom regex patterns from .pii-patterns if present."""
    patterns_file = repo_path / ".pii-patterns"
    if not patterns_file.exists():
        return []

    patterns = []
    for line in patterns_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def run_custom_scan(repo_path: Path, patterns: list[str]) -> dict:
    """Run grep across all commits for custom patterns."""
    if not patterns:
        return {"tool": "custom-grep", "findings": []}

    findings = []
    for pattern in patterns:
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_path),
                    "log",
                    "--all",
                    "--source",
                    "--pickaxe-regex",
                    "-S",
                    pattern,
                    "--pretty=format:%H",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            commits = [c for c in result.stdout.splitlines() if c.strip()]
            if commits:
                findings.append(
                    {
                        "pattern": pattern,
                        "match_count": len(commits),
                        "sample_commits": commits[:10],
                    }
                )
        except Exception as e:
            findings.append({"pattern": pattern, "error": str(e)})

    return {"tool": "custom-grep", "findings": findings}


def main():
    parser = argparse.ArgumentParser(description="Scan a repo for sensitive data.")
    parser.add_argument("--repo", required=True, help="Path to the git repository.")
    parser.add_argument("--output", required=True, help="Path for the JSON report.")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not (repo_path / ".git").is_dir():
        print(f"Not a git repository: {repo_path}", file=sys.stderr)
        sys.exit(1)

    patterns = DEFAULT_PATTERNS + load_custom_patterns(repo_path)

    gitleaks_result = run_gitleaks(repo_path, Path(args.output))
    custom_result = run_custom_scan(repo_path, patterns)

    report = {
        "repo": str(repo_path),
        "scanned_at": subprocess.run(
            ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
        "tools": [gitleaks_result, custom_result],
        "ai_semantic_review_required": True,
        "summary": {
            "gitleaks_findings": len(gitleaks_result.get("findings", [])),
            "custom_findings": len(custom_result.get("findings", [])),
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    total = report["summary"]["gitleaks_findings"] + report["summary"]["custom_findings"]
    print(f"Scan complete. Total findings: {total}")
    print(f"Report written to: {output_path}")
    print("IMPORTANT: Regex scanners miss semantic private context. Do an AI semantic review before pushing.")

    if total > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
