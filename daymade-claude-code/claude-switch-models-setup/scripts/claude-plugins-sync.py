#!/usr/bin/env python3
"""
Claude Code multi-profile plugin sync (replaces the old fix-marketplace-paths.py).

WHY THIS EXISTS
---------------
Claude Code validates a marketplace's installLocation with `path.resolve()`, which
normalises a path string but does NOT resolve symlinks. The check is roughly:

    c = path.resolve(<CURRENT_CONFIG_DIR>/plugins/marketplaces)
    u = path.resolve(installLocation)
    if (u !== c && !u.startsWith(c + sep)) -> "corrupted installLocation"

Each profile runs with its own CLAUDE_CONFIG_DIR, so `c` is a DIFFERENT literal string
per profile (~/.claude/... vs ~/.claude-profiles/kimi/... vs ~/.claude-profiles/deepseek/...),
and none is a prefix of another. Therefore a single SHARED known_marketplaces.json can
never satisfy more than one profile at a time.

If you symlink the whole plugins/ dir across profiles (the naive "install once, share
everywhere" approach), every profile ends up pointing at ONE physical
known_marketplaces.json, and whichever profile last wrote it wins — every OTHER profile
plus the default config then reports "corrupted installLocation". (The old
fix-marketplace-paths.py made this worse, not better: it rewrote that shared file to one
profile's prefix on every launch.)

THE FIX (idempotent)
--------------------
- Marketplace CONTENT stays shared (plugins/marketplaces, cache, data, ...): one copy on
  disk, symlinked into each profile -> still "install once, all profiles see it".
- known_marketplaces.json becomes PER-PROFILE and independent: each profile's copy stores
  installLocation with ITS OWN config-dir prefix, so each profile validates against itself
  and never corrupts.

Each ~/.claude-profiles/<p>/plugins becomes a REAL directory:
    marketplaces -> symlink ~/.claude/plugins/marketplaces   (shared content)
    cache        -> symlink ~/.claude/plugins/cache          (shared content)
    ... every other item -> symlink ~/.claude/plugins/<item>
    known_marketplaces.json  = independent real file (this profile's prefix)

~/.claude (the default profile / real plugins store) is never restructured; only its
known_marketplaces.json is canonicalised to the ~/.claude prefix.

Usage:
    python3 claude-plugins-sync.py            # apply
    python3 claude-plugins-sync.py --dry-run  # preview

Run automatically by claude-profile() at init and launch. Safe to run any time.

Env overrides (match claude-profiles.sh):
    CLAUDE_BASE_DIR       default ~/.claude
    CLAUDE_PROFILES_DIR   default ~/.claude-profiles
"""

import json
import os
import sys
import time
from pathlib import Path

BASE = Path(os.environ.get("CLAUDE_BASE_DIR", str(Path.home() / ".claude")))
BASE_PLUGINS = BASE / "plugins"
PROFILES_DIR = Path(os.environ.get("CLAUDE_PROFILES_DIR", str(Path.home() / ".claude-profiles")))
KM = "known_marketplaces.json"
MARKER = "/plugins/marketplaces/"

DRY = "--dry-run" in sys.argv or "-n" in sys.argv


def log(*a):
    print(*a)


def err(*a):
    print(*a, file=sys.stderr)


def shared_item_names():
    """Items under <base>/plugins to share (symlink) into each profile.
    Excludes the per-profile known_marketplaces.json and any *.bak* / pre-sync backups."""
    names = []
    for entry in os.scandir(BASE_PLUGINS):
        if entry.name == KM:
            continue
        if ".bak" in entry.name or entry.name.startswith("plugins.pre-sync-"):
            continue
        names.append(entry.name)
    return names


def _merge_entries(entries: dict, d):
    if isinstance(d, dict):
        for name, entry in d.items():
            if name not in entries and isinstance(entry, dict):
                entries[name] = entry


def collect_canonical():
    """Union of marketplace entries across default + all profiles (default wins on conflict).
    Captured BEFORE any restructuring so independent profile JSONs aren't lost.
    installLocation in the templates is irrelevant: it is rewritten per target below.

    BY DESIGN the marketplace SET is unified across profiles (install once -> every profile
    sees it). A consequence: a marketplace removed from one profile is re-added from the
    union on the next sync. Per-profile *different* marketplace sets are intentionally not
    supported — that matches the "install once, shared everywhere" goal of this setup.

    The default (~/.claude) KM is AUTHORITATIVE and REQUIRED to parse — a read/parse error
    propagates (NO silent fallback). Otherwise we would build a partial union and then
    overwrite the default file with it, silently dropping the user's marketplaces. Profile
    KMs are only supplementary, so an unreadable one is tolerated."""
    entries = {}
    # default: let JSONDecodeError/OSError propagate (caller refuses to write on failure)
    with open(BASE_PLUGINS / KM, encoding="utf-8") as fh:
        _merge_entries(entries, json.load(fh))
    # profiles: supplementary — tolerate unreadable ones
    if PROFILES_DIR.is_dir():
        for pd in sorted(PROFILES_DIR.iterdir()):
            if not pd.is_dir():
                continue
            f = pd / "plugins" / KM
            if not f.exists():
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    _merge_entries(entries, json.load(fh))
            except (json.JSONDecodeError, OSError):
                continue
    return entries


