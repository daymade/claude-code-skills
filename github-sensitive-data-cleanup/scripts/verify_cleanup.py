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
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Share the all-commits grep helper so fixes to chunking/error handling apply
# to both scanning and verification.
from scan_repo import grep_all_commits


def extract_patterns_from_replacements(replacements_path: Path) -> list[dict]:
    """
    Parse a git-filter-repo --replace-text file and return search descriptors.

    Supports:
        literal:old==>new
        regex:old==>new

    Returns a list of dicts: {"pattern": str, "is_regex": bool}
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
            patterns.append(
                {"pattern": left[len("literal:"):].strip(), "is_regex": False}
            )
        elif left.startswith("regex:"):
            patterns.append({"pattern": left[len("regex:"):].strip(), "is_regex": True})
        else:
            # Bare string, treat as literal.
            patterns.append({"pattern": left, "is_regex": False})
    return patterns


def load_extra_patterns(patterns_path: Path | None) -> list[dict]:
    if not patterns_path:
        return []
    patterns = []
    for line in patterns_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append({"pattern": line, "is_regex": True})
    return patterns


def check_pattern_in_history(
    repo_path: Path, pattern: str, is_regex: bool
) -> tuple[list[str], str | None]:
    """Return commits that still contain the pattern, or an error string."""
    effective_pattern = pattern if is_regex else re.escape(pattern)
    matched, error = grep_all_commits(repo_path, effective_pattern)
    if error:
        return [], error
    return list(matched), None


def check_pattern_in_messages(
    repo_path: Path, pattern: str, is_regex: bool
) -> tuple[list[str], int, str | None]:
    """Return (commit hashes, hit count, error) for commit MESSAGES.

    `git grep <commits>` only searches blob content; a rewrite that covered
    file content but missed --replace-message would pass blob checks while
    the entity still named itself in a commit message.

    Decoding uses errors="replace": repos with GBK/legacy-encoded commit
    messages must not crash verification (a repo being cleaned is by
    definition a repo with hygiene problems — old encodings included).
    Hashes are returned so a FAILED report locates the offending commits
    instead of just counting hits.
    """
    log = subprocess.run(
        ["git", "-C", str(repo_path), "log", "--all",
         "--format=%H%x1f%B%x1e", "--no-color"],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    if log.returncode != 0:
        return [], 0, f"git log failed: {log.stderr}"
    rx = re.compile(pattern) if is_regex else None
    hashes: list[str] = []
    hits = 0
    for record in log.stdout.split("\x1e"):
        sha, sep, msg = record.partition("\x1f")
        if not sep:
            continue
        sha = sha.strip()
        matched = bool(rx.search(msg)) if rx else pattern in msg
        if not matched:
            continue
        hits += len(rx.findall(msg)) if rx else msg.count(pattern)
        if sha and sha not in hashes:
            hashes.append(sha)
    return hashes, hits, None


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
    subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=False)

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
    check_errors = []
    for item in patterns:
        commits, error = check_pattern_in_history(
            repo_path, item["pattern"], item["is_regex"]
        )
        if error:
            check_errors.append(
                {"pattern": item["pattern"], "is_regex": item["is_regex"], "error": error}
            )
            continue
        msg_hashes, msg_hits, msg_error = check_pattern_in_messages(
            repo_path, item["pattern"], item["is_regex"]
        )
        if msg_error:
            check_errors.append(
                {"pattern": item["pattern"], "is_regex": item["is_regex"], "error": msg_error}
            )
            continue
        if commits or msg_hits:
            entry = {"pattern": item["pattern"], "is_regex": item["is_regex"]}
            if commits:
                entry["commits"] = commits[:10]
            if msg_hits:
                entry["commit_message_hits"] = msg_hits
                entry["commit_message_commits"] = msg_hashes[:10]
            remaining.append(entry)

    report = {
        "repo": str(repo_path),
        "patterns_checked": len(patterns),
        "gitleaks_findings": gitleaks_findings,
        "remaining_patterns": remaining,
        "check_errors": check_errors,
        "ai_semantic_review_required": True,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if gitleaks_findings or remaining or check_errors:
        print("\nVERIFICATION FAILED: sensitive data still present or check could not complete.", file=sys.stderr)
        sys.exit(1)

    print("\nVERIFICATION PASSED: no known sensitive patterns remain in history.")
    print("Remember to do an AI semantic review before pushing.")


if __name__ == "__main__":
    main()
