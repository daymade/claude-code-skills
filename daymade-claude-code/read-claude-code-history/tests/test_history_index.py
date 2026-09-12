"""Deterministic tests for the optional hybrid history index.

CI uses SQLite's built-in unicode61 tokenizer plus a test-only identity
``simple_query`` function. Real libsimple/MLX integration is exercised by an
explicit smoke run on supported machines, never by the registered Linux suite.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
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
        self.assertEqual(result["vectors_drop_deferred"], 0)
        self.assertEqual(
            sorted(row[0] for row in self.connection.execute("SELECT rowid FROM vec_chunks")),
            sorted([ids[0], distinct]),
        )
        # Every usable chunk still has its vector, so the marker is honest.
        self.assertEqual(
            history_index._meta_get(self.connection, "vectors_complete"), "true"
        )

    def test_vector_drop_is_deferred_when_the_backend_is_absent(self) -> None:
        """The nightly chunk stage runs without sqlite-vec; embed finishes it."""
        ids = [self.add_chunk(seq, self.repeated) for seq in range(3)]
        self.add_chunk(3, self.unique)
        result = history_index.apply_boilerplate_policy(self.connection)
        self.assertIsNone(result["vectors_dropped"])
        self.assertEqual(result["vectors_drop_deferred"], 2)
        self.assertEqual(result["boilerplate_demoted"], 2)
        self.assertEqual(
            sorted(
                row[0]
                for row in self.connection.execute(
                    "SELECT id FROM chunks WHERE usable=0"
                )
            ),
            sorted(ids[1:]),
        )
        # No live count was possible, so the pass must not claim completeness.
        self.assertEqual(
            history_index._meta_get(self.connection, "vectors_complete"), "false"
        )


if __name__ == "__main__":
    unittest.main()
