#!/usr/bin/env python3
"""Regression tests for archive-aware Claude session search."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "analyze_sessions.py"

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from _core.text import keywords_are_raw_byte_safe  # noqa: E402


def write_jsonl(path: Path, records: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def project_dir(home: Path, workspace: Path) -> Path:
    encoded = str(workspace.resolve()).replace("/", "-")
    result = home / "projects" / encoded
    result.mkdir(parents=True, exist_ok=True)
    return result


def user_record(session_id: str, workspace: Path, text: str, timestamp: str) -> dict:
    return {
        "type": "user",
        "sessionId": session_id,
        "cwd": str(workspace),
        "timestamp": timestamp,
        "message": {"role": "user", "content": text},
    }


class SessionAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.user_home = self.root / "user-home"
        self.active_home = self.user_home / ".claude"
        self.archive_home = self.root / "conversation-archive"
        self.workspace = self.root / "workspaces" / "demo-project"
        self.workspace.mkdir(parents=True)
        project_dir(self.active_home, self.workspace)
        project_dir(self.archive_home, self.workspace)
        self.manifest = self.active_home / "history-sources.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": [
                        {
                            "provider": "claude",
                            "kind": "archive",
                            "label": "full-backup",
                            "home": str(self.archive_home),
                            "required": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(
        self, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=check,
            env={**os.environ, "HOME": str(self.user_home)},
        )

    def seed_structured_events(self) -> tuple[str, str]:
        active_id = "11111111-1111-4111-8111-111111111111"
        archive_id = "22222222-2222-4222-8222-222222222222"
        active_file = project_dir(self.active_home, self.workspace) / f"{active_id}.jsonl"
        archive_file = project_dir(self.archive_home, self.workspace) / f"{archive_id}.jsonl"
        write_jsonl(
            active_file,
            [
                user_record(
                    active_id,
                    self.workspace,
                    "Active March session",
                    "2026-03-20T10:00:00Z",
                )
            ],
        )
        write_jsonl(
            archive_file,
            [
                user_record(
                    archive_id,
                    self.workspace,
                    "queued-topic before the requested window",
                    "2026-01-10T08:00:00Z",
                ),
                {
                    "type": "assistant",
                    "sessionId": archive_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-04-17T14:30:05Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "thinking",
                                "thinking": "reasoning-marker",
                                "signature": "signature-only-secret",
                            },
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {
                                    "command": "uv run python build_slides.py",
                                    "description": "Install python-pptx",
                                },
                            },
                        ],
                    },
                },
                {
                    "type": "user",
                    "sessionId": archive_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-04-18T09:00:00Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-1",
                                "content": [
                                    {"type": "text", "text": "topic-from-tool-result"}
                                ],
                            }
                        ],
                    },
                },
                {
                    "type": "queue-operation",
                    "operation": "enqueue",
                    "sessionId": archive_id,
                    "timestamp": "2026-04-18T10:00:00Z",
                    "content": "queued-topic",
                },
                {
                    "type": "attachment",
                    "sessionId": archive_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-04-18T12:36:48Z",
                    "attachment": {
                        "type": "file",
                        "path": "brief.txt",
                        "content": {"notes": "attachment-topic"},
                    },
                },
            ],
        )
        # Make file mtimes contradict their internal timestamps.
        os.utime(archive_file, (1, 1))
        os.utime(active_file, (2_000_000_000, 2_000_000_000))
        return active_id, archive_id

    def test_list_sorts_by_internal_timestamp_and_labels_archive_source(self) -> None:
        active_id, archive_id = self.seed_structured_events()
        completed = self.run_cli(
            "list",
            str(self.workspace),
            "--history-sources",
            str(self.manifest),
        )
        self.assertLess(completed.stdout.index(archive_id), completed.stdout.index(active_id))
        self.assertIn("Internal range:", completed.stdout)
        self.assertIn("archive:full-backup", completed.stdout)
        self.assertNotIn("Modified:", completed.stdout)

    def test_search_covers_structured_event_fields_and_filters_matching_records(self) -> None:
        _, archive_id = self.seed_structured_events()
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "topic-from-tool-result",
            "queued-topic",
            "attachment-topic",
            "python-pptx",
            "reasoning-marker",
            "--from-date",
            "2026-04-01",
            "--to-date",
            "2026-04-30",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn(archive_id, completed.stdout)
        self.assertIn("queued-topic(1)", completed.stdout)
        self.assertIn("Match range:", completed.stdout)
        self.assertIn("tool_result", completed.stdout)
        self.assertIn("tool_input:Bash", completed.stdout)
        self.assertIn("thinking", completed.stdout)
        self.assertIn("attachment", completed.stdout)
        self.assertIn("queue-operation", completed.stdout)

        signature_only = self.run_cli(
            "search",
            str(self.workspace),
            "signature-only-secret",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn("No matches found.", signature_only.stdout)

    def test_prefilter_and_no_prefilter_agree_byte_for_byte(self) -> None:
        """The 2026-08 pre-filter (rg/grep file-level + in-process line-level)
        must be a pure speedup: identical stdout with and without it, on a
        mix of matching, non-matching, and mixed-case sessions."""
        matching_id = "44444444-4444-4444-8444-444444444444"
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{matching_id}.jsonl",
            [
                user_record(matching_id, self.workspace, "irrelevant filler line", "2026-04-01T00:00:00Z"),
                user_record(matching_id, self.workspace, "contains the RareToken here", "2026-04-01T00:00:01Z"),
                user_record(matching_id, self.workspace, "more filler after the hit", "2026-04-01T00:00:02Z"),
            ],
        )
        no_match_id = "55555555-5555-4555-8555-555555555555"
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{no_match_id}.jsonl",
            [user_record(no_match_id, self.workspace, "nothing of interest", "2026-04-02T00:00:00Z")],
        )

        default_run = self.run_cli(
            "search", str(self.workspace), "raretoken",
            "--history-sources", str(self.manifest),
        )
        no_prefilter_run = self.run_cli(
            "search", str(self.workspace), "raretoken", "--no-prefilter",
            "--history-sources", str(self.manifest),
        )
        self.assertEqual(default_run.stdout, no_prefilter_run.stdout)
        self.assertIn(matching_id, default_run.stdout)
        self.assertNotIn(no_match_id, default_run.stdout)

    def test_prefilter_disabled_under_date_window_keeps_untimed_count_exact(self) -> None:
        """The pre-filter is gated off automatically whenever a date window is
        active (see search_sessions's use_prefilter docstring) because
        excluded_untimed_records counts every untimed record in a session
        regardless of keyword match, and skipping non-matching records would
        silently under-report it. Prove the count is identical either way,
        not just that both runs happen to exit 0."""
        session_id = "66666666-6666-4666-8666-666666666666"
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{session_id}.jsonl",
            [
                user_record(session_id, self.workspace, "has the target keyword", "2026-04-15T00:00:00Z"),
                {  # untimed record, no keyword — must still be counted while a date window is active
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(self.workspace),
                    "message": {"role": "user", "content": "untimed filler, no timestamp field at all"},
                },
                {  # a SECOND untimed record with no keyword — count must reach 2, not 1
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(self.workspace),
                    "message": {"role": "user", "content": "another untimed filler"},
                },
            ],
        )
        default_run = self.run_cli(
            "search", str(self.workspace), "target keyword",
            "--from-date", "2026-04-01", "--to-date", "2026-04-30",
            "--history-sources", str(self.manifest),
        )
        no_prefilter_run = self.run_cli(
            "search", str(self.workspace), "target keyword", "--no-prefilter",
            "--from-date", "2026-04-01", "--to-date", "2026-04-30",
            "--history-sources", str(self.manifest),
        )
        self.assertEqual(default_run.stdout, no_prefilter_run.stdout)
        self.assertIn("excluded 2 record(s) without an internal timestamp", default_run.stdout)

    def test_signature_only_keyword_finds_no_match_with_prefilter_on(self) -> None:
        """The pre-filter's raw byte scan is a deliberate OVER-approximation —
        it will say a file/line "could" match even when the keyword only
        appears in a field the structured search excludes (signature/id/
        tool_use_id — see _flatten_search_strings). Confirm that over-approval
        never leaks into an actual false-positive match."""
        session_id = "77777777-7777-4777-8777-777777777777"
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{session_id}.jsonl",
            [
                {
                    "type": "assistant",
                    "sessionId": session_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-04-10T00:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "thinking",
                                "thinking": "ordinary reasoning text",
                                "signature": "excluded-only-secret-marker",
                            }
                        ],
                    },
                }
            ],
        )
        result = self.run_cli(
            "search", str(self.workspace), "excluded-only-secret-marker",
            "--history-sources", str(self.manifest),
        )
        self.assertIn("No matches found.", result.stdout)

    def test_all_projects_hint_appears_for_bare_keyword_project_path(self) -> None:
        """Regression for a real trap: `search KEYWORD1 KEYWORD2` without
        --all-projects treats KEYWORD1 as a project path (documented
        argparse grammar), finds no project by that name, and used to print
        only "No sessions found for project: KEYWORD1" — which reads as "your
        keyword doesn't exist" rather than "you searched for a project by
        that name". An agent hit exactly this during a real investigation."""
        result = self.run_cli(
            "search", "embedding", "classifier",
            "--history-sources", str(self.manifest),
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("No sessions found for project: embedding", result.stdout)
        self.assertIn("--all-projects", result.stderr)

    def test_all_projects_hint_absent_for_a_real_existing_path(self) -> None:
        """The hint must not fire when project_path genuinely looks like (or
        is) a path — false "did you mean --all-projects" noise on an honest
        typo'd real path would be its own annoyance."""
        result = self.run_cli(
            "search", str(self.workspace), "no-such-keyword-at-all",
            "--history-sources", str(self.manifest),
            check=False,
        )
        self.assertNotIn("--all-projects", result.stderr)

    def test_duplicate_session_unions_distinct_records_and_keeps_provenance(self) -> None:
        session_id = "33333333-3333-4333-8333-333333333333"
        timestamp = "2026-04-20T10:00:00Z"
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{session_id}.jsonl",
            [user_record(session_id, self.workspace, "active-choice", timestamp)],
        )
        write_jsonl(
            project_dir(self.archive_home, self.workspace) / f"{session_id}.jsonl",
            [user_record(session_id, self.workspace, "archive-choice", timestamp)],
        )
        active_match = self.run_cli(
            "search",
            str(self.workspace),
            "active-choice",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn(session_id, active_match.stdout)
        self.assertIn("active:main, archive:full-backup", active_match.stdout)

        archive_match = self.run_cli(
            "search",
            str(self.workspace),
            "archive-choice",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn(session_id, archive_match.stdout)
        self.assertIn("Match sources: archive:full-backup", archive_match.stdout)
        self.assertIn(str(self.archive_home), archive_match.stdout)

        combined = self.run_cli(
            "search",
            str(self.workspace),
            "active-choice",
            "archive-choice",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn("active-choice(1)", combined.stdout)
        self.assertIn("archive-choice(1)", combined.stdout)
        self.assertIn("Other matching copies:", combined.stdout)

    def test_duplicate_identical_records_are_not_double_counted(self) -> None:
        session_id = "55555555-5555-4555-8555-555555555555"
        record = user_record(
            session_id,
            self.workspace,
            "shared-marker",
            "2026-04-20T10:00:00Z",
        )
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{session_id}.jsonl",
            [record, record],
        )
        write_jsonl(
            project_dir(self.archive_home, self.workspace) / f"{session_id}.jsonl",
            [record],
        )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "shared-marker",
            "--history-sources",
            str(self.manifest),
        )
        # Identical records copied to another physical file count once, while
        # two real occurrences inside one file remain two occurrences.
        self.assertIn("shared-marker(2)", completed.stdout)
        self.assertIn(
            "Match sources: active:main, archive:full-backup",
            completed.stdout,
        )

    def test_explicit_home_remains_an_exact_scope(self) -> None:
        archive_id = "44444444-4444-4444-8444-444444444444"
        write_jsonl(
            project_dir(self.archive_home, self.workspace) / f"{archive_id}.jsonl",
            [
                user_record(
                    archive_id,
                    self.workspace,
                    "archive-only-marker",
                    "2026-04-20T10:00:00Z",
                )
            ],
        )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "archive-only-marker",
            "--home",
            str(self.active_home),
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("No sessions found", completed.stdout)

    def test_all_projects_aggregates_sessions_across_projects(self) -> None:
        other_workspace = self.root / "workspaces" / "other-project"
        other_workspace.mkdir(parents=True)
        first_id = "66666666-6666-4666-8666-666666666666"
        second_id = "77777777-7777-4777-8777-777777777777"
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{first_id}.jsonl",
            [
                user_record(
                    first_id,
                    self.workspace,
                    "cross-project-marker second-marker",
                    "2026-04-20T10:00:00Z",
                )
            ],
        )
        write_jsonl(
            project_dir(self.active_home, other_workspace) / f"{second_id}.jsonl",
            [
                user_record(
                    second_id,
                    other_workspace,
                    "cross-project-marker second-marker",
                    "2026-04-21T10:00:00Z",
                )
            ],
        )
        completed = self.run_cli(
            "search",
            "--all-projects",
            "cross-project-marker",
            "second-marker",
            "--home",
            str(self.active_home),
            "--home",
            str(self.archive_home),
        )
        self.assertIn(first_id, completed.stdout)
        self.assertIn(second_id, completed.stdout)
        self.assertIn("Project:", completed.stdout)
        self.assertIn("2 project(s)", completed.stdout)
        self.assertIn("cross-project-marker(1), second-marker(1)", completed.stdout)

        listed = self.run_cli(
            "list",
            "--all-projects",
            "--home",
            str(self.active_home),
            "--home",
            str(self.archive_home),
        )
        self.assertIn("across 2 project(s)", listed.stdout)
        self.assertIn("== ", listed.stdout)

    def test_project_scope_is_required_and_list_scope_is_exclusive(self) -> None:
        neither = self.run_cli("search", "anything", check=False)
        self.assertEqual(neither.returncode, 2)
        both = self.run_cli(
            "list",
            str(self.workspace),
            "--all-projects",
            check=False,
        )
        self.assertEqual(both.returncode, 2)

    def test_exclude_session_skips_the_current_session(self) -> None:
        current_id = "88888888-8888-4888-8888-888888888888"
        target_id = "99999999-9999-4999-8999-999999999999"
        for session_id in (current_id, target_id):
            write_jsonl(
                project_dir(self.active_home, self.workspace)
                / f"{session_id}.jsonl",
                [
                    user_record(
                        session_id,
                        self.workspace,
                        "self-match-marker",
                        "2026-04-20T10:00:00Z",
                    )
                ],
            )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "self-match-marker",
            "--exclude-session",
            current_id,
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn(target_id, completed.stdout)
        self.assertNotIn(current_id, completed.stdout)

    def test_zero_match_hint_points_at_unapplied_widenings(self) -> None:
        write_jsonl(
            project_dir(self.active_home, self.workspace)
            / "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa.jsonl",
            [
                user_record(
                    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    self.workspace,
                    "unrelated content",
                    "2026-04-20T10:00:00Z",
                )
            ],
        )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "definitely-absent-marker",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn("No matches found.", completed.stdout)
        self.assertIn("--all-projects", completed.stderr)
        self.assertIn("--codex", completed.stderr)
        self.assertIn("substrings", completed.stderr)

        widened = self.run_cli(
            "search",
            "--all-projects",
            "definitely-absent-marker",
            "--codex",
            "--codex-home",
            str(self.root / "empty-codex"),
            "--home",
            str(self.active_home),
            "--home",
            str(self.archive_home),
        )
        self.assertNotIn("--all-projects", widened.stderr)
        self.assertNotIn("--codex (", widened.stderr)
        self.assertIn("substrings", widened.stderr)

    def test_search_finds_snapshot_only_original_path_once_across_copies(self) -> None:
        session_id = "abababab-abab-4bab-8bab-abababababab"
        original_path = "/tmp/generated/snapshot-only.bin"
        record = {
            "type": "file-history-snapshot",
            "snapshot": {
                "timestamp": "2026-04-22T10:00:00Z",
                "trackedFileBackups": {
                    original_path: {
                        "backupFileName": "snapshot@v2",
                        "version": 2,
                        "backupTime": "2026-04-22T10:00:00Z",
                    }
                },
            },
        }
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{session_id}.jsonl",
            [record, record],
        )
        write_jsonl(
            project_dir(self.archive_home, self.workspace) / f"{session_id}.jsonl",
            [record],
        )

        completed = self.run_cli(
            "search",
            str(self.workspace),
            "snapshot-only.bin",
            "--from-date",
            "2026-04-22",
            "--to-date",
            "2026-04-22",
            "--history-sources",
            str(self.manifest),
        )

        self.assertIn(session_id, completed.stdout)
        self.assertIn("snapshot-only.bin(1)", completed.stdout)
        self.assertIn("file_history_path", completed.stdout)
        self.assertIn("active:main, archive:full-backup", completed.stdout)

    def seed_codex_rollout(
        self,
        codex_home: Path,
        session_id: str,
        cwd: Path,
        text: str,
        *,
        mirror: bool = True,
        archived_copy: bool = False,
    ) -> Path:
        timestamp = "2026-04-20T10:00:00Z"
        records = [
            {
                "type": "session_meta",
                "timestamp": timestamp,
                "payload": {
                    "id": session_id,
                    "cwd": str(cwd),
                    "timestamp": timestamp,
                },
            },
            {
                "type": "response_item",
                "timestamp": timestamp,
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            },
        ]
        if mirror:
            # event_msg mirrors of message text must not double-count.
            records.append(
                {
                    "type": "event_msg",
                    "timestamp": timestamp,
                    "payload": {"type": "user_message", "message": text},
                }
            )
        rollout = (
            codex_home
            / "sessions"
            / "2026"
            / "04"
            / "20"
            / f"rollout-2026-04-20T10-00-00-{session_id}.jsonl"
        )
        write_jsonl(rollout, records)
        if archived_copy:
            write_jsonl(
                codex_home / "archived_sessions" / rollout.name, records
            )
        return rollout

    def test_codex_search_finds_rollout_once_and_counts_mirror_once(self) -> None:
        codex_home = self.root / "codex-home"
        session_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        self.seed_codex_rollout(
            codex_home,
            session_id,
            self.workspace,
            "codex-only-marker",
            archived_copy=True,
        )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "codex-only-marker",
            "--codex",
            "--codex-home",
            str(codex_home),
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn("Codex rollout matches", completed.stdout)
        self.assertIn(session_id, completed.stdout)
        # sessions/ + archived_sessions/ copies of one rollout dedupe to a
        # single result, and the event_msg mirror adds no extra mention.
        self.assertEqual(completed.stdout.count("📦"), 1)
        self.assertIn("Total mentions: 1", completed.stdout)
        self.assertIn("Match fields: message", completed.stdout)

    def test_codex_search_filters_rollouts_by_project_cwd(self) -> None:
        codex_home = self.root / "codex-home"
        matching_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        other_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        self.seed_codex_rollout(
            codex_home, matching_id, self.workspace, "codex-cwd-marker"
        )
        self.seed_codex_rollout(
            codex_home,
            other_id,
            self.root / "elsewhere",
            "codex-cwd-marker",
        )
        scoped = self.run_cli(
            "search",
            str(self.workspace),
            "codex-cwd-marker",
            "--codex",
            "--codex-home",
            str(codex_home),
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn(matching_id, scoped.stdout)
        self.assertNotIn(other_id, scoped.stdout)

        swept = self.run_cli(
            "search",
            "--all-projects",
            "codex-cwd-marker",
            "--codex",
            "--codex-home",
            str(codex_home),
            "--home",
            str(self.active_home),
            "--home",
            str(self.archive_home),
        )
        self.assertIn(matching_id, swept.stdout)
        self.assertIn(other_id, swept.stdout)


class RawBytePrefilterSafetyTests(unittest.TestCase):
    """The raw-byte pre-filter must never rule out a session a full parse
    would have matched.

    Every case here was a real divergence found by an A/B run of the CLI
    against its own pre-pre-filter version — and every one of them slipped
    past the 59 tests above, because those fixtures are written with
    ``ensure_ascii=False`` and searched with ASCII-only keywords. The shapes
    below are exactly the ones that combination cannot reach.
    """

    def test_non_ascii_keyword_is_not_raw_byte_safe(self) -> None:
        # Two independent reasons, either one sufficient: json.dumps defaults
        # to ensure_ascii=True (so "café" is stored as "caf\\u00e9" and the
        # UTF-8 bytes are absent), and case folding disagrees between Python
        # and the byte scanners.
        for keyword in ("café", "你好", "straße", "ẞ"):
            with self.subTest(keyword=keyword):
                self.assertFalse(keywords_are_raw_byte_safe([keyword]))

    def test_ascii_keyword_is_raw_byte_safe(self) -> None:
        # The guard must not misfire on ordinary input — killing the speedup
        # for everyone would be a worse outcome than the bug it prevents.
        for keyword in ("hello", "TODO", "session_id", "a-b_c.d"):
            with self.subTest(keyword=keyword):
                self.assertTrue(keywords_are_raw_byte_safe([keyword]))

    def test_guard_must_see_original_keyword_not_the_folded_one(self) -> None:
        # "ß".casefold() == "ss", which is pure ASCII. A call site that folds
        # before asking would get "safe" back for the exact input the guard
        # exists to reject, silently restoring the bug.
        self.assertFalse(keywords_are_raw_byte_safe(["ß"]))
        self.assertTrue(keywords_are_raw_byte_safe(["ß".casefold()]))

    def test_json_escaped_keywords_are_not_raw_byte_safe(self) -> None:
        # JSON *must* escape control characters, '"' and '\\'; '/' is optional
        # but some writers escape it. All of them mean the keyword's bytes are
        # not in the file verbatim. The quote and backslash cases are the ones
        # that matter most in practice — quoted error fragments, JSON config
        # snippets and Windows paths are common history queries.
        for keyword in ("foo\nbar", "a\tb", "src/main.py",
                        'say "hello world"', r"C:\Users", r"a\b"):
            with self.subTest(keyword=keyword):
                self.assertFalse(keywords_are_raw_byte_safe([keyword]))

    def test_ascii_keyword_matches_fold_equivalent_content(self) -> None:
        # The keyword-side guard cannot see the CONTENT. Python's casefold does
        # full folding, so an all-ASCII keyword legitimately matches non-ASCII
        # content — "financial" must find "ﬁnancial" (U+FB01, what you get
        # pasting from a PDF). A byte scanner does not fold that way, so the
        # pre-filter has to treat such content as unscannable.
        for content, keyword in (
            ("the ﬁnancial model is attached", "financial"),
            ("DIE STRAẞE IST LANG", "strasse"),
            ("a ﬅudy of ﬆate machines", "study"),
        ):
            with self.subTest(content=content):
                self._assert_search_finds(content, keyword)

    def test_fold_equivalent_table_is_derived_not_hand_written(self) -> None:
        # Guards against someone "tidying" the table into a hand-typed literal.
        # A hand-written draft of this list had 17 entries, several of which do
        # not fold to ASCII at all.
        from _core.text import _FOLDS_TO_ASCII

        self.assertIn("ﬁ", _FOLDS_TO_ASCII)
        self.assertIn("ß", _FOLDS_TO_ASCII)
        for ch in _FOLDS_TO_ASCII:
            self.assertFalse(ch.isascii(), f"{ch!r} is already ASCII")
            self.assertTrue(ch.casefold().isascii(), f"{ch!r} does not fold to ASCII")

    def _assert_search_finds(self, content: str, keyword: str,
                             ensure_ascii: bool = False) -> None:
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            home, workspace = root / "home", root / "ws"
            workspace.mkdir()
            target = project_dir(home, workspace) / "018f0000-0000-4000-8000-0000000000ab.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "type": "user",
                "timestamp": "2026-04-01T00:00:00Z",
                "message": {"role": "user", "content": content},
            }
            target.write_text(
                json.dumps(record, ensure_ascii=ensure_ascii) + "\n", encoding="utf-8"
            )
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "search", str(workspace), keyword],
                capture_output=True, text=True, check=False,
                env=dict(os.environ, CLAUDE_CONFIG_DIR=str(home)),
            )
            self.assertNotIn("No matches found", completed.stdout,
                             f"lost a match: content={content!r} keyword={keyword!r}")

    def test_one_unsafe_keyword_disables_the_filter_for_the_whole_query(self) -> None:
        self.assertFalse(keywords_are_raw_byte_safe(["safe", "你好"]))

    def test_escaped_unicode_session_is_still_found(self) -> None:
        # End-to-end: a session file written with ensure_ascii=True (as any
        # archive rewritten by default-parameter json.dumps would be) must
        # still be found by a non-ASCII keyword.
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            home = root / "home"
            workspace = root / "ws"
            workspace.mkdir()
            target = project_dir(home, workspace) / "018f0000-0000-4000-8000-0000000000ff.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "type": "user",
                "timestamp": "2026-04-01T00:00:00Z",
                "message": {"role": "user", "content": "café 你好世界 discussion"},
            }
            # ensure_ascii=True is the point of this fixture — do not "fix" it.
            target.write_text(json.dumps(record, ensure_ascii=True) + "\n", encoding="utf-8")

            env = dict(os.environ, CLAUDE_CONFIG_DIR=str(home))
            for keyword in ("café", "你好"):
                with self.subTest(keyword=keyword):
                    completed = subprocess.run(
                        [sys.executable, str(SCRIPT), "search", str(workspace), keyword],
                        capture_output=True, text=True, env=env, check=False,
                    )
                    self.assertNotIn("No matches found", completed.stdout)
                    self.assertIn("018f0000", completed.stdout)

    def test_codex_path_does_not_build_line_keywords(self) -> None:
        # Line-level filtering is incompatible with Codex's session_range:
        # observe() needs every record (including the session_meta first line)
        # to report the conversation's span. With line filtering on, a measured
        # 4-line rollout reported "01-10 .. 01-10" instead of "01-01 .. 01-20"
        # — a wrong value in a field callers quote, on the default
        # no-date-window search. This asserts nobody adds it back.
        lines = SCRIPT.read_text(encoding="utf-8").splitlines()
        starts = [i for i, l in enumerate(lines) if l.startswith("def search_codex_rollouts")]
        self.assertEqual(len(starts), 1, "anchor is no longer unique")
        start = starts[0]
        # The next top-level construct is a `class`, not a `def` — searching
        # only for "\ndef " runs past it and swallows SessionAnalyzer's own
        # (legitimate) line_keywords, failing this test on correct code.
        end = next(
            (i for i, l in enumerate(lines)
             if i > start and (l.startswith("def ") or l.startswith("class "))),
            len(lines),
        )
        codex_body = "\n".join(lines[start:end])
        self.assertIn(
            "line_keywords = None", codex_body,
            "sliced the wrong region — Codex body should contain the disabling line",
        )
        self.assertNotIn(
            "[kw.casefold() for kw in keywords]",
            codex_body,
            "Codex must not build line_keywords — it collapses Internal range",
        )


if __name__ == "__main__":
    unittest.main()
