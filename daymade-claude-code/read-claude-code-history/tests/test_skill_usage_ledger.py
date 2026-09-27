"""Tests for the skill invocation ledger: initiator attribution and incrementality."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import history_index  # noqa: E402
import skill_usage_ledger as ledger  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"
CODEX_SID = "019a0000-0000-7000-8000-00000000abcd"


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def user(text, ts, uuid, **extra):
    return {"type": "user", "uuid": uuid, "sessionId": SID, "timestamp": ts,
            "isSidechain": False, "entrypoint": "cli",
            "message": {"role": "user", "content": text}, **extra}


def skill_call(skill, ts, tool_id):
    return {"type": "assistant", "uuid": "a-" + tool_id, "sessionId": SID,
            "timestamp": ts, "isSidechain": False, "entrypoint": "cli",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": tool_id, "name": "Skill",
                 "input": {"skill": skill}}]}}


def tool_result(text, ts, uuid):
    return {"type": "user", "uuid": uuid, "sessionId": SID, "timestamp": ts,
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t", "content": text}]}}


def claude_session() -> list[dict]:
    return [
        # 1. user types a slash command -> user_command
        user("<command-message>alpha-skill</command-message>\n"
             "<command-name>/alpha-skill</command-name>", "2026-09-01T00:00:00Z", "u1"),
        # 2. user names beta, model calls it -> model_named
        user("please use beta-skill for this", "2026-09-01T00:01:00Z", "u2"),
        skill_call("plugin:beta-skill", "2026-09-01T00:02:00Z", "t1"),
        # 3. a tool result quoting an envelope must not count as a command
        tool_result("<command-name>/ghost</command-name>", "2026-09-01T00:03:00Z", "u3"),
        # 4. new prompt without a name; model calls gamma -> model_auto
        user("fix the flaky test", "2026-09-01T00:04:00Z", "u4"),
        skill_call("gamma-skill", "2026-09-01T00:05:00Z", "t2"),
        # 5. compaction summary quoting an envelope must not count either,
        #    and must not become the prompt that "names" a later skill
        user("This session is being continued...\n<command-name>/phantom</command-name>"
             " gamma-skill", "2026-09-01T00:06:00Z", "u5"),
        skill_call("gamma-skill", "2026-09-01T00:07:00Z", "t3"),
        # 6. meta record (skill body injection) is ignored
        user("Base directory for this skill: /x/alpha-skill", "2026-09-01T00:08:00Z",
             "u6", isMeta=True),
        # 7. model reaches for a hidden skill and the host refuses -> blocked
        user("tidy the notes", "2026-09-01T00:09:00Z", "u7"),
        skill_call("iota-skill", "2026-09-01T00:10:00Z", "t4"),
        {"type": "user", "uuid": "u8", "timestamp": "2026-09-01T00:10:01Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "t4", "is_error": True,
              "content": "<tool_use_error>Skill iota-skill is disabled for model "
                         "invocation in skillOverrides settings</tool_use_error>"}]}},
    ]


def codex_session(cwd: Path) -> list[dict]:
    def item(payload, ts):
        return {"type": "response_item", "timestamp": ts, "payload": payload}

    def umsg(text, ts):
        return item({"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": text}]}, ts)

    def call(cmd, ts, name="exec_command"):
        return item({"type": "function_call", "name": name,
                     "arguments": json.dumps({"cmd": cmd})}, ts)

    return [
        {"type": "session_meta", "timestamp": "2026-09-02T00:00:00Z",
         "payload": {"id": CODEX_SID, "cwd": str(cwd), "originator": "codex-tui"}},
        umsg("# AGENTS.md instructions\n<INSTRUCTIONS>use delta-skill</INSTRUCTIONS>",
             "2026-09-02T00:00:01Z"),
        umsg("<skill>\n<name>delta-skill</name>\n<path>/s/delta-skill/SKILL.md</path>\n</skill>",
             "2026-09-02T00:00:02Z"),
        umsg("summarise the report", "2026-09-02T00:00:03Z"),
        call("cat /home/u/.agents/skills/epsilon-skill/SKILL.md", "2026-09-02T00:00:04Z"),
        umsg("run zeta-skill please", "2026-09-02T00:00:05Z"),
        call("sed -n 1,200p /home/u/.agents/skills/zeta-skill/SKILL.md", "2026-09-02T00:00:06Z"),
        call("cat /a/one/SKILL.md /a/two/SKILL.md", "2026-09-02T00:00:07Z"),
        call("sed -n 1,80p kappa-skill/SKILL.md", "2026-09-02T00:00:09Z"),
        call(f"cat {cwd}/lambda-skill/SKILL.md", "2026-09-02T00:00:10Z"),
        call(f"cat {cwd}/.agents/skills/mu-skill/SKILL.md", "2026-09-02T00:00:11Z"),
        item({"type": "custom_tool_call", "name": "apply_patch",
              "input": "*** Update File: /s/eta-skill/SKILL.md"}, "2026-09-02T00:00:08Z"),
    ]


class LedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.workspace = root / "ws"
        self.workspace.mkdir()
        self.claude_home = root / "claude"
        self.codex_home = root / "codex"
        encoded = str(self.workspace.resolve()).replace("/", "-")
        self.claude_file = self.claude_home / "projects" / encoded / f"{SID}.jsonl"
        write_jsonl(self.claude_file, claude_session())
        write_jsonl(
            self.codex_home / "sessions" / "2026" / "09" / "02" / f"rollout-2026-09-02T00-00-00-{CODEX_SID}.jsonl",
            codex_session(self.workspace),
        )
        self.db = root / "ledger.db"
        self.settings = root / "settings.json"
        self.settings.write_text(json.dumps({"skillOverrides": {
            "gamma-skill": "user-invocable-only", "unused-skill": "user-invocable-only"}}))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def scope(self):
        return history_index.IndexScope(
            sources=[
                history_index.HistorySource("claude", "active", "main", self.claude_home),
                history_index.HistorySource("codex", "active", "codex", self.codex_home),
            ],
            warnings=[], project_path=None, all_projects=True,
        )

    def events(self) -> list[tuple]:
        connection = sqlite3.connect(self.db)
        rows = connection.execute(
            "SELECT provider, bare, initiator FROM events ORDER BY ts, bare").fetchall()
        connection.close()
        return rows

    def test_initiators_attributed_per_provider(self) -> None:
        result = ledger.update(self.db, self.scope())
        self.assertEqual(result["sessions"], 2)
        self.assertEqual(self.events(), [
            ("claude", "alpha-skill", "user_command"),
            ("claude", "beta-skill", "model_named"),
            ("claude", "gamma-skill", "model_auto"),
            ("claude", "gamma-skill", "model_auto"),
            ("claude", "iota-skill", "model_auto"),
            ("codex", "delta-skill", "user_command"),
            ("codex", "epsilon-skill", "model_auto"),
            ("codex", "zeta-skill", "model_named"),
            ("codex", "one", "bulk_read"),
            ("codex", "two", "bulk_read"),
            ("codex", "kappa-skill", "dev_read"),
            ("codex", "lambda-skill", "dev_read"),
            ("codex", "mu-skill", "model_auto"),
        ])

    def test_unchanged_files_are_not_reparsed(self) -> None:
        ledger.update(self.db, self.scope())
        second = ledger.update(self.db, self.scope())
        self.assertEqual((second["added"], second["changed"], second["unchanged"]), (0, 0, 2))
        with self.claude_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(skill_call("theta-skill", "2026-09-03T00:00:00Z", "t9"),
                                    separators=(",", ":")) + "\n")
        stat = self.claude_file.stat()
        os.utime(self.claude_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))
        third = ledger.update(self.db, self.scope())
        self.assertEqual((third["changed"], third["unchanged"]), (1, 1))
        self.assertIn(("claude", "theta-skill", "model_auto"), self.events())
        self.assertEqual(len(self.events()), 14)

    def test_report_joins_overrides_and_lists_unused_hidden_skills(self) -> None:
        ledger.update(self.db, self.scope())
        rows = {r["skill"]: r for r in ledger.report(
            self.db, names=[], since=None, settings_path=self.settings,
            only_override="user-invocable-only")}
        self.assertEqual(set(rows), {"gamma-skill", "unused-skill"})
        self.assertEqual((rows["gamma-skill"]["model_auto"], rows["gamma-skill"]["override"]),
                         (2, "user-invocable-only"))
        self.assertEqual(rows["unused-skill"]["total"], 0)
        everything = {r["skill"] for r in ledger.report(
            self.db, names=[], since=None, settings_path=self.settings, only_override=None)}
        self.assertNotIn("one", everything, "bulk reads must not count as use")
        self.assertEqual(len(everything), 8)
        iota = ledger.report(self.db, names=["iota-skill"], since=None,
                             settings_path=self.settings, only_override=None)[0]
        self.assertEqual((iota["blocked"], iota["model_auto"], iota["total"]), (1, 0, 0))
        connection = sqlite3.connect(self.db)
        outcomes = dict(connection.execute(
            "SELECT bare, outcome FROM events WHERE provider='claude' "
            "AND initiator LIKE 'model%'").fetchall())
        connection.close()
        self.assertEqual(outcomes["iota-skill"], "blocked")


if __name__ == "__main__":
    unittest.main()
