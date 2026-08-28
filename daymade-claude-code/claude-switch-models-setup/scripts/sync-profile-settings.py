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
denylist applied. Profile-only TOP-LEVEL keys (absent from main) are
PRESERVED — sync is additive at the top level and never deletes them;
--check lists them so drift stays visible. Nested collections inside a
key main also has (permissions.allow, enabledPlugins, ...) are NOT
preserved item-by-item: the whole key converges to main's value, and any
profile-only nested entries dropped that way are listed (detail under
--check, count on write) so the loss is visible, never silent.

--- Layer 2: per-profile `.claude.json` behavior keys (added 2026-08-17) ---

settings.json is not the only per-profile config layer. Claude Code also
keeps a `<config-dir>/.claude.json` per profile (`~/.claude.json` for the
main one), and a handful of BEHAVIOR settings live only there — e.g.
`workflowSizeGuideline`. On 2026-08-17 that key was set to "small" on the
main profile while 10/11 third-party profiles had no copy at all; a Kimi
session then fanned a Dynamic Workflow out to 30+ agents with no size
guidance in its system prompt. So this script ALSO converges the behavior
slice of each profile's `.claude.json`.

That file mixes three kinds of keys, and the classifier — not a hand
maintained full list — is the safety mechanism, because new keys appear
with every Claude Code release and a whitelist of "known behavior keys"
alone would silently miss the next one:

1. BEHAVIOR_KEYS (explicit allowlist) — synced main -> profile.
2. State keys (is_state_key(): prefixes/substrings/exact names) — per-
   profile runtime state, caches, counters, migration flags, identity and
   credentials. NEVER synced; syncing them would smear one profile's
   session state or account identity onto another.
3. Everything else is GRAY: if main and a profile differ on a gray key,
   the drift is REPORTED (never auto-written) — one line per drifted key
   per run, until a human classifies it: move it into BEHAVIOR_KEYS,
   teach is_state_key() its pattern, or park it in GRAY_ACKNOWLEDGED
   with a reason. This is the tripwire that surfaces the next
   `workflowSizeGuideline` the day it appears, instead of after the
   next incident.

Write-safety for this layer, measured before shipping (2026-08-17): a
marker key written into an ACTIVE profile's `.claude.json` survived 30+
minutes of the running harness rewriting the file — writes are merged,
not full-file clobbers, and SessionStart re-runs make the sync convergent
regardless. Backup + atomic replace + post-write validation apply here
too; the main profile's own `.claude.json` is never written (it is the
SSOT), and a profile missing `.claude.json` is skipped, never created.

