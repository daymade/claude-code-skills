#!/usr/bin/env python3
"""Fixture tests for claude-plugins-sync.py — enabledPlugins adoption + mirror.

Runs the real script via subprocess against synthetic main/profile dirs in a tmp root
(CLAUDE_BASE_DIR / CLAUDE_PROFILES_DIR), never touching real ~/.claude. Exit 0 = green.

Covers the 2026-09-03 loss incident: `claude plugin install` writes the new enabledPlugins
key into the ACTIVE profile only; the replace-style mirror then wiped it from every
profile. The fix adopts profile-only keys back into main before mirroring.

  python3 scripts/claude-plugins-sync.test.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("claude-plugins-sync.py")

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL {name}  {detail}")


def make_world(main_enabled, profiles_enabled, extra_main_settings=None):
    """Build tmp main + profiles dirs. Returns (root, run, read_json) helpers."""
    root = Path(tempfile.mkdtemp(prefix="plugins-sync-test-"))
    base = root / "main"
    profiles = root / "profiles"
    (base / "plugins" / "marketplaces").mkdir(parents=True)
    profiles.mkdir(parents=True)

    main_settings = {"model": "opus", "hooks": {"SessionStart": [{"hooks": [{"type": "command"}]}]}}
    if extra_main_settings:
        main_settings.update(extra_main_settings)
    main_settings["enabledPlugins"] = main_enabled
    (base / "settings.json").write_text(json.dumps(main_settings))
    (base / "plugins" / "known_marketplaces.json").write_text(json.dumps({"m1": {"source": {"source": "github", "repo": "a/b"}, "installLocation": str(base / "plugins" / "marketplaces" / "m1")}}))

    for name, enabled in profiles_enabled.items():
        pd = profiles / name
        (pd / "plugins").mkdir(parents=True)
        (pd / "settings.json").write_text(json.dumps({"model": "glm", "enabledPlugins": enabled}))

    def run(*args):
        env = dict(os.environ)
        env["CLAUDE_BASE_DIR"] = str(base)
        env["CLAUDE_PROFILES_DIR"] = str(profiles)
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            env=env, capture_output=True, text=True,
        )

    def read_json(p):
        return json.loads(Path(p).read_text())

    return root, run, read_json


def test_noop_when_no_extras():
    """Healthy input: profile already equals main -> no adoption, main file byte-stable."""
    root, run, read_json = make_world({"a@x": True}, {"kimi": {"a@x": True}})
    before = (root / "main" / "settings.json").read_text()
    r = run()
    check("noop: exit 0", r.returncode == 0, r.stderr)
    check("noop: no adoption log", "adopt" not in r.stdout, r.stdout)
    check("noop: main settings untouched", (root / "main" / "settings.json").read_text() == before)
    check("noop: profile still matches main", read_json(root / "profiles" / "kimi" / "settings.json")["enabledPlugins"] == {"a@x": True})


def test_adopt_true_survives_mirror_everywhere():
    """The incident shape: install ran in the active profile, key absent from main."""
    root, run, read_json = make_world(
        {"a@x": True},
        {"kimi": {"a@x": True, "daymade-audio@daymade-skills": True}, "deepseek": {"a@x": True}},
    )
    r = run()
    check("adopt: exit 0", r.returncode == 0, r.stderr)
    check("adopt: main gained the key", read_json(root / "main" / "settings.json")["enabledPlugins"].get("daymade-audio@daymade-skills") is True)
    check("adopt: main kept unrelated keys", read_json(root / "main" / "settings.json")["model"] == "opus")
    for prof in ("kimi", "deepseek"):
        ep = read_json(root / "profiles" / prof / "settings.json")["enabledPlugins"]
        check(f"adopt: {prof} sees the installed plugin", ep.get("daymade-audio@daymade-skills") is True, str(ep))


def test_adopt_false_consistent():
    """An explicit disable done in a profile is adopted as false globally."""
    root, run, read_json = make_world(
        {"a@x": True},
        {"kimi": {"a@x": True, "b@x": False}},
    )
    r = run()
    check("adopt-false: main gained b@x=false", read_json(root / "main" / "settings.json")["enabledPlugins"].get("b@x") is False)
    check("adopt-false: kimi keeps b@x=false", read_json(root / "profiles" / "kimi" / "settings.json")["enabledPlugins"].get("b@x") is False)


def test_conflict_kept_per_profile_and_warned():
    """Same key, different values across profiles: never adopted, never overwritten."""
    root, run, read_json = make_world(
        {"a@x": True},
        {"kimi": {"a@x": True, "d@x": True}, "deepseek": {"a@x": True, "d@x": False}},
    )
    r = run()
    check("conflict: exit 0", r.returncode == 0, r.stderr)
    check("conflict: warned", "conflicting values" in r.stderr, r.stderr)
    check("conflict: not adopted into main", "d@x" not in read_json(root / "main" / "settings.json")["enabledPlugins"])
    check("conflict: kimi kept true", read_json(root / "profiles" / "kimi" / "settings.json")["enabledPlugins"].get("d@x") is True)
    check("conflict: deepseek kept false", read_json(root / "profiles" / "deepseek" / "settings.json")["enabledPlugins"].get("d@x") is False)


def test_main_authoritative_on_existing_keys():
    """Existing merge rule unchanged: main's value wins for keys main already has."""
    root, run, read_json = make_world(
        {"a@x": False},
        {"kimi": {"a@x": True}},
    )
    r = run()
    check("authority: profile conformed to main", read_json(root / "profiles" / "kimi" / "settings.json")["enabledPlugins"] == {"a@x": False})


