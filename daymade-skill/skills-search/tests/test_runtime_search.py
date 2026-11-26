#!/usr/bin/env python3
"""Unit tests for hardened runtime_search.py and mcp_server.py (Python 3.9+ compatible)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import runtime_search as rs


def make_skill(root: Path, dirname: str, name: str, description: str, body: str = "# Body\n", with_script: bool = False) -> Path:
    d = root / dirname
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: >-\n  {description}\n---\n\n{body}",
        encoding="utf-8",
    )
    if with_script:
        sd = d / "scripts"
        sd.mkdir(exist_ok=True)
        (sd / "run.py").write_text("print('ok')\n", encoding="utf-8")
        # Add vendor dir that must be pruned
        nm = sd / "node_modules" / "pkg"
        nm.mkdir(parents=True, exist_ok=True)
        (nm / "index.js").write_text("// ignored\n", encoding="utf-8")
    return d


class RuntimeSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.installed = self.base / "installed"
        self.installed.mkdir()
        self.repo_src = self.base / "repo_src"
        self.repo_src.mkdir()
        self.gov = self.base / "gov"
        self.gov.mkdir()
        self.cache = self.base / "cache.json"
        self.telem = self.base / "telemetry.jsonl"
        self.sources_cfg = self.base / "sources.json"

        make_skill(
            self.installed,
            "douban-skill",
            "douban-skill",
            "Export and sync Douban (豆瓣) book/movie collections and X posts to local CSV.",
            body="# Douban Skill\n\n## Usage\nRun scripts/run.py.\n",
            with_script=True,
        )
        real_target = make_skill(
            self.repo_src,
            "wechat-article-scraper",
            "wechat-article-scraper",
            "抓取微信公众号文章内容，提取正文、图片和元数据，输出 Markdown。",
        )
        os.symlink(real_target, self.installed / "wechat-article-scraper")

        make_skill(
            self.installed,
            "giant-skill",
            "giant-skill",
            "Huge diagnostic handbook for macOS battery drain.",
            body="# Giant Handbook\n\n## Section A\n" + ("A" * 25000) + "\n## Section B\n" + ("B" * 25000),
        )

        make_skill(
            self.installed,
            "retired-skill",
            "retired-skill",
            "Deprecated old tool for legacy print.",
        )

        extra_repo = self.base / "qcc_repo"
        make_skill(
            extra_repo / "skills",
            "credit-rating-qcc",
            "credit-rating-qcc",
            "Enterprise credit rating due diligence via Qichacha.",
        )
        self.sources_cfg.write_text(
            json.dumps({
                "schema": 1,
                "sources": [{
                    "id": "qcc",
                    "path": str(extra_repo),
                    "skill_roots": ["skills"],
                    "tier": "owned",
                    "ref": "HEAD",
                    "priority": 1,
                    "enabled": True,
                }],
            }),
            encoding="utf-8",
        )

        (self.gov / "hot-set.json").write_text(
            json.dumps({
                "schema": 1,
                "pinned": ["skills-search"],
                "dynamic_hot": ["wechat-article-scraper"],
                "router_children": [],
                "blocked_cold": ["retired-skill"],
            }),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bilingual_search_1char_and_blocked_exclusion(self) -> None:
        res = rs.search_skills(
            query="抓取公众号文章",
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
            telemetry_path=self.telem,
            host="antigravity",
        )
        self.assertEqual(res["indexed_count"], 5)
        self.assertEqual(res["candidates"][0]["name"], "wechat-article-scraper")

        # Blocked skill excluded
        res_ret = rs.search_skills(
            query="Deprecated legacy print",
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
            telemetry_path=self.telem,
        )
        self.assertEqual(res_ret["matched_count"], 0)

        # P1-3: 1-char query ("X") and stopword query ("skill") must NOT crash
        res_x = rs.search_skills(
            query="X",
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
            telemetry_path=self.telem,
        )
        self.assertEqual(res_x["candidates"][0]["name"], "douban-skill")

        res_sw = rs.search_skills(
            query="skill",
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
            telemetry_path=self.telem,
        )
        self.assertIsInstance(res_sw["candidates"], list)

    def test_get_skill_pagination_pruning_and_cache_invalidation(self) -> None:
        # P0-3 + P1-3: giant skill must be truncated cleanly AND page 2 (offset>0) must NOT emit a 2nd load event
        loaded = rs.get_skill(
            name="giant-skill",
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
            telemetry_path=self.telem,
            max_chars=16000,
        )
        self.assertTrue(loaded["truncated"])
        self.assertEqual(len(loaded["content"]), 16000)
        self.assertEqual(loaded["next_offset"], 16000)
        self.assertIn("## Section B", loaded["toc_headings"])
        rs.get_skill(
            name="giant-skill",
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
            telemetry_path=self.telem,
            max_chars=16000,
            offset=16000,
        )
        stats_after_p2 = rs.telemetry_stats(self.telem)
        self.assertEqual(stats_after_p2["loads"], 1)

        # P2-2: node_modules pruned from scripts listing
        douban = rs.get_skill(
            name="douban-skill",
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
            telemetry_path=self.telem,
        )
        self.assertIn("scripts/run.py", douban["scripts"])
        self.assertFalse(any("node_modules" in s for s in douban["scripts"]))

        # P1-2: editing SKILL.md invalidates runtime-index.json cache immediately
        p = self.installed / "douban-skill" / "SKILL.md"
        p.write_text(p.read_text(encoding="utf-8").replace("book/movie", "unique-edited-marker"), encoding="utf-8")
        res_edit = rs.search_skills(
            query="unique-edited-marker",
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
            telemetry_path=self.telem,
        )
        self.assertEqual(res_edit["candidates"][0]["name"], "douban-skill")

    def test_categories_browse_guards_and_no_watchpaths_noise(self) -> None:
        # P0-4 + P0-5: categories/browse must NOT write to telemetry.jsonl
        cats = rs.list_skill_categories(
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
        )
        self.assertGreaterEqual(cats["total_skills"], 3)
        self.assertFalse(self.telem.exists())

        with self.assertRaises(ValueError):
            rs.browse_skill_category(
                "all",
                installed_root=self.installed,
                sources_config=self.sources_cfg,
                governance_dir=self.gov,
                cache_path=self.cache,
                confirm_full_scan=False,
            )

        all_res = rs.browse_skill_category(
            "all",
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
            confirm_full_scan=True,
        )
        self.assertIn("douban-skill", all_res["catalog"])

    def test_mcp_server_strict_jsonrpc_and_malformed_inputs(self) -> None:
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "method": "ping"},  # notification without id -> must NOT emit response
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": []},  # malformed params -> -32602
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search_local_skills", "arguments": []}},  # malformed args -> -32602
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "search_local_skills", "arguments": {"query": "豆瓣", "limit": None}}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "browse_skill_category", "arguments": {"category": "bogus-cat"}}},
            {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "browse_skill_category", "arguments": {"category": "all", "confirm_full_scan": "false"}}},  # P1-5 string false must NOT bypass!
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "list_skill_categories", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "get_local_skill", "arguments": {"name": "douban-skill", "query": "导出 https://secret.example/token"}}},
        ]
        stdin_payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in requests) + "\n"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "mcp_server.py"),
                "--host", "antigravity",
                "--installed-root", str(self.installed),
                "--sources-config", str(self.sources_cfg),
                "--governance-dir", str(self.gov),
                "--cache", str(self.cache),
                "--telemetry", str(self.telem),
            ],
            input=stdin_payload,
            text=True,
            capture_output=True,
            check=True,
        )
        responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual([r["id"] for r in responses], [1, 2, 3, 4, 5, 6, 9, 7, 8])
        self.assertEqual(
            [t["name"] for t in responses[1]["result"]["tools"]],
            ["list_skill_categories", "browse_skill_category", "search_local_skills", "get_local_skill"],
        )
        self.assertEqual(responses[2]["error"]["code"], -32602)
        self.assertEqual(responses[3]["error"]["code"], -32602)
        self.assertFalse(responses[4]["result"]["isError"])
        self.assertTrue(responses[5]["result"]["isError"])  # bogus category returns error
        self.assertTrue(responses[6]["result"]["isError"])  # confirm_full_scan="false" MUST be rejected
        self.assertIn("Cold local skills", responses[7]["result"]["content"][0]["text"])
        self.assertIn("skill: douban-skill", responses[8]["result"]["content"][0]["text"])

        # Verify sensitive URL was redacted in telemetry
        telem_text = self.telem.read_text(encoding="utf-8")
        self.assertNotIn("secret.example", telem_text)
        self.assertIn("[redacted]", telem_text)

    def test_agent_skill_ops_category_matches_agent_message_antigravity_and_legacy_peer_message(self) -> None:
        make_skill(
            self.installed,
            "agent-message",
            "agent-message",
            "Bridges local cross-session messaging across terminal windows.",
        )
        make_skill(
            self.installed,
            "agy-helper",
            "agy-helper",
            "Inspects Antigravity workspace transcripts.",
        )
        make_skill(
            self.installed,
            "peer-message",
            "peer-message",
            "Deprecated compatibility alias forwarding legacy scripts.",
        )

        # Invalidate index cache and verify all three land in agent-skill-ops
        browsed = rs.browse_skill_category(
            "agent-skill-ops",
            installed_root=self.installed,
            sources_config=self.sources_cfg,
            governance_dir=self.gov,
            cache_path=self.cache,
        )
        catalog = browsed["catalog"]
        self.assertIn("agent-message", catalog)
        self.assertIn("agy-helper", catalog)
        self.assertIn("peer-message", catalog)


if __name__ == "__main__":
    unittest.main()
