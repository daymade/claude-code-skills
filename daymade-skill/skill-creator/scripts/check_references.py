#!/usr/bin/env python3
"""
Reference-integrity checker for mined skill references.

Runs against a target skill and an enrichment directory produced by
mine_conversation.py. Reports:
  - Duplicate or near-duplicate topics vs existing references
  - Broken internal links in candidates
  - Missing cross-links that should point to existing references
  - Overlap in content between candidates and existing references

Exit codes:
  0 - no blocking issues
  1 - warnings only (broken links, minor overlaps)
  2 - blocking issues (duplicate reference names, severe overlaps)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# Allow script to be run as module or directly.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from utils import parse_skill_md  # noqa: E402


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def _extract_frontmatter(path: Path) -> tuple[dict, str]:
    """Return (frontmatter dict, body text) for a markdown file."""
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter_text = parts[1]
    body = parts[2]
    try:
        import yaml
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except Exception:
        frontmatter = {}
    return frontmatter, body


def _reference_name(path: Path) -> str:
    frontmatter, _ = _extract_frontmatter(path)
    return frontmatter.get("name") or path.stem


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------

def _extract_internal_links(text: str) -> list[str]:
    """Find references/* or relative .md links inside a markdown body."""
    links: list[str] = []
    # Markdown links [text](path)
    links.extend(re.findall(r"\[([^\]]+)\]\((references/[^\)]+)\)", text))
    # Bare references/...
    links.extend(re.findall(r"\b(references/[\w./-]+\.md)\b", text))
    # Also catch `references/xxx` in inline code / backticks as hints, not strict links
    return links


def _extract_heading_slugs(text: str) -> set[str]:
    """Return a set of markdown heading slugs (lowercase, spaces-to-dashes)."""
    headings = re.findall(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)
    return {re.sub(r"[^\w\s-]", "", h).strip().lower().replace(" ", "-") for h in headings}


# ---------------------------------------------------------------------------
# Overlap helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Simple word-token overlap check."""
    return set(re.findall(r"[a-zA-Z0-9一-鿿]+", text.lower()))


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_duplicates(existing_refs: dict[str, Path], candidates: dict[str, Path]) -> list[dict]:
    issues = []
    existing_names = {name.lower(): path for name, path in existing_refs.items()}
    for _, path in candidates.items():
        name = _reference_name(path)
        lower = name.lower()
        if lower in existing_names:
            issues.append({
                "severity": "blocking",
                "type": "duplicate_reference_name",
                "candidate": str(path),
                "existing": str(existing_names[lower]),
                "message": f"Candidate name '{name}' already exists in references/",
            })
    return issues


def check_broken_links(skill_dir: Path, enrich_dir: Path, candidates: dict[str, Path]) -> list[dict]:
    issues = []
    for path in candidates.values():
        _, body = _extract_frontmatter(path)
        links = _extract_internal_links(body)
        for link in links:
            # link may be a tuple from markdown link regex or a string from bare regex
            link_path = link[1] if isinstance(link, tuple) else link
            # Resolve relative to skill root
            target = skill_dir / link_path
            if not target.exists():
                candidate_rel = path.relative_to(enrich_dir) if path.is_relative_to(enrich_dir) else path
                issues.append({
                    "severity": "warning",
                    "type": "broken_internal_link",
                    "file": str(candidate_rel),
                    "link": link_path,
                    "message": f"Link target does not exist: {link_path}",
                })
    return issues


def check_overlaps(existing_refs: dict[str, Path], candidates: dict[str, Path], threshold: float = 0.6) -> list[dict]:
    issues = []
    existing_tokens = {name: _tokenize(path.read_text(encoding="utf-8")) for name, path in existing_refs.items()}
    candidate_tokens = {name: _tokenize(path.read_text(encoding="utf-8")) for name, path in candidates.items()}

    for c_name, c_tokens in candidate_tokens.items():
        for e_name, e_tokens in existing_tokens.items():
            overlap = _jaccard(c_tokens, e_tokens)
            if overlap >= threshold:
                severity = "blocking" if overlap >= 0.8 else "warning"
                issues.append({
                    "severity": severity,
                    "type": "content_overlap",
                    "candidate": c_name,
                    "existing": e_name,
                    "overlap": round(overlap, 3),
                    "message": f"High overlap ({overlap:.2%}) between candidate '{c_name}' and existing '{e_name}'",
                })
    return issues


def check_missing_crosslinks(skill_dir: Path, enrich_dir: Path, existing_refs: dict[str, Path], candidates: dict[str, Path]) -> list[dict]:
    """Warn if a candidate does not mention any existing reference."""
    issues = []
    existing_names = set(existing_refs.keys())
    for name, path in candidates.items():
        _, body = _extract_frontmatter(path)
        mentioned = any(other in body for other in existing_names if other != name)
        if not mentioned and existing_names:
            candidate_rel = path.relative_to(enrich_dir) if path.is_relative_to(enrich_dir) else path
            issues.append({
                "severity": "warning",
                "type": "missing_crosslink",
                "candidate": str(candidate_rel),
                "message": "Candidate does not reference any existing skill reference file",
            })
    return issues


# ---------------------------------------------------------------------------
# Directory loading
# ---------------------------------------------------------------------------

def _load_references(dir_path: Path) -> dict[str, Path]:
    refs: dict[str, Path] = {}
    if not dir_path.exists():
        return refs
    for path in dir_path.glob("*.md"):
        frontmatter, _ = _extract_frontmatter(path)
        name = frontmatter.get("name") if frontmatter else None
        if not name:
            # Fall back to filename stem
            name = path.stem
        refs[name] = path
    return refs


def _load_candidates(enrich_dir: Path) -> dict[str, Path]:
    candidates_dir = enrich_dir / "candidates"
    if not candidates_dir.exists():
        return {}
    refs: dict[str, Path] = {}
    for path in candidates_dir.rglob("*.md"):
        if path.name.endswith(".prompt.md"):
            continue
        # Key by path, not frontmatter name/stem: different mining agents
        # naturally emit files named chunk-000.md. Name-keying silently
        # overwrote all but the last candidate before any check could see them.
        refs[str(path.relative_to(candidates_dir))] = path
    return refs


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _print_report(issues: list[dict], verbose: bool) -> int:
    if not issues:
        print("✅ No reference-integrity issues found.")
        return 0

    blocking = [i for i in issues if i["severity"] == "blocking"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    if blocking:
        print(f"\n🔴 Blocking issues ({len(blocking)}):")
        for issue in blocking:
            print(f"  [{issue['type']}] {issue['message']}")
            if verbose:
                for k, v in issue.items():
                    if k not in ("severity", "type", "message"):
                        print(f"    {k}: {v}")

    if warnings:
        print(f"\n⚠️  Warnings ({len(warnings)}):")
        for issue in warnings:
            print(f"  [{issue['type']}] {issue['message']}")
            if verbose:
                for k, v in issue.items():
                    if k not in ("severity", "type", "message"):
                        print(f"    {k}: {v}")

    return 2 if blocking else 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check reference integrity for mined skill references")
    parser.add_argument("--skill", required=True, type=Path, help="Path to target skill directory")
    parser.add_argument("--enrich", required=True, type=Path, help="Path to .enrich/<timestamp> directory")
    parser.add_argument("--overlap-threshold", type=float, default=0.6, help="Jaccard overlap threshold for duplicate warnings")
    parser.add_argument("--output", type=Path, help="Write JSON report to this file")
    parser.add_argument("--verbose", action="store_true", help="Show details")
    args = parser.parse_args(argv)

    skill_dir = args.skill
    if not skill_dir.is_dir():
        print(f"Skill directory not found: {skill_dir}", file=sys.stderr)
        return 2

    if not args.enrich.is_dir():
        print(f"Enrich directory not found: {args.enrich}", file=sys.stderr)
        return 2

    # Parse SKILL.md for the skill name
    try:
        skill_name, _, _ = parse_skill_md(skill_dir)
    except Exception as e:
        print(f"Warning: could not parse SKILL.md: {e}", file=sys.stderr)
        skill_name = skill_dir.name

    existing_refs = _load_references(skill_dir / "references")
    candidates = _load_candidates(args.enrich)

    if args.verbose:
        print(f"Checking skill: {skill_name}")
        print(f"Existing references: {len(existing_refs)}")
        print(f"Candidate references: {len(candidates)}")

    issues: list[dict] = []
    issues.extend(check_duplicates(existing_refs, candidates))
    issues.extend(check_broken_links(skill_dir, args.enrich, candidates))
    issues.extend(check_overlaps(existing_refs, candidates, threshold=args.overlap_threshold))
    issues.extend(check_missing_crosslinks(skill_dir, args.enrich, existing_refs, candidates))

    report = {
        "skill": skill_name,
        "skill_dir": str(skill_dir.resolve()),
        "enrich_dir": str(args.enrich.resolve()),
        "existing_reference_count": len(existing_refs),
        "candidate_count": len(candidates),
        "issues": issues,
    }

    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if args.verbose:
            print(f"\nReport written to {args.output}")

    return _print_report(issues, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
