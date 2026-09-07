#!/usr/bin/env python3
"""skill-install-audit.py — read-only reconciliation of every skill install surface.

One command that answers "which of my skills are actually usable where?" by joining
five layers that otherwise drift silently:

  1. REGISTRY   each local marketplace's .claude-plugin/marketplace.json
  2. INSTALLED  ~/.claude/plugins/installed_plugins.json  (shared via symlink)
  3. ENABLED    ~/.claude/settings.json enabledPlugins    (the authoritative map; profiles
                are converged onto it by claude-plugins-sync.py)
  4. CODEX      ~/.config/claude-switch-models-setup/codex-active-skills.json manifest vs
                the real ~/.agents/skills entries
  5. RUNTIME    the plugin version the background sync daemon actually executes, vs the
                version registered in the source marketplace
  6. FRESHNESS  whether the local checkouts every layer above is read from are themselves
                behind their already-fetched remote-tracking refs

Findings (each list is empty-friendly; a clean run prints only the summary):

  ENABLED                  installed + enabledPlugins true (visible in Claude Code)
  INSTALLED_DISABLED       installed, explicitly false in enabledPlugins
  INSTALLED_NO_KEY         installed, no enabledPlugins entry (NOT visible by default)
  REGISTERED_NOT_INSTALLED in a marketplace.json but never installed
  ORPHAN_INSTALLED         installed but no longer in any marketplace.json (loads nothing)
  DAEMON_RUNTIME_LAG       the sync daemon runs a pinned copy older than the source, so every
                           fix shipped to this repo stays invisible to it until the pin moves
  SOURCE_CHECKOUT_BEHIND   a registry checkout is behind its remote-tracking ref, so every
                           finding above was judged against a stale reference
  PROFILE_ONLY_RISK        enabledPlugins keys present in a profile but absent from main —
                           pre-fix these were wiped by the next mirror; now they are adopted
                           or preserved, but conflicts still deserve eyeballs
  MANUAL_LINK_RISK         absolute symlink owned by a successfully loaded source, but not
                           selected by activation policy -> the source-sync daemon will prune it;
                           ownership follows the source-sync classifier; relative links are preserved
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
import importlib.util
import json
import os
import re
import subprocess
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
# The background syncer deliberately executes a pinned plugin copy rather than a live
# checkout, so editing the source cannot change what a running daemon does. Nothing
# advances that pin automatically and nothing else compares the two numbers, so a fix
# can be merged, tested and believed shipped while the daemon keeps running the old one.
DAEMON_ENTRY = Path(
    os.environ.get(
        "SKILL_SYNC_DAEMON_ENTRY",
        str(HOME / ".config" / "claude-switch-models-setup" / "sync-local-skill-sources.py"),
    )
)
DAEMON_PLUGIN = "daymade-claude-code"


def source_sync():
    """Use the bundled activation owner's parser, including suite membership."""
    name = "skill_install_audit_source_sync"
    if name not in sys.modules:
        path = Path(__file__).with_name("sync-local-skill-sources.py")
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load source resolver: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def registered_sources():
    resolver = source_sync()
    return [resolver.load_marketplace(repo) for _, repo in REGISTRY_REPOS
            if (repo / ".claude-plugin" / "marketplace.json").is_file()]


def read_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate_plugin_identity(identity):
    if (not isinstance(identity, str) or identity.count("@") != 1
            or any(not part or part != part.strip() for part in identity.split("@"))):
        raise ValueError(f"invalid qualified plugin identity: {identity!r}")


def load_registry():
    """{marketplace_name: set(plugin_names)} for every local repo's marketplace.json."""
    registry = {}
    for label, repo in REGISTRY_REPOS:
        mp = repo / ".claude-plugin" / "marketplace.json"
        if not mp.exists():
            print(f"WARNING: {mp} missing; registry '{label}' skipped", file=sys.stderr)
            continue
        data = read_json(mp)
        name = data.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{mp}: missing marketplace name")
        if name in registry:
            raise ValueError(f"duplicate marketplace identity: {name}")
        registry[name] = {p["name"] for p in data["plugins"]}
    return registry


