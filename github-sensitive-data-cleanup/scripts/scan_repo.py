#!/usr/bin/env python3
"""
Scan a git repository for sensitive data across PII Guard layers.

Layer 1: gitleaks (secrets, API keys, tokens)
Layer 2: Custom regex patterns (internal IPs, phone numbers, repo-specific PII)
Layer 3: Private infrastructure context from the user's gitleaks.toml
         (private domains, known IPs, optional identities file)
Layer 4: AI semantic review flag (must be performed manually by an agent)

Usage:
    uv run --with gitpython scripts/scan_repo.py --repo /path/to/repo --output /tmp/report.json

    With Layer 3 enabled:
    uv run --with gitpython scripts/scan_repo.py \
      --repo /path/to/repo \
      --gitleaks-config ~/scripts/git-pii-guard/gitleaks.toml \
      --identities-file ~/.config/github-sensitive-data-cleanup/identities.txt \
      --output /tmp/report.json
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None
from pathlib import Path

# Default Layer 2 patterns for context that gitleaks may miss.
# Add repo-specific patterns in a .pii-patterns file next to the repo root.
# Do NOT hardcode real private domains here; distribute them via .pii-patterns
# or via --gitleaks-config for Layer 3.
DEFAULT_PATTERNS = [
    # Internal IP ranges
    r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    r"\b172\.(1[6-9]|2[0-9]|3[01])\.\d{1,3}\.\d{1,3}\b",
    r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
    # Chinese mobile phone numbers (approximate; adjust strictness as needed)
    r"\b1[3-9]\d{9}\b",
]

# Layer 3: rule IDs to extract from the user's gitleaks config.
LAYER3_RULE_IDS = ["private-domain-context", "private-ip-context"]
GITLEAKS_FINDINGS_EXIT = 10


def run_gitleaks(repo_path: Path, output_path: Path | None = None) -> dict:
    """Return validated, redacted findings, or an explicit scan error.

    output_path remains accepted for existing callers; the CLI writes the final
    multi-layer report independently of gitleaks' temporary report.
    """
    def failed(message):
        return {"tool": "gitleaks", "error": message, "findings": []}

    gitleaks_bin = shutil.which("gitleaks")
    if not gitleaks_bin:
        return failed("gitleaks not found on PATH; install with `brew install gitleaks`")

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
    except OSError:
        return failed("gitleaks report could not be created")

    cmd = [
        gitleaks_bin,
        "detect",
        "--source",
        str(repo_path),
        "--report-format",
        "json",
        "--report-path",
        str(tmp_path),
        "--exit-code",
        str(GITLEAKS_FINDINGS_EXIT),
        "--redact",
    ]

    def read_report():
        try:
            try:
                process = subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=False)
            except OSError:
                return failed("gitleaks could not be executed")
            if process.returncode not in (0, GITLEAKS_FINDINGS_EXIT):
                return failed(f"gitleaks scan failed (exit {process.returncode})")
            with tmp_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                findings = data
            elif isinstance(data, dict):
                findings = data.get("findings")
            else:
                findings = None
            if not isinstance(findings, list):
                return failed("gitleaks report must contain a findings array")
            for finding in findings:
                if not isinstance(finding, dict) or any(
                    not isinstance(finding.get(key), str) or not finding[key].strip()
                    for key in ("RuleID", "File")
                ):
                    return failed("gitleaks report contains an invalid finding")
                if "StartLine" in finding and (type(finding["StartLine"]) is not int or finding["StartLine"] < 1):
                    return failed("gitleaks report contains an invalid finding location")
            if bool(findings) != (process.returncode == GITLEAKS_FINDINGS_EXIT):
                return failed("gitleaks exit status disagrees with its report")
            # Keep rule/file/commit/line metadata usable without echoing credentials.
            findings = [dict(finding) for finding in findings]
            for finding in findings:
                for key in ("Secret", "Match"):
                    if key in finding:
                        finding[key] = "REDACTED"
            return {"tool": "gitleaks", "error": None, "findings": findings}
        except (OSError, UnicodeError):
            return failed("gitleaks report is missing or unreadable")
        except json.JSONDecodeError:
            return failed("gitleaks report is empty or invalid JSON")

    cleanup_error = None
    try:
        result = read_report()
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            cleanup_error = "gitleaks temporary report could not be removed"
    return failed(cleanup_error) if cleanup_error else result


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


def load_identities(identities_path: Path | None) -> list[str]:
    """Load known identities from a one-per-line file."""
    if identities_path is None:
        return []
    identities = []
    for line in identities_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            identities.append(line)
    return identities


def parse_gitleaks_rules(config_path: Path) -> dict[str, str]:
    """
    Extract rule ID -> regex mappings from a gitleaks TOML config.

    Uses the standard library tomllib when available (Python 3.11+) so TOML
    escaping is handled correctly. Falls back to a minimal parser for older
    interpreters, which only reliably supports the triple-single-quoted regex
    style used by the reference gitleaks config.
    """
    rules = {}

    if tomllib is not None:
        with config_path.open("rb") as f:
            data = tomllib.load(f)
        for rule in data.get("rules", []):
            rule_id = rule.get("id")
            regex = rule.get("regex")
            if rule_id and regex is not None:
                rules[rule_id] = regex.strip()
        return rules

    # Fallback minimal parser for Python < 3.11 without tomli.
    text = config_path.read_text(encoding="utf-8")

    # Split into [[rules]] blocks. The first chunk may itself start with a rule.
    blocks = re.split(r"\[\[rules\]\]\n", text)
    for block in blocks:
        id_match = re.search(r'^id\s*=\s*"([^"]+)"', block, re.MULTILINE)
        if not id_match:
            continue
        rule_id = id_match.group(1)

        # regex may be triple-quoted or double-quoted.
        triple = re.search(r"^regex\s*=\s*'''(.*?)'''", block, re.DOTALL | re.MULTILINE)
        double = re.search(r'^regex\s*=\s*"([^"]+)"', block, re.MULTILINE)
        regex = triple.group(1) if triple else (double.group(1) if double else None)
        if regex is not None:
            rules[rule_id] = regex.strip()

    return rules


def grep_all_commits(
    repo_path: Path,
    pattern: str,
    commits: list[str] | None = None,
    batch_size: int = 500,
) -> tuple[set[str], str | None]:
    """
    Search all commits for a PCRE pattern using `git grep --perl-regexp`.

    If `commits` is not provided, it is fetched once with `git rev-list --all`.
    The commit list is processed in batches to avoid command-line length limits
    and to ensure the entire history is searched (not just the newest N).

    Returns a set of commit hashes that contain the pattern, or an error string.
    """
    if commits is None:
        commits, error = get_all_commits(repo_path)
        if error:
            return set(), error

    if not commits:
        return set(), None

    matched: set[str] = set()
    for i in range(0, len(commits), batch_size):
        batch = commits[i : i + batch_size]
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "grep", "--perl-regexp", "-n", "-e", pattern] + batch,
                capture_output=True,
                text=True, errors="replace",
                check=False,
            )
        except OSError:
            return set(), "git grep could not be executed"
        if result.returncode == 1 and not result.stdout:
            # No matches in this batch.
            continue
        if result.returncode != 0:
            return set(), f"git grep failed (exit {result.returncode})"

        for line in result.stdout.splitlines():
            if ":" in line:
                matched.add(line.split(":", 1)[0])

    return matched, None


def run_custom_scan(
    repo_path: Path, patterns: list[str], commits: list[str] | None = None
) -> dict:
    """Run grep across all commits for custom patterns."""
    if not patterns:
        return {"tool": "custom-grep", "findings": []}

    findings = []
    errors = []
    for pattern in patterns:
        matched, error = grep_all_commits(repo_path, pattern, commits=commits)
        if error:
            errors.append({"pattern": pattern, "error": error})
            continue
        if matched:
            findings.append(
                {
                    "pattern": pattern,
                    "match_count": len(matched),
                    "sample_commits": list(matched)[:10],
                }
            )

    return {"tool": "custom-grep", "findings": findings, "errors": errors,
            "error": "custom pattern scan could not complete" if errors else None}


def run_layer3_scan(
    repo_path: Path,
    gitleaks_config_path: Path | None,
    identities_path: Path | None,
    commits: list[str] | None = None,
) -> dict:
    """
    Layer 3: scan for private infrastructure context from the user's gitleaks
    config plus an optional identities file.

    Uses `git grep --perl-regexp` across all commits so that PCRE features
    (e.g., \b word boundaries) in the gitleaks rules work as intended.
    """
    patterns = []
    rule_sources = {}

    if gitleaks_config_path is not None:
        try:
            rules = parse_gitleaks_rules(gitleaks_config_path)
            for rule_id in LAYER3_RULE_IDS:
                regex = rules.get(rule_id)
                if rule_id in rules and not regex:
                    raise ValueError
                if regex:
                    patterns.append(regex)
                    rule_sources[regex] = f"gitleaks:{rule_id}"
            if not patterns:
                raise ValueError
        except (OSError, ValueError, TypeError, AttributeError):
            return {
                "tool": "layer3-context",
                "error": "Layer 3 config is missing, unreadable or invalid",
                "findings": [],
            }

    try:
        identities = load_identities(identities_path)
    except (OSError, UnicodeError):
        return {"tool": "layer3-context", "error": "Layer 3 identities file is missing or unreadable", "findings": []}
    if identities_path is not None and not identities:
        return {"tool": "layer3-context", "error": "Layer 3 identities file contains no identities", "findings": []}
    for identity in identities:
        escaped = re.escape(identity)
        patterns.append(escaped)
        rule_sources[escaped] = "identities-file"

    if not patterns:
        return {
            "tool": "layer3-context",
            "note": "No Layer 3 patterns available. Pass --gitleaks-config and/or --identities-file.",
            "findings": [],
        }

    findings = []
    errors = []
    for pattern in patterns:
        matched, error = grep_all_commits(repo_path, pattern, commits=commits)
        if error:
            errors.append(
                {"source": rule_sources.get(pattern, "unknown"), "error": error}
            )
            continue
        if matched:
            findings.append(
                {
                    "source": rule_sources.get(pattern, "unknown"),
                    "pattern": pattern,
                    "match_count": len(matched),
                    "sample_commits": list(matched)[:10],
                }
            )

    return {"tool": "layer3-context", "findings": findings, "errors": errors,
            "error": "Layer 3 scan could not complete" if errors else None}


def get_all_commits(repo_path: Path) -> tuple[list[str], str | None]:
    """Return all commit hashes for the repo, or an error string."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-list", "--all"],
            capture_output=True,
            text=True, errors="replace",
            check=False,
        )
    except OSError:
        return [], "git rev-list could not be executed"
    if result.returncode != 0:
        return [], f"git rev-list failed (exit {result.returncode})"
    return [c for c in result.stdout.splitlines() if c.strip()], None


