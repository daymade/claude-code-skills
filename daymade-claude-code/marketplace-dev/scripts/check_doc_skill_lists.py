#!/usr/bin/env python3
"""Drift guard: keep the skill lists in CLAUDE.md / README.md / README.zh-CN.md
in sync with the authoritative source (.claude-plugin/marketplace.json).

The marketplace manifest is the single source of truth for which skills exist
(single-skill plugins + every suite's `skills` array, expanded). The three
human-facing docs each maintain their own numbered skill list, and those lists
drift over time — skills get added to the manifest but not the docs, or a skill
is deleted but its doc entry lingers as a ghost.

This script reports, per document:
  - MISSING: skills in the manifest but absent from that doc's list
  - GHOST:   skills listed in that doc but not in the manifest (deleted/renamed)

Exit code is non-zero when any drift is found, so it can gate CI / pre-push.

Usage:
  check_doc_skill_lists.py [repo_root]      # defaults to two levels up
"""
import json
import os
import re
import sys

# A few bold tokens in prose match the "**name**" list pattern but are not
# skills. Ignore them so they don't show up as false GHOSTs.
PROSE_TOKENS = {"Metadata", "gitleaks", "Unreleased"}


def manifest_skills(repo):
    d = json.load(open(os.path.join(repo, ".claude-plugin", "marketplace.json")))
    skills = set()
    for p in d["plugins"]:
        if p.get("skills"):
            for s in p["skills"]:
                skills.add(s.strip("./").split("/")[-1])
        else:
            skills.add(p["source"].strip("./").split("/")[-1])
    return skills


def doc_listed(path):
    """Skills referenced in a numbered list line: `### 12. **name**` or `12. **name**`."""
    if not os.path.exists(path):
        return None
    txt = open(path, encoding="utf-8").read()
    found = set(re.findall(r"^\s*#*\s*\d+\.\s+\*\*([a-zA-Z0-9_-]+)\*\*", txt, re.M))
    return found - PROSE_TOKENS


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    authoritative = manifest_skills(repo)
    docs = {
        "CLAUDE.md": os.path.join(repo, "CLAUDE.md"),
        "README.md": os.path.join(repo, "README.md"),
        "README.zh-CN.md": os.path.join(repo, "README.zh-CN.md"),
    }
    print(f"Authoritative skills in marketplace.json: {len(authoritative)}")
    drift = False
    for name, path in docs.items():
        listed = doc_listed(path)
        if listed is None:
            print(f"\n{name}: NOT FOUND")
            continue
        missing = sorted(authoritative - listed)
        ghost = sorted(listed - authoritative)
        status = "OK" if not (missing or ghost) else "DRIFT"
        print(f"\n{name}: {len(listed)} listed — {status}")
        if missing:
            drift = True
            print("  MISSING (in manifest, not in doc):")
            for s in missing:
                print(f"    - {s}")
        if ghost:
            drift = True
            print("  GHOST (in doc, not in manifest):")
            for s in ghost:
                print(f"    - {s}")

    # Version-badge coherence: the README version badge must equal the manifest's
    # metadata.version. This badge is a derived value that has silently drifted
    # twice (1.63->1.64, 1.64->1.65) when a metadata bump forgot to move the badge,
    # so the drift guard now asserts it instead of leaving it to manual discipline.
    meta_version = json.load(
        open(os.path.join(repo, ".claude-plugin", "marketplace.json"))
    )["metadata"]["version"]
    print(f"\nmarketplace metadata.version: {meta_version}")
    for name in ("README.md", "README.zh-CN.md"):
        path = os.path.join(repo, name)
        if not os.path.exists(path):
            continue
        m = re.search(r"version-(\d+\.\d+\.\d+)-", open(path, encoding="utf-8").read())
        badge = m.group(1) if m else "(none)"
        if badge != meta_version:
            drift = True
            print(f"{name} version badge: {badge} — DRIFT (expected {meta_version})")
        else:
            print(f"{name} version badge: {badge} — OK")

    if drift:
        print("\nResult: DRIFT — sync the doc lists with marketplace.json.")
        sys.exit(1)
    print("\nResult: all doc skill lists are in sync with marketplace.json.")


if __name__ == "__main__":
    main()