def load_installed():
    """Keep qualified identities; two marketplaces may install the same name."""
    installed = {}
    data = read_json(BASE / "plugins" / "installed_plugins.json")
    plugins = data.get("plugins", {})
    if not isinstance(plugins, dict):
        raise ValueError("installed_plugins.json: plugins must be an object")
    for key in plugins:
        validate_plugin_identity(key)
        name, _, mkt = key.rpartition("@")
        installed[key] = mkt
    return installed


def load_enabled():
    enabled = read_json(BASE / "settings.json").get("enabledPlugins", {})
    if not isinstance(enabled, dict):
        raise ValueError(f"{BASE / 'settings.json'}: enabledPlugins must be an object")
    for identity, value in enabled.items():
        validate_plugin_identity(identity)
        if not isinstance(value, bool):
            raise ValueError(f"enabledPlugins[{identity!r}] must be a boolean")
    return enabled


def load_codex():
    resolver = source_sync()
    policy = resolver.load_skill_activation_policy(CODEX_MANIFEST)
    manifest = set(policy.active_names)
    sources = registered_sources()
    found = {source.name for source in sources}
    unknown = set(policy.active_marketplaces) - found
    if unknown:
        raise ValueError(f"active marketplaces have no source: {', '.join(sorted(unknown))}")
    for source in sources:
        if source.name in policy.active_marketplaces:
            manifest.update(source.skills)
    registered = resolver.merge_source_skills(sources)
    pool = set()
    if AGENTS_SKILLS.is_dir():
        for entry in AGENTS_SKILLS.iterdir():
            if not (entry / "SKILL.md").is_file():
                continue
            if entry.name in manifest and entry.name not in registered:
                continue
            if entry.name in registered:
                try:
                    resolver.verify_selected_skill_links(
                        AGENTS_SKILLS, {entry.name: registered[entry.name]}
                    )
                except (OSError, RuntimeError):
                    continue
            pool.add(entry.name)
    return manifest, pool


def load_daemon_runtime_lag():
    """Compare the version the daemon executes against the source registry.

    Advisory only: returns [] when current, undeployed, or unparseable, so a machine
    that does not run this daemon never looks broken.
    """
    if not DAEMON_ENTRY.is_symlink():
        return []
    try:
        target = os.readlink(DAEMON_ENTRY)
    except OSError:
        return []
    match = re.search(rf"/{re.escape(DAEMON_PLUGIN)}/([^/]+)/", target)
    if not match:
        return []
    running = match.group(1)

    source = None
    for _label, repo in REGISTRY_REPOS:
        for plugin in read_json(repo / ".claude-plugin" / "marketplace.json").get("plugins", []):
            if plugin.get("name") == DAEMON_PLUGIN:
                source = plugin.get("version")
    if not source or source == running:
        return []

    def parts(value):
        try:
            return tuple(int(x) for x in value.split("."))
        except ValueError:
            return None

    running_parts, source_parts = parts(running), parts(source)
    if running_parts is None or source_parts is None or running_parts >= source_parts:
        return []
    return [
        f"{DAEMON_PLUGIN}: daemon runs {running}, source registers {source}. "
        f"Advance the pin against the daemon's own config dir "
        f"(`claude plugin marketplace update <mkt>` then `claude plugin update "
        f"{DAEMON_PLUGIN}@<mkt>`), then repoint the symlinks in "
        f"{DAEMON_ENTRY.parent} at the new version directory."
    ]


