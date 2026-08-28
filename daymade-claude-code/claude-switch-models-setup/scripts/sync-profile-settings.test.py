#!/usr/bin/env python3
"""Fixture tests for sync-profile-settings.py — both config layers.

Runs against synthetic main/profile directories in a tmp dir; never touches
real ~/.claude or ~/.claude-profiles. Exit 0 = all green.

  python3 scripts/sync-profile-settings.test.py
"""
import importlib.util
import json
import os
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


def cli_tree(corrupt_main=False):
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
    env = dict(os.environ)
    env["CLAUDE_MAIN_CONFIG_DIR"] = str(main)
    env["CLAUDE_PROFILES_ROOT"] = str(root / "profiles")
    return root, env


def run_cli(args, env):
    return subprocess.run([sys.executable, str(MODULE), *args],
                          capture_output=True, text=True, env=env)


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

e1_p1 = dict(e1, CLAUDE_CONFIG_DIR=str(r1 / "profiles/p1"))
(r1 / "profiles/p2/.claude.json").write_text(json.dumps({"workflowSizeGuideline": "medium"}))
r = run_cli([], e1_p1)
check("SessionStart mode on profile: exit 0", r.returncode == 0, r.stderr[-200:])
check("SessionStart synced only the active profile",
      json.loads((r1 / "profiles/p2/.claude.json").read_text())["workflowSizeGuideline"] == "medium")

r2, e2 = cli_tree(corrupt_main=True)
r = run_cli(["--check", "--all"], e2)
check("corrupt main + --check exits 2 with warning", r.returncode == 2 and "not valid JSON" in r.stdout,
      f"rc={r.returncode} out={r.stdout!r}")
r = run_cli([], dict(e2, CLAUDE_CONFIG_DIR=str(r2 / "profiles/p1")))
check("corrupt main + SessionStart mode still exits 0 (never blocks)",
      r.returncode == 0 and "not valid JSON" in r.stdout, f"rc={r.returncode}")

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

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURES: {FAILURES}")
    sys.exit(1)
print("ALL GREEN")
