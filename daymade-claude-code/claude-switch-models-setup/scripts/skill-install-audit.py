#!/usr/bin/env python3
"""skill-install-audit.py — read-only reconciliation of every skill install surface.

One command that answers "which of my skills are actually usable where?" by joining
four layers that otherwise drift silently:

  1. REGISTRY   each local marketplace's .claude-plugin/marketplace.json
  2. INSTALLED  ~/.claude/plugins/installed_plugins.json  (shared via symlink)
  3. ENABLED    ~/.claude/settings.json enabledPlugins    (the authoritative map; profiles
                are converged onto it by claude-plugins-sync.py)
  4. CODEX      ~/.config/claude-switch-models-setup/codex-active-skills.json manifest vs
                the real ~/.agents/skills entries

Findings (each list is empty-friendly; a clean run prints only the summary):

  ENABLED                  installed + enabledPlugins true (visible in Claude Code)
  INSTALLED_DISABLED       installed, explicitly false in enabledPlugins
  INSTALLED_NO_KEY         installed, no enabledPlugins entry (NOT visible by default)
  REGISTERED_NOT_INSTALLED in a marketplace.json but never installed
  ORPHAN_INSTALLED         installed but no longer in any marketplace.json (loads nothing)
  PROFILE_ONLY_RISK        enabledPlugins keys present in a profile but absent from main —
                           pre-fix these were wiped by the next mirror; now they are adopted
                           or preserved, but conflicts still deserve eyeballs
  MANUAL_LINK_RISK         ~/.agents/skills symlink pointing into a managed repo but its
                           name is absent from codex-active-skills.json -> the source-sync
                           daemon will prune it
  CODEX_UNLISTED_ENABLED   enabled in Claude yet absent from both the Codex manifest and
                           ~/.agents/skills (fine if unwanted in Codex; informational)

Usage:
    python3 skill-install-audit.py            # human-readable report
    python3 skill-install-audit.py --json     # machine-readable
    python3 skill-install-audit.py --list ENABLED INSTALLED_DISABLED

Env overrides (match the sibling sync scripts):
    CLAUDE_BASE_DIR / CLAUDE_PROFILES_DIR / AGENTS_SKILLS_DIR
"""

import argparse
import json
import os
import sys
from pathlib import Path

HOME = Path.home()
BASE = Path(os.environ.get("CLAUDE_BASE_DIR", str(HOME / ".claude")))
PROFILES_DIR = Path(os.environ.get("CLAUDE_PROFILES_DIR", str(HOME / ".claude-profiles")))
AGENTS_SKILLS = Path(os.environ.get("AGENTS_SKILLS_DIR", str(HOME / ".agents" / "skills")))
CODEX_MANIFEST = Path(
    os.environ.get(
        "CODEX_ACTIVE_SKILLS",
        str(HOME / ".config" / "claude-switch-models-setup" / "codex-active-skills.json"),
    )
)

# Local marketplace repos: (label, repo root). Directory-source marketplaces only —
# GitHub-sourced marketplaces are third-party and out of scope for this audit.
REGISTRY_REPOS = [
    ("daymade-skills", HOME / "workspace" / "md" / "claude-code-skills"),
    ("daymade-skills-pro", HOME / "workspace" / "md" / "claude-code-skills-pro"),
    ("cemakanshan-skills", HOME / "workspace" / "md" / "cemakanshan-skills"),
]
MANAGED_REPO_PREFIXES = tuple(str(repo.resolve()) for _l, repo in REGISTRY_REPOS)


def read_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_registry():
    """{marketplace_name: set(plugin_names)} for every local repo's marketplace.json."""
    registry = {}
    for label, repo in REGISTRY_REPOS:
        mp = repo / ".claude-plugin" / "marketplace.json"
        if not mp.exists():
            print(f"WARNING: {mp} missing; registry '{label}' skipped", file=sys.stderr)
            continue
        registry[label] = {p["name"] for p in read_json(mp)["plugins"]}
    return registry


def load_installed():
    """{plugin_name: marketplace_name} from installed_plugins.json (latest entry wins)."""
    installed = {}
    data = read_json(BASE / "plugins" / "installed_plugins.json")
    for key in data.get("plugins", {}):
        name, _, mkt = key.rpartition("@")
        installed[name] = mkt
    return installed


def load_enabled():
    enabled = read_json(BASE / "settings.json").get("enabledPlugins", {})
    if not isinstance(enabled, dict):
        raise ValueError(f"{BASE / 'settings.json'}: enabledPlugins must be an object")
    return enabled