def load_source_checkout_freshness():
    """Report registry checkouts that lag the ref they were last fetched against.

    Every layer of this audit is judged against the working tree of a local repo.
    When that tree is behind, a daemon running the previous release and a checkout
    still on it agree with each other, and the report is clean while the published
    source has moved on. That silence is the failure this section exists to break.

    Reads only refs already on disk. Fetching here would make an audit fail on a
    flaky network, which is the one condition under which nobody would run it.

    Bounded deliberately: this reports a checkout that is behind *its own* upstream,
    which is a defect. A checkout sitting on a feature branch is ordinary work, and
    its tree can still differ from the published source — firing on that would make
    the section noise in a repository where branches are the normal state, and a
    section people learn to skip protects nothing.
    """
    behind = []
    for label, repo in REGISTRY_REPOS:
        if not (repo / ".git").exists():
            continue
        probe = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--count", "HEAD..@{upstream}"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            continue  # detached, no upstream, or never fetched: not a staleness claim
        try:
            count = int(probe.stdout.strip())
        except ValueError:
            continue
        if count:
            branch = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            behind.append(
                f"{label}: checkout on '{branch}' is {count} commit(s) behind its "
                f"upstream, so every finding here was judged against it rather than "
                f"the published source; `git -C {repo} pull --ff-only` and re-run"
            )
    return behind


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
    sources = registered_sources()
    installed = load_installed()
    enabled = load_enabled()
    manifest, pool = load_codex()
    profile_only = load_profile_only_keys()

    rows = []  # (name, marketplace, state, orphan)
    for identity, mkt in sorted(installed.items()):
        name = identity.rpartition("@")[0]
        if enabled.get(identity) is True:
            state = "ENABLED"
        elif enabled.get(identity) is False:
            state = "INSTALLED_DISABLED"
        else:
            state = "INSTALLED_NO_KEY"
        # True orphan = owned by a LOCAL managed repo yet absent from that repo's own
        # registry. Third-party marketplaces (official, baoyu, ...) are simply not
        # audited here — flagging them would be noise, not finding.
        orphan = mkt in registry and name not in registry[mkt]
        rows.append((identity, mkt, state, orphan))

    all_registered = {f"{name}@{market}" for market, names in registry.items() for name in names}
    registered_not_installed = sorted(all_registered - set(installed))
    orphans = sorted(r[0] for r in rows if r[3])
    manual_risk = []
    if AGENTS_SKILLS.is_dir():
        resolver = source_sync()
        with resolver.pin_skill_root(
            resolver.absolute_without_symlink_resolution(AGENTS_SKILLS),
            label="audit skill root", apply=False, create_missing=False,
        ) as root:
            if root is not None:
                for entry in os.scandir(root.fd):
                    snapshot = resolver.capture_entry_snapshot(root, entry.name)
                    target = snapshot.absolute_link_target if snapshot else None
                    # Use the same snapshot and ownership classifier as apply.
                    if (target is not None and entry.name not in manifest
                            and resolver.path_is_under(target, [source.repo for source in sources])):
                        manual_risk.append(entry.name)
    # Plugin names are not Skill names: a suite has multiple independently
    # discoverable members. Audit only registered owned members, not vendor
    # plugins whose inventory this tool never loaded.
    enabled_skill_names = {
        name for source in sources for name, skill in source.skills.items()
        if enabled.get(skill.plugin_id) is True
    }
    codex_unlisted = sorted(enabled_skill_names - manifest - pool)
    codex_missing = sorted(manifest - pool)

    return {
        "ENABLED": sorted(r[0] for r in rows if r[2] == "ENABLED"),
        "INSTALLED_DISABLED": sorted(r[0] for r in rows if r[2] == "INSTALLED_DISABLED"),
        "INSTALLED_NO_KEY": sorted(r[0] for r in rows if r[2] == "INSTALLED_NO_KEY"),
        "REGISTERED_NOT_INSTALLED": registered_not_installed,
        "ORPHAN_INSTALLED": orphans,
        "PROFILE_ONLY_RISK": profile_only,
        "MANUAL_LINK_RISK": sorted(manual_risk),
        "CODEX_UNLISTED_ENABLED": codex_unlisted,
        "CODEX_SELECTED_MISSING": codex_missing,
        "DAEMON_RUNTIME_LAG": load_daemon_runtime_lag(),
        "SOURCE_CHECKOUT_BEHIND": load_source_checkout_freshness(),
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
        "MANUAL_LINK_RISK -> add the name to codex-active-skills.json or drop the link; "
        "DAEMON_RUNTIME_LAG -> the daemon is executing code older than this repo; "
        "SOURCE_CHECKOUT_BEHIND -> this report's own reference is stale."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