def is_new_structure(plugins: Path) -> bool:
    """True if plugins is already the per-profile structure: a REAL dir (not a symlink)
    holding a REAL per-profile known_marketplaces.json. We deliberately do NOT require a
    `marketplaces` symlink: a user with no installed marketplaces has no marketplaces/ in
    the base store, so requiring it would mis-classify an already-migrated profile as 'old'
    on every launch and re-rename it into a fresh pre-sync backup forever (unbounded growth)."""
    if plugins.is_symlink() or not plugins.is_dir():
        return False
    km = plugins / KM
    return km.is_file() and not km.is_symlink()


def ensure_structure(profile_dir: Path):
    """Make profile_dir/plugins the per-profile structure. Safe & idempotent.
    NEVER touches <base> (the real store)."""
    plugins = profile_dir / "plugins"
    name = profile_dir.name

    if plugins.is_symlink():
        # Old whole-dir symlink -> remove the LINK only (never the target / real store).
        tgt = os.readlink(plugins)
        log(f"  [{name}] migrate: old symlink plugins -> {tgt} (removing link)")
        if not DRY:
            plugins.unlink()
    elif plugins.is_dir() and not is_new_structure(plugins):
        # Old real dir residue -> rename to backup, never delete.
        bak = profile_dir / f"plugins.pre-sync-{time.strftime('%Y%m%d-%H%M%S')}"
        log(f"  [{name}] migrate: old real plugins dir -> backup {bak.name}")
        if not DRY:
            plugins.rename(bak)
    elif is_new_structure(plugins):
        log(f"  [{name}] already new structure (refreshing content symlinks)")

    if not DRY:
        plugins.mkdir(parents=True, exist_ok=True)

    for item in shared_item_names():
        link = plugins / item
        src = BASE_PLUGINS / item
        if DRY:
            if not (link.is_symlink() or link.exists()):
                log(f"      + symlink {item}")
            continue
        if link.is_symlink():
            if os.readlink(link) != str(src):
                link.unlink()
                link.symlink_to(src)
        elif link.exists():
            log(f"      ! {item} is a real file/dir (unexpected) — left as-is for manual review")
        else:
            link.symlink_to(src)

    # Prune stale links whose base-store source disappeared (e.g. a marketplace removed
    # from ~/.claude/plugins): an orphaned symlink into the base store would otherwise
    # linger in every profile and trip claude-profiles-doctor's broken-symlink check.
    if not DRY:
        for entry in os.scandir(plugins):
            if entry.name == KM:
                continue
            if entry.is_symlink() and not os.path.exists(entry.path):  # dangling (target gone)
                if os.readlink(entry.path).startswith(str(BASE_PLUGINS)):
                    os.unlink(entry.path)
                    log(f"      - pruned dangling symlink {entry.name}")


def rewrite_loc(loc: str, target_marketplaces: str) -> str:
    """Repoint a .../plugins/marketplaces/<suffix> installLocation to this target.
    Directory-source marketplaces (no /plugins/marketplaces/ segment) are returned unchanged."""
    i = loc.find(MARKER)
    if i == -1:
        return loc
    suffix = loc[i + len(MARKER):]
    return f"{target_marketplaces}/{suffix}"


def write_profile_json(config_dir: Path, canonical: dict):
    """Write config_dir/plugins/known_marketplaces.json with this config dir's own prefix."""
    plugins = config_dir / "plugins"
    target_mk = str(plugins / "marketplaces")
    data = {}
    for name, entry in canonical.items():
        e = json.loads(json.dumps(entry))  # deep copy
        if "installLocation" in e:
            e["installLocation"] = rewrite_loc(e["installLocation"], target_mk)
        data[name] = e
    out = plugins / KM
    if DRY:
        log(f"  [{config_dir.name}] would write {len(data)} marketplaces -> {out}")
        return
    tmp = out.with_name(out.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, out)  # atomic — concurrent launches never see a half-written file


def _target_profile():
    """Optional `--profile <name>` limits structure+write to that ONE profile (used at
    launch — only the profile being started needs syncing, which also shrinks the
    concurrent-write surface). Without it, all profiles are synced (init)."""
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == "--profile" and i + 1 < len(argv):
            return argv[i + 1]
    return None


def main():
    if not (BASE_PLUGINS / KM).exists():
        log(f"No canonical {KM} at {BASE_PLUGINS}; nothing to do.")
        return

    try:
        canonical = collect_canonical()
    except (json.JSONDecodeError, OSError) as e:
        # NO FALLBACK: refuse to sync rather than overwrite the default KM with a partial set.
        err(f"ERROR: default {KM} unreadable ({e}); refusing to sync. Fix/restore it first.")
        return
    log(f"canonical: {len(canonical)} marketplace(s) (union of default + profiles)")

    # 1) default (~/.claude): canonicalise its JSON only, never restructure the real store.
    write_profile_json(BASE, canonical)
    log(f"  [default] synced {BASE_PLUGINS / KM}")

    # 2) profiles: ensure structure + write own JSON (one if --profile given, else all).
    target = _target_profile()
    if PROFILES_DIR.is_dir():
        for profile_dir in sorted(PROFILES_DIR.iterdir()):
            if not profile_dir.is_dir():
                continue
            if target and profile_dir.name != target:
                continue
            ensure_structure(profile_dir)
            write_profile_json(profile_dir, canonical)

    log("Done." + (" (dry-run)" if DRY else ""))


if __name__ == "__main__":
    main()
