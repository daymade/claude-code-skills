"""Contracts for the two mixed-suite cold-discovery boundaries."""

import json
import re
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SPECS = {
    "daymade-financial": {
        "router": "financial-router",
        "cold": {
            "ashare-news-fetcher", "bigdata-skill", "financial-data-collector",
            "daymade-sector-research", "pharma-daily-report", "gangtise-copilot",
        },
        "hot": {"devils-advocate", "benchmark-due-diligence"},
        "prefix": ("Bigdata/RavenPack", "US fundamentals/yfinance", "A-share",
                   "sector Top N/announcements", "pharma daily/医药日报",
                   "Gangtise/岗底斯"),
    },
    "daymade-claude-code": {
        "router": "claude-code-ops-router",
        "cold": {
            "claude-skills-troubleshooting", "statusline-generator",
            "claude-export-txt-better", "marketplace-dev", "claude-usage-analyst",
            "claude-switch-models-setup", "claude-migrate-memory-to-doc",
            "claude-code-ping-start-5h-quota",
        },
        "hot": {
            "local-conversation-history", "read-claude-code-history",
            "read-codex-history", "continue-claude-code-work", "continue-codex-work",
            "prior-work-retrieval", "claude-code-hooks", "lark-cli-router",
            "tech-selection", "terminal-screenshot", "agent-web-search-setup",
            "read-claude-web-conversation", "claude-md-progressive-disclosurer",
        },
        "prefix": ("plugin/Skill repair", "marketplace", "statusline",
                   "model profiles/source sync", "usage/quota reset ping",
                   "memory→docs", ".txt export repair"),
    },
}


def frontmatter(path):
    first, header, _body = path.read_text(encoding="utf-8").split("---", 2)
    assert first == "", path
    return header


class MixedSuiteRouterContractTest(unittest.TestCase):
    def test_routes_are_exact_installed_siblings_and_survive_symlink_entry(self):
        manifest = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
        by_name = {item["name"]: item for item in manifest["plugins"]}
        for suite_name, spec in SPECS.items():
            with self.subTest(suite=suite_name):
                suite = REPO / suite_name
                router = suite / spec["router"] / "SKILL.md"
                body = router.read_text(encoding="utf-8")
                routes = re.findall(r"\.\./([^/]+)/SKILL\.md", body)
                self.assertEqual(len(routes), len(set(routes)))
                self.assertEqual(set(routes), spec["cold"])
                for name in routes:
                    target = (router.parent / ".." / name / "SKILL.md").resolve(strict=True)
                    self.assertEqual(target, (suite / name / "SKILL.md").resolve())
                with tempfile.TemporaryDirectory() as temp:
                    link = Path(temp) / "SKILL.md"
                    link.symlink_to(router)
                    self.assertEqual(link.resolve(strict=True), router.resolve())
                plugin = by_name[suite_name]
                self.assertEqual(plugin["source"], f"./{suite_name}")
                self.assertEqual(
                    set(plugin["skills"]),
                    {f"./{path.parent.name}" for path in suite.glob("*/SKILL.md")},
                )

    def test_only_selected_leaves_are_manual_only(self):
        for suite_name, spec in SPECS.items():
            with self.subTest(suite=suite_name):
                suite = REPO / suite_name
                router = suite / spec["router"] / "SKILL.md"
                self.assertNotIn("disable-model-invocation: true", frontmatter(router))
                for name in spec["cold"]:
                    self.assertIn(
                        "disable-model-invocation: true",
                        frontmatter(suite / name / "SKILL.md"),
                        name,
                    )
                for name in spec["hot"]:
                    self.assertNotIn(
                        "disable-model-invocation: true",
                        frontmatter(suite / name / "SKILL.md"),
                        name,
                    )

    def test_each_first_160_characters_identifies_its_routes(self):
        for suite_name, spec in SPECS.items():
            with self.subTest(suite=suite_name):
                router = REPO / suite_name / spec["router"] / "SKILL.md"
                header = frontmatter(router)
                description = " ".join(
                    line.strip()
                    for line in header.split("description: >-", 1)[1].splitlines()
                    if line.startswith("  ")
                )
                for signal in spec["prefix"]:
                    self.assertIn(signal, description[:160], (suite_name, signal))


if __name__ == "__main__":
    unittest.main()
