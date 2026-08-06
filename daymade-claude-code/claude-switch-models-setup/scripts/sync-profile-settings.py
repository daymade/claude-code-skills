#!/usr/bin/env python3
"""Converge Claude Code profile settings.json onto the main profile's.

Goal (2026-07-18, user directive): except for the model/provider, every
profile supports the same functionality as the main (official) profile —
same hooks, marketplaces, plugin set, env feature flags, permissions and
behavior preferences. The plugin STATE is already shared via symlinks
(plugins/{cache,data,installed_plugins.json}); this script converges the
CONFIG layer (settings.json), which is per-profile by design and had fully
drifted (9/9 profiles had zero hooks, 7/9 had zero marketplaces, all had
no env feature flags).

Two denylists define the identity boundary — these are NEVER synced:

1. DENYLIST top-level keys: the profile's provider identity (`model`).
2. ENV_KEY_DENYLIST env vars: provider-routing and Anthropic-native
   isolation flags. Provider routing lives in ~/.claude/settings/<name>.json
   (ANTHROPIC_MODEL / BASE_URL / AUTH_TOKEN per window), and third-party
   profiles deliberately run ENABLE_TOOL_SEARCH=false plus DISABLE_* flags
   because those features are Anthropic-native and fail with 400s against
   third-party endpoints. Syncing main's values over them breaks the
   isolation the profiles were built for — parity means "everything that
   CAN work there", not "smear Anthropic-only flags everywhere".

Merge rule: every key present in main's settings.json overwrites the
profile's, except denylisted ones; `env` is merged per-key with the env
denylist applied. Profile-only keys (absent from main) are PRESERVED —
sync is additive, never deletes; --check lists them so drift stays visible.

Modes:
  (no args)   SessionStart mode — sync the ACTIVE profile ($CLAUDE_CONFIG_DIR).
              No-op for the main profile itself. Silent when converged,
              one line when it synced. Never blocks (always exit 0).
  --all       sync every profile under ~/.claude-profiles/* (initial
              alignment and manual re-convergence).
  --check     report drift, no writes; exit 1 when drifted.

Backup: before each write, target is copied to settings.json.sync-backup
(single rolling file); writes are atomic (tmp + os.replace) and validated.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
MAIN_DIR = Path(os.environ.get("CLAUDE_MAIN_CONFIG_DIR", str(HOME / ".claude")))
PROFILES_ROOT = HOME / ".claude-profiles"
DENYLIST = {"model"}  # profile identity: the whole point of profiles
BACKUP_SUFFIX = ".sync-backup"


def _env_key_is_identity(key: str) -> bool:
    """Provider-routing and Anthropic-native isolation flags."""
    if key.startswith("ANTHROPIC_"):
        return True
    return key in {
        "CLAUDE_CODE_SUBAGENT_MODEL",
        "ENABLE_TOOL_SEARCH",
        "DISABLE_GROWTHBOOK",
        "DISABLE_TELEMETRY",
        "DISABLE_AUTOUPDATER",
    }


def merge_env(main_env: dict, prof_env: dict) -> dict:
    """Per-key env merge: main wins except for identity env vars."""
    return {k: v for k, v in main_env.items() if not _env_key_is_identity(k)}


def load(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def sync_profile(profile_dir: Path, write: bool):
    """Returns (changed_keys, profile_only_keys). Writes only if write=True."""
    target = profile_dir / "settings.json"
    main = load(MAIN_DIR / "settings.json")
    prof = load(target)
    changed = {}
    for k, v in main.items():
        if k in DENYLIST:
            continue
        if k == "env" and isinstance(v, dict):
            filtered = merge_env(v, prof.get("env", {}))
            if filtered and prof.get("env", {}) != {**prof.get("env", {}), **filtered}:
                changed[k] = {**prof.get("env", {}), **filtered}
            continue
        if prof.get(k) != v:
            changed[k] = v
    extra = sorted(set(prof) - set(main))
    if changed and write:
        merged = {**prof, **changed}
        if target.exists():
            shutil.copy2(target, target.with_suffix(target.suffix + BACKUP_SUFFIX))
        fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".settings-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, target)
        json.loads(target.read_text())  # validate the file we just wrote
    return sorted(changed), extra


def run() -> int:
    args = set(sys.argv[1:])
    check = "--check" in args
    if "--all" in args:
        dirs = sorted(p for p in PROFILES_ROOT.iterdir() if p.is_dir())
    else:
        active = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(MAIN_DIR)))
        if active.resolve() == MAIN_DIR.resolve():
            return 0  # main profile is the SSOT itself
        dirs = [active]
    drifted = False
    for d in dirs:
        changed, extra = sync_profile(d, write=not check)
        if changed:
            drifted = True
            verb = "drift" if check else "synced"
            suffix = "" if check else " (applies next session)"
            print(f"[{d.name}] {verb} {len(changed)} key(s): {', '.join(changed)}{suffix}")
        if extra and check:
            print(f"[{d.name}] profile-only keys (preserved): {', '.join(extra)}")
    return 1 if (check and drifted) else 0


if __name__ == "__main__":
    sys.exit(run())
