from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prior_work = load_module("prior_work", SCRIPTS_DIR / "prior_work.py")
hook = load_module("prior_work_hook_under_test", SCRIPTS_DIR / "prior_work_hook.py")


class PriorWorkHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "known.md").write_text(
            "known existing provider contract\n", encoding="utf-8"
        )
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "state_dir": str(self.root / "state"),
                    "sources": [
                        {
                            "id": "docs",
                            "carrier": "docs",
                            "mode": "filesystem",
                            "root": str(self.source),
                            "includes": ["**/*.md"],
                            "authority": "project_ssot",
                            "required": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.env = mock.patch.dict(
            os.environ, {"PRIOR_WORK_MANIFEST": str(self.manifest_path)}
        )
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    def test_prompt_classifier_preserves_old_recall_hook_families(self) -> None:
        prompts = [
            "我们之前在本地跑这个用的是哪个框架？",
            "上次做的方案叫什么来着？",
            "我记得是某个脚本，但记不清是哪一个",
            "已有代码和 SOP，别重复造轮子",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    hook.classify_prompt(prompt, False), "required_prior_signal"
                )

    def test_production_prompt_marks_requirement_and_injects_context(self) -> None:
        event = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-1",
            "prompt": "帮我设计并实现一套新的报告流程",
        }
        output = hook.handle_event(event)
        self.assertIn(
            "Prior Work Retrieval",
            output["hookSpecificOutput"]["additionalContext"],
        )
        requirement = prior_work.load_requirement(hook._manifest(), "session-1")
        self.assertTrue(requirement["required"])

    def test_new_or_large_writes_gate_but_small_edit_and_tinkle_file_pass(self) -> None:
        new_write = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "formal.py"),
                "content": "x = 1\n",
            },
        }
        self.assertTrue(hook.substantial_tool_use(new_write)[0])
        small_edit = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.source / "known.md"),
                "new_string": "typo",
            },
        }
        self.assertFalse(hook.substantial_tool_use(small_edit)[0])
        temporary = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "tinkle_probe.py"),
                "content": "x" * 1000,
            },
        }
        self.assertFalse(hook.substantial_tool_use(temporary)[0])

    def test_implicit_pretool_requirement_blocks_until_receipt(self) -> None:
        event = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-2",
            "tool_name": "apply_patch",
            "tool_input": {
                "patch": "*** Add File: formal.py\n+one\n+two\n+three\n+four\n+five\n"
            },
        }
        denied = hook.handle_event(event)
        self.assertEqual(
            denied["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        manifest = hook._manifest()
        run = prior_work.retrieve(
            manifest,
            "reuse provider contract",
            ["provider contract"],
            "session-2",
        )
        candidate = run["candidates"][0]
        prior_work.complete(
            manifest,
            run["run_id"],
            "session-2",
            [f"{candidate['candidate_id']}=reuse verified provider contract"],
            [],
            [],
            [],
            None,
        )
        self.assertIsNone(hook.handle_event(event))

    def test_new_substantial_prompt_invalidates_old_receipt(self) -> None:
        first = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-3",
            "prompt": "已有 provider contract，复用它实现代码",
        }
        hook.handle_event(first)
        manifest = hook._manifest()
        run = prior_work.retrieve(
            manifest, "reuse provider", ["provider contract"], "session-3"
        )
        candidate = run["candidates"][0]
        prior_work.complete(
            manifest,
            run["run_id"],
            "session-3",
            [f"{candidate['candidate_id']}=reuse current contract"],
            [],
            [],
            [],
            None,
        )
        hook.handle_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session-3",
                "prompt": "现在设计另一套报告系统",
            }
        )
        with self.assertRaisesRegex(prior_work.PriorWorkError, "older prompt"):
            prior_work.check_receipt(manifest, "session-3", None)

    def test_user_optout_is_prompt_scoped_and_allows_write(self) -> None:
        hook.handle_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session-4",
                "prompt": "这次不用查历史，跳过已有工作检索",
            }
        )
        write = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-4",
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "new.md"),
                "content": "substantial" * 100,
            },
        }
        self.assertIsNone(hook.handle_event(write))
        status = prior_work.check_receipt(hook._manifest(), "session-4", None)
        self.assertEqual(status["status"], "not_required")

    def test_stop_blocks_substantial_reply_and_anti_loop_releases_retry(self) -> None:
        event = {
            "hook_event_name": "Stop",
            "session_id": "session-5",
            "stop_hook_active": False,
            "last_assistant_message": "- detailed item\n" * 80,
        }
        self.assertEqual(hook.handle_event(event)["decision"], "block")
        event["stop_hook_active"] = True
        self.assertIsNone(hook.handle_event(event))

    def test_missing_manifest_fails_closed_only_for_substantial_action(self) -> None:
        os.environ["PRIOR_WORK_MANIFEST"] = str(self.root / "missing.json")
        large = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-6",
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "new.py"),
                "content": "x" * 300,
            },
        }
        self.assertEqual(
            hook.handle_event(large)["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )
        read_only = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-6",
            "tool_name": "Read",
            "tool_input": {"file_path": str(self.source / "known.md")},
        }
        self.assertIsNone(hook.handle_event(read_only))

    def test_hook_config_merge_is_additive_idempotent_and_retires_legacy(self) -> None:
        wrapper = self.root / "prior-work-retrieval.sh"
        wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
        current = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {"type": "command", "command": "keep-me.sh"},
                            {
                                "type": "command",
                                "command": "~/.claude/hooks/recall-first-evidence.sh",
                            },
                        ]
                    }
                ],
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "other.sh"}],
                    }
                ],
            }
        }
        merged = hook.merged_hooks(
            current, wrapper, "claude", remove_legacy_recall=True
        )
        rendered = json.dumps(merged)
        self.assertIn("keep-me.sh", rendered)
        self.assertIn("other.sh", rendered)
        self.assertNotIn("recall-first-evidence", rendered)
        self.assertEqual(rendered.count("prior-work-retrieval"), 3)
        second = hook.merged_hooks(
            merged, wrapper, "claude", remove_legacy_recall=True
        )
        self.assertEqual(second, merged)

    def test_codex_and_claude_matchers_cover_native_write_tools(self) -> None:
        wrapper = self.root / "prior-work-retrieval.sh"
        wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
        claude = hook.desired_hook_groups(wrapper, "claude")
        codex = hook.desired_hook_groups(wrapper, "codex")
        self.assertIn("Write", claude["PreToolUse"]["matcher"])
        self.assertIn("Agent", claude["PreToolUse"]["matcher"])
        self.assertIn("apply_patch", codex["PreToolUse"]["matcher"])
        self.assertIn("spawn_agent", codex["PreToolUse"]["matcher"])


if __name__ == "__main__":
    unittest.main()