def get_repository_layout(repo_path: Path) -> tuple[dict | None, str | None]:
    """Discover a readable Git root; callers enforce their own write boundaries."""
    if repo_path is None or repo_path == "":
        return None, "Repository path must not be empty"

    def value(flag):
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", flag],
            capture_output=True, text=True, errors="replace", check=False,
        )
        if result.returncode != 0 or not isinstance(result.stdout, str):
            raise ValueError
        # Git terminates each result with LF; spaces belong to the actual path.
        text = result.stdout.removesuffix("\n")
        if not text:
            raise ValueError
        return text

    try:
        root = Path(repo_path).resolve()
        bare = value("--is-bare-repository")
        if bare not in ("true", "false"):
            raise ValueError
        git_dir_text = value("--absolute-git-dir")
        if not Path(git_dir_text).is_absolute():
            raise ValueError
        git_dir = Path(git_dir_text).resolve()
        common_dir_text = value("--git-common-dir")
        common_dir = Path(common_dir_text)
        if not common_dir.is_absolute():
            common_dir = root / common_dir
        common_dir = common_dir.resolve()
        discovered_root = git_dir if bare == "true" else Path(value("--show-toplevel"))
        if not discovered_root.is_absolute() or discovered_root.resolve() != root:
            return None, "Repository path must be the Git repository root"
        if not root.is_dir() or not git_dir.is_dir() or not common_dir.is_dir():
            raise ValueError
        return {"root": root, "is_bare": bare == "true",
                "git_dir": git_dir, "common_dir": common_dir}, None
    except (OSError, ValueError, TypeError, RuntimeError):
        return None, "Git repository discovery failed or returned invalid layout data"


