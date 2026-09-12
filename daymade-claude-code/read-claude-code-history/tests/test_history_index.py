"""Deterministic tests for the optional hybrid history index.

CI uses SQLite's built-in unicode61 tokenizer plus a test-only identity
``simple_query`` function. Real libsimple/MLX integration is exercised by an
explicit smoke run on supported machines, never by the registered Linux suite.
"""

from __future__ import annotations

import fcntl
import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "history_index.py"
sys.path.insert(0, str(SKILL_DIR / "scripts"))


def load_module():
    spec = importlib.util.spec_from_file_location("history_index_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


history_index = load_module()


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def project_dir(home: Path, workspace: Path) -> Path:
    encoded = str(workspace.resolve()).replace("/", "-")
    result = home / "projects" / encoded
    result.mkdir(parents=True, exist_ok=True)
    return result


def user_record(
    session_id: str,
    workspace: Path,
    text: str,
    timestamp: str,
    *,
    sidechain: bool = False,
) -> dict:
    return {
        "type": "user",
        "sessionId": session_id,
        "cwd": str(workspace),
        "timestamp": timestamp,
        "isSidechain": sidechain,
        "message": {"role": "user", "content": text},
    }


def plain_connect(db_path: Path, *, readonly: bool = False, **_kwargs):
    uri = f"file:{db_path}?mode=ro" if readonly else str(db_path)
    connection = sqlite3.connect(uri, uri=readonly)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.create_function(
        "simple_query",
        1,
        lambda value: '"' + str(value).replace('"', '""') + '"',
    )
    return connection


@contextmanager
def portable_backend():
    portable_schema = history_index.SCHEMA.replace(
        "tokenize='simple'", "tokenize='unicode61'"
    )
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(history_index, "SCHEMA", portable_schema))
        stack.enter_context(mock.patch.object(history_index, "_connect", plain_connect))
        yield


class HistoryIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspaces" / "demo"
        self.workspace.mkdir(parents=True)
        self.active = self.root / "active"
        self.archive = self.root / "archive"
        self.db = self.root / "finder.db"
        self.active_source = history_index.HistorySource(
            provider="claude",
            kind="active",
            label="main",
            home=self.active,
        )
        self.archive_source = history_index.HistorySource(
            provider="claude",
            kind="archive",
            label="backup",
            home=self.archive,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def scope(self, *sources):
        return history_index.IndexScope(
            sources=list(sources),
            warnings=[],
            project_path=None,
            all_projects=True,
        )

    def test_embed_defaults_are_bounded_and_invalid_limits_fail_before_backend(self) -> None:
        args = history_index.build_parser().parse_args(["embed"])
        self.assertEqual(args.batch_size, 16)
        self.assertEqual(args.memory_limit_gb, 8.0)
        self.assertEqual(args.cache_limit_gb, 0.5)
        with self.assertRaisesRegex(history_index.IndexError, "memory-limit"):
            history_index.embed_chunks(
                self.db,
                model_path=None,
                download_model=False,
                max_seconds=1,
                batch_size=16,
                memory_limit_gb=0,
                cache_limit_gb=0,
            )
        with self.assertRaisesRegex(history_index.IndexError, "cache-limit"):
            history_index.embed_chunks(
                self.db,
                model_path=None,
                download_model=False,
                max_seconds=1,
                batch_size=16,
                memory_limit_gb=8,
                cache_limit_gb=9,
            )

    def test_fresh_build_has_versioned_schema_and_usable_column(self) -> None:
        session_id = "11111111-1111-4111-8111-111111111111"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{session_id}.jsonl",
            [user_record(session_id, self.workspace, "known marker", "2026-08-01T00:00:00Z")],
        )
        with portable_backend():
            result = history_index.update_index(
                self.db, self.scope(self.active_source), rebuild=True
            )
        self.assertEqual(result["sessions"], 1)
        connection = plain_connect(self.db, readonly=True)
        self.assertEqual(
            connection.execute("PRAGMA user_version").fetchone()[0],
            history_index.SCHEMA_VERSION,
        )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(chunks)")
        }
        self.assertIn("usable", columns)
        self.assertIn("text_hash", columns)
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        self.assertIn("idx_chunks_text_hash", indexes)
        self.assertEqual(
            connection.execute("SELECT count(*) FROM records").fetchone()[0], 1
        )
        self.assertIsNotNone(history_index._meta_get(connection, "index_scope"))
        self.assertEqual(history_index._meta_get(connection, "chunks_complete"), "false")
        connection.close()

    def test_same_session_unions_distinct_copies_and_keeps_provenance(self) -> None:
        session_id = "22222222-2222-4222-8222-222222222222"
        active_path = project_dir(self.active, self.workspace) / f"{session_id}.jsonl"
        archive_path = project_dir(self.archive, self.workspace) / f"{session_id}.jsonl"
        write_jsonl(
            active_path,
            [user_record(session_id, self.workspace, "active-only", "2026-08-01T00:00:00Z")],
        )
        write_jsonl(
            archive_path,
            [user_record(session_id, self.workspace, "archive-only", "2026-07-01T00:00:00Z")],
        )
        with portable_backend():
            history_index.update_index(
                self.db,
                self.scope(self.active_source, self.archive_source),
                rebuild=True,
            )
            archive_result = history_index.recall(
                self.db,
                "archive-only",
                mode="bm25",
                limit=10,
                project=None,
                exclude_sessions=[],
                include_agent_prompts=False,
                model_path=None,
                simple_root=None,
            )
        connection = plain_connect(self.db, readonly=True)
        texts = {
            row[0] for row in connection.execute("SELECT fts_text FROM records")
        }
        self.assertEqual(texts, {"active-only", "archive-only"})
        sources = json.loads(
            connection.execute("SELECT sources_json FROM sessions").fetchone()[0]
        )
        self.assertEqual(sources, ["active:main", "archive:backup"])
        connection.close()
        result = archive_result["results"][0]
        self.assertEqual(Path(result["path"]).resolve(), archive_path.resolve())
        self.assertIn("archive-only", Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(result["sources"], ["archive:backup"])

    def test_agent_prompt_policy_keeps_assistant_and_excludes_tool_payloads(self) -> None:
        session_id = "33333333-3333-4333-8333-333333333333"
        path = project_dir(self.active, self.workspace) / f"{session_id}.jsonl"
        write_jsonl(
            path,
            [
                user_record(
                    session_id,
                    self.workspace,
                    "hidden-agent-prompt",
                    "2026-08-01T00:00:00Z",
                    sidechain=True,
                ),
                {
                    "type": "assistant",
                    "sessionId": session_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-08-01T00:00:01Z",
                    "isSidechain": True,
                    "message": {"role": "assistant", "content": "visible-agent-output"},
                },
                {
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-08-01T00:00:02Z",
                    "isSidechain": True,
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-1",
                                "content": "visible-tool-result",
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-08-01T00:00:03Z",
                    "isSidechain": True,
                    "message": {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "hidden-mixed-agent-prompt"},
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-2",
                                "content": "visible-mixed-tool-result",
                            },
                        ],
                    },
                },
            ],
        )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.active_source), rebuild=True
            )
            hidden = history_index.recall(
                self.db,
                "hidden-agent-prompt",
                mode="bm25",
                limit=10,
                project=None,
                exclude_sessions=[],
                include_agent_prompts=False,
                model_path=None,
                simple_root=None,
            )
            included = history_index.recall(
                self.db,
                "hidden-agent-prompt",
                mode="bm25",
                limit=10,
                project=None,
                exclude_sessions=[],
                include_agent_prompts=True,
                model_path=None,
                simple_root=None,
            )
            agent_output = history_index.recall(
                self.db,
                "visible-agent-output",
                mode="bm25",
                limit=10,
                project=None,
                exclude_sessions=[],
                include_agent_prompts=False,
                model_path=None,
                simple_root=None,
            )
            mixed_hidden = history_index.recall(
                self.db,
                "hidden-mixed-agent-prompt",
                mode="bm25",
                limit=10,
                project=None,
                exclude_sessions=[],
                include_agent_prompts=False,
                model_path=None,
                simple_root=None,
            )
            mixed_included = history_index.recall(
                self.db,
                "hidden-mixed-agent-prompt",
                mode="bm25",
                limit=10,
                project=None,
                exclude_sessions=[],
                include_agent_prompts=True,
                model_path=None,
                simple_root=None,
            )
        self.assertEqual(hidden["results"], [])
        self.assertEqual(len(included["results"]), 1)
        self.assertEqual(len(agent_output["results"]), 1)
        self.assertEqual(mixed_hidden["results"], [])
        self.assertEqual(len(mixed_included["results"]), 1)
        connection = plain_connect(self.db, readonly=True)
        self.assertEqual(
            connection.execute(
                "SELECT count(*) FROM records WHERE fts_text='visible-tool-result'"
            ).fetchone()[0],
            0,
        )
        connection.close()

    def test_auto_mode_reports_bm25_and_hybrid_requires_complete_vectors(self) -> None:
        session_id = "44444444-4444-4444-8444-444444444444"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{session_id}.jsonl",
            [
                user_record(
                    session_id,
                    self.workspace,
                    ("prefix " * 100) + "lexical marker",
                    "2026-08-01T00:00:00Z",
                )
            ],
        )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.active_source), rebuild=True
            )
            status = history_index.index_status(
                self.db,
                simple_root=None,
                inspect_sources=False,
                scope=None,
            )
            auto = history_index.recall(
                self.db,
                "lexical marker",
                mode="auto",
                limit=10,
                project=None,
                exclude_sessions=[],
                include_agent_prompts=False,
                model_path=None,
                simple_root=None,
            )
            with self.assertRaisesRegex(
                history_index.IndexError, "chunks_complete=False"
            ):
                history_index.recall(
                    self.db,
                    "lexical marker",
                    mode="hybrid",
                    limit=10,
                    project=None,
                    exclude_sessions=[],
                    include_agent_prompts=False,
                    model_path=None,
                    simple_root=None,
                )
        self.assertEqual(auto["mode"], "bm25")
        self.assertEqual(len(auto["results"]), 1)
        self.assertIn("lexical marker", auto["results"][0]["snippet"])
        self.assertFalse(status["chunks_complete"])
        self.assertEqual(status["counts"]["missing_chunk_records"], 1)

    def test_vector_only_result_uses_the_matched_chunk_as_snippet(self) -> None:
        session_id = "44444444-4444-4444-8444-444444444445"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{session_id}.jsonl",
            [
                user_record(
                    session_id,
                    self.workspace,
                    "repairing a broken car",
                    "2026-08-01T00:00:00Z",
                )
            ],
        )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.active_source), rebuild=True
            )
            connection = plain_connect(self.db)
            record_id = connection.execute("SELECT id FROM records").fetchone()[0]
            connection.execute(
                "INSERT INTO chunks(record_id,seq,ntok,text,usable) VALUES(?,?,?,?,1)",
                (record_id, 0, 5, "repairing a broken car"),
            )
            chunk_id = connection.execute("SELECT id FROM chunks").fetchone()[0]
            connection.execute("CREATE TABLE vec_chunks(embedding BLOB)")
            connection.execute(
                "INSERT INTO vec_chunks(rowid,embedding) VALUES(?,?)",
                (chunk_id, b"fixture"),
            )
            history_index._meta_set(connection, "chunks_complete", "true")
            history_index._meta_set(connection, "vectors_complete", "true")
            connection.commit()
            connection.close()
            with mock.patch.object(
                history_index, "_vector_query", return_value=(b"query", 0.01)
            ), mock.patch.object(
                history_index,
                "_vector_candidates",
                return_value=(
                    {record_id: 1},
                    {record_id: "repairing a broken car"},
                    1,
                ),
            ):
                result = history_index.recall(
                    self.db,
                    "automobile maintenance",
                    mode="hybrid",
                    limit=10,
                    project=None,
                    exclude_sessions=[],
                    include_agent_prompts=False,
                    model_path=None,
                    simple_root=None,
                )
        self.assertEqual(result["mode"], "hybrid")
        self.assertEqual(result["results"][0]["snippet"], "repairing a broken car")
        self.assertEqual(result["results"][0]["vector_rank"], 1)
        with portable_backend():
            bm25 = history_index.recall(
                self.db,
                "repairing a broken car",
                mode="bm25",
                limit=10,
                project=None,
                exclude_sessions=[],
                include_agent_prompts=False,
                model_path=None,
                simple_root=None,
            )
        self.assertIsNone(bm25["vector_backend_error"])

    def test_failed_rebuild_does_not_replace_active_database(self) -> None:
        self.db.write_bytes(b"old-index-sentinel")
        session_id = "55555555-5555-4555-8555-555555555555"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{session_id}.jsonl",
            [user_record(session_id, self.workspace, "marker", "2026-08-01T00:00:00Z")],
        )
        with portable_backend(), mock.patch.object(
            history_index, "_insert_session", side_effect=RuntimeError("injected")
        ), self.assertRaises(RuntimeError):
            history_index.update_index(
                self.db, self.scope(self.active_source), rebuild=True
            )
        self.assertEqual(self.db.read_bytes(), b"old-index-sentinel")

    def test_index_json_leaves_stdout_a_single_document_while_building(self) -> None:
        """`index --json | jq` has to work on a fresh build too.

        The per-checkpoint progress line only prints while building a
        disposable database — a first install or ``--rebuild`` — which is
        exactly the run nobody watches interactively. On the live index that
        branch fires once per 500 sessions, so its output lands ahead of the
        JSON document rather than after it.
        """
        for number in range(4):
            session_id = f"6666666{number}-6666-4666-8666-666666666666"
            write_jsonl(
                project_dir(self.active, self.workspace) / f"{session_id}.jsonl",
                [
                    user_record(
                        session_id,
                        self.workspace,
                        f"body number {number}",
                        f"2026-08-01T00:00:0{number}Z",
                    )
                ],
            )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(portable_backend())
            stack.enter_context(
                mock.patch.object(history_index, "INDEX_CHECKPOINT_EVERY", 2)
            )
            stack.enter_context(
                mock.patch.object(
                    history_index,
                    "_scope_from_args",
                    return_value=self.scope(self.active_source),
                )
            )
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            code = history_index.main(["--db", str(self.db), "index", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["added"], 4)
        # The progress the checkpoint produced went somewhere — to stderr.
        self.assertIn("indexed 2/4 sessions", stderr.getvalue())
        self.assertIn("indexed 4/4 sessions", stderr.getvalue())

    def test_scope_change_refuses_to_prune_an_existing_database(self) -> None:
        second_workspace = self.root / "workspaces" / "other"
        second_workspace.mkdir(parents=True)
        first_session = "77777777-7777-4777-8777-777777777777"
        second_session = "88888888-8888-4888-8888-888888888888"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{first_session}.jsonl",
            [user_record(first_session, self.workspace, "first", "2026-08-01T00:00:00Z")],
        )
        write_jsonl(
            project_dir(self.active, second_workspace) / f"{second_session}.jsonl",
            [user_record(second_session, second_workspace, "second", "2026-08-01T00:00:01Z")],
        )
        full_scope = self.scope(self.active_source)
        restricted_scope = history_index.IndexScope(
            sources=[self.active_source],
            warnings=[],
            project_path=str(self.workspace.resolve()),
            all_projects=False,
        )
        with portable_backend():
            history_index.update_index(self.db, full_scope, rebuild=True)
            with self.assertRaisesRegex(
                history_index.IndexError, "Status source check scope"
            ):
                history_index.index_status(
                    self.db,
                    simple_root=None,
                    inspect_sources=True,
                    scope=restricted_scope,
                )
            with self.assertRaisesRegex(history_index.IndexError, "different source/project scope"):
                history_index.update_index(self.db, restricted_scope)
        connection = plain_connect(self.db, readonly=True)
        self.assertEqual(
            connection.execute("SELECT count(*) FROM sessions").fetchone()[0], 2
        )
        connection.close()

    def test_failed_incremental_update_rolls_back_every_changed_session(self) -> None:
        paths = []
        session_ids = [
            "99999999-9999-4999-8999-999999999991",
            "99999999-9999-4999-8999-999999999992",
        ]
        for index, session_id in enumerate(session_ids):
            path = project_dir(self.active, self.workspace) / f"{session_id}.jsonl"
            paths.append(path)
            write_jsonl(
                path,
                [
                    user_record(
                        session_id,
                        self.workspace,
                        f"old-{index}",
                        f"2026-08-01T00:00:0{index}Z",
                    )
                ],
            )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.active_source), rebuild=True
            )
            for index, (path, session_id) in enumerate(zip(paths, session_ids)):
                write_jsonl(
                    path,
                    [
                        user_record(
                            session_id,
                            self.workspace,
                            f"new-{index}",
                            f"2026-08-02T00:00:0{index}Z",
                        )
                    ],
                )
            original_insert = history_index._insert_session
            calls = 0

            def fail_after_second_insert(connection, ref):
                nonlocal calls
                calls += 1
                result = original_insert(connection, ref)
                if calls == 2:
                    raise RuntimeError("injected incremental failure")
                return result

            with mock.patch.object(
                history_index, "_insert_session", side_effect=fail_after_second_insert
            ), self.assertRaisesRegex(RuntimeError, "injected incremental failure"):
                history_index.update_index(self.db, self.scope(self.active_source))
        connection = plain_connect(self.db, readonly=True)
        texts = {
            row[0] for row in connection.execute("SELECT fts_text FROM records")
        }
        self.assertEqual(texts, {"old-0", "old-1"})
        connection.close()

    def test_same_size_same_mtime_content_change_is_not_fresh(self) -> None:
        session_id = "99999999-9999-4999-8999-999999999993"
        path = project_dir(self.active, self.workspace) / f"{session_id}.jsonl"
        write_jsonl(
            path,
            [user_record(session_id, self.workspace, "alpha", "2026-08-01T00:00:00Z")],
        )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.active_source), rebuild=True
            )
            old_stat = path.stat()
            write_jsonl(
                path,
                [user_record(session_id, self.workspace, "bravo", "2026-08-01T00:00:00Z")],
            )
            self.assertEqual(path.stat().st_size, old_stat.st_size)
            os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
            result = history_index.update_index(
                self.db, self.scope(self.active_source)
            )
        self.assertEqual(result["changed"], 1)
        connection = plain_connect(self.db, readonly=True)
        self.assertEqual(
            connection.execute("SELECT fts_text FROM records").fetchone()[0],
            "bravo",
        )
        connection.close()

    def test_chunk_model_binding_precedes_and_survives_partial_chunks(self) -> None:
        session_id = "99999999-9999-4999-8999-999999999994"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{session_id}.jsonl",
            [user_record(session_id, self.workspace, "message", "2026-08-01T00:00:00Z")],
        )
        model_a = self.root / "model-A"
        model_b = self.root / "model-B"
        model_a.mkdir()
        model_b.mkdir()
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.active_source), rebuild=True
            )
            connection = plain_connect(self.db)
            history_index._bind_chunk_model(connection, model_a)
            self.assertEqual(
                history_index._meta_get(connection, "embedding_model_revision"),
                "model-A",
            )
            record_id = connection.execute("SELECT id FROM records").fetchone()[0]
            connection.execute(
                "INSERT INTO chunks(record_id,seq,ntok,text,usable) VALUES(?,?,?,?,1)",
                (record_id, 0, 1, "partial"),
            )
            connection.commit()
            with self.assertRaisesRegex(history_index.IndexError, "mixing revisions"):
                history_index._bind_chunk_model(connection, model_b)
            connection.execute(
                "DELETE FROM meta WHERE key='embedding_model_revision'"
            )
            connection.commit()
            with self.assertRaisesRegex(history_index.IndexError, "no recorded model revision"):
                history_index._bind_chunk_model(connection, model_a)
            connection.close()

    def test_readonly_uri_round_trips_reserved_and_cjk_filename(self) -> None:
        target = self.root / "finder ?#% 中文.db"
        connection = sqlite3.connect(target)
        connection.execute("PRAGMA user_version=7")
        connection.close()
        readonly = sqlite3.connect(history_index._readonly_uri(target), uri=True)
        opened = Path(readonly.execute("PRAGMA database_list").fetchone()[2])
        self.assertEqual(readonly.execute("PRAGMA user_version").fetchone()[0], 7)
        readonly.close()
        self.assertEqual(opened.resolve(), target.resolve())

    def test_utf8_stdio_reconfiguration_prevents_partial_cjk_output(self) -> None:
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        with mock.patch.object(history_index.sys, "stdout", stream):
            history_index._configure_utf8_stdio()
            history_index._print_payload({"项目": "中文😀"}, json_output=True)
            stream.flush()
        stream.detach()
        rendered = raw.getvalue().decode("utf-8")
        self.assertIn("项目", rendered)
        self.assertIn("中文😀", rendered)

    def test_bad_libsimple_is_reported_as_index_error_without_traceback(self) -> None:
        simple_root = self.root / "bad-simple"
        (simple_root / "dict").mkdir(parents=True)
        (simple_root / "dict" / "jieba.dict.utf8").write_text(
            "fixture", encoding="utf-8"
        )
        (simple_root / history_index._library_names()[0]).write_bytes(b"not-a-library")
        sqlite3.connect(self.db).close()
        with self.assertRaisesRegex(history_index.IndexError, "Failed to load libsimple"):
            history_index._connect(
                self.db,
                readonly=True,
                simple_root=simple_root,
            )
        stderr = io.StringIO()
        with mock.patch.object(history_index, "_configure_utf8_stdio"), mock.patch.object(
            history_index.sys, "stderr", stderr
        ):
            exit_code = history_index.main(
                [
                    "--db",
                    str(self.db),
                    "--simple-root",
                    str(simple_root),
                    "status",
                ]
            )
        self.assertEqual(exit_code, 2)
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertIn("Failed to load libsimple", stderr.getvalue())

    def test_changed_session_invalidates_vectors_and_reconciles_records(self) -> None:
        session_id = "66666666-6666-4666-8666-666666666666"
        path = project_dir(self.active, self.workspace) / f"{session_id}.jsonl"
        write_jsonl(
            path,
            [user_record(session_id, self.workspace, "first", "2026-08-01T00:00:00Z")],
        )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.active_source), rebuild=True
            )
            connection = plain_connect(self.db)
            history_index._meta_set(connection, "vectors_complete", "true")
            connection.commit()
            connection.close()
            write_jsonl(
                path,
                [
                    user_record(
                        session_id,
                        self.workspace,
                        "first",
                        "2026-08-01T00:00:00Z",
                    ),
                    user_record(
                        session_id,
                        self.workspace,
                        "second",
                        "2026-08-01T00:00:01Z",
                    ),
                ],
            )
            result = history_index.update_index(
                self.db, self.scope(self.active_source)
            )
        self.assertEqual(result["changed"], 1)
        connection = plain_connect(self.db, readonly=True)
        self.assertEqual(
            connection.execute("SELECT count(*) FROM records").fetchone()[0], 2
        )
        self.assertEqual(history_index._meta_get(connection, "vectors_complete"), "false")
        connection.close()

    def test_platform_asset_is_pinned(self) -> None:
        with mock.patch("platform.system", return_value="Darwin"), mock.patch(
            "platform.machine", return_value="arm64"
        ):
            asset, digest = history_index._platform_asset()
        self.assertEqual(asset, "libsimple-osx-arm64.zip")
        self.assertEqual(len(digest), 64)

    def test_explicit_simple_path_does_not_fall_back(self) -> None:
        index_root = self.root / "index-home"
        legacy = (
            index_root
            / "bin"
            / "tinkle_simple"
            / "libsimple-osx-arm64"
        )
        (legacy / "dict").mkdir(parents=True)
        (legacy / "dict" / "jieba.dict.utf8").write_text(
            "fixture", encoding="utf-8"
        )
        (legacy / history_index._library_names()[0]).write_bytes(b"fixture")
        explicit_bad = self.root / "configured-but-missing"

        with mock.patch.object(history_index, "index_home", return_value=index_root):
            self.assertIsNotNone(history_index.find_simple_runtime())
            self.assertIsNone(history_index.find_simple_runtime(explicit_bad))


