#!/usr/bin/env python3
"""Unit tests for hardened evolve_skill_surface.py (Python 3.9+ compatible)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import runpy
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import evolve_skill_surface as ev


def make_skill(root: Path, dirname: str, name: str | None = None, desc: str = "Sample skill description.") -> Path:
    d = root / dirname
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(f"---\nname: {name or dirname}\ndescription: {desc}\n---\n# {dirname}\n", encoding="utf-8")
    return p


class EvolveSkillSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.installed = self.base / ".agents" / "skills"
        self.installed.mkdir(parents=True)
        self.gov = self.base / "gov"
        self.data = self.base / "data"
        self.brain = self.base / "brain"
        self.ledger = self.base / "ledger.db"
        self.agy_skills = self.base / "agy_skills.json"
        self.codex_cfg = self.base / "config.toml"
        self.claude_settings = self.base / "settings.json"

        for name in [
            "skills-search",
            "docs-router",
            "doc-to-markdown",
            "expert-elicitation-engine",
            "hot-active",
            "hot-idle",
            "cold-rising",
            "cold-quiet",
            "explicitly-off-skill",
        ]:
            make_skill(self.installed, name)
        # Skill with frontmatter name != directory entry (P1-5)
        make_skill(self.installed, "gstack-benchmark", name="benchmark")

        # Existing Antigravity skills.json with another root that MUST be preserved (P0-6)
        self.agy_skills.write_text(
            json.dumps({
                "inherits": [{"path": "/custom/shared.json"}],
                "entries": [{"path": "/custom/other-skills"}],
            }, indent=2),
            encoding="utf-8",
        )

        self.codex_cfg.write_text(
            'model = "gpt-6.2-sol"\n\n'
            '[[skills.config]]\n'
            f'path = "{self.base}/.codex/skills/.system/skill-creator/SKILL.md"\n'
            'enabled = false\n\n'
            '[[skills.config]]\n'
            f'path = "{self.installed}/doc-to-markdown/SKILL.md"\n'
            'enabled = false\n',
            encoding="utf-8",
        )

        self.claude_settings.write_text(
            json.dumps({
                "model": "test",
                "skillOverrides": {
                    "explicitly-off-skill": "off",
                    "hot-active": "user-invocable-only",
                },
            }, indent=2),
            encoding="utf-8",
        )

        now = datetime(2026, 11, 20, 4, 0, 0, tzinfo=timezone.utc)
        self.now = now
        conn = sqlite3.connect(str(self.ledger))
        conn.execute(
            "CREATE TABLE events (event_key TEXT, session_id TEXT, provider TEXT, ts REAL, skill TEXT, bare TEXT, initiator TEXT, sidechain INT, entrypoint TEXT, outcome TEXT, origin TEXT)"
        )
        t_recent_ep = (now - timedelta(days=3)).timestamp()
        t_old_ep = (now - timedelta(days=60)).timestamp()
        rows = [
            ("1", "s1", "claude", t_recent_ep, "hot-active", "hot-active", "model_auto", 0, "main", "ok", "x"),
            ("2", "s2", "codex", t_recent_ep, "hot-active", "hot-active", "model_auto", 0, "main", "ok", "x"),
            ("3", "s3", "claude", t_old_ep, "hot-idle", "hot-idle", "model_auto", 0, "main", "ok", "x"),
            # Frontmatter name 'benchmark' should map to entry 'gstack-benchmark'
            ("4", "s4", "codex", t_recent_ep, "benchmark", "benchmark", "model_auto", 0, "main", "ok", "x"),
        ]
        conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
        conn.close()

        # Real Antigravity transcript shape: JSON-quoted INSTALLED Path counted; workspace dev read & MCP call NOT double-counted
        t_recent_iso = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        tpath = self.brain / "conv-real-shape" / ".system_generated" / "logs" / "transcript.jsonl"
        tpath.parent.mkdir(parents=True)
        tpath.write_text(
            "\n".join([
                json.dumps({
                    "created_at": t_recent_iso,
                    "tool_calls": [{
                        "name": "read_file",
                        "args": {"Path": json.dumps(str(self.installed / "hot-active" / "SKILL.md"))},
                    }],
                }),
                json.dumps({
                    "created_at": t_recent_iso,
                    "tool_calls": [{
                        "name": "read_file",
                        "args": {"Path": json.dumps(str(self.base / "workspace" / "claude-code-skills" / "cold-quiet" / "SKILL.md"))},
                    }],
                }),
                json.dumps({
                    "created_at": t_recent_iso,
                    "tool_calls": [{
                        "name": "call_mcp_tool",
                        "args": {
                            "ServerName": '"local-skills-search"',
                            "ToolName": '"get_local_skill"',
                            "Arguments": json.dumps({"name": "cold-rising", "query": "豆瓣导出"}),
                        },
                    }],
                }),
            ]) + "\n",
            encoding="utf-8",
        )

        # Nested cold skill inside ~/.agents/skills/ima-skill/notes/SKILL.md (P0-2)
        make_skill(self.installed, "ima-skill")
        make_skill(self.installed / "ima-skill", "notes", name="ima-skill-notes")

        self.data.mkdir(parents=True)
        (self.data / "telemetry.jsonl").write_text(
            "\n".join([
                json.dumps({"ts": t_recent_iso, "host": "antigravity", "event": "load", "skill": "cold-rising", "entry": "cold-rising", "surface": "cold", "query": "豆瓣导出"}),
                json.dumps({"ts": t_recent_iso, "host": "claude", "event": "load", "skill": "cold-rising", "entry": "cold-rising", "surface": "cold", "query": "豆瓣导出"}),
                # Oversized/sensitive query must NOT be learned as alias
                json.dumps({"ts": t_recent_iso, "host": "claude", "event": "load", "skill": "cold-rising", "entry": "cold-rising", "surface": "cold", "query": "https://secret.example/foo"}),
                json.dumps({"ts": t_recent_iso, "host": "claude", "event": "load", "skill": "cold-rising", "entry": "cold-rising", "surface": "cold", "query": "https://secret.example/foo"}),
            ]) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_watched_runner_refreshes_once_and_reuses_ledger_for_new_telemetry(self) -> None:
        runner = self.base / "runner.py"
        ledger_script = self.base / "index.py"
        runner.write_text(ev.render_evolution_runner(
            SCRIPTS_DIR / "evolve_skill_surface.py", ledger_script,
            python_bin=sys.executable, data_dir=self.data, ledger_db=self.ledger,
            refresh_interval=1800, auto_apply=False, hosts="claude",
        ), encoding="utf-8")
        main = runpy.run_path(str(runner))["main"]
        telemetry = self.data / "telemetry.jsonl"
        status = self.data / ".evolve-status"
        receipt = self.data / ".evolve-ledger-refresh"
        report = self.data / "reports" / "latest.md"
        calls = []

        def child(cmd, **kwargs):
            if cmd[1] == str(ledger_script):
                self.assertEqual(cmd[2:], ["--db", str(self.ledger), "index", "--json"])
                calls.append("index")
            else:
                self.assertEqual(cmd[2:5], ["--ledger-db", str(self.ledger), "propose"])
                calls.append("propose")
                report.parent.mkdir(exist_ok=True)
                report.write_text(telemetry.read_text(encoding="utf-8"), encoding="utf-8")
                if calls == ["index", "propose"]:
                    before = telemetry.stat()
                    telemetry.write_text("arrived during proposal", encoding="utf-8")
                    os.utime(telemetry, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch.object(subprocess, "run", side_effect=child):
            self.assertEqual(main(), 0)
            self.assertEqual(calls, ["index", "propose", "propose"])
            self.assertIn("ledger=refreshed", status.read_text())
            telemetry.write_text("next telemetry update")
            self.assertEqual(main(), 0)
            self.assertEqual(calls, ["index", "propose", "propose", "propose"])
            self.assertIn("ledger=reused", status.read_text())
            self.assertEqual(report.read_text(), "next telemetry update")

            fresh = json.loads(receipt.read_text())
            invalid_receipts = ["{", json.dumps({**fresh, "started_at": time.time() - 1800}),
                                json.dumps({**fresh, "started_at": time.time() + 60})]
            for invalid in invalid_receipts:
                receipt.write_text(invalid)
                self.assertEqual(main(), 0)
                self.assertEqual(calls[-2:], ["index", "propose"])
            self.ledger.touch()
            self.assertEqual(main(), 0)
            self.assertEqual(calls[-2:], ["index", "propose"])

        self.ledger.unlink()
        with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 2, "", "index failed",
        )) as fail:
            self.assertEqual(main(), 1)
            self.assertEqual(fail.call_count, 1)
            self.assertIn("ledger_rc=2", status.read_text())
            self.assertFalse(receipt.exists())
            self.assertEqual(report.read_text(), "next telemetry update")

    def test_antigravity_real_transcript_name_mapping_non_destructive_and_idempotent(self) -> None:
        installed, name_to_entry = ev.discover_installed_skills(self.installed)
        ledger = ev.collect_ledger_signals(self.ledger, name_to_entry, self.now)
        self.assertIn("gstack-benchmark", ledger)

        agy = ev.collect_antigravity_signals(self.brain, name_to_entry, self.now)
        self.assertIn("hot-active", agy)
        # Workspace source read must NOT pollute agy signals; MCP call must NOT double-count (telemetry owns it)
        self.assertNotIn("cold-quiet", agy)
        self.assertNotIn("cold-rising", agy)

        t_loads, pairs, zeros = ev.collect_telemetry_signals(self.data / "telemetry.jsonl", name_to_entry, self.now)
        scored = ev.merge_and_score(installed, ledger, agy, t_loads)

        hot_doc = {
            "schema": 1,
            "policy": {"max_hot": 5, "window_days": 90, "recent_days": 14, "demote_idle_days": 45,
                       "promote_min_recent_cold_loads": 2, "promote_min_recent_model_sessions": 3,
                       "hysteresis_margin": 1.2, "alias_min_recurrence": 2},
            "pinned": ["skills-search", "docs-router"],
            "dynamic_hot": ["hot-active", "hot-idle"],
            "router_children": ["doc-to-markdown"],
            "blocked_cold": ["expert-elicitation-engine"],
            "history": [],
        }

        proposal = ev.evaluate_evolution(hot_doc, installed, scored, pairs, zeros, {})
        self.assertIn("cold-rising", [p["skill"] for p in proposal["promotions"]])
        self.assertIn("hot-idle", [d["skill"] for d in proposal["demotions"]])
        # Safe alias kept; URL alias rejected
        self.assertEqual(proposal["learned_aliases"], [{"skill": "cold-rising", "term": "豆瓣导出", "count": 2}])

        # Non-destructive Antigravity projection preserves inherits + sibling entries
        r1 = ev.project_antigravity(self.agy_skills, self.installed, proposal["next_hot_set"])
        self.assertTrue(r1["changed"])
        agy_out = json.loads(self.agy_skills.read_text())
        self.assertEqual(agy_out["inherits"], [{"path": "/custom/shared.json"}])
        self.assertEqual(len(agy_out["entries"]), 2)
        self.assertEqual(agy_out["entries"][0]["path"], "/custom/other-skills")

        # Second projection is true no-op
        r2 = ev.project_antigravity(self.agy_skills, self.installed, proposal["next_hot_set"])
        self.assertFalse(r2["changed"])

        # Codex projection idempotency, nested ima-skill/notes disable, & unbalanced marker guard
        c1 = ev.project_codex(self.codex_cfg, installed, proposal["next_hot_set"], self.installed, codex_skills_root=None)
        self.assertTrue(c1["changed"])
        codex_txt = self.codex_cfg.read_text(encoding="utf-8")
        self.assertIn(f"{self.installed}/ima-skill/notes/SKILL.md", codex_txt)
        c2 = ev.project_codex(self.codex_cfg, installed, proposal["next_hot_set"], self.installed, codex_skills_root=None)
        self.assertFalse(c2["changed"])

        broken_codex = self.base / "broken.toml"
        broken_codex.write_text(ev.CODEX_MANAGED_BEGIN + "\norphan\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            ev.project_codex(broken_codex, installed, proposal["next_hot_set"])

    def test_default_ledger_script_resolution(self) -> None:
        resolved = ev.resolve_default_ledger_script(SCRIPTS_DIR / "evolve_skill_surface.py")
        self.assertTrue(resolved.is_file())
        self.assertEqual(resolved.name, "skill_usage_ledger.py")

    def test_project_claude_sync_lock_protocol_and_plugin_detection(self) -> None:
        installed, _ = ev.discover_installed_skills(self.installed)
        claude_skills = self.base / ".claude" / "skills"
        make_skill(claude_skills, "personal-only-cold", name="PersonalCold")
        sync_lock_dir = self.base / ".claude" / ".daymade-skill-sync.lock"
        guard_file = self.base / ".claude" / ".daymade-skill-sync.lock.guard"

        # Pre-seed a stale dead-PID lock directory to verify compatible stale recovery
        sync_lock_dir.mkdir(parents=True, mode=0o700)
        (sync_lock_dir / "pid").write_text("99999999", encoding="utf-8")

        # Build mock installed_plugins.json covering single-skill hot, single-skill cold,
        # multi-skill direct child, and nested skills/<name>/SKILL.md layouts
        cache = self.base / ".claude" / "plugins" / "cache"
        hot_single = cache / "mkt" / "hot-active" / "1.0.4"
        hot_single.mkdir(parents=True)
        (hot_single / "SKILL.md").write_text("---\nname: hot-active\n---\n", encoding="utf-8")

        cold_single = cache / "mkt" / "cold-standalone" / "2.3.1"
        cold_single.mkdir(parents=True)
        (cold_single / "SKILL.md").write_text("---\nname: cold-standalone\n---\n", encoding="utf-8")

        suite_dir = cache / "mkt" / "sample-suite" / "3.0.0"
        make_skill(suite_dir, "suite-cold-child")
        make_skill(suite_dir / "skills", "suite-nested-cold")
        make_skill(suite_dir, "skills-search")  # hot child inside suite

        installed_plugins = self.base / ".claude" / "plugins" / "installed_plugins.json"
        installed_plugins.parent.mkdir(parents=True, exist_ok=True)
        installed_plugins.write_text(json.dumps({
            "plugins": {
                "hot-active@mkt": [{"installPath": str(hot_single)}],
                "cold-standalone@mkt": [{"installPath": str(cold_single)}],
                "sample-suite@mkt": [{"installPath": str(suite_dir)}],
            }
        }), encoding="utf-8")

        settings_doc = json.loads(self.claude_settings.read_text(encoding="utf-8"))
        settings_doc["enabledPlugins"] = {
            "hot-active@mkt": True,
            "cold-standalone@mkt": True,
            "sample-suite@mkt": True,
        }
        self.claude_settings.write_text(json.dumps(settings_doc, indent=2), encoding="utf-8")

        hot_set = ["skills-search", "docs-router", "hot-active"]
        res = ev.project_claude(
            self.claude_settings,
            installed,
            hot_set,
            claude_skills_root=claude_skills,
            installed_plugins_path=installed_plugins,
            sync_lock_path=sync_lock_dir,
        )
        self.assertTrue(res["changed"])
        # Lock protocol compatibility: lock_dir removed on exit, private 0o600 .guard retained
        self.assertFalse(sync_lock_dir.exists())
        self.assertTrue(guard_file.is_file())
        self.assertEqual(stat.S_IMODE(guard_file.stat().st_mode) & 0o077, 0)

        out = json.loads(self.claude_settings.read_text(encoding="utf-8"))
        ov = out["skillOverrides"]
        self.assertEqual(ov["explicitly-off-skill"], "off")
        self.assertNotIn("hot-active", ov)
        self.assertEqual(ov["cold-quiet"], "user-invocable-only")
        # ~/.claude/skills-only personal skill governed by both entry and frontmatter name
        self.assertEqual(ov["personal-only-cold"], "user-invocable-only")
        self.assertEqual(ov["PersonalCold"], "user-invocable-only")

        # Single-skill semver cache dir must NOT leak version string "1.0.4" or "2.3.1"
        bypassed = res["plugin_bypassed_cold_sample"]
        self.assertNotIn("hot-active:1.0.4", bypassed)
        self.assertNotIn("cold-standalone:2.3.1", bypassed)
        self.assertIn("cold-standalone:cold-standalone", bypassed)
        self.assertIn("sample-suite:suite-cold-child", bypassed)
        self.assertIn("sample-suite:suite-nested-cold", bypassed)
        self.assertNotIn("sample-suite:skills-search", bypassed)
        self.assertEqual(res["plugin_bypassed_cold_count"], 3)

        # Second projection is true no-op
        res2 = ev.project_claude(
            self.claude_settings,
            installed,
            hot_set,
            claude_skills_root=claude_skills,
            installed_plugins_path=installed_plugins,
            sync_lock_path=sync_lock_dir,
        )
        self.assertFalse(res2["changed"])
        self.assertFalse(sync_lock_dir.exists())

    def test_backup_rollback_noop_retention_and_telemetry_prune(self) -> None:
        backups_root = self.base / "backups"
        # Pre-seed MAX_BACKUPS_RETAINED real backups
        for idx in range(ev.MAX_BACKUPS_RETAINED):
            d = backups_root / f"20260101T0000{idx:02d}000000Z"
            d.mkdir(parents=True)
            (d / "manifest.json").write_text('{"files":[]}', encoding="utf-8")

        sync_lock_dir = self.base / ".claude" / ".daymade-skill-sync.lock"
        orig_settings = self.claude_settings.read_text(encoding="utf-8")
        new_file = self.base / "newly_created.json"

        # backup_files must NOT prune older backups before apply decides applied vs noop
        bdir = ev.backup_files([self.claude_settings, new_file], backups_root)
        existing_dirs = [d for d in backups_root.iterdir() if d.is_dir()]
        self.assertEqual(len(existing_dirs), ev.MAX_BACKUPS_RETAINED + 1)

        # Mutate files, then roll back atomically while coordinating claude_sync_lock
        self.claude_settings.write_text('{"corrupted": true}\n', encoding="utf-8")
        new_file.write_text('{"temp": 1}\n', encoding="utf-8")
        rb = ev.rollback_backup(bdir, claude_settings=self.claude_settings, claude_sync_lock_path=sync_lock_dir)
        self.assertEqual(rb["status"], "rolled_back")
        self.assertEqual(self.claude_settings.read_text(encoding="utf-8"), orig_settings)
        self.assertFalse(new_file.exists())
        self.assertFalse(sync_lock_dir.exists())

        # prune_old_backups enforces retention bound when explicitly invoked
        ev.prune_old_backups(backups_root, ev.MAX_BACKUPS_RETAINED)
        self.assertEqual(len([d for d in backups_root.iterdir() if d.is_dir()]), ev.MAX_BACKUPS_RETAINED)

        # prune_telemetry_file skips small files (< threshold) and prunes stale rows above threshold
        telem = self.data / "telemetry.jsonl"
        self.assertEqual(ev.prune_telemetry_file(telem, self.now, retain_days=180), 0)
        old_iso = (self.now - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent_iso = (self.now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        telem.write_text(
            json.dumps({"ts": old_iso, "event": "load", "skill": "old"}) + "\n"
            + json.dumps({"ts": recent_iso, "event": "load", "skill": "new"}) + "\n",
            encoding="utf-8",
        )
        orig_min = ev.PRUNE_TELEMETRY_MIN_BYTES
        try:
            ev.PRUNE_TELEMETRY_MIN_BYTES = 1
            dropped = ev.prune_telemetry_file(telem, self.now, retain_days=180)
        finally:
            ev.PRUNE_TELEMETRY_MIN_BYTES = orig_min
        self.assertEqual(dropped, 1)
        remaining = [json.loads(line)["skill"] for line in telem.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(remaining, ["new"])

    def test_aliases_nested_codex_extract_and_dynamic_router_pinning(self) -> None:
        # Nested disable in config.toml must NOT classify parent as router_child
        self.codex_cfg.write_text(
            self.codex_cfg.read_text(encoding="utf-8")
            + f'\n[[skills.config]]\npath = "{self.installed}/ima-skill/notes/SKILL.md"\nenabled = false\n',
            encoding="utf-8",
        )
        disabled = ev.extract_codex_disabled_agents_skills(self.codex_cfg)
        self.assertIn("doc-to-markdown", disabled)
        self.assertNotIn("ima-skill", disabled)

        # Dynamic *-router pinning works without private router names in defaults
        make_skill(self.installed, "custom-domain-router")
        installed, name_to_entry = ev.discover_installed_skills(self.installed)
        ledger = ev.collect_ledger_signals(self.ledger, name_to_entry, self.now)
        scored = ev.merge_and_score(installed, ledger, {}, {})
        init_doc = ev.build_initial_hot_set(installed, scored, disabled, max_hot=5)
        self.assertIn("custom-domain-router", init_doc["pinned"])
        self.assertIn("doc-to-markdown", init_doc["router_children"])
        self.assertNotIn("ima-skill", init_doc["router_children"])

        # apply_learned_aliases is idempotent
        r1 = ev.apply_learned_aliases(self.gov, [{"skill": "cold-rising", "term": "豆瓣导出", "count": 2}])
        self.assertEqual(r1["added"], 1)
        r2 = ev.apply_learned_aliases(self.gov, [{"skill": "cold-rising", "term": "豆瓣导出", "count": 2}])
        self.assertEqual(r2["added"], 0)


if __name__ == "__main__":
    unittest.main()