def load_codex():
    manifest = set(read_json(CODEX_MANIFEST).get("active_skills", []))
    pool = set()
    if AGENTS_SKILLS.is_dir():
        pool = {e.name for e in AGENTS_SKILLS.iterdir()}
    return manifest, pool


def load_profile_only_keys():
    main_keys = set(load_enabled())
    drift = {}  # profile -> [keys]
    if not PROFILES_DIR.is_dir():
        return drift
    for pd in sorted(PROFILES_DIR.iterdir()):
        if not pd.is_dir() or pd == BASE:
            continue
        f = pd / "settings.json"
        if not f.exists():
            continue
        try:
            ep = read_json(f).get("enabledPlugins", {})
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(ep, dict):
            extra = sorted(k for k in ep if k not in main_keys)
            if extra:
                drift[pd.name] = extra
    return drift


def audit():
    registry = load_registry()
    installed = load_installed()
    enabled = load_enabled()
    manifest, pool = load_codex()
    profile_only = load_profile_only_keys()

    enabled_names = {n for n, v in ((k.rpartition("@")[0], v) for k, v in enabled.items()) if v}
    disabled_names = {k.rpartition("@")[0] for k, v in enabled.items() if not v}

    rows = []  # (name, marketplace, state, orphan)
    for name, mkt in sorted(installed.items()):
        if name in enabled_names:
            state = "ENABLED"
        elif name in disabled_names:
            state = "INSTALLED_DISABLED"
        else:
            state = "INSTALLED_NO_KEY"
        # True orphan = owned by a LOCAL managed repo yet absent from that repo's own
        # registry. Third-party marketplaces (official, baoyu, ...) are simply not
        # audited here — flagging them would be noise, not finding.
        orphan = mkt in registry and name not in registry[mkt]
        rows.append((name, mkt, state, orphan))

    all_registered = set().union(*registry.values()) if registry else set()
    registered_not_installed = sorted(all_registered - set(installed))
    orphans = sorted(r[0] for r in rows if r[3])
    manual_risk = []
    if AGENTS_SKILLS.is_dir():
        for e in AGENTS_SKILLS.iterdir():
            if not e.is_symlink():
                continue
            try:
                target = Path(os.readlink(e))
            except OSError:
                continue
            resolved = target if target.is_absolute() else (AGENTS_SKILLS / target)
            if str(resolved).startswith(MANAGED_REPO_PREFIXES) and e.name not in manifest:
                manual_risk.append(e.name)
    codex_unlisted = sorted(
        n for n in enabled_names if n not in manifest and n not in pool
    )

    return {
        "ENABLED": sorted(r[0] for r in rows if r[2] == "ENABLED"),
        "INSTALLED_DISABLED": sorted(r[0] for r in rows if r[2] == "INSTALLED_DISABLED"),
        "INSTALLED_NO_KEY": sorted(r[0] for r in rows if r[2] == "INSTALLED_NO_KEY"),
        "REGISTERED_NOT_INSTALLED": registered_not_installed,
        "ORPHAN_INSTALLED": orphans,
        "PROFILE_ONLY_RISK": profile_only,
        "MANUAL_LINK_RISK": sorted(manual_risk),
        "CODEX_UNLISTED_ENABLED": codex_unlisted,
    }


def main():
    ap = argparse.ArgumentParser(description="Read-only skill install surface audit")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    ap.add_argument(
        "--list", nargs="+", metavar="SECTION",
        help="print only these sections' name lists (e.g. --list INSTALLED_DISABLED)",
    )
    args = ap.parse_args()

    result = audit()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.list:
        for section in args.list:
            if section not in result:
                print(f"unknown section: {section}", file=sys.stderr)
                return 2
            print(f"== {section}")
            for name in result[section]:
                print(f"  {name}" if isinstance(name, str) else f"  {name}")
        return 0

    print("== skill install audit ==")
    for section, names in result.items():
        if isinstance(names, dict):
            if names:
                print(f"\n[{section}]")
                for prof, keys in names.items():
                    print(f"  {prof}: {', '.join(keys)}")
            else:
                print(f"\n[{section}] clean")
        else:
            print(f"\n[{section}] ({len(names)})")
            for name in names:
                print(f"  {name}")
    print(
        "\nLegend: DISABLED/NO_KEY -> enable via `claude plugin enable NAME@mkt`; "
        "REGISTERED_NOT_INSTALLED -> `claude plugin install NAME@mkt`; "
        "MANUAL_LINK_RISK -> add the name to codex-active-skills.json or drop the link."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
