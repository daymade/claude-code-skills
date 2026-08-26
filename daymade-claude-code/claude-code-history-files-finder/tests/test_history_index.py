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


if __name__ == "__main__":
    unittest.main()
