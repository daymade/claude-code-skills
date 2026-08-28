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
            "之前用的那个框架是什么来着？",
            "上次做的方案叫什么来着？",
            "我记得是某个脚本，但记不清是哪一个",
            "已有代码和 SOP，别重复造轮子",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    hook.classify_prompt(prompt, False), "required_prior_signal"
                )

    def test_ordinary_production_prompt_does_not_create_requirement(self) -> None:
        event = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-1",
            "prompt": "帮我设计并实现一套新的报告流程",
        }
        self.assertIsNone(hook.handle_event(event))

    def test_current_tests_files_and_readme_are_not_prior_work_requests(self) -> None:
        for prompt in [
            (
                "修复报价计算；只修改必要的实现，现有测试或 README "
                "如果与业务契约冲突才同步"
            ),
            "先读当前文件和现有测试，再修这个 bug",
            "保持现有行为不变，只调整当前函数的错误分支",
        ]:
            with self.subTest(prompt=prompt):
                self.assertEqual(hook.classify_prompt(prompt, False), "none")

    def test_explicit_existing_assets_still_trigger(self) -> None:
        for prompt in [
            "已有代码和 SOP，先复用再改",
            "先核对既有资产，再决定是否重写",
            "已有脚本可以直接沿用",
            "已有 SOP，先沿用再改",
            "直接沿用现有实现，不要重写",
            "已有一套脚本，直接沿用",
            "请先核对已有两套脚本，再决定怎么改",
            "请先核对已有 的 SOP，再决定怎么改",
            "先盘点既有好几批资产，再决定是否重做",
        ]:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    hook.classify_prompt(prompt, False),
                    "required_prior_signal",
                )
        requirement = prior_work.load_requirement(hook._manifest(), "session-1")
        self.assertIsNone(requirement)

    def test_explicit_read_only_maintenance_does_not_trigger_production(self) -> None:
        prompt = (
            "这是只读仓库维护任务：检查 Git 脏文件和会议规则，输出状态摘要；"
            "不要修改文件，不要派 agent。"
        )
        self.assertEqual(hook.classify_prompt(prompt, False), "none")
        event = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-read-only",
            "prompt": prompt,
        }
        self.assertIsNone(hook.handle_event(event))
        requirement = prior_work.load_requirement(
            hook._manifest(), "session-read-only"
        )
        self.assertIsNone(requirement)

    def test_prior_work_signal_still_wins_inside_read_only_request(self) -> None:
        prompt = "只读检查我们之前的 provider contract，不要修改文件"
        self.assertEqual(
            hook.classify_prompt(prompt, False), "required_prior_signal"
        )

    def test_new_or_large_writes_classify_but_small_edit_passes(self) -> None:
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
        named_scratch = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "tinkle_probe.py"),
                "content": "x" * 1000,
            },
        }
        self.assertTrue(hook.substantial_tool_use(named_scratch)[0])

    def test_tool_input_and_names_normalize_across_hosts(self) -> None:
        raw_patch = {
            "tool_name": "functions.apply_patch",
            "tool_input": "*** Add File: formal.py\n+one\n+two\n+three\n+four\n+five\n",
        }
        self.assertTrue(hook.substantial_tool_use(raw_patch)[0])

        existing = self.root / "existing.md"
        existing.write_text("present\n", encoding="utf-8")
        relative_write = {
            "tool_name": "Write",
            "cwd": str(self.root),
            "tool_input": {
                "file_path": "existing.md",
                "content": "small",
            },
        }
        substantial, reason = hook.substantial_tool_use(relative_write)
        self.assertFalse(substantial)
        self.assertIn("new=False", reason)

    def test_shell_and_exec_writes_gate_while_read_only_discovery_passes(self) -> None:
        bash_write = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 -c \"from pathlib import Path; Path('x').write_text('y')\""
            },
        }
        self.assertTrue(hook.substantial_tool_use(bash_write)[0])
        exec_patch = {
            "tool_name": "functions.exec",
            "tool_input": "await tools.apply_patch('*** Add File: x\\n+content')",
        }
        self.assertTrue(hook.substantial_tool_use(exec_patch)[0])
        read_only = {
            "tool_name": "Bash",
            "tool_input": {"command": "rg -n 'needle' README.md"},
        }
        self.assertFalse(hook.substantial_tool_use(read_only)[0])
        retrieval = {
            "tool_name": "functions.exec",
            "tool_input": "uv run python scripts/prior_work.py retrieve --query x",
        }
        self.assertFalse(hook.substantial_tool_use(retrieval)[0])
        for event in (
            {
                "tool_name": "Bash",
                "tool_input": {"command": "printf x > production.md"},
            },
            {
                "tool_name": "exec_command",
                "tool_input": {"cmd": "sed -n '1p' source.md > production.md"},
            },
            {
                "tool_name": "functions.exec",
                "tool_input": {
                    "code": "await tools.exec_command({cmd: 'printf x > production.md'})"
                },
            },
        ):
            with self.subTest(event=event):
                self.assertTrue(hook.substantial_tool_use(event)[0])
        scratch_redirect = {
            "tool_name": "Bash",
            "tool_input": {"command": "printf x > /tmp/tinkle_probe.txt"},
        }
        self.assertTrue(hook.substantial_tool_use(scratch_redirect)[0])

    def test_retrieval_route_prose_does_not_trip_write_signal(self) -> None:
        # Regression (2026-08-27): a --reject reason quoting "cp→symlink" let
        # \bcp\b match the write signal before the retrieval-route exemption
        # ran, blocking the gate's own receipt-completion command.
        prose_complete = {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "uv run --no-project python scripts/prior_work.py complete "
                    "--run RUN_ID --reject 'abc=独立评审讲 cp→symlink 部署演进' "
                    "--session-id SID"
                )
            },
        }
        substantial, reason = hook.substantial_tool_use(prose_complete)
        self.assertFalse(substantial, reason)

    def test_quoted_comparison_operators_are_argument_data(self) -> None:
        # Regression (2026-08-27): '未合并>7天' inside a quoted --reuse reason
        # scanned as `> 7天...` file redirection (the redirection check ran on
        # raw text, outside the retrieval-route exemption), blocking the
        # gate's own receipt-completion command.
        single_quoted = {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "uv run --no-project python scripts/prior_work.py complete "
                    "--run RUN_ID --reuse 'id=reuse: 两级判定(未合并>7天、已合并>30天)' "
                    "--session-id SID"
                )
            },
        }
        substantial, reason = hook.substantial_tool_use(single_quoted)
        self.assertFalse(substantial, reason)
        double_quoted = {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "uv run python scripts/prior_work.py retrieve "
                    '--outcome-term "age>30" --query q'
                )
            },
        }
        substantial, reason = hook.substantial_tool_use(double_quoted)
        self.assertFalse(substantial, reason)

    def test_unquoted_redirection_even_after_route_stays_gated(self) -> None:
        # Stripping quoted text must not weaken the gate: a real redirection
        # in unquoted position — even trailing a whitelisted route command —
        # is still a write.
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "uv run python scripts/prior_work.py check > receipt.json"
            },
        }
        substantial, reason = hook.substantial_tool_use(event)
        self.assertTrue(substantial, reason)
        self.assertEqual(reason, "Bash:write_signal")

    def test_gate_messages_carry_the_real_session_id(self) -> None:
        # Regression (2026-08-27): the deny message only ever showed the
        # sha256 receipt filename, so the agent could not recover its real
        # --session-id from the gate message and completed the receipt under
        # a made-up id (the hash itself) — the gate kept rejecting every
        # substantial write even though a receipt existed.
        prior_work.mark_requirement(
            hook._manifest(),
            "session-guidance-9f2",
            prompt="复用以前的正式实现",
            trigger="required_prior_signal",
            required=True,
        )
        event = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-guidance-9f2",
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "formal.py"),
                "content": "x = 1\n" * 30,
            },
        }
        denied = hook.handle_event(event)
        reason = denied["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("--session-id 'session-guidance-9f2'", reason)
        self.assertIn("sha256", reason)

    def test_dot_sh_paths_are_not_unknown_executors(self) -> None:
        # Regression (2026-08-27, session self-review finding 3): \bsh\b
        # matched the "sh" inside `.sh` path suffixes, so reading a script
        # with cat was gated as running an unknown interpreter.
        read_script = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "cat /scripts/stale-branch-watch/report.sh; ls -la /tmp",
            },
        }
        substantial, reason = hook.substantial_tool_use(read_script)
        self.assertFalse(substantial, reason)
        # The bare interpreter form still gates.
        bare = {
            "tool_name": "Bash",
            "tool_input": {"command": "sh -c 'echo hi'"},
        }
        substantial, reason = hook.substantial_tool_use(bare)
        self.assertTrue(substantial, reason)
        self.assertEqual(reason, "Bash:unknown_executor")
        # Interpreter via absolute path still gates.
        absolute = {
            "tool_name": "Bash",
            "tool_input": {"command": "/bin/zsh script.zsh"},
        }
        substantial, reason = hook.substantial_tool_use(absolute)
        self.assertTrue(substantial, reason)

    def test_retrieval_name_inside_arbitrary_code_cannot_launder_write(self) -> None:
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "python3 -c \"print('prior_work.py retrieve'); "
                    "from pathlib import Path; Path('x').write_text('y')\""
                )
            },
        }
        substantial, reason = hook.substantial_tool_use(event)
        self.assertTrue(substantial, reason)
        self.assertEqual(reason, "Bash:write_signal")

    def test_unknown_prefix_before_retrieval_route_stays_gated(self) -> None:
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    'python3 -c "print(123)" && '
                    "uv run python scripts/prior_work.py check"
                )
            },
        }
        substantial, reason = hook.substantial_tool_use(event)
        self.assertTrue(substantial, reason)
        self.assertEqual(reason, "Bash:unknown_executor")

    def test_route_classifier_requires_real_argv_entry(self) -> None:
        self.assertTrue(hook._segment_is_retrieval_route(
            "uv run --no-project python scripts/prior_work.py complete --reason 'cp→symlink'"
        ))
        self.assertTrue(hook._segment_is_retrieval_route(
            "env -u HTTP_PROXY MODE=test uv run --with PyYAML python scripts/prior_work.py check"
        ))
        self.assertTrue(hook._segment_is_retrieval_route(
            "command python3 /some/path/read_chat.py --talker example"
        ))
        self.assertFalse(hook._segment_is_retrieval_route(
            "python3 -c \"print('prior_work.py retrieve')\""
        ))
        self.assertFalse(hook._segment_is_retrieval_route(
            "echo 'prior_work.py retrieve'"
        ))

    def test_escaped_separator_in_retrieval_reason_is_argument_data(self) -> None:
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "uv run python scripts/prior_work.py complete "
                    "--reason escaped\\;cp"
                )
            },
        }
        substantial, reason = hook.substantial_tool_use(event)
        self.assertFalse(substantial, reason)

    def test_background_write_after_retrieval_route_stays_gated(self) -> None:
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "uv run python scripts/prior_work.py check & git commit -a"
            },
        }
        substantial, reason = hook.substantial_tool_use(event)
        self.assertTrue(substantial, reason)

    def test_process_substitution_cannot_hide_write_in_retrieval_args(self) -> None:
        for command in (
            "prior_work.py check < <(git push)",
            "prior_work.py check =(git push)",
        ):
            with self.subTest(command=command):
                event = {"tool_name": "Bash", "tool_input": {"command": command}}
                substantial, reason = hook.substantial_tool_use(event)
                self.assertTrue(substantial, reason)

    def test_write_signal_still_wins_outside_retrieval_args(self) -> None:
        cases = [
            # Magic words inside a git message must not launder a real write.
            'git commit -m "prior_work.py complete 修复"',
            # A write chained after the retrieval command is still a write.
            "uv run python scripts/prior_work.py check && git commit -a",
            # Substitution inside retrieval args still executes; stay closed.
            'uv run python scripts/prior_work.py check "$(git commit -a)"',
            # A write before the retrieval token in another segment.
            "git commit -a; uv run python scripts/prior_work.py check",
        ]
        for command in cases:
            with self.subTest(command=command):
                event = {"tool_name": "Bash", "tool_input": {"command": command}}
                substantial, reason = hook.substantial_tool_use(event)
                self.assertTrue(substantial, reason)

    def test_retrieval_chain_and_benign_segments_pass(self) -> None:
        event = {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "cd /some/path && uv run python scripts/prior_work.py retrieve "
                    "--query x --term y 2>&1 | tail -5"
                )
            },
        }
        substantial, reason = hook.substantial_tool_use(event)
        self.assertFalse(substantial, reason)

    def test_independent_review_adversarial_corpus(self) -> None:
        # Pins shapes from the 2026-08-27 two-round independent review that the
        # dedicated tests above do not cover (archive: PKM
        # next/_meta/skill-reviews/prior-work-retrieval/independent-review.md).
        # Every shape was verified behaviorally against this hook before pinning.
        gated = [
            # F3 literals: an inner shell re-parses the wrapper string.
            'bash -c "prior_work.py check; git push"',
            'eval "prior_work.py check && git push"',
            "printf '%s' 'prior_work.py check; git push' | xargs -I{} sh -c {}",
            # F4: a backslash-escaped quote outside quotes must not enter quote state.
            'prior_work.py check \\"& git push',
            # F5: a substring of a different filename is not the route.
            "python my_prior_work.py check & git push",
            # F-new-1: bare &- is a zsh async separator (only >&- is fd close).
            "prior_work.py check &- git push",
            # F-new-2: wrapper prefixes beyond the naive five-name list.
            'env FOO=1 bash -c "prior_work.py check; git push"',
            'command bash -c "prior_work.py check; git push"',
            '(bash -c "prior_work.py check; git push")',
            'ssh host "prior_work.py check; git push"',
            # F-new-3: $'…' ANSI-C quoting desyncs a naive quote state machine.
            "prior_work.py check $'x\\'y'; git push",
        ]
        for command in gated:
            with self.subTest(command=command):
                event = {"tool_name": "Bash", "tool_input": {"command": command}}
                substantial, reason = hook.substantial_tool_use(event)
                self.assertTrue(substantial, reason)
        allowed = [
            # Backgrounding the route command itself is benign.
            "uv run python scripts/prior_work.py check --session-id S &",
            # A wrapped route call without any write token stays allowed.
            'bash -c "prior_work.py check"',
            # >&- is fd close, not a separator.
            "uv run python scripts/prior_work.py check 2>&- --session-id S",
        ]
        for command in allowed:
            with self.subTest(command=command):
                event = {"tool_name": "Bash", "tool_input": {"command": command}}
                substantial, reason = hook.substantial_tool_use(event)
                self.assertFalse(substantial, reason)

    def test_pretool_never_invents_requirement_for_ordinary_write(self) -> None:
        event = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-2",
            "tool_name": "apply_patch",
            "tool_input": {
                "patch": "*** Add File: formal.py\n+one\n+two\n+three\n+four\n+five\n"
            },
        }
        self.assertIsNone(hook.handle_event(event))
        self.assertIsNone(
            prior_work.load_requirement(hook._manifest(), "session-2")
        )

    def test_new_explicit_prior_prompt_invalidates_old_receipt(self) -> None:
        first = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-3",
            "prompt": "已有 provider contract，复用它实现代码",
        }
        hook.handle_event(first)
        manifest = hook._manifest()
        run = prior_work.retrieve(
            manifest,
            "Reuse the verified provider contract before writing new code.",
            ["provider contract"],
            "reuse provider",
            ["provider contract"],
            "session-3",
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
                "prompt": "现在复用以前那套报告系统",
            }
        )
        with self.assertRaisesRegex(prior_work.PriorWorkError, "older prompt"):
            prior_work.check_receipt(manifest, "session-3", None)

    def test_ordinary_followup_does_not_invalidate_explicit_receipt(self) -> None:
        session_id = "session-ordinary-followup"
        hook.handle_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "prompt": "复用以前的 provider contract",
            }
        )
        manifest = hook._manifest()
        run = prior_work.retrieve(
            manifest,
            "Reuse the verified provider contract.",
            ["provider contract"],
            "reuse provider",
            ["provider contract"],
            session_id,
        )
        candidate = run["candidates"][0]
        prior_work.complete(
            manifest,
            run["run_id"],
            session_id,
            [f"{candidate['candidate_id']}=reuse current contract"],
            [],
            [],
            [],
            None,
        )
        hook.handle_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "prompt": "现在实现报告系统",
            }
        )
        self.assertEqual(
            prior_work.check_receipt(manifest, session_id, None)["status"],
            "valid",
        )

    def test_internal_templates_and_transcripts_are_not_user_prompts(self) -> None:
        # Every one of these opened its own gated session in production and
        # never produced a receipt: Claude Code's safety classifier and
        # suggestion generator, a sub-agent role prompt, an inter-agent
        # message, and a pasted transcript line.
        # Each body carries a signal word on purpose: the stored 240-char
        # previews are truncated, and it is the full template text that
        # matched and armed these sessions in production.
        not_the_user = [
            "You are an expert at upholding safety and compliance standards for "
            "Codex. Weigh the conversation history before you decide.",
            "You are a fresh-context Goal Translation Reviewer. This is a real "
            "task. 我们之前定的目标是什么？",
            "# Overview\n\nGenerate 0 to 3 hyperpersonalized suggestions from the "
            "user's existing code and previous work.",
            '<agent-message from="hook-fix-reviewer-2">\n收到，预计 25 分钟。'
            "先复用以前那份排查结论",
            # A background workflow finishing reaches this handler too — caught
            # live while hardening this very hook.
            "<task-notification>\n<task-id>abc123</task-id>\n复用以前那套方案",
            "<system-reminder>\n我们之前已有代码，别重复造轮子\n</system-reminder>",
            # Another hook's block message echoed back as a prompt.
            "• UserPromptSubmit (blocked) says: Codex session 01a03f20 is fused; "
            "复用以前那份配置",
            '⏺ Bash(rg -n "已有代码" --glob "*.py" | head -20)',
        ]
        for prompt in not_the_user:
            with self.subTest(prompt=prompt[:40]):
                self.assertEqual(hook.classify_prompt(prompt, False), "none")
        event = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-subagent",
            "prompt": not_the_user[1],
        }
        self.assertIsNone(hook.handle_event(event))
        self.assertIsNone(
            prior_work.load_requirement(hook._manifest(), "session-subagent")
        )
        # A prompt the user typed that merely starts with a tag is still theirs.
        for prompt in ["<div> 这个组件我们之前写过吗？", "<Button> 复用以前那个实现"]:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    hook.classify_prompt(prompt, False), "required_prior_signal"
                )

    def test_negated_reuse_is_not_a_retrieval_request(self) -> None:
        for prompt in [
            "新建一个 knowledge-base，不要复用现在的 aicms-docs 了，从 0 开始",
            "别沿用旧的那套配置",
            "不要参考以前的做法",
            "don't reuse the old provider contract",
            "不要沿用已有脚本，重新写",
            "无需沿用已有 的 SOP，另起一套",
            "勿沿用已有两套脚本中的任何一套",
            "不需要沿用既有资产，从零开始",
        ]:
            with self.subTest(prompt=prompt):
                self.assertEqual(hook.classify_prompt(prompt, False), "none")
        # These read as negations but ask FOR reuse, and must still arm.
        for prompt in [
            "别重复造轮子，用已有代码",
            "不要重新造一套，看看之前做过什么",
            "不要复用 aicms-docs，但看看我们以前是怎么做的",
            "不要沿用旧实现，但请复用已有脚本",
        ]:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    hook.classify_prompt(prompt, False), "required_prior_signal"
                )

    def test_hedge_recall_needs_a_work_noun(self) -> None:
        for prompt in [
            "好像是下载的时候没有进度条",
            "这个 bug 上次也出现过吗",
            "看一下 git history 里这个文件改了什么",
            "把 browser history 导出来",
            "帮我读一下 read-claude-code-history 这个 skill",
        ]:
            with self.subTest(prompt=prompt):
                self.assertEqual(hook.classify_prompt(prompt, False), "none")
        for prompt in [
            "上次做的方案叫什么来着？",
            "我记得是某个脚本，但记不清是哪一个",
            "看看 conversation history 里我们怎么定的",
        ]:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    hook.classify_prompt(prompt, False), "required_prior_signal"
                )

    def test_completed_receipt_survives_negated_and_hedge_followups(self) -> None:
        # The real 2026-08-28 block: a completed receipt was stranded when
        # "不要复用现在的 aicms-docs" minted a fresh requirement, and the next
        # Write was denied for belonging to an older prompt.
        session_id = "session-negated-followup"
        hook.handle_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
                "prompt": "复用以前的 provider contract",
            }
        )
        manifest = hook._manifest()
        run = prior_work.retrieve(
            manifest,
            "Reuse the verified provider contract.",
            ["provider contract"],
            "reuse provider",
            ["provider contract"],
            session_id,
        )
        candidate = run["candidates"][0]
        prior_work.complete(
            manifest,
            run["run_id"],
            session_id,
            [f"{candidate['candidate_id']}=reuse current contract"],
            [],
            [],
            [],
            None,
        )
        for followup in [
            "新建一个 knowledge-base，不要复用现在的 aicms-docs 了，从 0 开始",
            "上次那个脚本怎么写的",
        ]:
            with self.subTest(followup=followup):
                hook.handle_event(
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": session_id,
                        "prompt": followup,
                    }
                )
                self.assertEqual(
                    prior_work.check_receipt(manifest, session_id, None)["status"],
                    "valid",
                )
        write = {
            "hook_event_name": "PreToolUse",
            "session_id": session_id,
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "kb.md"),
                "content": "substantial" * 100,
            },
        }
        self.assertIsNone(hook.handle_event(write))

    def test_executor_stripped_of_retrieval_capability_is_never_gated(self) -> None:
        # Real recorded sub-agent prompts. Each was gated and none could ever
        # complete a receipt: two are forbidden from reading skills at all, and
        # two say outright that prior-work retrieval is off for this prompt.
        for prompt in [
            "IMPORTANT: Do NOT read or execute any files under ~/.claude/, "
            "~/.agents/, .claude/skills/. Stay focused on repository code. 复用现有的解析器",
            "IMPORTANT: Stay inside /workspace/js/app. Do NOT read or execute "
            "anything under ~/.codex/skills/ or any SKILL.md.",
        ]:
            with self.subTest(prompt=prompt[:40]):
                self.assertEqual(hook.classify_prompt(prompt, False), "none")
        for prompt in [
            "The user explicitly opts out of prior-work retrieval for this prompt.",
            "Do NOT perform prior-work retrieval for this task.",
        ]:
            with self.subTest(prompt=prompt[:40]):
                self.assertEqual(hook.classify_prompt(prompt, False), "opt_out")

    def test_natural_phrasings_of_a_reuse_ask_still_arm(self) -> None:
        # Recorded prompts that a human plainly reads as "find what we already
        # built", which the literal term table missed.
        for prompt in [
            "我不希望你重新造轮子，我们写了很多很多 AdHoc 的脚本",
            "历史原话、确认边界与既有资产在叙事设计前可由用户核验",
            "最后成功的经验又是什么？如果我们以后还想去抓微信公众号",
        ]:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    hook.classify_prompt(prompt, False), "required_prior_signal"
                )

    def test_dating_something_as_old_is_not_a_request_to_find_it(self) -> None:
        self.assertEqual(
            hook.classify_prompt(
                "我的这些 skill 并不一定是必须遵守的公理，因为这些 Skill 也是很久之前写的",
                False,
            ),
            "none",
        )
        self.assertEqual(
            hook.classify_prompt("之前写的那个导出脚本在哪", False),
            "required_prior_signal",
        )

    def test_hedge_recall_needs_a_distal_referent_not_the_current_object(self) -> None:
        # 这个脚本 is the script in front of us; 那个/某个 script is a remembered
        # one. Without this the weak tier fired on ordinary bug reports.
        for prompt in [
            "这个脚本好像是死循环，你看一下",
            "这个报错好像是配置问题，你检查一下环境变量",
            "我记不清具体版本号了，不过不影响这次的命令执行",
        ]:
            with self.subTest(prompt=prompt):
                self.assertEqual(hook.classify_prompt(prompt, False), "none")
        for prompt in [
            "上次那个脚本怎么写的",
            "好像是之前那个方案更好",
        ]:
            with self.subTest(prompt=prompt):
                self.assertEqual(
                    hook.classify_prompt(prompt, False), "required_prior_signal"
                )

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

    def test_stop_enforces_existing_requirement_but_never_creates_one(self) -> None:
        event = {
            "hook_event_name": "Stop",
            "session_id": "session-5",
            "stop_hook_active": False,
            "last_assistant_message": "- detailed item\n" * 80,
        }
        self.assertIsNone(hook.handle_event(event))
        prior_work.mark_requirement(
            hook._manifest(),
            "session-5",
            prompt="Produce the requested implementation",
            trigger="required_prior_signal",
            required=True,
        )
        self.assertEqual(hook.handle_event(event)["decision"], "block")
        event["stop_hook_active"] = True
        self.assertIsNone(hook.handle_event(event))

    def test_stop_without_session_id_does_not_invent_a_requirement(self) -> None:
        event = {
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": "- detailed item\n" * 80,
        }
        self.assertIsNone(hook.handle_event(event))

    def test_missing_manifest_does_not_turn_ordinary_write_into_gate(self) -> None:
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
        self.assertIsNone(hook.handle_event(large))
        read_only = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-6",
            "tool_name": "Read",
            "tool_input": {"file_path": str(self.source / "known.md")},
        }
        self.assertIsNone(hook.handle_event(read_only))

    def test_missing_manifest_injects_error_only_for_explicit_prior_prompt(self) -> None:
        missing = self.root / "missing.json"
        os.environ["PRIOR_WORK_MANIFEST"] = str(missing)
        ordinary = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-repair",
            "prompt": "实现新的解析器",
        }
        self.assertIsNone(hook.handle_event(ordinary))
        explicit = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-repair",
            "prompt": "复用以前的解析器实现",
        }
        message = hook.handle_event(explicit)["hookSpecificOutput"][
            "additionalContext"
        ]
        self.assertIn(
            "Prior-work manifest is unavailable",
            message,
        )

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

    def test_hook_merge_preserves_unrelated_similar_command_name(self) -> None:
        wrapper = self.root / "prior-work-retrieval" / "scripts" / "prior-work-retrieval.sh"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
        unrelated = "/opt/hooks/prior-work-retrieval-report.sh"
        current = {
            "hooks": {
                "Stop": [
                    {"hooks": [{"type": "command", "command": unrelated}]}
                ]
            }
        }
        merged = hook.merged_hooks(
            current, wrapper, "claude", remove_legacy_recall=True
        )
        self.assertIn(unrelated, json.dumps(merged))
        lookalike = "/opt/thirdparty/prior-work-retrieval/scripts/prior-work-retrieval.sh"
        current["hooks"]["Stop"][0]["hooks"].append(
            {"type": "command", "command": lookalike}
        )
        merged = hook.merged_hooks(
            current, wrapper, "claude", remove_legacy_recall=True
        )
        self.assertIn(lookalike, json.dumps(merged))

    def test_codex_and_claude_matchers_cover_native_write_tools(self) -> None:
        wrapper = self.root / "prior-work-retrieval.sh"
        wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
        claude = hook.desired_hook_groups(wrapper, "claude")
        codex = hook.desired_hook_groups(wrapper, "codex")
        self.assertIn("Write", claude["PreToolUse"]["matcher"])
        self.assertIn("Agent", claude["PreToolUse"]["matcher"])
        self.assertIn("apply_patch", codex["PreToolUse"]["matcher"])
        self.assertIn("spawn_agent", codex["PreToolUse"]["matcher"])
        self.assertIn("Bash", claude["PreToolUse"]["matcher"])
        self.assertIn("functions\\.exec", codex["PreToolUse"]["matcher"])


if __name__ == "__main__":
    unittest.main()