def main():
    parser = argparse.ArgumentParser(description="Scan a repo for sensitive data.")
    parser.add_argument("--repo", required=True, help="Path to the Git repository root (working tree or bare repository).")
    parser.add_argument("--output", required=True, help="Path for the JSON report.")
    parser.add_argument(
        "--gitleaks-config",
        help="Path to your private gitleaks.toml (enables Layer 3 private domain/IP scanning).",
    )
    parser.add_argument(
        "--identities-file",
        help="Path to a one-per-line file of known private identities (enables Layer 3 identity scanning).",
    )
    args = parser.parse_args()

    layout, error = get_repository_layout(args.repo)
    if error:
        print(error, file=sys.stderr)
        sys.exit(1)
    repo_path = layout["root"]

    for option in (args.gitleaks_config, args.identities_file):
        if option is not None and not option.strip():
            print("Explicit Layer 3 input paths must not be empty", file=sys.stderr)
            sys.exit(1)
    gitleaks_config = Path(args.gitleaks_config) if args.gitleaks_config is not None else None
    identities_file = Path(args.identities_file) if args.identities_file is not None else None

    all_commits, commits_err = get_all_commits(repo_path)
    if commits_err:
        print(f"Failed to list commits: {commits_err}", file=sys.stderr)
        sys.exit(1)

    try:
        patterns = DEFAULT_PATTERNS + load_custom_patterns(repo_path)
    except (OSError, UnicodeError):
        print("Custom patterns file could not be read", file=sys.stderr)
        sys.exit(1)

    gitleaks_result = run_gitleaks(repo_path, Path(args.output))
    custom_result = run_custom_scan(repo_path, patterns, commits=all_commits)
    layer3_result = run_layer3_scan(
        repo_path, gitleaks_config, identities_file, commits=all_commits
    )

    report = {
        "repo": str(repo_path),
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tools": [gitleaks_result, custom_result, layer3_result],
        "ai_semantic_review_required": True,
        "ai_semantic_review_prompt": "Use references/ai_semantic_review_prompt.md",
        "summary": {
            "gitleaks_findings": len(gitleaks_result.get("findings", [])),
            "custom_findings": len(custom_result.get("findings", [])),
            "layer3_findings": len(layer3_result.get("findings", [])),
        },
    }

    output_path = Path(args.output)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError:
        print("Scan report could not be written", file=sys.stderr)
        sys.exit(1)

    errors = [result["error"] for result in report["tools"] if result.get("error")]
    if errors:
        print("Scan failed: " + "; ".join(errors), file=sys.stderr)
        print(f"Report written to: {output_path}")
        sys.exit(1)

    total = (
        report["summary"]["gitleaks_findings"]
        + report["summary"]["custom_findings"]
        + report["summary"]["layer3_findings"]
    )
    print(f"Scan complete. Total findings: {total}")
    print(f"Report written to: {output_path}")
    print("IMPORTANT: Layers 1-3 are regex/grep. Layer 4 AI semantic review is mandatory.")

    if total > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