def test_broken_profile_settings_skipped():
    """Unreadable profile settings must not crash the pass nor block other profiles."""
    root, run, read_json = make_world(
        {"a@x": True},
        {"kimi": {"a@x": True, "e@x": True}},
    )
    (root / "profiles" / "deepseek").mkdir()
    (root / "profiles" / "deepseek" / "settings.json").write_text("{not json")
    r = run()
    check("broken: exit 0", r.returncode == 0, r.stderr)
    check("broken: warned", "unreadable" in r.stderr, r.stderr)
    check("broken: adoption still happened", read_json(root / "main" / "settings.json")["enabledPlugins"].get("e@x") is True)


def test_dry_run_writes_nothing():
    root, run, read_json = make_world(
        {"a@x": True},
        {"kimi": {"a@x": True, "f@x": True}},
    )
    before = (root / "main" / "settings.json").read_text()
    r = run("--dry-run")
    check("dry: exit 0", r.returncode == 0, r.stderr)
    check("dry: main untouched", (root / "main" / "settings.json").read_text() == before)
    check("dry: profile untouched", read_json(root / "profiles" / "kimi" / "settings.json")["enabledPlugins"] == {"a@x": True, "f@x": True})


def test_profile_flag_scopes_adoption():
    """--profile <name>: adoption scans only that profile; other profiles' extras untouched."""
    root, run, read_json = make_world(
        {"a@x": True},
        {"kimi": {"a@x": True, "g@x": True}, "deepseek": {"a@x": True, "h@x": True}},
    )
    r = run("--profile", "kimi")
    check("scoped: main adopted only kimi's key", read_json(root / "main" / "settings.json")["enabledPlugins"].get("g@x") is True)
    check("scoped: deepseek's key NOT adopted", "h@x" not in read_json(root / "main" / "settings.json")["enabledPlugins"])
    check("scoped: deepseek profile untouched", read_json(root / "profiles" / "deepseek" / "settings.json")["enabledPlugins"] == {"a@x": True, "h@x": True})


def main():
    tests = [
        test_noop_when_no_extras,
        test_adopt_true_survives_mirror_everywhere,
        test_adopt_false_consistent,
        test_conflict_kept_per_profile_and_warned,
        test_main_authoritative_on_existing_keys,
        test_broken_profile_settings_skipped,
        test_dry_run_writes_nothing,
        test_profile_flag_scopes_adoption,
    ]
    for t in tests:
        print(t.__name__)
        t()
    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {FAILURES}")
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
