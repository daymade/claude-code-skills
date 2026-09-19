#!/usr/bin/env python3
"""Fixture tests for sync-profile-settings.py — both config layers, plus the
mode table (scope, strictness, silence) every invocation resolves through.

Runs against synthetic main/profile directories in a tmp dir; never touches
real ~/.claude or ~/.claude-profiles. Exit 0 = all green.

  python3 scripts/sync-profile-settings.test.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MODULE = Path(__file__).with_name("sync-profile-settings.py")
spec = importlib.util.spec_from_file_location("sync_profile_settings", MODULE)
sps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sps)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL {name}  {detail}")


def make_tree(main_json, prof_json, prof_name="kimi"):
    """Build tmp main dir + profile dir, rewire module constants, return profile Path."""
    root = Path(tempfile.mkdtemp(prefix="sync-test-"))
    main = root / "main"
    prof = root / "profiles" / prof_name
    main.mkdir(parents=True)
    prof.mkdir(parents=True)
    # main state json lives at <main-dir>.json (sibling), matching MAIN_JSON
    (root / "main.json").write_text(json.dumps(main_json))
    (main / "settings.json").write_text(json.dumps({"env": {"X": "1"}}))
    if prof_json is not None:
        pj = prof / ".claude.json"
        pj.write_text(json.dumps(prof_json))
        os.chmod(pj, 0o644)  # loose source perms: backup must still come out 600
    (prof / "settings.json").write_text(json.dumps({"env": {"X": "1"}}))
    sps.MAIN_DIR = main
    sps.MAIN_JSON = root / "main.json"
    sps.PROFILES_ROOT = root / "profiles"
    return prof


BASE_MAIN = {
    "workflowSizeGuideline": "small",
    "preferredNotifChannel": "ghostty",
    "agentPushNotifEnabled": True,
    "projects": {"/main/proj": {"history": ["a"]}},
    "oauthAccount": {"email": "main@example.com", "accountUuid": "uuid-main"},
    "tipsHistory": {"agent-flag": 100},
    "cachedGrowthBookFeatures": {"f": True},
    "autoUpdates": False,                    # GRAY_ACKNOWLEDGED
    "teammateDefaultModel": "opus[1m]",      # GRAY_ACKNOWLEDGED
    "brandNewBehaviorKey2027": "whatever",   # unclassified gray -> must report, not write
    "numStartups": 999,
    "machineID": "abc123",
}

BASE_PROF = {
    "workflowSizeGuideline": "medium",       # behavior, differs -> sync to small
    "preferredNotifChannel": "iterm",        # behavior, differs -> sync
    # agentPushNotifEnabled absent          -> behavior, missing -> sync
    "projects": {"/prof/proj": {"history": ["b"]}},   # state -> untouched
    "oauthAccount": {"email": "prof@example.com"},     # state -> untouched
    "tipsHistory": {"agent-flag": 3},                  # state -> untouched
    "cachedGrowthBookFeatures": {"f": False},          # state -> untouched
    "autoUpdates": True,                    # acknowledged gray -> untouched, unreported
    "numStartups": 7,
    "showExpandedTodos": True,              # profile-only -> preserved
}

print("== sync_claude_json: behavior converge, state untouched, gray reported-not-written ==")
prof = make_tree(BASE_MAIN, BASE_PROF)
synced, gray = sps.sync_claude_json(prof, write=True)
out = json.loads((prof / ".claude.json").read_text())

check("behavior key overwritten", out["workflowSizeGuideline"] == "small")
check("behavior key 2 overwritten", out["preferredNotifChannel"] == "ghostty")
check("behavior key missing->filled", out["agentPushNotifEnabled"] is True)
check("synced list matches", synced == ["agentPushNotifEnabled", "preferredNotifChannel", "workflowSizeGuideline"], synced)
check("state projects untouched", out["projects"] == {"/prof/proj": {"history": ["b"]}})
check("state oauth untouched", out["oauthAccount"] == {"email": "prof@example.com"})
check("state tips untouched", out["tipsHistory"] == {"agent-flag": 3})
check("state cache untouched", out["cachedGrowthBookFeatures"] == {"f": False})
check("state counter untouched", out["numStartups"] == 7)
check("acknowledged gray NOT written (autoUpdates)", out["autoUpdates"] is True)
check("acknowledged gray NOT reported", "autoUpdates" not in gray and "teammateDefaultModel" not in gray, gray)
check("unclassified gray NOT written", "brandNewBehaviorKey2027" not in out)
check("unclassified gray IS reported", gray == ["brandNewBehaviorKey2027"], gray)
check("profile-only key preserved", out["showExpandedTodos"] is True)
bak = prof / ".claude.json.sync-backup"
check("backup written", bak.exists())
check("backup holds pre-write state", json.loads(bak.read_text())["workflowSizeGuideline"] == "medium")
check("backup chmod 600 regardless of source perms", (bak.stat().st_mode & 0o777) == 0o600,
      oct(bak.stat().st_mode & 0o777))
check("state key only in main NOT copied in (machineID)", "machineID" not in out)

print("== idempotent second run ==")
synced2, gray2 = sps.sync_claude_json(prof, write=True)
check("second run no behavior writes", synced2 == [], synced2)
check("second run gray still reported (not acked)", gray2 == ["brandNewBehaviorKey2027"])

print("== check mode writes nothing ==")
prof2 = make_tree(BASE_MAIN, BASE_PROF, prof_name="glm")
synced3, gray3 = sps.sync_claude_json(prof2, write=False)
out2 = json.loads((prof2 / ".claude.json").read_text())
check("check mode reports would-change", "workflowSizeGuideline" in synced3)
check("check mode leaves file untouched", out2["workflowSizeGuideline"] == "medium")
check("check mode writes no backup", not (prof2 / ".claude.json.sync-backup").exists())

print("== missing profile .claude.json -> skipped, never created ==")
prof3 = make_tree(BASE_MAIN, None, prof_name="empty")
synced4, gray4 = sps.sync_claude_json(prof3, write=True)
check("missing file -> no-op", synced4 == [] and gray4 == [])
check("missing file NOT created", not (prof3 / ".claude.json").exists())

print("== is_state_key classifier sanity ==")
for k in ("projects", "oauthAccount", "tipsHistory", "cachedX", "hasSeenY", "numZ",
          "migrationVersion", "opusProMigrationComplete", "remoteControlReadyPushKey",
          "unpinOpus48LaunchEffort", "skillUsage", "myApiKeyThing", "changelogLastFetched",
          "feedbackDraftsTurnOffPromptDeclines"):
    check(f"state: {k}", sps.is_state_key(k))
for k in sps.BEHAVIOR_KEYS:
    check(f"behavior not swallowed: {k}", not sps.is_state_key(k))
for k in ("someFutureBehaviorFlag", "anotherNewToggle"):
    check(f"unknown falls gray (not state): {k}", not sps.is_state_key(k))

print("== settings.json layer regression (DENYLIST + env merge unchanged) ==")
main_s = {"model": "opus[1m]", "hooks": {"Stop": []},
          "env": {"A": "1", "ENABLE_TOOL_SEARCH": "true", "ANTHROPIC_MODEL": "x"}}
prof_s = {"model": "k3[1m]", "env": {"B": "2", "ENABLE_TOOL_SEARCH": "false"}}
root = Path(tempfile.mkdtemp(prefix="sync-test-settings-"))
sps.MAIN_DIR = root / "main"
sps.MAIN_DIR.mkdir()
(sps.MAIN_DIR / "settings.json").write_text(json.dumps(main_s))
pdir = root / "profiles" / "kimi"
pdir.mkdir(parents=True)
(pdir / "settings.json").write_text(json.dumps(prof_s))
changed, extra, nested = sps.sync_profile(pdir, write=True)
outs = json.loads((pdir / "settings.json").read_text())
check("model identity preserved", outs["model"] == "k3[1m]")
check("hooks converged", outs["hooks"] == {"Stop": []})
check("env main wins", outs["env"]["A"] == "1")
check("env identity key NOT synced (ENABLE_TOOL_SEARCH)", outs["env"]["ENABLE_TOOL_SEARCH"] == "false")
check("env identity key NOT synced (ANTHROPIC_MODEL)", "ANTHROPIC_MODEL" not in outs["env"])
check("env profile-only preserved", outs["env"]["B"] == "2")

print("== top-level DENYLIST: advisorModel is provider identity ==")
root_d = Path(tempfile.mkdtemp(prefix="sync-test-deny-"))
sps.MAIN_DIR = root_d / "main"
sps.MAIN_DIR.mkdir()
(sps.MAIN_DIR / "settings.json").write_text(json.dumps({"model": "m1", "advisorModel": "fable", "theme": "dark"}))
pd2 = root_d / "profiles" / "kimi"
pd2.mkdir(parents=True)
(pd2 / "settings.json").write_text(json.dumps({"model": "k3", "advisorModel": "fable-old"}))
changed_d, _, _ = sps.sync_profile(pd2, write=True)
outd = json.loads((pd2 / "settings.json").read_text())
check("advisorModel NOT synced (identity)", outd["advisorModel"] == "fable-old")
check("advisorModel not in changed", "advisorModel" not in changed_d)
check("non-identity key still synced", outd["theme"] == "dark")

print("== nested overwrite: visible, semantics pinned ==")
sps.MAIN_DIR = root_d / "main"
(sps.MAIN_DIR / "settings.json").write_text(json.dumps({
    "permissions": {"allow": ["Bash(wc:*)"]},
    "enabledPlugins": {"plug-a@m": True},
}))
pd3 = root_d / "profiles" / "glm"
pd3.mkdir(parents=True)
(pd3 / "settings.json").write_text(json.dumps({
    "permissions": {"allow": ["Bash(wc:*)", "Bash(myGlmOnlyRule:*)"]},
    "enabledPlugins": {"plug-a@m": True, "glm-only-plugin@m": True},
}))
changed_n, extra_n, nested_n = sps.sync_profile(pd3, write=True)
outn = json.loads((pd3 / "settings.json").read_text())
check("nested overwrite HAPPENS (convergence intent)",
      outn["permissions"]["allow"] == ["Bash(wc:*)"])
check("nested lost list collected (recursed into allow)",
      nested_n.get("permissions") == [{"allow": ["Bash(myGlmOnlyRule:*)"]}], nested_n)
check("nested lost dict-key collected", nested_n.get("enabledPlugins") == ["glm-only-plugin@m"], nested_n)
check("nested overwrite reported for exactly the drifted keys",
      sorted(nested_n) == ["enabledPlugins", "permissions"])

print("== corrupt profile settings.json warns + rebuilds ==")
pd4 = root_d / "profiles" / "deepseek"
pd4.mkdir(parents=True)
(pd4 / "settings.json").write_text("{corrupt")
check("file_corrupt detects", sps.file_corrupt(pd4 / "settings.json"))
sps.sync_profile(pd4, write=True)
outc = json.loads((pd4 / "settings.json").read_text())
check("corrupt settings.json rebuilt from main",
      outc.get("permissions") == {"allow": ["Bash(wc:*)"]})
check("corrupt original in backup", "{corrupt" in (pd4 / "settings.json.sync-backup").read_text())
check("missing file is NOT 'corrupt'", not sps.file_corrupt(pd4 / "nonexistent.json"))

print("== --all enumeration excludes a symlink pointing at MAIN_DIR ==")
root_s = Path(tempfile.mkdtemp(prefix="sync-test-ssot-"))
maindir = root_s / "main"
maindir.mkdir()
(maindir / "settings.json").write_text(json.dumps({"theme": "dark"}))
proot = root_s / "profiles"
proot.mkdir()
(proot / "real-p").mkdir()
(proot / "real-p" / "settings.json").write_text("{}")
(proot / "main-link").symlink_to(maindir)
sps.MAIN_DIR = maindir
sps.PROFILES_ROOT = proot
dirs = sps._iter_profile_dirs()
check("symlink-to-main excluded from --all enumeration",
      [d.name for d in dirs] == ["real-p"], [d.name for d in dirs])

print("== run() CLI contract (subprocess, real exit codes) ==")


def cli_env(main, profiles_root, active=None):
    """The complete env a CLI run gets: PATH + a throwaway HOME, plus only the
    CLAUDE_* keys named here.

    Deliberately NOT `dict(os.environ)`: a hook-shaped env inherited from the
    running harness carries CLAUDE_CONFIG_DIR pointing at a REAL profile, and
    `_profile_dirs_to_converge()` unions that dir in — so a leaked value makes
    the run converge a live profile from a synthetic main. That happened in an
    earlier revision of this suite: the live profile's `hooks` was replaced
    with `{"Stop": []}` (its `settings.json.sync-backup` still holds the
    77-entry original). Every variable the script reads is opted into here.
    """
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": tempfile.mkdtemp(prefix="sync-test-home-")}
    env["CLAUDE_MAIN_CONFIG_DIR"] = str(main)
    env["CLAUDE_PROFILES_ROOT"] = str(profiles_root)
    if active is not None:
        env["CLAUDE_CONFIG_DIR"] = str(active)
    return env


def cli_env_no_active(main, profiles_root):
    """cli_env with CLAUDE_CONFIG_DIR absent entirely — the other side of the
    variable, and the one that used to make the CWD a profile."""
    env = cli_env(main, profiles_root, active=None)
    env.pop("CLAUDE_CONFIG_DIR", None)
    return env


def cli_tree(corrupt_main=False, active=None):
    """Build an isolated main+profiles tree; return (root, env) for subprocess runs."""
    root = Path(tempfile.mkdtemp(prefix="sync-cli-"))
    main = root / "maincfg"
    main.mkdir()
    (root / "maincfg.json").write_text(
        "{corrupt" if corrupt_main else json.dumps({"workflowSizeGuideline": "small"}))
    (main / "settings.json").write_text(
        "{corrupt" if corrupt_main else json.dumps({"hooks": {"Stop": []}, "env": {"A": "1"}}))
    for name, wg in (("p1", None), ("p2", "medium")):
        p = root / "profiles" / name
        p.mkdir(parents=True)
        cj = {}
        if wg:
            cj["workflowSizeGuideline"] = wg
        (p / ".claude.json").write_text(json.dumps(cj))
        (p / "settings.json").write_text("{}")
    (root / "profiles" / ".archived-profiles").mkdir()
    return root, cli_env(main, root / "profiles", active if active is not None else main)


def run_cli(args, env):
    return subprocess.run([sys.executable, str(MODULE), *args],
                          capture_output=True, text=True, env=env)


ABSENT = "<absent>"


def _converger_writable(data) -> tuple:
    """The .claude.json subset the converger may write, value-or-ABSENT per key.

    Deliberately NOT the whole file. The harness rewrites `.claude.json`
    continuously for a live session — measured 2026-09-19 during a fixture run:
    exactly the two profiles with an open session changed, and no non-live
    profile did — so a byte or key-count comparison would redden every run on any
    machine that has a session open, which is how a tripwire gets trained into
    noise. Comparing only what the converger is allowed to write needs no oracle
    for "is this profile live", which has no reliable machine-readable signal.

    ABSENT rather than "only the keys that are present": a synthetic main
    carrying a key the real profile lacks ADDS it, and an absent-vs-present map
    catches that where a present-only map would miss it.
    """
    if not isinstance(data, dict):
        return ("<not-an-object>",)
    keys = sorted(sps.BEHAVIOR_KEYS | sps.MERGE_KEYS)
    return tuple((k, data.get(k, ABSENT)) for k in keys)


def converger_artifact_census(root: Path | None = None) -> tuple:
    """Every `*.sync-backup` and `.sync-*.json` under root, with sizes.

    `write_json_atomic()` copies the target to `<file>.sync-backup` and stages
    through a `.sync-*.json` temp file in the same directory. Nothing else in
    the harness names files either way, so their presence is a converger
    fingerprint that survives on EITHER config layer — including a write that
    only touches `.claude.json` behavior keys and leaves `settings.json`
    untouched, which is the case the profile fingerprint below cannot see.

    Size, not mtime: the backup is made with `shutil.copy2`, which preserves the
    source's mtime, so an old timestamp does not mean "no write happened".
    """
    root = Path(root) if root is not None else Path.home() / ".claude-profiles"
    if not root.is_dir():
        return ()
    out = []
    for p in sorted(root.rglob("*")):
        if p.name.endswith(sps.BACKUP_SUFFIX) or (
            p.name.startswith(".sync-") and p.name.endswith(".json")
        ):
            try:
                out.append((str(p.relative_to(root)), p.stat().st_size))
            except OSError:
                out.append((str(p.relative_to(root)), -1))
    return tuple(out)


def real_profile_fingerprint(root: Path | None = None):
    """Read-only snapshot of what a converger write would change in each profile.

    `root` is overridable so the calibration below can point this at a synthetic
    tree; it defaults to the real profiles root, which is what the tripwire uses.

    Returns None when there is no profiles root (a contributor's machine), so
    the guard degrades to a no-op instead of inventing a baseline.
    """
    root = Path(root) if root is not None else Path.home() / ".claude-profiles"
    if not root.is_dir():
        return None
    fp = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        entry = {}
        s = d / "settings.json"
        if s.exists():
            try:
                data = json.loads(s.read_text())
            except json.JSONDecodeError as exc:
                # Recorded, NOT skipped. The previous version did `continue`
                # here, which dropped a genuinely damaged profile out of the
                # baseline — so the tripwire passed on exactly the damage it
                # exists to catch, in the fail-open direction.
                entry["settings.json"] = ("<invalid-json>", str(exc)[:80])
            else:
                hooks = data.get("hooks", {}) if isinstance(data, dict) else None
                env = data.get("env", {}) if isinstance(data, dict) else None
                entry["settings.json"] = (
                    sum(len(v) for v in hooks.values()) if isinstance(hooks, dict) else -1,
                    len(env) if isinstance(env, dict) else -1,
                )
        cj = d / ".claude.json"
        if cj.exists():
            try:
                cdata = json.loads(cj.read_text())
            except json.JSONDecodeError as exc:
                entry[".claude.json"] = ("<invalid-json>", str(exc)[:80])
            else:
                entry[".claude.json"] = _converger_writable(cdata)
        if entry:
            fp[d.name] = entry
    return fp


def diff_signals(before, after) -> list:
    """Name which signal moved, so a red tripwire says what it caught.

    A bare `before != after` sends the reader to diff two nested structures by
    hand; this is the difference between "tripwire fired" and "the .claude.json
    behavior subset of one profile changed from X to Y".
    """
    if before == after:
        return []
    if not isinstance(before, dict) or not isinstance(after, dict):
        return [f"fingerprint shape changed: {before!r} -> {after!r}"]
    out = []
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name, "<profile absent>"), after.get(name, "<profile absent>")
        if b == a:
            continue
        if isinstance(b, dict) and isinstance(a, dict):
            for signal in sorted(set(b) | set(a)):
                bv, av = b.get(signal, "<absent>"), a.get(signal, "<absent>")
                if bv != av:
                    out.append(f"  profile {name} / {signal}: {bv!r} -> {av!r}")
        else:
            out.append(f"  profile {name}: {b!r} -> {a!r}")
    return out


# Snapshot BEFORE any subprocess runs, so the tripwire at the end can prove
# these tests touched no real profile.
REAL_BEFORE = real_profile_fingerprint()
ARTIFACTS_BEFORE = converger_artifact_census()

r1, e1 = cli_tree()
r = run_cli(["--check", "--all"], e1)
check("--check --all with drift exits 1", r.returncode == 1, f"rc={r.returncode} out={r.stdout!r}")
check("--check writes nothing (p1 still lacks key)",
      "workflowSizeGuideline" not in json.loads((r1 / "profiles/p1/.claude.json").read_text()))
r = run_cli(["--all"], e1)
check("--all exits 0", r.returncode == 0, r.stderr[-200:])
check("--all wrote p1", json.loads((r1 / "profiles/p1/.claude.json").read_text())["workflowSizeGuideline"] == "small")
check("--all overwrote p2", json.loads((r1 / "profiles/p2/.claude.json").read_text())["workflowSizeGuideline"] == "small")
check("--all skipped dot-archive dir", not (r1 / "profiles/.archived-profiles/settings.json").exists())
r = run_cli(["--check", "--all"], e1)
check("post-sync --check --all exits 0", r.returncode == 0, f"rc={r.returncode} out={r.stdout!r}")

e1_main = dict(e1, CLAUDE_CONFIG_DIR=str(r1 / "maincfg"))
r = run_cli([], e1_main)
check("SessionStart mode on main itself: exit 0, no output", r.returncode == 0 and r.stdout == "", f"rc={r.returncode} out={r.stdout!r}")
check("SessionStart mode never writes the main profile's settings.json (it is the SSOT)",
      json.loads((r1 / "maincfg/settings.json").read_text()) == {"hooks": {"Stop": []}, "env": {"A": "1"}})

e1_p1 = dict(e1, CLAUDE_CONFIG_DIR=str(r1 / "profiles/p1"))
(r1 / "profiles/p2/.claude.json").write_text(json.dumps({"workflowSizeGuideline": "medium"}))
r = run_cli([], e1_p1)
check("SessionStart mode on profile: exit 0", r.returncode == 0, r.stderr[-200:])
check("SessionStart converged EVERY profile, not just the active one",
      json.loads((r1 / "profiles/p2/.claude.json").read_text())["workflowSizeGuideline"] == "small",
      json.loads((r1 / "profiles/p2/.claude.json").read_text()))

r2, e2 = cli_tree(corrupt_main=True)
r = run_cli(["--check", "--all"], e2)
check("corrupt main + --check exits 2 with warning", r.returncode == 2 and "not valid JSON" in r.stdout,
      f"rc={r.returncode} out={r.stdout!r}")
r = run_cli(["--all"], e2)
check("corrupt main + --all keeps its exit-2 semantics", r.returncode == 2, f"rc={r.returncode}")
r = run_cli([], dict(e2, CLAUDE_CONFIG_DIR=str(r2 / "profiles/p1")))
check("corrupt main + SessionStart mode still exits 0 (never blocks)",
      r.returncode == 0 and "not valid JSON" in r.stdout, f"rc={r.returncode}")
check("corrupt main + SessionStart writes NOTHING (a corrupt main reads as {} and would converge profiles toward empty)",
      json.loads((r2 / "profiles/p1/.claude.json").read_text()) == {}
      and json.loads((r2 / "profiles/p1/settings.json").read_text()) == {},
      json.loads((r2 / "profiles/p1/.claude.json").read_text()))

print("== new default: no-arg call scope, strictness, and silence ==")


def cli_tree3(names=("p1", "p2", "p3"), drift=("p2",), active=None):
    """Same shape as cli_tree, with a settable profile count and drift set.

    Drift is placed only in `.claude.json`; a profile not in `drift` starts
    already converged, so a run's output line count is decidable.
    """
    root = Path(tempfile.mkdtemp(prefix="sync-cli3-"))
    main = root / "maincfg"
    main.mkdir()
    (root / "maincfg.json").write_text(json.dumps({"workflowSizeGuideline": "small"}))
    (main / "settings.json").write_text(json.dumps({"hooks": {"Stop": []}, "env": {"A": "1"}}))
    for name in names:
        p = root / "profiles" / name
        p.mkdir(parents=True)
        wg = "medium" if name in drift else "small"
        (p / ".claude.json").write_text(json.dumps({"workflowSizeGuideline": wg}))
        (p / "settings.json").write_text(json.dumps({"hooks": {"Stop": []}, "env": {"A": "1"}}))
    (root / "profiles" / ".archived-profiles").mkdir()
    return root, cli_env(main, root / "profiles", active if active is not None else main)


r3a, e3a = cli_tree3()
r = run_cli([], e3a)
check("no-arg call converged p2 (the drifted one)",
      json.loads((r3a / "profiles/p2/.claude.json").read_text())["workflowSizeGuideline"] == "small")
check("no-arg call left already-converged p1/p3 alone (no gratuitous writes)",
      json.loads((r3a / "profiles/p1/.claude.json").read_text()) == {"workflowSizeGuideline": "small"}
      and json.loads((r3a / "profiles/p3/.claude.json").read_text()) == {"workflowSizeGuideline": "small"}
      and not (r3a / "profiles/p1/.claude.json.sync-backup").exists()
      and not (r3a / "profiles/p3/.claude.json.sync-backup").exists())
check("no-arg call exited 0", r.returncode == 0, r.stderr[-200:])
check("no-arg call printed exactly one line, naming the profile it changed",
      r.stdout.splitlines() == ["[p2] .claude.json synced 1 behavior key(s): workflowSizeGuideline (applies next session)"],
      r.stdout)
check("no-arg call skipped the dot-archive dir",
      not (r3a / "profiles/.archived-profiles/settings.json").exists())

r = run_cli([], e3a)
check("no-arg call is silent once converged", r.stdout == "" and r.returncode == 0, f"rc={r.returncode} out={r.stdout!r}")
r = run_cli(["--check", "--all"], e3a)
check("--check --all is silent once converged", r.stdout == "" and r.returncode == 0, f"rc={r.returncode} out={r.stdout!r}")

print("== mode table is total: no unlisted flag set falls through ==")
r3b, e3b = cli_tree3(drift=())  # clean tree: every listed mode must exit 0
for flags in (["--check"], ["--all"], ["--check", "--all"]):
    r = run_cli(flags, e3b)
    check(f"{' '.join(flags)} exits 0 on a clean tree", r.returncode == 0,
          f"rc={r.returncode} out={r.stdout!r} err={r.stderr[-200:]!r}")
for flags in (["--all", "--all"], ["--check", "--check"]):
    r = run_cli(flags, e3b)
    check(f"repeated {' '.join(flags)} resolves to the same mode (exit 0, no refusal)",
          r.returncode == 0 and "unknown arg" not in r.stdout, f"rc={r.returncode} out={r.stdout!r}")

print("== a missing PROFILES_ROOT is empty, not an exception ==")
r3c, e3c = cli_tree3()
shutil.rmtree(r3c / "profiles")
r = run_cli([], dict(e3c, CLAUDE_CONFIG_DIR=str(r3c / "maincfg")))
check("no profiles root: exit 0, no traceback", r.returncode == 0 and "Traceback" not in r.stderr,
      f"rc={r.returncode} err={r.stderr[-200:]!r}")
r = run_cli(["--check", "--all"], e3c)
check("no profiles root + audit: exit 0 (no drift, no crash)", r.returncode == 0 and "Traceback" not in r.stderr,
      f"rc={r.returncode} err={r.stderr[-200:]!r}")

print("== a profile outside PROFILES_ROOT is converged when it is the active dir ==")
r3d, e3d = cli_tree3()
outside = r3d / "outside-profiles" / "loose"
outside.mkdir(parents=True)
(outside / ".claude.json").write_text(json.dumps({"workflowSizeGuideline": "medium"}))
(outside / "settings.json").write_text("{}")
bystander = r3d / "outside-profiles" / "bystander"
bystander.mkdir(parents=True)
(bystander / ".claude.json").write_text(json.dumps({"workflowSizeGuideline": "medium"}))
(bystander / "settings.json").write_text("{}")
r = run_cli([], dict(e3d, CLAUDE_CONFIG_DIR=str(outside)))
check("out-of-root profile converged via CLAUDE_CONFIG_DIR",
      json.loads((outside / ".claude.json").read_text())["workflowSizeGuideline"] == "small")
check("another out-of-root profile NOT visited when it is not the active dir",
      json.loads((bystander / ".claude.json").read_text())["workflowSizeGuideline"] == "medium")
check("an out-of-root active dir is enumerated exactly once per layer, not twice",
      [ln for ln in r.stdout.splitlines() if ln.startswith("[loose] .claude.json")].__len__() == 1
      and [ln for ln in r.stdout.splitlines() if ln.startswith("[loose] synced")].__len__() == 1,
      r.stdout)

print("== an unset or non-profile CLAUDE_CONFIG_DIR fabricates nothing ==")
# Path("") is Path("."), and Path(".").is_dir() is always True — so without a
# membership test an unset variable makes the CWD a profile, and the settings
# layer then CREATES a settings.json in whatever directory the session started
# in (reproduced 2026-09-19: a stray settings.json landed in a git repo).
r3e, e3e = cli_tree3()
scratch = r3e / "a-project-dir"
scratch.mkdir()
r = subprocess.run([sys.executable, str(MODULE)], capture_output=True, text=True,
                   cwd=str(scratch), env=cli_env_no_active(r3e / "maincfg", r3e / "profiles"))
check("unset CLAUDE_CONFIG_DIR: exit 0, no traceback", r.returncode == 0 and "Traceback" not in r.stderr,
      f"rc={r.returncode} err={r.stderr[-200:]!r}")
check("unset CLAUDE_CONFIG_DIR fabricates NO settings.json in the cwd",
      sorted(p.name for p in scratch.iterdir()) == [], sorted(p.name for p in scratch.iterdir()))
check("unset CLAUDE_CONFIG_DIR still converged the in-root profiles",
      json.loads((r3e / "profiles/p2/.claude.json").read_text())["workflowSizeGuideline"] == "small")
check("unset CLAUDE_CONFIG_DIR names no empty [] profile in the output",
      "[] " not in r.stdout and "[]" not in r.stdout.split(), r.stdout)

r3f, e3f = cli_tree3()
nonprofile = r3f / "not-a-config-dir"
nonprofile.mkdir()
(nonprofile / "package.json").write_text("{}")
r = run_cli([], dict(e3f, CLAUDE_CONFIG_DIR=str(nonprofile)))
check("CLAUDE_CONFIG_DIR pointing at a non-config dir writes nothing there",
      sorted(p.name for p in nonprofile.iterdir()) == ["package.json"],
      sorted(p.name for p in nonprofile.iterdir()))

print("== one malformed profile does not cancel convergence for the others ==")
r3g, e3g = cli_tree3(names=("aaa-broken", "p1", "p3"), drift=("p1",))
(r3g / "profiles/aaa-broken/settings.json").write_text(json.dumps({"env": "not-an-object"}))
(r3g / "profiles/aaa-broken/.claude.json").write_text("{}")
r = run_cli([], e3g)
check("non-dict env no longer raises TypeError",
      "TypeError" not in r.stderr and "Traceback" not in r.stderr, f"err={r.stderr[-300:]!r}")
check("the profile AFTER the broken one still converged",
      json.loads((r3g / "profiles/p1/.claude.json").read_text())["workflowSizeGuideline"] == "small",
      json.loads((r3g / "profiles/p1/.claude.json").read_text()))
check("the broken profile's non-dict env was replaced by main's",
      json.loads((r3g / "profiles/aaa-broken/settings.json").read_text())["env"] == {"A": "1"},
      json.loads((r3g / "profiles/aaa-broken/settings.json").read_text()))
check("SessionStart still exits 0 with a malformed profile present", r.returncode == 0, r.returncode)

print("== a profile the run could not process: 2 in both audit modes, 0 in SessionStart ==")
# The half of the exit-code contract the docs state but the suite never pinned.
# A whole file that is valid JSON but not an object is what raises inside
# _converge_one (load() returns the list as-is) and sets `failed`. p1 is left
# drifted on purpose: the assertion is that 2 wins over 1, not that the run
# happens to be clean. The name sorts before p1, so "p1 still converged" also
# proves the failing profile did not cancel the one after it.
r3i, e3i = cli_tree3(names=("aaa-wrongshape", "p1"), drift=("p1",))
(r3i / "profiles/aaa-wrongshape/settings.json").write_text("[]")
(r3i / "profiles/aaa-wrongshape/.claude.json").write_text("{}")

r = run_cli(["--check"], e3i)
check("a wrong-shape profile is reported and skipped, not silently audited",
      "aaa-wrongshape" in r.stdout and "ERROR" in r.stdout, f"out={r.stdout!r}")
check("--check exits 2 on a profile it could not read (2, not the drift's 1)",
      r.returncode == 2, f"rc={r.returncode} err={r.stderr[-200:]!r}")
check("--check wrote nothing for that profile",
      not (r3i / "profiles/aaa-wrongshape/settings.json.sync-backup").exists())

r = run_cli(["--all"], e3i)
check("--all exits 2 on a profile it could not read", r.returncode == 2,
      f"rc={r.returncode} err={r.stderr[-200:]!r}")
check("--all still converged the profile after the failing one",
      json.loads((r3i / "profiles/p1/.claude.json").read_text())["workflowSizeGuideline"] == "small",
      json.loads((r3i / "profiles/p1/.claude.json").read_text()))

# Re-drift p1 first: the --all step above already converged it, so without this
# the assertion below would only prove p1 is in a converged state, not that the
# bare run put it there.
(r3i / "profiles/p1/.claude.json").write_text(json.dumps({"workflowSizeGuideline": "medium"}))
r = run_cli([], e3i)
check("argument-free SessionStart exits 0 on that same failing profile", r.returncode == 0,
      f"rc={r.returncode} err={r.stderr[-200:]!r}")
check("SessionStart converged p1 despite the failing profile",
      json.loads((r3i / "profiles/p1/.claude.json").read_text())["workflowSizeGuideline"] == "small")
check("SessionStart names the failing profile in its output",
      "aaa-wrongshape" in r.stdout, f"out={r.stdout!r}")

print("== corrupt main writes nothing in EVERY writing mode (not just no-args) ==")


def tree_snapshot(root):
    """Byte-level snapshot of both config files in every profile dir."""
    snap = {}
    for p in sorted((root / "profiles").iterdir()):
        if not p.is_dir():
            continue
        snap[p.name] = tuple(
            (p / f).read_text() if (p / f).exists() else "<absent>"
            for f in ("settings.json", ".claude.json")
        )
    return snap


r3h, e3h = cli_tree(corrupt_main=True)
before = tree_snapshot(r3h)
for flags in (["--all"], ["--check", "--all"], ["--check"]):
    r = run_cli(flags, e3h)
    check(f"corrupt main + {' '.join(flags)} exits 2", r.returncode == 2, f"rc={r.returncode}")
    check(f"corrupt main + {' '.join(flags)} wrote NOTHING to any profile",
          before == tree_snapshot(r3h),
          f"drifted={[k for k in before if before[k] != tree_snapshot(r3h).get(k)]}")
    check(f"corrupt main + {' '.join(flags)} left no backup files behind",
          not list((r3h / "profiles").glob("*/settings.json.sync-backup"))
          and not list((r3h / "profiles").glob("*/.claude.json.sync-backup")),
          [str(x) for x in (r3h / "profiles").glob("*/*.sync-backup")])

print("== corrupt profile rebuild + unknown-arg refusal ==")
r3, e3 = cli_tree()
(r3 / "profiles/p1/.claude.json").write_text("{corrupt-json")
r = run_cli(["--all"], e3)
rebuilt = json.loads((r3 / "profiles/p1/.claude.json").read_text())
check("corrupt profile .claude.json rebuilt from main (behavior keys)",
      rebuilt.get("workflowSizeGuideline") == "small")
check("corrupt original retained in backup",
      (r3 / "profiles/p1/.claude.json.sync-backup").read_text() == "{corrupt-json")
r = run_cli(["--bogus"], e3)
check("unknown arg refused with exit 2, no writes", r.returncode == 2 and "unknown arg" in r.stdout,
      f"rc={r.returncode} out={r.stdout!r}")

print("== mcpServers: merged across profiles, never replaced (2026-09-18) ==")
MCP_MAIN = dict(BASE_MAIN, mcpServers={"anydo": {"type": "sse", "url": "A"},
                                       "exa": {"type": "http", "url": "E"}})

# A profile with no mcpServers key at all gets main's registry.
prof = make_tree(MCP_MAIN, {})
sps.sync_claude_json(prof, write=True)
got = json.loads((prof / ".claude.json").read_text()).get("mcpServers", {})
check("missing mcpServers key receives main's servers", set(got) == {"anydo", "exa"}, f"got={sorted(got)}")

# An empty mapping is a DISTINCT side from a missing key: both must fill.
prof = make_tree(MCP_MAIN, {"mcpServers": {}})
sps.sync_claude_json(prof, write=True)
got = json.loads((prof / ".claude.json").read_text()).get("mcpServers", {})
check("empty mcpServers {} receives main's servers", set(got) == {"anydo", "exa"}, f"got={sorted(got)}")

# The regression this merge exists for: a profile-only server must SURVIVE.
prof = make_tree(MCP_MAIN, {"mcpServers": {"only-here": {"type": "stdio", "command": "x"}}})
sps.sync_claude_json(prof, write=True)
got = json.loads((prof / ".claude.json").read_text())["mcpServers"]
check("profile-only server survives the sync", set(got) == {"anydo", "exa", "only-here"}, f"got={sorted(got)}")

# On a shared name, main is the SSOT and wins.
prof = make_tree(MCP_MAIN, {"mcpServers": {"anydo": {"type": "STALE"}}})
sps.sync_claude_json(prof, write=True)
got = json.loads((prof / ".claude.json").read_text())["mcpServers"]
check("main wins on a name both sides define", got["anydo"]["type"] == "sse", f"got={got['anydo']}")

# Already converged: no write, so a SessionStart run stays silent.
prof = make_tree(MCP_MAIN, {"mcpServers": {"anydo": {"type": "sse", "url": "A"},
                                           "exa": {"type": "http", "url": "E"}}})
changed, _ = sps.sync_claude_json(prof, write=True)
check("converged mcpServers reports no change", "mcpServers" not in changed, f"changed={changed}")

# A non-dict value is corrupt, not a mapping to merge: main's registry replaces it.
prof = make_tree(MCP_MAIN, {"mcpServers": "garbage"})
sps.sync_claude_json(prof, write=True)
got = json.loads((prof / ".claude.json").read_text())["mcpServers"]
check("non-dict mcpServers replaced by main's", set(got) == {"anydo", "exa"}, f"got={got!r}")

# Reclassification must not drag identity keys along with it.
check("mcpServers left STATE_EXACT", not sps.is_state_key("mcpServers"))
check("mcpServers entered BEHAVIOR_KEYS", "mcpServers" in sps.BEHAVIOR_KEYS)
for _k in ("userID", "oauthAccount", "projects", "machineID", "claudeAiMcpEverConnected"):
    check(f"identity key {_k} still never synced",
          sps.is_state_key(_k) and _k not in sps.BEHAVIOR_KEYS)

# The notice-delivered ledger rides alongside mcpServers but is per-profile state:
# syncing it would suppress the prompt in a profile that never saw it.
check("mcpNeedsAuthNoticed classified as state",
      sps.is_state_key("mcpNeedsAuthNoticed")
      and "mcpNeedsAuthNoticed" not in sps.BEHAVIOR_KEYS)

print("== tripwire calibration: it must fire on an injected leak, and stay quiet on harness noise ==")
# A tripwire nobody has seen go red is a green square, not a proof. Both sides:
#
# FALSE NEGATIVE — inject a converger write into a synthetic tree and require the
# tripwire to go red AND name which signal caught it. This reproduces the
# 2026-09-19 incident's mechanism without touching a real profile: the fake
# profile is reached through $CLAUDE_CONFIG_DIR (which `_profile_dirs_to_converge`
# unions in) while CLAUDE_PROFILES_ROOT points elsewhere, and the synthetic
# main's settings.json layer is empty — the shape that left the previous
# settings.json-only fingerprint blind while the real profile's .claude.json
# behavior keys were rewritten.
#
# FALSE POSITIVE — a harness-style write to .claude.json must NOT fire it. The
# live harness rewrites a profile's .claude.json continuously while a session is
# open, so if state-key churn tripped the tripwire it would redden every run on
# any machine with a session open and get trained into noise.

_cal = Path(tempfile.mkdtemp(prefix="tripwire-cal-"))
try:
    _watch = _cal / "watch"
    _fake = _watch / "fake-live"
    _fake.mkdir(parents=True)
    # No-op for the settings layer: the synthetic main's settings.json is empty,
    # so nothing about hooks/env can move and the old signal stays flat.
    (_fake / "settings.json").write_text(json.dumps({"hooks": {}, "env": {}}))
    (_fake / ".claude.json").write_text(json.dumps({"someSessionState": 1}))

    _main = _cal / "maincfg"
    _main.mkdir()
    (_main / "settings.json").write_text(json.dumps({}))
    (_cal / "maincfg.json").write_text(json.dumps({"workflowSizeGuideline": "small"}))
    _other = _cal / "other-profiles"
    _other.mkdir()
    (_cal / "home").mkdir()

    # Scrubbed from zero — never dict(os.environ). A leaked CLAUDE_CONFIG_DIR is
    # the whole failure mode this suite encodes, and the calibration must not be
    # the one place it gets reintroduced.
    _cal_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(_cal / "home"),
        "CLAUDE_MAIN_CONFIG_DIR": str(_main),
        "CLAUDE_PROFILES_ROOT": str(_other),
        "CLAUDE_CONFIG_DIR": str(_fake),
    }

    _fp_before = real_profile_fingerprint(_watch)
    _art_before = converger_artifact_census(_watch)
    subprocess.run([sys.executable, str(MODULE)], capture_output=True, text=True,
                   env=_cal_env, check=False)
    _fp_leaked = real_profile_fingerprint(_watch)
    _art_leaked = converger_artifact_census(_watch)

    _moved = diff_signals(_fp_before, _fp_leaked)
    check("calibration: an injected converger write moves the profile fingerprint",
          _fp_before != _fp_leaked, f"before={_fp_before!r} after={_fp_leaked!r}")
    check("calibration: it caught the .claude.json side, which settings.json alone missed",
          any(".claude.json" in m for m in _moved), f"moved signals: {_moved}")
    check("calibration: settings.json stayed flat (this is the blind spot it closes)",
          _fp_before["fake-live"]["settings.json"] == _fp_leaked["fake-live"]["settings.json"],
          f"{_fp_before['fake-live']['settings.json']!r} -> {_fp_leaked['fake-live']['settings.json']!r}")
    check("calibration: the write named itself in the diff output",
          "workflowSizeGuideline" in "\n".join(_moved), f"moved signals: {_moved}")
    check("calibration: an injected converger write leaves a .sync-backup",
          _art_before != _art_leaked and any(
              n.endswith(sps.BACKUP_SUFFIX) for n, _ in _art_leaked),
          f"before={_art_before} after={_art_leaked}")

    # FALSE POSITIVE side: churn the keys the converger never touches. Merged
    # into the file rather than replacing it — overwriting would also drop the
    # behavior key the converger just wrote, and the disappearance of a
    # converger-writable key is real signal, not harness noise. (Found by this
    # calibration: the first draft replaced the file and the tripwire correctly
    # went red on it.)
    (_fake / ".claude.json").write_text(json.dumps({
        **json.loads((_fake / ".claude.json").read_text()),
        "someSessionState": 2, "numStartups": 99, "tipsHistory": {"a": 1},
        "brandNewHarnessKey": True,
    }))
    _fp_noise = real_profile_fingerprint(_watch)
    _art_noise = converger_artifact_census(_watch)
    check("calibration: harness-style .claude.json churn does NOT move the fingerprint",
          _fp_noise == _fp_leaked,
          f"leaked={_fp_leaked!r} after noise={_fp_noise!r}")
    check("calibration: harness-style churn creates no converger artifact",
          _art_noise == _art_leaked, f"{_art_leaked} -> {_art_noise}")

    # And the fail-open this also closes: a damaged file must be RECORDED, so a
    # profile broken by a leak cannot quietly drop out of the baseline.
    (_fake / "settings.json").write_text("{corrupt")
    _fp_broken = real_profile_fingerprint(_watch)
    check("calibration: a profile with unparseable settings.json stays in the fingerprint",
          "fake-live" in _fp_broken
          and _fp_broken["fake-live"]["settings.json"][0] == "<invalid-json>",
          f"{_fp_broken!r}")
finally:
    shutil.rmtree(_cal, ignore_errors=True)

print("== the suite touched no real profile (hermeticity tripwire) ==")
# The failure this encodes: an earlier revision built its subprocess env from
# dict(os.environ), so the harness's CLAUDE_CONFIG_DIR reached the run and
# `_profile_dirs_to_converge()` converged the LIVE profile from a synthetic
# main — its `hooks` became `{"Stop": []}` and every guard in it was gone.
# A scrubbed env prevents it; this check proves it did.
#
# Two signals, because they see different damage. The profile fingerprint sees
# settings.json's hooks/env and the .claude.json behavior subset — but a leak
# whose synthetic main has an empty settings.json layer leaves settings.json
# untouched, and the harness's own writes to a live .claude.json mean the whole
# file cannot be compared. The artifact census closes that gap: `.sync-backup`
# and `.sync-*.json` are made by write_json_atomic() and by nothing else, so a
# write on either layer leaves one behind.
REAL_AFTER = real_profile_fingerprint()
ARTIFACTS_AFTER = converger_artifact_census()
if REAL_BEFORE is None:
    check("no real profiles root here — tripwire not applicable (skipped)", True)
else:
    _signals = diff_signals(REAL_BEFORE, REAL_AFTER)
    check("no real profile changed across the whole suite",
          REAL_BEFORE == REAL_AFTER,
          ("\n" + "\n".join(_signals)) if _signals else f"before={REAL_BEFORE} after={REAL_AFTER}")
    check("the converger left no .sync-backup or .sync-*.json in any real profile",
          ARTIFACTS_BEFORE == ARTIFACTS_AFTER,
          f"before={ARTIFACTS_BEFORE} after={ARTIFACTS_AFTER}")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURES: {FAILURES}")
    sys.exit(1)
print("ALL GREEN")
