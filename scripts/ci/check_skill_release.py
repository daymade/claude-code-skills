"""Local pre-push check; private review evidence is deliberately not required in CI."""
import argparse
import json
import sys
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "daymade-skill/skill-creator/scripts"))
from release_readiness import git, verify, receipt_path, scope
from packaging_policy import should_exclude_skill_relative, inclusion_policy_metadata


def affected(repo, base, candidate):
    roots = set()
    for ref in (base, candidate):
        manifest = json.loads(git(repo, "show", ref + ":.claude-plugin/marketplace.json"))
        files = set(git(repo, "ls-tree", "-r", "--name-only", "-z", ref).split("\0"))
        for plugin in manifest["plugins"]:
            source = plugin["source"].removeprefix("./").rstrip("/")
            for child in plugin.get("skills") or [""]:
                root = source + ("/" + child.removeprefix("./").rstrip("/") if child else "")
                if root + "/SKILL.md" in files:
                    roots.add(root)
    changed = git(repo, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", base, candidate).split("\0")
    return sorted(r for r in roots if any(p.startswith(r + "/") and not should_exclude_skill_relative(Path(p[len(r)+1:]), policy=inclusion_policy_metadata()) for p in changed))


def integrated_base(repo, base, candidate):
    """Diagnose integration drift before it looks like somebody else's review gap.

    Keep affected() two-point: it describes the actual publication tree. Once
    current main is an ancestor, that scope is also the candidate's own change.
    """
    base_commit = git(repo, "rev-parse", base + "^{commit}")
    candidate_commit = git(repo, "rev-parse", candidate + "^{commit}")
    common = git(repo, "merge-base", base_commit, candidate_commit)
    if common != base_commit:
        raise ValueError(
            f"candidate does not include current base {base_commit}; integrate the "
            "current main tree and rerun version progression before binding review "
            "evidence to the resulting exact candidate (this is integration drift, "
            "not a request to review main's unrelated Skills)"
        )



def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--base", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--projected-merge", action="store_true")
    a = p.parse_args()
    try:
        if a.projected_merge:
            from git_projection import projected_merge
            base, candidate, projected = projected_merge(a.repo, a.base, a.candidate)
            paths = affected(a.repo, base, projected)
            if paths:
                record = json.loads(receipt_path(a.repo, candidate).read_text())
                if not isinstance(record, dict):
                    raise ValueError("exact source receipt must be an object")
                declared = scope(record.get("skill_paths"))
                verified = verify(a.repo, candidate, declared)
                if not set(paths).issubset(scope(verified.get("skill_paths"))):
                    raise ValueError("exact source review does not cover all projected shipped Skill changes")
            label = f"branch projection {projected} onto {base}; exact source {candidate}; "
        else:
            integrated_base(a.repo, a.base, a.candidate)
            paths = affected(a.repo, a.base, a.candidate)
            if paths:
                verify(a.repo, a.candidate, paths)
            label = ""
        print("skill release check OK: " + label + (", ".join(paths) or "no shipped Skill changes"))
    except (ValueError, OSError, TypeError, IndexError, ImportError) as e:
        p.exit(2, f"skill release blocked: {e}; use skill-creator/scripts/release_readiness.py attest for this exact head\n")


if __name__ == "__main__":
    main()
