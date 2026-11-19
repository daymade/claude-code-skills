#!/usr/bin/env python3
"""Unit tests for hardened evolve_skill_surface.py (Python 3.9+ compatible)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

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
            'path = "/Users/test/.codex/skills/.system/skill-creator/SKILL.md"\n'
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
                        "args": {"Path": json.dumps("/Users/test/workspace/md/claude-code-skills/cold-quiet/SKILL.md")},
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


if __name__ == "__main__":
    unittest.main()