Modes:
  (no args)   SessionStart mode — sync the ACTIVE profile ($CLAUDE_CONFIG_DIR).
              No-op for the main profile itself. Silent when converged,
              one line when it synced. Never blocks the session: unexpected
              exceptions print a traceback and still exit 0 in this mode
              (interactive --check/--all runs exit nonzero instead).
  --all       sync every profile under ~/.claude-profiles/* (initial
              alignment and manual re-convergence). Dot-prefixed archive
              dirs (e.g. .archived-profiles) are skipped.
  --check     report drift, no writes; exit 1 when drifted, exit 2 when a
              main file is corrupt (a corrupt main reads as empty and would
              otherwise fake-green the audit).

Asymmetry worth knowing when maintaining this: the settings.json layer
CREATES a profile's settings.json if missing (pure config, harmless), while
the .claude.json layer SKIPS a missing file (the harness creates it on first
launch, and it carries identity/session state a sync must not fabricate).
Also, no-args mode syncs whatever directory CLAUDE_CONFIG_DIR points at —
it does not require the dir to live under PROFILES_ROOT.

Backup: before each write, target is copied to <file>.sync-backup
(single rolling file, chmod 600 regardless of source permissions); writes
are atomic (tmp + os.replace) and validated.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
MAIN_DIR = Path(os.environ.get("CLAUDE_MAIN_CONFIG_DIR", str(HOME / ".claude")))
PROFILES_ROOT = Path(os.environ.get("CLAUDE_PROFILES_ROOT", str(HOME / ".claude-profiles")))
# Profile identity keys: `model` is the whole point of profiles; `advisorModel`
# is Anthropic-model routing — third-party endpoints don't serve its literal
# value (e.g. "fable"), same isolation class as CLAUDE_CODE_SUBAGENT_MODEL.
DENYLIST = {"model", "advisorModel"}
BACKUP_SUFFIX = ".sync-backup"

# The harness's per-config state file lives at an ASYMMETRIC path (verified
# on disk 2026-08-17): the main profile's is `~/.claude.json` (sibling of
# the config dir), while each third-party profile's is INSIDE its config
# dir (`~/.claude-profiles/<name>/.claude.json`). A stale pre-migration
# copy at `~/.claude/.claude.json` (April) is NOT the live file.
MAIN_JSON = MAIN_DIR.parent / f"{MAIN_DIR.name}.json"

# ---------------------------------------------------------------------------
# Layer 2: `.claude.json` behavior-key convergence.
#
# BEHAVIOR_KEYS is an ALLOWLIST of confirmed behavior settings — keys whose
# value a user sets once and expects everywhere. Each entry must carry a
# one-line reason so future classifiers can re-derive the intent.
# Calibrated against the live key census on 2026-08-17: main's file held
# 102 keys, classified 7 behavior / 91 state / 4 acknowledged-gray /
# 0 unclassified (reproduce: classify every top-level key of ~/.claude.json
# with BEHAVIOR_KEYS + is_state_key() + GRAY_ACKNOWLEDGED).
# ---------------------------------------------------------------------------
BEHAVIOR_KEYS = {
    # Workflow fan-out scale guidance injected into the system prompt; absent
    # in 10/11 profiles on 2026-08-17 and a Kimi session fanned one Dynamic
    # Workflow out to 30+ agents with no constraint.
    "workflowSizeGuideline",
    # Pure UI / interaction preferences with identical meaning per profile:
    "agentPushNotifEnabled",   # push notification when an agent needs input
    "preferredNotifChannel",   # notification sink (e.g. ghostty)
    "showSpinnerTree",         # spinner rendering style
    "fleetViewGroupMode",      # agent fleet view grouping
    "prStatusFooterEnabled",   # PR status in the footer
    "deepLinkTerminal",        # terminal for deep links
}

# Keys a sync must NEVER touch: per-profile runtime state, caches, counters,
# migration/one-shot flags, identity and credentials. Patterns first, exact
# names for the irregular ones. Syncing these would smear one profile's
# session state — or the main profile's account identity — onto another.
#
# Known blind spot (accepted, fail-safe direction): the substring patterns
# (last/tip/count/seen/usage/token/...) can also match a FUTURE behavior key
# whose name happens to contain one (e.g. a hypothetical `showUsageFooter`).
# Such a key is then silently never synced AND never tripwire-reported. The
# failure direction is safe (no state smearing), and the backstop is a
# periodic manual census — classify every top-level key of ~/.claude.json
# with the three buckets and eyeball the state bucket for preference-looking
# names. Widening the tripwire to cover these would fire on healthy state
# keys constantly (hasUsedStash et al.) and train the report into noise.
STATE_EXACT = {
    "projects", "mcpServers", "userID", "machineID", "oauthAccount",
    "companion", "chromeExtension", "githubRepoPaths", "replBridgePlaceholders",
    "claudeAiMcpEverConnected", "claudeCodeFirstTokenDate", "firstStartTime",
    "installMethod", "officialMarketplaceAutoInstallAttempted",
    "officialMarketplaceAutoInstalled", "autoUpdatesProtectedForNative",
    "penguinModeOrgEnabled", "agentLastUsed", "skillUsage", "pluginUsage",
    "seenNotifications", "tipsHistory", "tipLifetimeShownCounts",
    "announcementImpressions", "clientDataCacheSlots", "groveConfigCache",
    "fotwUpsellFulfilled",
}
STATE_PREFIX = ("cached", "has", "num", "unpin", "remotecontrol")
STATE_SUBSTR = (
    "cache", "count", "seen", "dismissed", "fulfilled", "impressions",
    "watermark", "upsell", "nudge", "usage", "oauth", "apikey", "last",
    "tip", "token", "credential", "secret", "migration", "declin",
)

# Gray keys a human already classified as "deliberately not synced", with the
# reason — they stay silent. A gray key NOT in this set gets reported once
# per profile until someone classifies it; that report is the tripwire.
GRAY_ACKNOWLEDGED = {
    # settings.json carries the same name with a CONFLICTING value; which
    # layer actually wins is unverified, so auto-writing it is a guess.
    "autoCompactEnabled",
    # Third-party profiles already force this off via DISABLE_AUTOUPDATER=1
    # in their provider settings; the .claude.json flag is redundant there.
    "autoUpdates",
    # Model routing is provider identity (same boundary as ANTHROPIC_MODEL).
    "teammateDefaultModel",
    # Chrome-extension pairing is an Anthropic-account feature, meaningless
    # against third-party endpoints.
    "claudeInChromeDefaultEnabled",
}


# Provider-routing and Anthropic-native isolation env vars — the complete
# list docs refer to. Third-party profiles set these differently on purpose
# (see module docstring), so main's values must never overwrite them.
ENV_KEY_DENYLIST = {
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "ENABLE_TOOL_SEARCH",
    "DISABLE_GROWTHBOOK",
    "DISABLE_TELEMETRY",
    "DISABLE_AUTOUPDATER",
}


def _env_key_is_identity(key: str) -> bool:
    """Provider-routing and Anthropic-native isolation flags."""
    if key.startswith("ANTHROPIC_"):
        return True
    return key in ENV_KEY_DENYLIST


def merge_env(main_env: dict) -> dict:
    """Env keys main propagates: everything except identity env vars."""
    return {k: v for k, v in main_env.items() if not _env_key_is_identity(k)}


def is_state_key(key: str) -> bool:
    """True if a `.claude.json` key is per-profile state (never synced)."""
    if key in STATE_EXACT:
        return True
    kl = key.lower()
    if any(kl.startswith(p) for p in STATE_PREFIX):
        return True
    return any(s in kl for s in STATE_SUBSTR)


def load(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def file_corrupt(p: Path) -> bool:
    """Exists but not valid JSON (distinct from missing, which is fine)."""
    try:
        json.loads(p.read_text())
        return False
    except json.JSONDecodeError:
        return True
    except FileNotFoundError:
        return False


def _nested_profile_only(main_v, prof_v):
    """Items present in the profile's nested collection but absent from
    main's — they are lost when the top-level key is overwritten with
    main's value. dict → key difference, recursing one level into shared
    keys (so permissions.allow's list elements are seen); list → element
    difference; scalars don't count as nested loss."""
    if isinstance(main_v, dict) and isinstance(prof_v, dict):
        lost = sorted(k for k in prof_v if k not in main_v)
        for k in sorted(prof_v.keys() & main_v.keys()):
            sub = _nested_profile_only(main_v[k], prof_v[k])
            if sub:
                lost.append({k: sub})
        return lost
    if isinstance(main_v, list) and isinstance(prof_v, list):
        return [x for x in prof_v if x not in main_v]
    return []


def write_json_atomic(target: Path, data: dict):
    """Backup + atomic replace + validate, for either config layer."""
    if target.exists():
        bak = target.with_suffix(target.suffix + BACKUP_SUFFIX)
        shutil.copy2(target, bak)
        # copy2 preserves the source's permissions; these files can hold
        # credentials-adjacent state, so a loose source must not yield a
        # loose backup.
        os.chmod(bak, 0o600)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".sync-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, target)
    json.loads(target.read_text())  # validate the file we just wrote


def main_files_corrupt() -> list:
    """Main-layer files that exist but are not valid JSON.

    A corrupt main file reads as {} via load(), which makes every profile
    look converged — a false-green audit. Distinct from a MISSING main file
    (load() -> {} is then correct: nothing to propagate yet).
    """
    bad = []
    for p in (MAIN_DIR / "settings.json", MAIN_JSON):
        try:
            json.loads(p.read_text())
        except json.JSONDecodeError:
            bad.append(p)
        except FileNotFoundError:
            pass
    return bad


def sync_profile(profile_dir: Path, write: bool):
    """Returns (changed_keys, profile_only_keys, nested_overwritten).

    nested_overwritten maps a top-level key to the profile-only nested
    entries the overwrite drops (dict keys or list elements) — the
    convergence is intentional, but it must be VISIBLE, not silent.
    """
    target = profile_dir / "settings.json"
    main = load(MAIN_DIR / "settings.json")
    prof = load(target)
    changed = {}
    nested_lost = {}
    for k, v in main.items():
        if k in DENYLIST:
            continue
        if k == "env" and isinstance(v, dict):
            filtered = merge_env(v)
            if filtered and prof.get("env", {}) != {**prof.get("env", {}), **filtered}:
                changed[k] = {**prof.get("env", {}), **filtered}
            continue
        if prof.get(k) != v:
            changed[k] = v
            lost = _nested_profile_only(v, prof.get(k))
            if lost:
                nested_lost[k] = lost
    extra = sorted(set(prof) - set(main))
    if changed and write:
        write_json_atomic(target, {**prof, **changed})
    return sorted(changed), extra, nested_lost


def sync_claude_json(profile_dir: Path, write: bool):
    """Converge the behavior slice of <profile>/.claude.json from main's.

    Returns (synced_keys, gray_drifted). Behavior keys overwrite the
    profile's value (main is SSOT); state keys are never touched; gray keys
    are only REPORTED. A missing profile .claude.json is skipped, never
    created — the harness creates it on first launch. A CORRUPT profile
    file reads as {} and will be overwritten with main's behavior keys
    (the pre-write backup retains the original bytes) — this rebuild-from-
    main semantic matches the settings.json layer.
    """
    target = profile_dir / ".claude.json"
    if not target.exists():
        return [], []
    main = load(MAIN_JSON)
    if not main:
        return [], []  # nothing to propagate; a CORRUPT main is alarmed on in run()
    prof = load(target)  # an empty object {} is valid content, not a load failure
    changed = {
        k: main[k]
        for k in BEHAVIOR_KEYS
        if k in main and prof.get(k) != main[k]
    }
    gray = sorted(
        k for k in main
        if k not in BEHAVIOR_KEYS
        and k not in GRAY_ACKNOWLEDGED
        and not is_state_key(k)
        and prof.get(k) != main[k]
    )
    if changed and write:
        write_json_atomic(target, {**prof, **changed})
    return sorted(changed), gray


def _iter_profile_dirs():
    """--all enumeration: real profile dirs only — no dot-prefixed archive
    dirs, and never the main config dir itself through a symlink."""
    return sorted(
        p for p in PROFILES_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith(".")
        and p.resolve() != MAIN_DIR.resolve()
    )


def run() -> int:
    args = set(sys.argv[1:])
    unknown = args - {"--check", "--all"}
    if unknown:
        print(f"[sync-profile-settings] unknown arg(s): {', '.join(sorted(unknown))} "
              "(usage: [--check] [--all]) — refusing to guess the mode")
        return 2
    check = "--check" in args
    interactive = bool(args)  # after the unknown-arg guard, any arg = human-run
    bad = main_files_corrupt()
    if bad:
        for p in bad:
            print(f"[sync-profile-settings] WARNING: main file is not valid JSON: {p} — "
                  "skipping convergence (a corrupt main reads as empty and would fake-green the audit)")
        if interactive:
            return 2
        return 0  # SessionStart must never block the session
    if "--all" in args:
        dirs = _iter_profile_dirs()
    else:
        active = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(MAIN_DIR)))
        if active.resolve() == MAIN_DIR.resolve():
            return 0  # main profile is the SSOT itself
        dirs = [active]
    drifted = False
    for d in dirs:
        for layer in ("settings.json", ".claude.json"):
            if file_corrupt(d / layer):
                print(f"[{d.name}] WARNING: {layer} is corrupt — "
                      "rebuilding from main (original retained in .sync-backup)")
        changed, extra, nested_lost = sync_profile(d, write=not check)
        if changed:
            drifted = True
            verb = "drift" if check else "synced"
            suffix = "" if check else " (applies next session)"
            print(f"[{d.name}] {verb} {len(changed)} key(s): {', '.join(changed)}{suffix}")
        for k, items in sorted(nested_lost.items()):
            if check:
                print(f"[{d.name}] {k}: {len(items)} profile-only nested entr(y/ies) "
                      f"main would overwrite: {items!r}")
            else:
                print(f"[{d.name}] note: {k} overwrite dropped {len(items)} "
                      "profile-only nested entr(y/ies) (rerun --check to list them)")
        if extra and check:
            print(f"[{d.name}] profile-only keys (preserved): {', '.join(extra)}")
        cj_changed, gray = sync_claude_json(d, write=not check)
        if cj_changed:
            drifted = True
            verb = "drift" if check else "synced"
            suffix = "" if check else " (applies next session)"
            print(f"[{d.name}] .claude.json {verb} {len(cj_changed)} behavior key(s): {', '.join(cj_changed)}{suffix}")
        for k in gray:
            print(
                f"[{d.name}] .claude.json UNCLASSIFIED drift: {k!r} — "
                "classify in sync-profile-settings.py: BEHAVIOR_KEYS (sync it) / "
                "is_state_key pattern (never sync) / GRAY_ACKNOWLEDGED (snooze with reason)"
            )
    return 1 if (check and drifted) else 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception:
        import traceback
        traceback.print_exc()
        # SessionStart mode must never block a session on an unexpected
        # failure; an interactive --check/--all run exits nonzero so the
        # traceback cannot masquerade as a clean audit.
        sys.exit(0 if len(sys.argv) == 1 else 2)