def codex_rollout(path, session_id, cwd, turns):
    """Write a Codex rollout file: session_meta then response_item messages."""
    records = [
        {
            "timestamp": "2026-05-01T00:00:00.000Z",
            "type": "session_meta",
            "payload": {"id": session_id, "cwd": str(cwd)},
        }
    ]
    for ordinal, (role, text) in enumerate(turns, start=1):
        records.append(
            {
                "timestamp": f"2026-05-01T00:00:{ordinal:02d}.000Z",
                "ordinal": ordinal,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": role,
                    "content": [
                        {
                            "type": "input_text" if role == "user" else "output_text",
                            "text": text,
                        }
                    ],
                },
            }
        )
    write_jsonl(path, records)


def kimi_session(home, session_id, cwd, main_turns, subagent_turns=()):
    """Write one Kimi session directory with a main wire and optional subagent."""
    session_dir = home / "sessions" / "wd_demo_abc" / session_id
    state = {
        "id": session_id,
        "cwd": str(cwd),
        "title": "fixture",
        "createdAt": 1757000000000,
        "updatedAt": 1757000600000,
    }
    (session_dir).mkdir(parents=True, exist_ok=True)
    (session_dir / "state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    main_records = [{"type": "metadata", "protocol_version": "1.5"}]
    for offset, (role, text) in enumerate(main_turns, start=1):
        if role == "user":
            main_records.append(
                {
                    "type": "turn.prompt",
                    "time": 1757000000000 + offset * 1000,
                    "input": [{"type": "text", "text": text}],
                    "origin": {"kind": "user"},
                }
            )
        else:
            main_records.append(
                {
                    "type": "context.append_message",
                    "time": 1757000000000 + offset * 1000,
                    "message": {"role": role, "content": text},
                }
            )
    write_jsonl(session_dir / "agents" / "main" / "wire.jsonl", main_records)
    if subagent_turns:
        sub_records = [{"type": "metadata", "protocol_version": "1.5"}]
        for offset, (role, text) in enumerate(subagent_turns, start=1):
            sub_records.append(
                {
                    "type": "turn.prompt",
                    "time": 1757000100000 + offset * 1000,
                    "input": [{"type": "text", "text": text}],
                    "origin": {"kind": "user"},
                }
            )
        write_jsonl(session_dir / "agents" / "agent-1" / "wire.jsonl", sub_records)
    return session_dir


class MultiProviderIndexTests(unittest.TestCase):
    """Cover indexing providers other than Claude, and the v1 upgrade path."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspaces" / "demo"
        self.workspace.mkdir(parents=True)
        self.active = self.root / "active"
        self.codex_home = self.root / "codex"
        self.kimi_home = self.root / "kimi"
        self.db = self.root / "finder.db"
        self.claude_source = history_index.HistorySource(
            provider="claude", kind="active", label="main", home=self.active
        )
        self.codex_source = history_index.HistorySource(
            provider="codex", kind="active", label="codex", home=self.codex_home
        )
        self.kimi_source = history_index.HistorySource(
            provider="kimi", kind="active", label="kimi", home=self.kimi_home
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def scope(self, *sources, project_path=None):
        return history_index.IndexScope(
            sources=list(sources),
            warnings=[],
            project_path=project_path,
            all_projects=project_path is None,
        )

    def test_codex_rollouts_index_with_provider_and_skip_injected_preamble(self) -> None:
        session_id = "019a0000-0000-7000-8000-000000000001"
        codex_rollout(
            self.codex_home / "sessions" / "2026" / "05" / "01" / f"rollout-{session_id}.jsonl",
            session_id,
            self.workspace,
            [
                ("user", "<user_instructions>\nproject boilerplate\n</user_instructions>"),
                ("user", "<environment_context>\n<cwd>/tmp</cwd>\n</environment_context>"),
                # Goal-mode context is re-sent every turn and subagent status is
                # machine-to-machine; a skill block is a pasted file. None of
                # the three is anything a person said.
                ("user", "<goal_context>\ncurrent goal restated\n</goal_context>"),
                ("user", "<subagent_notification>\nagent finished\n</subagent_notification>"),
                ("user", "<skill>\nskill file contents\n</skill>"),
                ("user", "codex distinctive question"),
                ("assistant", "codex distinctive answer"),
            ],
        )
        with portable_backend():
            result = history_index.update_index(
                self.db, self.scope(self.codex_source), rebuild=True
            )
        self.assertEqual(result["sessions"], 1)
        connection = plain_connect(self.db, readonly=True)
        providers = connection.execute(
            "SELECT provider, count(*) FROM sessions GROUP BY provider"
        ).fetchall()
        self.assertEqual([tuple(row) for row in providers], [("codex", 1)])
        texts = [
            row[0]
            for row in connection.execute("SELECT fts_text FROM records ORDER BY seq")
        ]
        self.assertEqual(texts, ["codex distinctive question", "codex distinctive answer"])
        connection.close()

    def test_kimi_subagent_wire_keeps_its_own_records(self) -> None:
        session_id = "session_11111111-2222-3333-4444-555555555555"
        kimi_session(
            self.kimi_home,
            session_id,
            self.workspace,
            [("user", "kimi main prompt"), ("assistant", "kimi main reply")],
            subagent_turns=[("user", "kimi subagent prompt")],
        )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.kimi_source), rebuild=True
            )
        connection = plain_connect(self.db, readonly=True)
        rows = {
            row[0]
            for row in connection.execute("SELECT fts_text FROM records")
        }
        self.assertEqual(
            rows, {"kimi main prompt", "kimi main reply", "kimi subagent prompt"}
        )
        self.assertEqual(
            connection.execute("SELECT count(*) FROM sessions").fetchone()[0], 1
        )
        connection.close()

    def test_kimi_boilerplate_records_stay_out_of_the_index(self) -> None:
        session_id = "session_22222222-2222-4222-8222-222222222222"
        session_dir = kimi_session(
            self.kimi_home, session_id, self.workspace, [("user", "real kimi prompt")]
        )
        wire = session_dir / "agents" / "main" / "wire.jsonl"
        with wire.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "type": "config.update",
                        "time": 1757000500000,
                        "content": "shared system prompt boilerplate",
                    }
                )
                + "\n"
            )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.kimi_source), rebuild=True
            )
        connection = plain_connect(self.db, readonly=True)
        texts = [row[0] for row in connection.execute("SELECT fts_text FROM records")]
        self.assertEqual(texts, ["real kimi prompt"])
        connection.close()

    def test_project_scope_matches_a_cwd_spelled_through_a_symlink(self) -> None:
        real = self.root / "real-project"
        real.mkdir()
        link = self.root / "linked-project"
        link.symlink_to(real, target_is_directory=True)
        resolved = str(real.resolve())
        self.assertTrue(history_index._cwd_matches_project(str(link), resolved))
        self.assertTrue(history_index._cwd_matches_project(resolved, resolved))
        self.assertFalse(
            history_index._cwd_matches_project(str(self.root / "other"), resolved)
        )
        self.assertTrue(history_index._cwd_matches_project("anything", None))

    def test_widening_scope_adds_a_provider_without_dropping_sessions(self) -> None:
        claude_session = "11111111-1111-4111-8111-111111111111"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{claude_session}.jsonl",
            [user_record(claude_session, self.workspace, "claude marker", "2026-08-01T00:00:00Z")],
        )
        codex_id = "019a0000-0000-7000-8000-000000000001"
        codex_rollout(
            self.codex_home / "sessions" / "2026" / "05" / "01" / f"rollout-{codex_id}.jsonl",
            codex_id,
            self.workspace,
            [("user", "codex marker")],
        )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.claude_source), rebuild=True
            )
            widened = history_index.update_index(
                self.db, self.scope(self.claude_source, self.codex_source)
            )
        self.assertEqual(widened["removed"], 0)
        connection = plain_connect(self.db, readonly=True)
        providers = dict(
            connection.execute(
                "SELECT provider, count(*) FROM sessions GROUP BY provider"
            ).fetchall()
        )
        self.assertEqual(providers, {"claude": 1, "codex": 1})
        connection.close()

    def test_narrowing_scope_is_refused_so_nothing_is_pruned(self) -> None:
        claude_session = "11111111-1111-4111-8111-111111111111"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{claude_session}.jsonl",
            [user_record(claude_session, self.workspace, "claude marker", "2026-08-01T00:00:00Z")],
        )
        codex_id = "019a0000-0000-7000-8000-000000000001"
        codex_rollout(
            self.codex_home / "sessions" / "2026" / "05" / "01" / f"rollout-{codex_id}.jsonl",
            codex_id,
            self.workspace,
            [("user", "codex marker")],
        )
        with portable_backend():
            history_index.update_index(
                self.db,
                self.scope(self.claude_source, self.codex_source),
                rebuild=True,
            )
            with self.assertRaisesRegex(history_index.IndexError, "different source"):
                history_index.update_index(self.db, self.scope(self.claude_source))
        connection = plain_connect(self.db, readonly=True)
        self.assertEqual(
            connection.execute("SELECT count(*) FROM sessions").fetchone()[0], 2
        )
        connection.close()

    def seed_legacy_chunk_and_vector(self, text: str) -> None:
        """Give the index one chunk and one vector, as a pre-v3 index would."""
        connection = plain_connect(self.db)
        record_id = connection.execute("SELECT id FROM records").fetchone()[0]
        connection.execute(
            "INSERT INTO chunks(record_id,seq,ntok,text,usable,text_hash) "
            "VALUES(?,0,5,?,1,?)",
            (record_id, text, history_index._chunk_text_hash(text)),
        )
        chunk_id = connection.execute("SELECT id FROM chunks").fetchone()[0]
        connection.execute("CREATE TABLE vec_chunks(embedding BLOB)")
        connection.execute(
            "INSERT INTO vec_chunks(rowid,embedding) VALUES(?,?)",
            (chunk_id, b"fixture"),
        )
        connection.commit()
        connection.close()

    def build_one_claude_session(self) -> None:
        session_id = "11111111-1111-4111-8111-111111111111"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{session_id}.jsonl",
            [user_record(session_id, self.workspace, "legacy marker", "2026-08-01T00:00:00Z")],
        )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.claude_source), rebuild=True
            )

    def test_v1_index_migrates_in_place_and_keeps_every_record(self) -> None:
        """A v1 index reaches v3 in one call, both steps chained."""
        chunk_text = "legacy chunk text kept across the migration"
        self.build_one_claude_session()
        self.seed_legacy_chunk_and_vector(chunk_text)
        downgrade = plain_connect(self.db)
        downgrade.execute("DROP INDEX IF EXISTS idx_sessions_provider")
        downgrade.execute("ALTER TABLE sessions DROP COLUMN provider")
        downgrade.execute("DROP INDEX IF EXISTS idx_chunks_text_hash")
        downgrade.execute("ALTER TABLE chunks DROP COLUMN text_hash")
        downgrade.execute("PRAGMA user_version=1")
        downgrade.commit()
        before = downgrade.execute("SELECT count(*) FROM records").fetchone()[0]
        downgrade.close()

        connection = plain_connect(self.db)
        note = history_index._migrate_schema_if_needed(connection)
        self.assertIsNotNone(note)
        self.assertEqual(
            connection.execute("PRAGMA user_version").fetchone()[0],
            history_index.SCHEMA_VERSION,
        )
        self.assertEqual(
            connection.execute("SELECT count(*) FROM records").fetchone()[0], before
        )
        self.assertEqual(
            connection.execute("SELECT DISTINCT provider FROM sessions").fetchone()[0],
            "claude",
        )
        self.assertEqual(
            connection.execute("SELECT text_hash FROM chunks").fetchone()[0],
            history_index._chunk_text_hash(chunk_text),
        )
        self.assertEqual(
            connection.execute("SELECT count(*) FROM vec_chunks").fetchone()[0], 1
        )
        history_index._validate_schema(connection)
        self.assertIsNone(history_index._migrate_schema_if_needed(connection))
        connection.close()

    def test_v2_index_gains_backfilled_text_hash_without_losing_vectors(self) -> None:
        """v2->v3 adds one column; recomputing 678k vectors is not an option."""
        chunk_text = "a v2 chunk that already has its vector computed"
        self.build_one_claude_session()
        self.seed_legacy_chunk_and_vector(chunk_text)
        downgrade = plain_connect(self.db)
        downgrade.execute("DROP INDEX IF EXISTS idx_chunks_text_hash")
        downgrade.execute("ALTER TABLE chunks DROP COLUMN text_hash")
        downgrade.execute("PRAGMA user_version=2")
        downgrade.commit()
        downgrade.close()

        connection = plain_connect(self.db)
        note = history_index._migrate_schema_if_needed(connection)
        self.assertIn("text_hash", note)
        self.assertEqual(
            connection.execute("PRAGMA user_version").fetchone()[0],
            history_index.SCHEMA_VERSION,
        )
        self.assertEqual(
            connection.execute("SELECT text_hash FROM chunks").fetchone()[0],
            history_index._chunk_text_hash(chunk_text),
        )
        self.assertEqual(
            connection.execute("SELECT count(*) FROM records").fetchone()[0], 1
        )
        self.assertEqual(
            connection.execute("SELECT count(*) FROM vec_chunks").fetchone()[0], 1
        )
        self.assertEqual(
            connection.execute("SELECT DISTINCT provider FROM sessions").fetchone()[0],
            "claude",
        )
        history_index._validate_schema(connection)
        self.assertIsNone(history_index._migrate_schema_if_needed(connection))
        connection.close()

    def test_index_prunes_injected_codex_records_already_stored(self) -> None:
        """An index built before the prefix list grew still holds the blocks.

        The session file has not changed, so it is never re-extracted: without
        a sweep over stored records, those blocks stay lexically searchable for
        the life of the index.
        """
        session_id = "019a0000-0000-7000-8000-000000000002"
        rollout = (
            self.codex_home
            / "sessions"
            / "2026"
            / "05"
            / "01"
            / f"rollout-{session_id}.jsonl"
        )
        codex_rollout(rollout, session_id, self.workspace, [("user", "codex distinctive question")])
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.codex_source), rebuild=True
            )
        legacy = plain_connect(self.db)
        for seq, text in enumerate(
            [
                "<goal_context>\nzzgoalmarker restated goal\n</goal_context>",
                "<subagent_notification>\nzzgoalmarker agent done\n</subagent_notification>",
                "<skill>\nzzgoalmarker skill body\n</skill>",
                # LIKE would read the '_' in every prefix as a wildcard and
                # take this one too.
                "<userXinstructions> zzdecoy kept",
            ],
            start=90,
        ):
            legacy.execute(
                "INSERT INTO records(session_id,record_key,seq,role,ts,fts_text,"
                "semantic_text,noise,agent_prompt,segment_sources_json,"
                "copy_paths_json,source_labels_json) "
                "VALUES(?,?,?,'user',0,?,?,0,0,'[]',?,'[]')",
                (
                    session_id,
                    f"legacy-{seq}",
                    seq,
                    text,
                    text,
                    json.dumps([str(rollout)]),
                ),
            )
        legacy.execute("INSERT INTO records_fts(records_fts) VALUES('rebuild')")
        legacy.commit()
        legacy.close()

        with portable_backend():
            before = history_index.recall(
                self.db,
                "zzgoalmarker",
                mode="bm25",
                limit=10,
                project=None,
                exclude_sessions=[],
                include_agent_prompts=False,
                model_path=None,
                simple_root=None,
            )
            self.assertEqual(len(before["results"]), 3)
            pruned = history_index.update_index(self.db, self.scope(self.codex_source))
            after = history_index.recall(
                self.db,
                "zzgoalmarker",
                mode="bm25",
                limit=10,
                project=None,
                exclude_sessions=[],
                include_agent_prompts=False,
                model_path=None,
                simple_root=None,
            )
            again = history_index.update_index(self.db, self.scope(self.codex_source))
        self.assertEqual(pruned["records_pruned"], 3)
        self.assertEqual(after["results"], [])
        self.assertEqual(again["records_pruned"], 0)
        connection = plain_connect(self.db, readonly=True)
        self.assertEqual(
            sorted(row[0] for row in connection.execute("SELECT fts_text FROM records")),
            ["<userXinstructions> zzdecoy kept", "codex distinctive question"],
        )
        connection.close()

    def test_claude_harness_envelopes_never_reach_the_index(self) -> None:
        """Task notifications and teammate envelopes are harness text.

        Both arrive as ``type=user`` on the main thread, so the sidechain test
        that hides agent prompts never sees them, and neither tag is in
        NOISE_PREFIXES: before this they ranked exactly like something a person
        typed.
        """
        session_id = "44444444-4444-4444-8444-444444444444"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{session_id}.jsonl",
            [
                user_record(
                    session_id,
                    self.workspace,
                    "<task-notification>\n<task-id>abc</task-id>\n<status>failed</status>\n"
                    "</task-notification>",
                    "2026-08-01T00:00:00Z",
                ),
                user_record(
                    session_id,
                    self.workspace,
                    '<teammate-message teammate_id="reviewer" color="blue">\n'
                    '{"type":"idle_notification","from":"reviewer"}\n</teammate-message>',
                    "2026-08-01T00:00:01Z",
                ),
                {
                    # The model echoing the tag back is still machine text, so
                    # the match is on the text, not on the role.
                    "type": "assistant",
                    "sessionId": session_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-08-01T00:00:02Z",
                    "isSidechain": False,
                    "message": {
                        "role": "assistant",
                        "content": "<task-notification>\n<task-id>echo</task-id>\n"
                        "</task-notification>",
                    },
                },
                user_record(
                    session_id,
                    self.workspace,
                    "claude distinctive question",
                    "2026-08-01T00:00:03Z",
                ),
            ],
        )
        with portable_backend():
            result = history_index.update_index(
                self.db, self.scope(self.claude_source), rebuild=True
            )
        self.assertEqual(result["sessions"], 1)
        connection = plain_connect(self.db, readonly=True)
        texts = [
            row[0]
            for row in connection.execute("SELECT fts_text FROM records ORDER BY seq")
        ]
        connection.close()
        self.assertEqual(texts, ["claude distinctive question"])

    def test_index_prunes_stored_claude_envelopes_within_their_provider(self) -> None:
        session_id = "55555555-5555-4555-8555-555555555555"
        path = project_dir(self.active, self.workspace) / f"{session_id}.jsonl"
        write_jsonl(
            path,
            [
                user_record(
                    session_id,
                    self.workspace,
                    "claude distinctive question",
                    "2026-08-01T00:00:00Z",
                )
            ],
        )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.claude_source), rebuild=True
            )
        legacy = plain_connect(self.db)
        stored = [
            "<task-notification>\n<task-id>zzteammarker</task-id>\n</task-notification>",
            '<teammate-message teammate_id="zzteammarker">\nreport\n</teammate-message>',
            # Neither prefix matches this one, and a shorter prefix would have.
            "<taskmaster> zzteammarker kept",
            # A Codex-only block inside a Claude session stays: the evidence
            # that made these prefixes machine text was gathered per harness,
            # so the sweep is scoped to the provider it was proven on.
            "<goal_context>\nzzteammarker kept too\n</goal_context>",
        ]
        for seq, text in enumerate(stored, start=90):
            legacy.execute(
                "INSERT INTO records(session_id,record_key,seq,role,ts,fts_text,"
                "semantic_text,noise,agent_prompt,segment_sources_json,"
                "copy_paths_json,source_labels_json) "
                "VALUES(?,?,?,'user',0,?,?,0,0,'[]',?,'[]')",
                (session_id, f"legacy-{seq}", seq, text, text, json.dumps([str(path)])),
            )
        legacy.execute("INSERT INTO records_fts(records_fts) VALUES('rebuild')")
        legacy.commit()
        legacy.close()

        def marker_hits():
            return len(
                history_index.recall(
                    self.db,
                    "zzteammarker",
                    mode="bm25",
                    limit=10,
                    project=None,
                    exclude_sessions=[],
                    include_agent_prompts=False,
                    model_path=None,
                    simple_root=None,
                )["results"]
            )

        with portable_backend():
            self.assertEqual(marker_hits(), 4)
            pruned = history_index.update_index(self.db, self.scope(self.claude_source))
            after = marker_hits()
            again = history_index.update_index(self.db, self.scope(self.claude_source))
        self.assertEqual(pruned["records_pruned"], 2)
        self.assertEqual(after, 2)
        self.assertEqual(again["records_pruned"], 0)
        connection = plain_connect(self.db, readonly=True)
        self.assertEqual(
            sorted(row[0] for row in connection.execute("SELECT fts_text FROM records")),
            sorted(
                [
                    "claude distinctive question",
                    "<taskmaster> zzteammarker kept",
                    "<goal_context>\nzzteammarker kept too\n</goal_context>",
                ]
            ),
        )
        connection.close()

    def test_recall_refuses_a_provider_the_index_does_not_cover(self) -> None:
        session_id = "11111111-1111-4111-8111-111111111111"
        write_jsonl(
            project_dir(self.active, self.workspace) / f"{session_id}.jsonl",
            [user_record(session_id, self.workspace, "claude marker", "2026-08-01T00:00:00Z")],
        )
        with portable_backend():
            history_index.update_index(
                self.db, self.scope(self.claude_source), rebuild=True
            )
            with self.assertRaisesRegex(history_index.IndexError, "does not cover"):
                history_index.recall(
                    self.db,
                    "marker",
                    mode="bm25",
                    limit=5,
                    project=None,
                    exclude_sessions=[],
                    include_agent_prompts=False,
                    model_path=None,
                    simple_root=None,
                    providers=["codex"],
                )

    def test_coverage_names_the_providers_that_are_missing(self) -> None:
        payload = {
            "project_path": None,
            "sources": [
                {"provider": "claude", "kind": "active", "label": "main"},
                {"provider": "kimi", "kind": "active", "label": "kimi"},
            ],
        }
        description = history_index._coverage_description(payload)
        self.assertIn("claude/kimi", description)
        self.assertIn("Providers NOT indexed here: codex", description)
        self.assertIn("kimi:active:kimi", description)
        self.assertIn("active:main", description)

    def test_codex_rollout_without_session_meta_uses_its_filename_id(self) -> None:
        """A truncated rollout keeps its conversation instead of crashing the sweep.

        Real stores contain rollouts with no session_meta record at all. The
        first run over 8,919 real rollouts died on one of them, because the
        meta lookup returns None and was passed straight into the id reader.
        """
        session_id = "019a0000-0000-7000-8000-00000000beef"
        rollout = (
            self.codex_home / "sessions" / "2026" / "05" / "02"
            / f"rollout-2026-05-02T00-00-00-{session_id}.jsonl"
        )
        write_jsonl(
            rollout,
            [
                {
                    "timestamp": "2026-05-02T00:00:01.000Z",
                    "ordinal": 1,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "orphan rollout prose"}
                        ],
                    },
                }
            ],
        )
        with portable_backend():
            result = history_index.update_index(
                self.db, self.scope(self.codex_source), rebuild=True
            )
        self.assertEqual(result["sessions"], 1)
        connection = plain_connect(self.db, readonly=True)
        row = connection.execute(
            "SELECT session_id, provider, project FROM sessions"
        ).fetchone()
        self.assertEqual(row["session_id"], session_id)
        self.assertEqual(row["provider"], "codex")
        self.assertEqual(row["project"], "codex")
        self.assertEqual(
            connection.execute("SELECT fts_text FROM records").fetchone()[0],
            "orphan rollout prose",
        )
        connection.close()

    def test_one_unreadable_rollout_does_not_abort_the_sweep(self) -> None:
        good_id = "019a0000-0000-7000-8000-000000000002"
        codex_rollout(
            self.codex_home / "sessions" / "2026" / "05" / "03"
            / f"rollout-{good_id}.jsonl",
            good_id,
            self.workspace,
            [("user", "surviving codex prose")],
        )
        broken = (
            self.codex_home / "sessions" / "2026" / "05" / "03"
            / "rollout-019a0000-0000-7000-8000-000000000003.jsonl"
        )
        broken.parent.mkdir(parents=True, exist_ok=True)
        broken.write_bytes(b"\xff\xfe not valid utf-8 or json\n")
        warnings: list[str] = []
        refs = history_index._codex_session_refs(self.codex_source, None, warnings)
        self.assertIn(good_id, {ref["session_id"] for ref in refs})

    def test_resumed_codex_session_keeps_both_rollout_halves(self) -> None:
        """Two rollouts sharing one session_meta.id are halves, not copies.

        Resuming a Codex session writes a second rollout that keeps the
        original id and appends a fork id to the filename. Treating them as
        separate sessions violates the sessions PK; sharing a record key drops
        the resumed half, because its ordinals restart at 1. Both failures were
        hit on the real 8,924-rollout store.
        """
        session_id = "019a0000-0000-7000-8000-00000000f00d"
        fork_id = "019a0000-0000-7000-8000-00000000f00e"
        day = self.codex_home / "sessions" / "2026" / "05" / "04"
        codex_rollout(
            day / f"rollout-2026-05-04T01-00-00-{session_id}.jsonl",
            session_id,
            self.workspace,
            [("user", "first half question")],
        )
        codex_rollout(
            day / f"rollout-2026-05-04T02-00-00-{session_id}_{fork_id}.jsonl",
            session_id,
            self.workspace,
            [("user", "resumed half question")],
        )
        with portable_backend():
            result = history_index.update_index(
                self.db, self.scope(self.codex_source), rebuild=True
            )
        self.assertEqual(result["sessions"], 1)
        connection = plain_connect(self.db, readonly=True)
        texts = {
            row[0] for row in connection.execute("SELECT fts_text FROM records")
        }
        self.assertEqual(texts, {"first half question", "resumed half question"})
        copies = json.loads(
            connection.execute("SELECT copy_paths_json FROM records LIMIT 1").fetchone()[0]
        )
        self.assertTrue(copies)
        connection.close()

    def test_kimi_internal_agent_sessions_are_excluded_and_reported(self) -> None:
        """Title/vault/skill-summary runs are machine chatter, not conversation.

        A real Kimi store keeps them in the same sessions/ tree as real
        conversations, separated only by a directory prefix. Left in, a
        ctitle- run ("用户要求为以下对话生成一个简洁的标题") outranks the human's
        own words for the very query that quotes them.
        """
        kimi_session(
            self.kimi_home,
            "conv-1111111111111111",
            self.workspace,
            [("user", "genuine kimi conversation")],
        )
        for internal in ("ctitle-2222", "dvlt-3333", "sklsum-4444"):
            kimi_session(
                self.kimi_home, internal, self.workspace, [("user", "machine chatter")]
            )
        warnings: list[str] = []
        refs = history_index._kimi_session_refs(self.kimi_source, None, warnings)
        self.assertEqual([ref["session_id"] for ref in refs], ["conv-1111111111111111"])
        self.assertTrue(any("skipped 3 internal" in w for w in warnings), warnings)

    def test_kimi_workdir_comes_from_the_session_index_when_state_lacks_cwd(self) -> None:
        """Newer Kimi builds keep cwd only in session_index.jsonl.

        Without that lookup every Kimi session collapses into one "kimi"
        project label instead of joining the Claude and Codex sessions for the
        same repository, which is the whole point of one shared index.
        """
        session_id = "conv-5555555555555555"
        session_dir = kimi_session(
            self.kimi_home, session_id, self.workspace, [("user", "kimi prose")]
        )
        state = json.loads((session_dir / "state.json").read_text(encoding="utf-8"))
        state.pop("cwd", None)
        (session_dir / "state.json").write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
        (self.kimi_home / "session_index.jsonl").write_text(
            json.dumps(
                {
                    "sessionId": session_id,
                    "sessionDir": str(session_dir),
                    "workDir": str(self.workspace),
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        refs = history_index._kimi_session_refs(self.kimi_source, None, [])
        self.assertEqual(len(refs), 1)
        self.assertEqual(
            refs[0]["project"], str(self.workspace).replace("/", "-")
        )


class BoilerplatePolicyTests(unittest.TestCase):
    """Cover the chunk-time policy that decides which chunks earn a vector."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = self.root / "finder.db"
        self.repeated = "the same injected instruction block, verbatim again"
        self.unique = "a sentence that occurs exactly once in this corpus"
        self.short = "too short"
        with portable_backend():
            self.connection = history_index._new_database(self.db, None)
        self.connection.execute(
            "INSERT INTO sessions(session_id,project,primary_path,sources_json,"
            "fingerprint,started,ended,provider) "
            "VALUES('s','p','/p','[]','f',0,0,'codex')"
        )
        self.connection.execute(
            "INSERT INTO records(id,session_id,record_key,seq,role,ts,fts_text,"
            "semantic_text,noise,agent_prompt,segment_sources_json,copy_paths_json,"
            "source_labels_json) "
            "VALUES(1,'s','k',1,'user',0,'prose','prose',0,0,'[]','[]','[]')"
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def add_chunk(self, seq: int, text: str) -> int:
        """Insert a chunk the way build_chunks does, minus the hash.

        Leaving text_hash NULL is deliberate: it is what every chunk migrated
        from v2 looks like, so the policy's backfill is exercised too.
        """
        self.connection.execute(
            "INSERT INTO chunks(record_id,seq,ntok,text,usable) VALUES(1,?,?,?,?)",
            (seq, len(text), text, int(history_index._is_length_eligible(text))),
        )
        return self.connection.execute("SELECT max(id) FROM chunks").fetchone()[0]

    def usable_by_id(self) -> dict[int, int]:
        return {
            row[0]: row[1]
            for row in self.connection.execute("SELECT id,usable FROM chunks")
        }

    def test_third_copy_demotes_every_copy_but_the_lowest_id(self) -> None:
        first = self.add_chunk(0, self.repeated)
        second = self.add_chunk(1, self.repeated)
        third = self.add_chunk(2, self.repeated)
        distinct = self.add_chunk(3, self.unique)
        result = history_index.apply_boilerplate_policy(self.connection)
        self.assertEqual(result["hashes_backfilled"], 4)
        self.assertEqual(result["boilerplate_demoted"], 2)
        self.assertEqual(result["boilerplate_restored"], 0)
        self.assertEqual(
            self.usable_by_id(),
            {first: 1, second: 0, third: 0, distinct: 1},
        )
        hashes = {
            row[0]: row[1]
            for row in self.connection.execute("SELECT id,text_hash FROM chunks")
        }
        self.assertEqual(
            hashes[first], history_index._chunk_text_hash(self.repeated)
        )
        self.assertEqual(hashes[first], hashes[third])

    def test_two_copies_and_short_chunks_are_left_alone(self) -> None:
        first = self.add_chunk(0, self.repeated)
        second = self.add_chunk(1, self.repeated)
        shorts = [self.add_chunk(seq, self.short) for seq in (2, 3, 4)]
        result = history_index.apply_boilerplate_policy(self.connection)
        self.assertEqual(result["boilerplate_demoted"], 0)
        self.assertEqual(result["boilerplate_restored"], 0)
        usable = self.usable_by_id()
        self.assertEqual(usable[first], 1)
        self.assertEqual(usable[second], 1)
        # Three identical copies, but each is below the embed length gate, so
        # they were never usable and must not be "restored" into usability.
        self.assertEqual([usable[chunk_id] for chunk_id in shorts], [0, 0, 0])

    def test_copies_dropping_below_the_threshold_are_restored(self) -> None:
        first = self.add_chunk(0, self.repeated)
        second = self.add_chunk(1, self.repeated)
        third = self.add_chunk(2, self.repeated)
        history_index.apply_boilerplate_policy(self.connection)
        self.assertEqual(self.usable_by_id(), {first: 1, second: 0, third: 0})
        # Pruning injected records takes their chunks with them, which is how a
        # text falls back under BOILERPLATE_MIN_COPIES.
        self.connection.execute("DELETE FROM chunks WHERE id=?", (third,))
        result = history_index.apply_boilerplate_policy(self.connection)
        self.assertEqual(result["boilerplate_restored"], 1)
        self.assertEqual(result["boilerplate_demoted"], 0)
        self.assertEqual(self.usable_by_id(), {first: 1, second: 1})

    def test_pass_is_idempotent(self) -> None:
        for seq in range(3):
            self.add_chunk(seq, self.repeated)
        self.add_chunk(3, self.unique)
        history_index.apply_boilerplate_policy(self.connection)
        settled = self.usable_by_id()
        repeat = history_index.apply_boilerplate_policy(self.connection)
        self.assertEqual(
            (
                repeat["hashes_backfilled"],
                repeat["boilerplate_demoted"],
                repeat["boilerplate_restored"],
            ),
            (0, 0, 0),
        )
        self.assertEqual(self.usable_by_id(), settled)

    def test_demoted_vectors_are_dropped_when_the_backend_is_present(self) -> None:
        ids = [self.add_chunk(seq, self.repeated) for seq in range(3)]
        distinct = self.add_chunk(3, self.unique)
        self.connection.execute("CREATE TABLE vec_chunks(embedding BLOB)")
        for chunk_id in [*ids, distinct]:
            self.connection.execute(
                "INSERT INTO vec_chunks(rowid,embedding) VALUES(?,?)",
                (chunk_id, b"fixture"),
            )
        result = history_index.apply_boilerplate_policy(self.connection)
        self.assertEqual(result["vectors_dropped"], 2)
        self.assertEqual(result["non_embeddable_chunks"], 2)
        self.assertEqual(
            sorted(row[0] for row in self.connection.execute("SELECT rowid FROM vec_chunks")),
            sorted([ids[0], distinct]),
        )
        # The count is a standing property of the index, not a queue: the two
        # demoted copies stay non-embeddable after their vectors are gone, so a
        # second pass reports the same total with nothing left to drop. Reading
        # it as "work still owed" is what the old name invited.
        repeat = history_index.apply_boilerplate_policy(self.connection)
        self.assertEqual(repeat["vectors_dropped"], 0)
        self.assertEqual(repeat["non_embeddable_chunks"], 2)
        # Every usable chunk still has its vector, so the marker is honest.
        self.assertEqual(
            history_index._meta_get(self.connection, "vectors_complete"), "true"
        )

    def test_vector_drop_is_deferred_when_the_backend_is_absent(self) -> None:
        """The nightly chunk stage runs without sqlite-vec; embed finishes it."""
        ids = [self.add_chunk(seq, self.repeated) for seq in range(3)]
        self.add_chunk(3, self.unique)
        too_short = self.add_chunk(4, self.short)
        result = history_index.apply_boilerplate_policy(self.connection)
        # A null count is the signal that embed still has to drop the vectors:
        # without the backend there is no way to count how many rows that is.
        self.assertIsNone(result["vectors_dropped"])
        self.assertEqual(result["boilerplate_demoted"], 2)
        # Not a count of deferred deletions: it also carries the chunk that was
        # never embeddable and never had a vector to drop.
        self.assertEqual(result["non_embeddable_chunks"], 3)
        self.assertEqual(
            sorted(
                row[0]
                for row in self.connection.execute(
                    "SELECT id FROM chunks WHERE usable=0"
                )
            ),
            sorted([*ids[1:], too_short]),
        )
        # No live count was possible, so the pass must not claim completeness.
        self.assertEqual(
            history_index._meta_get(self.connection, "vectors_complete"), "false"
        )


class FakeClock:
    """A clock the embed loop reads instead of the wall clock.

    ``time()`` advances by a fixed step on every read, so a bounded run stops
    after an exact number of batches instead of after a real wait.
    """

    def __init__(self, step: float = 0.25) -> None:
        self.now = 1000.0
        self.step = step
        self.slept: list[float] = []

    def time(self) -> float:
        value = self.now
        self.now += self.step
        return value

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class _FakeEmbeddings:
    """One batch of MLX vectors: only the shape matters to the loop."""

    def __init__(self, rows: int) -> None:
        self.rows = rows

    def astype(self, _dtype):
        return self


class _FakeGenerated:
    def __init__(self, rows: int) -> None:
        self.text_embeds = _FakeEmbeddings(rows)


class _FakeVectorArray:
    def __init__(self, rows: int) -> None:
        self.rows = rows

    def tobytes(self) -> bytes:
        return bytes(history_index.EMBEDDING_DIM * 4 * self.rows)


@contextmanager
def fake_embedding_backend(*, generate_hook=None, peak_bytes: int = 2_300_000_000):
    """Run the real embed loop against stand-in MLX/NumPy modules.

    The registered suite is standard-library only and runs on Linux, so what is
    under test is the loop's own bookkeeping — progress, commits, lifecycle
    markers. MLX itself is exercised by the macOS smoke run.

    ``generate_hook`` receives the call count; call 1 is the warmup, so loop
    batch N is call N+1.
    """
    calls: list[list[str]] = []

    def generate(model, tokenizer, *, texts, max_length):
        calls.append(list(texts))
        if generate_hook is not None:
            generate_hook(len(calls))
        return _FakeGenerated(len(texts))

    core = types.SimpleNamespace(
        float32="float32",
        set_memory_limit=lambda value: None,
        set_cache_limit=lambda value: None,
        reset_peak_memory=lambda: None,
        clear_cache=lambda: None,
        eval=lambda value: None,
        get_active_memory=lambda: 1024,
        get_cache_memory=lambda: 2048,
        get_peak_memory=lambda: peak_bytes,
    )
    mlx = types.ModuleType("mlx")
    mlx.core = core
    embeddings = types.ModuleType("mlx_embeddings")
    embeddings.generate = generate
    embeddings.load = lambda path: (object(), object())
    numpy = types.ModuleType("numpy")
    numpy.float32 = "float32"
    numpy.array = lambda value, dtype=None: _FakeVectorArray(value.rows)
    with ExitStack() as stack:
        stack.enter_context(
            mock.patch.dict(
                sys.modules,
                {
                    "mlx": mlx,
                    "mlx.core": core,
                    "mlx_embeddings": embeddings,
                    "numpy": numpy,
                },
            )
        )
        stack.enter_context(
            mock.patch.object(
                history_index,
                "platform",
                types.SimpleNamespace(system=lambda: "Darwin", machine=lambda: "arm64"),
            )
        )
        # The pause policy has its own tests; it must never fire in these.
        stack.enter_context(
            mock.patch.object(
                history_index,
                "_host_memory_pressure_level",
                lambda: history_index.HOST_PRESSURE_NORMAL,
            )
        )
        yield calls


class HostPressurePauseTests(unittest.TestCase):
    """Cover the pause that replaced the unconditional four-second sleep."""

    def probe(self, **run_kwargs):
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    history_index,
                    "platform",
                    types.SimpleNamespace(system=lambda: "Darwin"),
                )
            )
            stack.enter_context(
                mock.patch.object(history_index.subprocess, "run", **run_kwargs)
            )
            return history_index._host_memory_pressure_level()

    def test_the_probe_reads_the_level_and_treats_every_failure_as_normal(self) -> None:
        self.assertEqual(
            self.probe(
                return_value=types.SimpleNamespace(returncode=0, stdout="4\n", stderr="")
            ),
            4,
        )
        # A level that cannot be read is not evidence of pressure: refusing to
        # embed because sysctl is missing would turn a diagnostic into an outage.
        self.assertEqual(
            self.probe(
                return_value=types.SimpleNamespace(returncode=1, stdout="", stderr="no")
            ),
            history_index.HOST_PRESSURE_NORMAL,
        )
        self.assertEqual(
            self.probe(
                return_value=types.SimpleNamespace(returncode=0, stdout="???", stderr="")
            ),
            history_index.HOST_PRESSURE_NORMAL,
        )
        self.assertEqual(
            self.probe(
                side_effect=subprocess.TimeoutExpired(cmd="sysctl", timeout=2)
            ),
            history_index.HOST_PRESSURE_NORMAL,
        )
        self.assertEqual(
            self.probe(side_effect=FileNotFoundError("sysctl")),
            history_index.HOST_PRESSURE_NORMAL,
        )

    def test_a_platform_without_the_sysctl_is_not_probed_at_all(self) -> None:
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    history_index,
                    "platform",
                    types.SimpleNamespace(system=lambda: "Linux"),
                )
            )
            runner = stack.enter_context(
                mock.patch.object(history_index.subprocess, "run")
            )
            self.assertEqual(
                history_index._host_memory_pressure_level(),
                history_index.HOST_PRESSURE_NORMAL,
            )
        runner.assert_not_called()

    def pause(self, levels, *, deadline=None, ceiling=None):
        """Run the pause against a scripted pressure trace and a fake clock."""
        clock = FakeClock()
        stdout = io.StringIO()
        stderr = io.StringIO()
        trace = iter(levels)
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(history_index, "time", clock))
            stack.enter_context(
                mock.patch.object(
                    history_index, "_host_memory_pressure_level", lambda: next(trace)
                )
            )
            if ceiling is not None:
                stack.enter_context(
                    mock.patch.object(
                        history_index, "EMBED_PAUSE_CEILING_SECONDS", ceiling
                    )
                )
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            waited, outcome = history_index._pause_while_host_is_under_pressure(
                deadline
            )
        # Progress is not a result: stdout has to stay a single JSON document.
        self.assertEqual(stdout.getvalue(), "")
        return clock, waited, outcome, stderr.getvalue()

    def test_a_healthy_host_is_never_paused(self) -> None:
        clock, waited, outcome, output = self.pause([1])
        self.assertEqual((waited, outcome), (0.0, "clear"))
        self.assertEqual(clock.slept, [])
        self.assertEqual(output, "")

    def test_pressure_backs_off_to_a_ceiling_and_reports_both_edges(self) -> None:
        clock, waited, outcome, output = self.pause([2, 2, 2, 4, 4, 4, 4, 2, 1])
        self.assertEqual(clock.slept, [1, 2, 4, 8, 16, 30, 30, 30])
        self.assertEqual((waited, outcome), (121.0, "clear"))
        lines = output.splitlines()
        self.assertEqual(
            lines[0],
            "  paused: host memory pressure 2 (1=normal, 2=warning, 4=critical); "
            "waiting for it to clear",
        )
        # A multi-minute wait has to keep saying so, or it is indistinguishable
        # from a hang.
        self.assertEqual(
            lines[1], "  still paused after 61s · host memory pressure 4"
        )
        self.assertEqual(lines[-1], "  resumed after 121s · host memory pressure 1")

    def test_the_callers_deadline_ends_the_pause(self) -> None:
        """--max-seconds has to stay the run's upper bound.

        The nightly job passes --max-seconds 10800 so embedding cannot run past
        06:30. A pause with no deadline turned that into a suggestion: the loop
        enters the pause before it checks its budget, so a host that stayed at
        warning level kept the pass sleeping — and holding the writer lock —
        indefinitely.
        """
        # FakeClock starts at 1000.0 and advances 0.25 s per read, so a deadline
        # of 1000.5 is already spent by the time the second iteration looks.
        clock, waited, outcome, output = self.pause([2] * 8, deadline=1000.5)
        self.assertEqual(outcome, "deadline")
        self.assertEqual(clock.slept, [1])
        self.assertEqual(waited, 1.0)
        self.assertIn("time budget spent", output.splitlines()[-1])

    def test_pressure_that_never_clears_hits_a_ceiling(self) -> None:
        """An unbounded run has no deadline; it still must not wait forever."""
        clock, waited, outcome, output = self.pause([2] * 12, ceiling=10)
        self.assertEqual(outcome, "ceiling")
        # 1+2+4+8 = 15 is the first total at or above the ten-second ceiling.
        self.assertEqual(clock.slept, [1, 2, 4, 8])
        self.assertEqual(waited, 15.0)
        self.assertIn("outlasted the 10s ceiling", output.splitlines()[-1])


