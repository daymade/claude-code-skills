#!/usr/bin/env python3
"""Drift guard for human-facing README catalogs and CLAUDE.md authority.

The marketplace manifest is the single source of truth for which skills exist
(single-skill plugins + every suite's `skills` array, expanded). README.md and
README.zh-CN.md keep human-facing capability guides with unnumbered headings.
CLAUDE.md carries only a stable pointer to those sources.

This script reports, per README:
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
CLAUDE_AUTHORITY_SENTINEL = (
    "Current plugin names, versions, sources, and suite membership are defined only"
)


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
    """Skills referenced by an unnumbered level-three capability heading."""
    if not os.path.exists(path):
        return None
    txt = open(path, encoding="utf-8").read()
    found = set(re.findall(r"^\s*###\s+\*\*([a-zA-Z0-9_-]+)\*\*", txt, re.M))
    return found - PROSE_TOKENS


def numbered_skill_entries(path):
    if not os.path.exists(path):
        return []
    txt = open(path, encoding="utf-8").read()
    return re.findall(
        r"^\s*(?:###\s+)?\d+\.\s+\*\*([a-zA-Z0-9_-]+)\*\*",
        txt,
        re.M,
    )


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    authoritative = manifest_skills(repo)
    docs = {
        "README.md": os.path.join(repo, "README.md"),
        "README.zh-CN.md": os.path.join(repo, "README.zh-CN.md"),
    }
    print(f"Authoritative skills in marketplace.json: {len(authoritative)}")
    drift = False
    for name, path in docs.items():
        listed = doc_listed(path)
        if listed is None:
            print(f"\n{name}: NOT FOUND")
            drift = True
            continue
        numbered = [skill for skill in numbered_skill_entries(path) if skill in authoritative]
        if numbered:
            drift = True
            print(f"\n{name}: DERIVED NUMBERED HEADING")
            for skill in numbered:
                print(f"  - {skill}")
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

    claude_path = os.path.join(repo, "CLAUDE.md")
    if not os.path.exists(claude_path):
        print("\nCLAUDE.md: NOT FOUND")
        drift = True
    else:
        claude_text = open(claude_path, encoding="utf-8").read()
        claude_snapshot = [
            skill for skill in numbered_skill_entries(claude_path) if skill in authoritative
        ]
        authority_ok = (
            CLAUDE_AUTHORITY_SENTINEL in claude_text
            and "`.claude-plugin/marketplace.json`" in claude_text
            and "README.md / README.zh-CN.md" in claude_text
        )
        status = "OK" if authority_ok and not claude_snapshot else "DRIFT"
        print(f"\nCLAUDE.md authority pointer: {status}")
        if not authority_ok:
            drift = True
            print("  Missing the manifest authority and README guide pointer.")
        if claude_snapshot:
            drift = True
            print("  DERIVED SNAPSHOT (remove from model-loaded instructions):")
            for skill in claude_snapshot:
                print(f"    - {skill}")

    # A marketplace-version badge is a persisted copy of metadata.version.
    for name in ("README.md", "README.zh-CN.md"):
        path = os.path.join(repo, name)
        if not os.path.exists(path):
            continue
        m = re.search(r"version-(\d+\.\d+\.\d+)-", open(path, encoding="utf-8").read())
        if m:
            drift = True
            print(f"{name} marketplace-version badge: {m.group(1)} — DERIVED SNAPSHOT")
        else:
            print(f"{name} marketplace-version badge: absent — OK")

    if drift:
        print("\nResult: DRIFT — repair the reported documentation contract failures.")
        sys.exit(1)
    print("\nResult: README catalogs match marketplace.json; CLAUDE.md carries only the authority pointer.")


if __name__ == "__main__":
    main()