class EmbedLifecycleTests(unittest.TestCase):
    """Cover token progress, the heartbeat and the recorded stop reason."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = self.root / "finder.db"
        self.model = self.root / "snapshot-abc123"
        self.model.mkdir()
        with portable_backend():
            self.connection = history_index._new_database(self.db, None)
        self.connection.execute(
            "INSERT INTO sessions(session_id,project,primary_path,sources_json,"
            "fingerprint,started,ended,provider) "
            "VALUES('s','p','/p','[]','f',0,0,'claude')"
        )
        self.connection.execute(
            "INSERT INTO records(id,session_id,record_key,seq,role,ts,fts_text,"
            "semantic_text,noise,agent_prompt,segment_sources_json,copy_paths_json,"
            "source_labels_json) "
            "VALUES(1,'s','k',1,'user',0,'prose','prose',0,0,'[]','[]','[]')"
        )
        # Stand-in for the vec0 virtual table: CREATE VIRTUAL TABLE IF NOT
        # EXISTS is a no-op once the name is taken, so the loop runs unchanged.
        self.connection.execute("CREATE TABLE vec_chunks(embedding BLOB)")
        history_index._meta_set(self.connection, "chunks_complete", "true")
        history_index._meta_set(
            self.connection, "embedding_model_revision", self.model.name
        )
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def add_chunks(self, count: int, *, ntok: int = 100) -> None:
        for seq in range(count):
            text = f"chunk body number {seq} with enough characters to embed"
            self.connection.execute(
                "INSERT INTO chunks(record_id,seq,ntok,text,usable,text_hash) "
                "VALUES(1,?,?,?,1,?)",
                (seq, ntok, text, history_index._chunk_text_hash(text)),
            )
        self.connection.commit()

    def embed(
        self,
        *,
        batch_size: int = 4,
        commit_every: int = 4,
        max_seconds: int | None = None,
        clock_step: float = 0.25,
        generate_hook=None,
        pressure=None,
        pause_ceiling: float | None = None,
        pause_hook=None,
    ):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(portable_backend())
            stack.enter_context(fake_embedding_backend(generate_hook=generate_hook))
            # Entered after the backend, so these win over its healthy-host stub.
            if pressure is not None:
                stack.enter_context(
                    mock.patch.object(
                        history_index, "_host_memory_pressure_level", pressure
                    )
                )
            if pause_ceiling is not None:
                stack.enter_context(
                    mock.patch.object(
                        history_index, "EMBED_PAUSE_CEILING_SECONDS", pause_ceiling
                    )
                )
            if pause_hook is not None:
                stack.enter_context(
                    mock.patch.object(
                        history_index,
                        "_pause_while_host_is_under_pressure",
                        pause_hook,
                    )
                )
            stack.enter_context(
                mock.patch.object(history_index, "EMBED_COMMIT_EVERY", commit_every)
            )
            stack.enter_context(
                mock.patch.object(history_index, "time", FakeClock(clock_step))
            )
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            try:
                result = history_index.embed_chunks(
                    self.db,
                    model_path=self.model,
                    download_model=False,
                    max_seconds=max_seconds,
                    batch_size=batch_size,
                    memory_limit_gb=8.0,
                    cache_limit_gb=0.5,
                )
            finally:
                # Every test in this class carries the invariant: embed writes
                # progress to stderr, because `embed --json` has to leave stdout
                # a single parseable document.
                self.assertEqual(stdout.getvalue(), "")
        return result, stderr.getvalue()

    def meta(self, key: str) -> str | None:
        return history_index._meta_get(self.connection, key)

    def vector_count(self) -> int:
        return self.connection.execute("SELECT count(*) FROM vec_chunks").fetchone()[0]

    def test_progress_counts_tokens_not_only_chunks(self) -> None:
        """Chunks are a bad unit for an ETA: this backlog is 365-602 tokens
        per chunk, so the remaining *token* mass is what predicts the time."""
        self.add_chunks(12, ntok=100)
        result, output = self.embed()
        lines = [line for line in output.splitlines() if "embedded" in line]
        self.assertEqual(
            lines[0],
            "  embedded 4/12 chunks · 400/1200 tok (33.3%) · 16 chunks/s "
            "(1600 tok/s) · ETA 0 min · MLX peak 2.14 GiB",
        )
        self.assertEqual(
            lines[-1],
            "  embedded 12/12 chunks · 1200/1200 tok (100.0%) · 16 chunks/s "
            "(1600 tok/s) · ETA 0 min · MLX peak 2.14 GiB",
        )
        self.assertEqual(result["embedded"], 12)
        self.assertEqual(result["embedded_tokens"], 1200)
        self.assertEqual(result["remaining"], 0)
        self.assertEqual(result["remaining_tokens"], 0)
        self.assertEqual(result["stop_reason"], "complete")
        self.assertEqual(self.vector_count(), 12)
        self.assertEqual(self.meta("vectors_complete"), "true")
        self.assertEqual(self.meta("embed_stop_reason"), "complete")
        self.assertIsNotNone(self.meta("last_embedded_at"))

    def test_an_unmeasurable_rate_prints_a_question_mark_not_a_number(self) -> None:
        self.add_chunks(8, ntok=0)
        _, output = self.embed()
        self.assertIn("0/0 tok (0.0%)", output)
        self.assertIn("ETA ? min", output)

    def test_the_heartbeat_is_on_disk_before_the_run_ends(self) -> None:
        """A run that dies mid-pass must leave a timestamp that is already true.

        Read the committed state from a second connection while the first is
        mid-transaction: the value has to be on disk, not in this process.
        """
        self.add_chunks(16)
        seen: dict[str, object] = {}

        def snapshot(call_number: int) -> None:
            if call_number != 4:  # warmup, batch 1, batch 2, then this one
                return
            observer = plain_connect(self.db, readonly=True)
            seen["last_embedded_at"] = history_index._meta_get(
                observer, "last_embedded_at"
            )
            seen["vectors_complete"] = history_index._meta_get(
                observer, "vectors_complete"
            )
            seen["vectors"] = observer.execute(
                "SELECT count(*) FROM vec_chunks"
            ).fetchone()[0]
            observer.close()

        result, _ = self.embed(generate_hook=snapshot)
        self.assertEqual(seen["vectors"], 8)
        self.assertIsNotNone(seen["last_embedded_at"])
        # Eight of sixteen are done, so the marker must not claim completeness.
        self.assertEqual(seen["vectors_complete"], "false")
        self.assertEqual(result["embedded"], 16)
        self.assertEqual(self.meta("vectors_complete"), "true")

    def test_a_bounded_run_records_why_it_stopped(self) -> None:
        self.add_chunks(12)
        result, _ = self.embed(max_seconds=1)
        self.assertEqual(result["stop_reason"], "max_seconds")
        self.assertEqual(result["embedded"], 8)
        self.assertEqual(result["remaining"], 4)
        self.assertEqual(result["remaining_tokens"], 400)
        self.assertEqual(self.meta("embed_stop_reason"), "max_seconds")
        self.assertEqual(self.meta("vectors_complete"), "false")

    def test_a_memory_boundary_stop_is_recorded_before_the_error_surfaces(self) -> None:
        self.add_chunks(12)

        def fail_on_the_second_batch(call_number: int) -> None:
            if call_number == 3:  # warmup, batch 1, then this one
                raise RuntimeError("[metal::malloc] attempted to allocate too much")

        with self.assertRaisesRegex(history_index.IndexError, "memory boundary"):
            self.embed(generate_hook=fail_on_the_second_batch)
        self.assertEqual(self.meta("embed_stop_reason"), "memory_boundary")
        self.assertIsNotNone(self.meta("last_embedded_at"))
        # The committed batch survives; the run is resumable, not lost.
        self.assertEqual(self.vector_count(), 4)
        self.assertEqual(self.meta("vectors_complete"), "false")

    def test_an_empty_backlog_reports_complete_without_touching_the_model(self) -> None:
        result, output = self.embed()
        self.assertEqual(
            (result["embedded"], result["embedded_tokens"], result["stop_reason"]),
            (0, 0, "complete"),
        )
        self.assertEqual(result["remaining_tokens"], 0)
        self.assertEqual(self.meta("embed_stop_reason"), "complete")
        self.assertEqual(self.meta("vectors_complete"), "true")
        self.assertEqual(output, "")

    def test_the_dead_vectors_embed_drops_are_counted_in_its_result(self) -> None:
        """The one destructive step in this stage needs a receipt.

        The nightly chunk stage runs without sqlite-vec, so it defers both
        deletions here and says so with ``vectors_dropped: null``. On the live
        index the first pass after the boilerplate policy lands drops tens of
        thousands of already-embedded vectors; without a number in the JSON
        that night is indistinguishable from a night that dropped none, except
        by diffing status counts across runs.
        """
        self.add_chunks(4)
        demoted_text = "a demoted duplicate chunk with enough characters to embed"
        demoted_id = self.connection.execute(
            "INSERT INTO chunks(record_id,seq,ntok,text,usable,text_hash) "
            "VALUES(1,?,?,?,0,?)",
            (99, 100, demoted_text, history_index._chunk_text_hash(demoted_text)),
        ).lastrowid
        for rowid in (demoted_id, 4242):
            self.connection.execute(
                "INSERT INTO vec_chunks(rowid,embedding) VALUES(?,?)",
                (rowid, b"fixture"),
            )
        self.connection.commit()

        result, _ = self.embed(commit_every=10_000)
        # An orphan is a vector whose chunk is gone; a demoted one is a vector
        # whose chunk is still there but is no longer embeddable.
        self.assertEqual(result["orphan_vectors_dropped"], 1)
        self.assertEqual(result["demoted_vectors_dropped"], 1)
        self.assertEqual(result["embedded"], 4)
        # Only the four live chunks keep vectors, and they are the new ones.
        self.assertEqual(
            sorted(
                row[0]
                for row in self.connection.execute("SELECT rowid FROM vec_chunks")
            ),
            [1, 2, 3, 4],
        )

        # Idempotent, and it still says so: the second night reports zero
        # rather than going quiet, which is what makes the first night's
        # large number readable as one-off cleanup.
        second, _ = self.embed(commit_every=10_000)
        self.assertEqual(second["stop_reason"], "complete")
        self.assertEqual(second["orphan_vectors_dropped"], 0)
        self.assertEqual(second["demoted_vectors_dropped"], 0)

    def test_a_pass_marks_itself_running_before_it_starts_working(self) -> None:
        """A killed pass runs no handler, so it can only be told apart from a
        finished one by a marker written on the way in.

        Host OOM and Ctrl-C are exactly the endings this field exists to
        diagnose, and neither reaches the RuntimeError handler. Without the
        entry write, status reports the *previous* pass's `complete` next to a
        stale heartbeat.
        """
        self.add_chunks(16)
        # The previous pass finished cleanly; this one must not inherit its
        # ending.
        history_index._meta_set(self.connection, "embed_stop_reason", "complete")
        self.connection.commit()
        seen: dict[str, object] = {}

        def watch(call_number: int) -> None:
            if call_number != 2:  # warmup, then the first real batch
                return
            observer = plain_connect(self.db, readonly=True)
            seen["stop_reason"] = history_index._meta_get(
                observer, "embed_stop_reason"
            )
            observer.close()
            raise KeyboardInterrupt("the host killed this pass")

        with self.assertRaises(KeyboardInterrupt):
            self.embed(generate_hook=watch)
        self.assertEqual(seen["stop_reason"], "running")
        # And it survives the kill: no handler ran, so this is what status sees.
        observer = plain_connect(self.db, readonly=True)
        self.assertEqual(
            history_index._meta_get(observer, "embed_stop_reason"), "running"
        )
        observer.close()

    def test_a_warmup_failure_is_recorded_before_the_error_surfaces(self) -> None:
        self.add_chunks(8)

        def fail_the_warmup(call_number: int) -> None:
            if call_number == 1:
                raise RuntimeError("[metal::malloc] attempted to allocate too much")

        with self.assertRaisesRegex(history_index.IndexError, "warmup"):
            self.embed(generate_hook=fail_the_warmup)
        self.assertEqual(self.meta("embed_stop_reason"), "warmup_failed")
        self.assertEqual(self.vector_count(), 0)

    def test_a_pause_is_a_durable_safe_point(self) -> None:
        """Being killed during the wait that exists to avoid being killed must
        not throw away the batches already computed.

        The pause fires every eight batches and the commit checkpoint every
        EMBED_COMMIT_EVERY chunks; the cadences are not aligned, so without an
        explicit commit the loop could start waiting with a whole checkpoint's
        worth of vectors still only in this process.
        """
        self.add_chunks(40)
        seen: dict[str, object] = {}

        def pressure() -> int:
            # The first probe runs inside the pause, i.e. after the safe point.
            if "vectors" not in seen:
                observer = plain_connect(self.db, readonly=True)
                seen["vectors"] = observer.execute(
                    "SELECT count(*) FROM vec_chunks"
                ).fetchone()[0]
                seen["last_embedded_at"] = history_index._meta_get(
                    observer, "last_embedded_at"
                )
                observer.close()
                return history_index.HOST_PRESSURE_WARNING
            return history_index.HOST_PRESSURE_NORMAL

        # A checkpoint far beyond this run, so the only commit that can have
        # happened by the pause is the safe point itself.
        result, output = self.embed(commit_every=10_000, pressure=pressure)
        self.assertEqual(seen["vectors"], 32)  # eight batches of four
        self.assertIsNotNone(seen["last_embedded_at"])
        self.assertEqual(result["stop_reason"], "complete")
        self.assertEqual(result["embedded"], 40)
        self.assertIn("paused: host memory pressure 2", output)

    def test_pressure_that_never_clears_stops_the_pass(self) -> None:
        """Waiting forever is worse than stopping: the pass holds the writer
        lock while it waits, so the next night's index cannot even start."""
        self.add_chunks(40)
        result, output = self.embed(
            commit_every=10_000,
            pressure=lambda: history_index.HOST_PRESSURE_WARNING,
            pause_ceiling=10,
        )
        self.assertEqual(result["stop_reason"], "host_pressure")
        self.assertEqual(self.meta("embed_stop_reason"), "host_pressure")
        # Stopped through the normal exit: what was committed is resumable.
        self.assertEqual(result["embedded"], 32)
        self.assertEqual(result["remaining"], 8)
        self.assertEqual(self.vector_count(), 32)
        self.assertEqual(self.meta("vectors_complete"), "false")
        self.assertIn("outlasted the 10s ceiling", output)

    def test_a_host_pressure_stop_exits_zero_so_only_status_can_show_it(self) -> None:
        """Stopping on host pressure is a success as far as the shell knows.

        The nightly wrapper's only failure signal is the exit code, so a host
        that stays under pressure advances a few batches a night and still
        writes OK. That is a real blind spot and the reason the reference doc
        has to route the alert through `embed_stop_reason` instead of `$?` —
        this test is what keeps the two honest about each other.
        """
        self.add_chunks(40)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(portable_backend())
            stack.enter_context(fake_embedding_backend())
            # After the backend, so this wins over its healthy-host stub.
            stack.enter_context(
                mock.patch.object(
                    history_index,
                    "_host_memory_pressure_level",
                    lambda: history_index.HOST_PRESSURE_WARNING,
                )
            )
            stack.enter_context(
                mock.patch.object(history_index, "EMBED_PAUSE_CEILING_SECONDS", 10)
            )
            stack.enter_context(
                mock.patch.object(history_index, "EMBED_COMMIT_EVERY", 10_000)
            )
            stack.enter_context(mock.patch.object(history_index, "time", FakeClock()))
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            code = history_index.main(
                [
                    "--db",
                    str(self.db),
                    "embed",
                    "--model-path",
                    str(self.model),
                    "--batch-size",
                    "4",
                    "--json",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["stop_reason"], "host_pressure")
        # Exit 0 with the queue not drained: the exit code cannot show this.
        self.assertEqual(payload["embedded"], 32)
        self.assertEqual(payload["remaining"], 8)
        self.assertEqual(self.meta("embed_stop_reason"), "host_pressure")
        self.assertEqual(self.meta("vectors_complete"), "false")

    def test_the_pause_is_given_this_runs_own_deadline(self) -> None:
        """--max-seconds is the run's upper bound, so the pause has to know it."""
        self.add_chunks(40)
        seen: list[float | None] = []

        def pause(deadline=None):
            seen.append(deadline)
            return 0.0, "clear"

        self.embed(commit_every=10_000, max_seconds=10_000, pause_hook=pause)
        self.assertTrue(seen, "the loop never reached a pause point")
        # FakeClock starts at 1000.0 and only moves forward.
        self.assertTrue(all(value is not None for value in seen))
        self.assertGreaterEqual(seen[0], 1000.0 + 10_000)

        seen.clear()
        self.connection.execute("DELETE FROM vec_chunks")
        self.connection.commit()
        self.embed(commit_every=10_000, pause_hook=pause)
        self.assertTrue(seen, "the loop never reached a pause point")
        # An unbounded run has no deadline to pass; the ceiling still bounds it.
        self.assertEqual(seen, [None] * len(seen))

    def test_embed_json_leaves_stdout_a_single_document(self) -> None:
        """`embed --json | jq` has to work: progress is not a result."""
        self.add_chunks(12)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(portable_backend())
            stack.enter_context(fake_embedding_backend())
            stack.enter_context(
                mock.patch.object(history_index, "EMBED_COMMIT_EVERY", 4)
            )
            stack.enter_context(mock.patch.object(history_index, "time", FakeClock()))
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            code = history_index.main(
                [
                    "--db",
                    str(self.db),
                    "embed",
                    "--model-path",
                    str(self.model),
                    "--batch-size",
                    "4",
                    "--json",
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["embedded"], 12)
        self.assertEqual(payload["stop_reason"], "complete")
        self.assertIn("embedded 4/12 chunks", stderr.getvalue())

    def test_status_surfaces_the_stop_reason_and_the_heartbeat(self) -> None:
        self.add_chunks(8)
        history_index._meta_set(
            self.connection,
            "index_scope",
            json.dumps({"all_projects": True, "project_path": None, "sources": []}),
        )
        self.connection.commit()
        self.embed(max_seconds=1)
        with portable_backend():
            payload = history_index.index_status(
                self.db, simple_root=None, inspect_sources=False, scope=None
            )
        self.assertEqual(payload["embed_stop_reason"], "max_seconds")
        self.assertEqual(payload["last_embedded_at"], self.meta("last_embedded_at"))


class WriterLockTests(unittest.TestCase):
    """One writer at a time: nothing coordinated manual and nightly runs."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = self.root / "finder.db"
        self.lock_path = Path(str(self.db) + ".lock")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @contextmanager
    def held_from_another_run(self):
        """flock is per open file description, so this really does conflict."""
        handle = self.lock_path.open("a")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def test_a_second_writer_is_refused_and_told_which_file_to_wait_on(self) -> None:
        stderr = io.StringIO()
        with self.held_from_another_run():
            with ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(
                        history_index,
                        "update_index",
                        side_effect=AssertionError("ran while another writer held the lock"),
                    )
                )
                # Zero budget: this test is about the refusal, not the wait.
                stack.enter_context(
                    mock.patch.object(history_index, "WRITER_LOCK_WAIT_SECONDS", 0.0)
                )
                stack.enter_context(mock.patch("sys.stderr", stderr))
                code = history_index.main(["--db", str(self.db), "index"])
        self.assertEqual(code, 2)
        message = stderr.getvalue()
        self.assertIn(str(self.lock_path), message)
        self.assertIn("Wait for it to finish", message)

    def test_a_short_overlap_is_waited_out_instead_of_failing_the_night(self) -> None:
        """The nightly script fails the whole night on any non-zero exit.

        Refusing the instant the lock is taken made a one-second overlap with a
        manual run cost that night's index, chunk and embed; the run is waited
        out instead, and only an overlap longer than the budget is refused.
        """
        handle = self.lock_path.open("a")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        released: list[float] = []

        def sleep(seconds: float) -> None:
            """Stand in for the wall clock: the other writer finishes here."""
            released.append(seconds)
            if len(released) == 1:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

        stderr = io.StringIO()
        payload = {"database": str(self.db)}
        try:
            with ExitStack() as stack:
                stack.enter_context(
                    mock.patch.object(history_index, "_scope_from_args", return_value=None)
                )
                stack.enter_context(
                    mock.patch.object(history_index, "update_index", return_value=payload)
                )
                stack.enter_context(
                    mock.patch.object(
                        history_index,
                        "time",
                        types.SimpleNamespace(sleep=sleep, time=lambda: 0.0),
                    )
                )
                stack.enter_context(mock.patch("sys.stderr", stderr))
                stack.enter_context(redirect_stdout(io.StringIO()))
                code = history_index.main(["--db", str(self.db), "index", "--json"])
        finally:
            handle.close()
        self.assertEqual(code, 0)
        self.assertEqual(released, [history_index.WRITER_LOCK_POLL_SECONDS])
        # A wait is not a hang: it says what it is waiting for.
        self.assertIn(str(self.lock_path), stderr.getvalue())

    def test_the_nightly_sequence_hands_the_lock_on_instead_of_deadlocking(self) -> None:
        payload = {"database": str(self.db)}
        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(history_index, "_scope_from_args", return_value=None)
            )
            stack.enter_context(
                mock.patch.object(history_index, "update_index", return_value=payload)
            )
            stack.enter_context(
                mock.patch.object(history_index, "build_chunks", return_value=payload)
            )
            stack.enter_context(
                mock.patch.object(history_index, "embed_chunks", return_value=payload)
            )
            stack.enter_context(redirect_stdout(io.StringIO()))
            codes = [
                history_index.main(["--db", str(self.db), command, "--json"])
                for command in ("index", "chunk", "embed")
            ]
        self.assertEqual(codes, [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
