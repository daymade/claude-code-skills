#!/usr/bin/env python3
"""Regressions for exact, reversible context_rules state management."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli import cmd_disable_context_rule, create_argument_parser
from core.correction_repository import (
    CorrectionRepository,
    DatabaseError,
    ValidationError,
)
from core.correction_service import CorrectionService


TARGET_PATTERN = r"alpha(?= cue)"
OTHER_PATTERN = r"beta(?= cue)"
LITERAL_GLOBAL_PATTERN = r"literal-global(?= cue)"
NULL_GLOBAL_PATTERN = r"null-global(?= cue)"
REASON = "synthetic reversible state check"
CLI_SCRIPT = Path(__file__).resolve().parent.parent / "fix_transcription.py"


def _rows(db_path: Path, table: str):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()


def _snapshot(db_path: Path):
    return {
        table: _rows(db_path, table)
        for table in ("context_rules", "corrections", "audit_log", "review_items")
    }


def _audit_count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]


def _new_service(db_path: Path, initialize_schema: bool = True):
    return CorrectionService(
        CorrectionRepository(db_path, initialize_schema=initialize_schema)
    )


def _database_snapshot(db_path: Path, exclude: set[str] | None = None):
    excluded = exclude or set()
    with sqlite3.connect(db_path) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            if row[0] not in excluded
        ]
        return {
            table: conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
            for table in tables
        }


def _run_state_cli(
    db_path: Path,
    action: str,
    rule_id: int,
    domain: str | None,
    pattern: str,
    config_dir: Path,
    reason: str = REASON,
):
    argv = [
        sys.executable,
        str(CLI_SCRIPT),
        action,
        str(rule_id),
        "--db",
        str(db_path),
    ]
    if domain is not None:
        argv.extend(["--context-rule-domain", domain])
    argv.extend([
        "--context-rule-pattern",
        pattern,
        "--reason",
        reason,
        "--json",
    ])
    env = os.environ.copy()
    env["TRANSCRIPT_FIXER_CONFIG_DIR"] = str(config_dir)
    env["TRANSCRIPT_FIXER_DB_PATH"] = str(config_dir / "decoy.db")
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=20,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"CLI did not emit one JSON result: exit={completed.returncode}, "
            f"stdout={completed.stdout!r}, stderr={completed.stderr!r}"
        ) from exc
    return completed, payload


def _loaded_patterns(db_path: Path) -> set[str]:
    service = _new_service(db_path, initialize_schema=False)
    try:
        return {
            rule["pattern"]
            for rule in service.load_context_rules([
                "project-alpha", "project-beta", "global",
            ])
        }
    finally:
        service.close()


def _add_representation_rules(db_path: Path):
    service = _new_service(db_path)
    ids = {
        "ordinary": service.add_context_rule(
            TARGET_PATTERN, "omega", domain="project-alpha"
        ),
        "literal": service.add_context_rule(
            LITERAL_GLOBAL_PATTERN, "delta", domain="global"
        ),
        "null": service.add_context_rule(
            NULL_GLOBAL_PATTERN, "theta"
        ),
        "control": service.add_context_rule(
            OTHER_PATTERN, "gamma", domain="project-beta"
        ),
    }
    service.add_correction(
        "garbled-token", "fixed-token", domain="project-alpha"
    )
    service.close()
    return ids


@pytest.fixture
def state_case(tmp_path):
    db_path = tmp_path / "state.db"
    service = _new_service(db_path)
    target_id = service.add_context_rule(
        TARGET_PATTERN,
        "omega",
        domain="project-alpha",
        description="synthetic target",
        added_by="test",
    )
    other_id = service.add_context_rule(
        OTHER_PATTERN,
        "delta",
        domain="project-beta",
        description="synthetic control",
        added_by="test",
    )
    service.add_correction(
        "garbled-token",
        "fixed-token",
        domain="project-alpha",
    )
    yield service, db_path, target_id, other_id
    service.close()


def test_disable_enable_reload_and_idempotent_audit(state_case):
    service, db_path, target_id, other_id = state_case
    corrections_before = _rows(db_path, "corrections")
    other_before = [
        row for row in _rows(db_path, "context_rules") if row[0] == other_id
    ]
    rule_count_before = len(_rows(db_path, "context_rules"))
    audit_before = _audit_count(db_path)

    disabled = service.disable_context_rule(
        target_id, "project-alpha", TARGET_PATTERN, REASON, changed_by="test"
    )
    assert disabled == {
        "status": "disabled",
        "rule_id": target_id,
        "domain": "project-alpha",
        "pattern": TARGET_PATTERN,
        "is_active": False,
        "changed": True,
        "audit_written": True,
    }
    assert _audit_count(db_path) == audit_before + 1
    assert _rows(db_path, "corrections") == corrections_before
    assert [
        row for row in _rows(db_path, "context_rules") if row[0] == other_id
    ] == other_before

    reloaded = _new_service(db_path)
    try:
        loaded = reloaded.load_context_rules(["project-alpha", "project-beta"])
        assert OTHER_PATTERN in {rule["pattern"] for rule in loaded}
        assert TARGET_PATTERN not in {rule["pattern"] for rule in loaded}

        audit_before_repeat = _audit_count(db_path)
        already_disabled = reloaded.disable_context_rule(
            target_id, "project-alpha", TARGET_PATTERN, REASON, changed_by="test"
        )
        assert already_disabled["status"] == "already_disabled"
        assert already_disabled["changed"] is False
        assert already_disabled["audit_written"] is False
        assert _audit_count(db_path) == audit_before_repeat

        enabled = reloaded.enable_context_rule(
            target_id,
            "project-alpha",
            TARGET_PATTERN,
            "synthetic restore check",
            changed_by="test",
        )
        assert enabled["status"] == "enabled"
        assert enabled["is_active"] is True
        assert enabled["changed"] is True
        assert enabled["audit_written"] is True
        assert _audit_count(db_path) == audit_before_repeat + 1
        assert TARGET_PATTERN in {
            rule["pattern"]
            for rule in reloaded.load_context_rules(["project-alpha"])
        }

        already_enabled = reloaded.enable_context_rule(
            target_id, "project-alpha", TARGET_PATTERN, REASON, changed_by="test"
        )
        assert already_enabled["status"] == "already_enabled"
        assert already_enabled["changed"] is False
        assert already_enabled["audit_written"] is False
        assert _audit_count(db_path) == audit_before_repeat + 1
    finally:
        reloaded.close()

    assert len(_rows(db_path, "context_rules")) == rule_count_before
    assert _rows(db_path, "corrections") == corrections_before
    assert [
        row for row in _rows(db_path, "context_rules") if row[0] == other_id
    ] == other_before
    with sqlite3.connect(db_path) as conn:
        transitions = conn.execute(
            """
            SELECT action, entity_type, entity_id, details
            FROM audit_log
            WHERE action IN ('disable_context_rule', 'enable_context_rule')
            ORDER BY id
            """
        ).fetchall()
    assert [row[:3] for row in transitions] == [
        ("disable_context_rule", "context_rules", target_id),
        ("enable_context_rule", "context_rules", target_id),
    ]
    disable_details = json.loads(transitions[0][3])
    enable_details = json.loads(transitions[1][3])
    assert disable_details["reason"] == REASON
    assert disable_details["previous_is_active"] is True
    assert disable_details["is_active"] is False
    assert enable_details["reason"] == "synthetic restore check"
    assert enable_details["previous_is_active"] is False
    assert enable_details["is_active"] is True


def test_global_domain_is_explicit_and_checked(state_case):
    service, db_path, _target_id, _other_id = state_case
    global_id = service.add_context_rule(
        r"global(?= cue)", "gamma", description="synthetic global"
    )
    with pytest.raises(ValidationError, match="domain mismatch"):
        service.disable_context_rule(
            global_id, "project-alpha", r"global(?= cue)", REASON
        )
    result = service.disable_context_rule(
        global_id, None, r"global(?= cue)", REASON
    )
    assert result["status"] == "disabled"
    assert result["domain"] is None
    assert global_id in {
        rule["id"] for rule in service.list_context_rules(include_inactive=True)
    }


@pytest.mark.parametrize(
    "overrides, error_match",
    [
        ({"rule_id": 9999}, "does not exist"),
        ({"rule_id": 0}, "positive integer"),
        ({"rule_id": -2}, "positive integer"),
        ({"rule_id": None}, "positive integer"),
        ({"rule_id": True}, "positive integer"),
        ({"pattern": r"alpha(?= wrong)"}, "pattern mismatch"),
        ({"pattern": None}, "must not be empty"),
        ({"pattern": ""}, "must not be empty"),
        ({"pattern": "   "}, "must not be empty"),
        ({"domain": "project-beta"}, "domain mismatch"),
        ({"domain": "bad/domain"}, "invalid characters"),
        ({"reason": None}, "reason must not be empty"),
        ({"reason": ""}, "reason must not be empty"),
        ({"reason": " \t "}, "reason must not be empty"),
    ],
)
def test_invalid_identity_inputs_write_nothing(state_case, overrides, error_match):
    service, db_path, target_id, _other_id = state_case
    arguments = {
        "rule_id": target_id,
        "domain": "project-alpha",
        "pattern": TARGET_PATTERN,
        "reason": REASON,
    }
    arguments.update(overrides)
    before = _snapshot(db_path)
    with pytest.raises(ValidationError, match=error_match):
        service.disable_context_rule(**arguments)
    assert _snapshot(db_path) == before


def test_missing_required_service_argument_writes_nothing(state_case):
    service, db_path, target_id, _other_id = state_case
    before = _snapshot(db_path)
    with pytest.raises(TypeError):
        service.disable_context_rule(
            rule_id=target_id,
            pattern=TARGET_PATTERN,
            reason=REASON,
        )
    assert _snapshot(db_path) == before


@pytest.mark.parametrize("missing", ["domain", "audit_log"])
def test_missing_schema_preflight_is_byte_identical_and_state_has_no_delta(
    tmp_path, missing
):
    db_path = tmp_path / f"missing-{missing}.db"
    setup = _new_service(db_path)
    rule_id = setup.add_context_rule(
        TARGET_PATTERN, "omega", domain="project-alpha"
    )
    setup.close()
    with sqlite3.connect(db_path) as conn:
        if missing == "domain":
            conn.execute("ALTER TABLE context_rules DROP COLUMN domain")
        else:
            conn.execute("DROP TABLE audit_log")

    service = _new_service(db_path, initialize_schema=False)
    before_bytes = db_path.read_bytes()
    before_snapshot = _snapshot(db_path) if missing == "domain" else None
    try:
        with pytest.raises(ValidationError, match="schema is incomplete"):
            service.preflight_context_rule_state(
                rule_id, "project-alpha", TARGET_PATTERN, REASON
            )
        assert db_path.read_bytes() == before_bytes
        with pytest.raises(DatabaseError, match="schema is incomplete"):
            service.disable_context_rule(
                rule_id, "project-alpha", TARGET_PATTERN, REASON
            )
        if before_snapshot is not None:
            assert _snapshot(db_path) == before_snapshot
        else:
            with sqlite3.connect(db_path) as conn:
                assert conn.execute(
                    "SELECT is_active FROM context_rules WHERE id = ?", (rule_id,)
                ).fetchone()[0] == 1
    finally:
        service.close()


def test_audit_insert_failure_rolls_back_state(state_case):
    service, db_path, target_id, _other_id = state_case
    before = _snapshot(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TRIGGER reject_context_state_audit
            BEFORE INSERT ON audit_log
            WHEN NEW.action IN ('disable_context_rule', 'enable_context_rule')
            BEGIN
                SELECT RAISE(ABORT, 'injected audit failure');
            END
            """
        )
    with pytest.raises(DatabaseError, match="injected audit failure"):
        service.disable_context_rule(
            target_id, "project-alpha", TARGET_PATTERN, REASON
        )
    after = _snapshot(db_path)
    assert after["context_rules"] == before["context_rules"]
    assert after["corrections"] == before["corrections"]
    assert after["audit_log"] == before["audit_log"]
    assert after["review_items"] == before["review_items"]


@pytest.mark.parametrize(
    "table,column,index",
    [
        ("context_rules", "replacement", None),
        ("context_rules", "description", None),
        ("context_rules", "priority", "idx_context_rules_priority"),
        ("context_rules", "added_at", None),
        ("context_rules", "added_by", None),
        ("audit_log", "timestamp", "idx_audit_timestamp"),
    ],
)
def test_incomplete_consumer_schema_rejects_without_state_or_audit_write(
    state_case, table, column, index
):
    service, db_path, target_id, _other_id = state_case
    with sqlite3.connect(db_path) as conn:
        if index:
            conn.execute(f"DROP INDEX {index}")
        conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    before = _snapshot(db_path)
    before_bytes = db_path.read_bytes()
    with pytest.raises(ValidationError, match="schema is incomplete"):
        service.preflight_context_rule_state(
            target_id, "project-alpha", TARGET_PATTERN, REASON
        )
    assert db_path.read_bytes() == before_bytes
    with pytest.raises(DatabaseError, match="schema is incomplete"):
        service.disable_context_rule(
            target_id, "project-alpha", TARGET_PATTERN, REASON
        )
    assert _snapshot(db_path) == before


@pytest.mark.parametrize(
    "other_command",
    [
        ["--list-context-rules"],
        ["--add-context-rule", "beta", "delta"],
        ["--init"],
        ["--consolidate-review", "--review-file", "synthetic.md"],
        ["--resolve-review", "0"],
        ["--input", "synthetic.md"],
        ["--enable-context-rule", "1"],
    ],
)
def test_state_command_conflicts_fail_before_any_database_dispatch(
    state_case, tmp_path, monkeypatch, capsys, other_command
):
    from fix_transcription import main

    _service, db_path, target_id, _other_id = state_case
    configured_db = tmp_path / "configured.db"
    configured = _new_service(configured_db)
    configured.close()
    before_target = _snapshot(db_path)
    before_configured = _snapshot(configured_db)
    monkeypatch.setenv("TRANSCRIPT_FIXER_DB_PATH", str(configured_db))
    monkeypatch.setattr(sys, "argv", [
        "fix_transcription.py", "--disable-context-rule", str(target_id),
        "--db", str(db_path), "--context-rule-domain", "project-alpha",
        "--context-rule-pattern", TARGET_PATTERN, "--reason", REASON,
        "--json", *other_command,
    ])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    assert "must be the only command" in capsys.readouterr().err
    assert _snapshot(db_path) == before_target
    assert _snapshot(configured_db) == before_configured


def test_cli_domain_representations_disable_enable_and_reload(tmp_path):
    db_path = tmp_path / "representations.db"
    ids = _add_representation_rules(db_path)
    patterns = {
        "ordinary": TARGET_PATTERN,
        "literal": LITERAL_GLOBAL_PATTERN,
        "null": NULL_GLOBAL_PATTERN,
        "control": OTHER_PATTERN,
    }
    cases = [
        ("ordinary", "project-alpha", "project-alpha"),
        ("literal", "domain:global", "global"),
        ("null", "global", None),
    ]
    before_non_audit = _database_snapshot(db_path, exclude={"audit_log"})
    before_audit_count = _audit_count(db_path)
    expected_loaded = set(patterns.values())
    assert _loaded_patterns(db_path) == expected_loaded

    for action, active in (("--disable-context-rule", False), ("--enable-context-rule", True)):
        for key, cli_domain, stored_domain in cases:
            completed, payload = _run_state_cli(
                db_path,
                action,
                ids[key],
                cli_domain,
                patterns[key],
                tmp_path / "config",
            )
            assert completed.returncode == 0, completed.stderr
            assert completed.stderr == ""
            assert payload == {
                "status": "enabled" if active else "disabled",
                "rule_id": ids[key],
                "domain": stored_domain,
                "pattern": patterns[key],
                "is_active": active,
                "changed": True,
                "audit_written": True,
            }
            with sqlite3.connect(db_path) as conn:
                assert conn.execute(
                    "SELECT domain, is_active FROM context_rules WHERE id = ?",
                    (ids[key],),
                ).fetchone() == (stored_domain, int(active))
            if active:
                expected_loaded.add(patterns[key])
            else:
                expected_loaded.remove(patterns[key])
            assert _loaded_patterns(db_path) == expected_loaded

    assert _database_snapshot(db_path, exclude={"audit_log"}) == before_non_audit
    assert _audit_count(db_path) == before_audit_count + 6
    with sqlite3.connect(db_path) as conn:
        transitions = conn.execute(
            "SELECT action, entity_id FROM audit_log "
            "WHERE action IN ('disable_context_rule', 'enable_context_rule') "
            "ORDER BY id"
        ).fetchall()
    assert transitions == [
        (action, ids[key])
        for action in ("disable_context_rule", "enable_context_rule")
        for key, _cli_domain, _stored_domain in cases
    ]


@pytest.mark.parametrize(
    "case",
    [
        {
            "name": "wrong id",
            "rule_id": 999999,
            "error": "does not exist",
        },
        {
            "name": "wrong pattern",
            "pattern": r"wrong(?= cue)",
            "error": "pattern mismatch",
        },
        {
            "name": "wrong literal domain",
            "domain": "domain:project-alpha",
            "error": "domain mismatch",
        },
        {
            "name": "NULL representation cannot select literal global",
            "domain": "global",
            "error": "domain mismatch",
        },
        {
            "name": "literal representation cannot select SQL NULL",
            "target": "null",
            "domain": "domain:global",
            "error": "domain mismatch",
        },
        {
            "name": "missing domain",
            "domain": None,
            "error": "--context-rule-domain",
        },
        {
            "name": "empty domain",
            "domain": "",
            "error": "expected context rule domain",
        },
        {
            "name": "empty prefixed payload",
            "domain": "domain:",
            "error": "expected context rule domain",
        },
        {
            "name": "blank prefixed payload",
            "domain": "domain:   ",
            "error": "expected context rule domain",
        },
        {
            "name": "invalid prefixed payload",
            "domain": "domain:bad/domain",
            "error": "invalid characters",
        },
        {
            "name": "only one prefix is stripped",
            "domain": "domain:domain:global",
            "error": "invalid characters",
        },
    ],
    ids=lambda case: case["name"],
)
def test_cli_state_rejections_preserve_entire_database(tmp_path, case):
    db_path = tmp_path / "rejections.db"
    ids = _add_representation_rules(db_path)
    patterns = {
        "ordinary": TARGET_PATTERN,
        "literal": LITERAL_GLOBAL_PATTERN,
        "null": NULL_GLOBAL_PATTERN,
        "control": OTHER_PATTERN,
    }
    target = case.get("target", "literal")
    before = _database_snapshot(db_path)
    before_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()

    completed, payload = _run_state_cli(
        db_path,
        "--disable-context-rule",
        case.get("rule_id", ids[target]),
        case.get("domain", "domain:global"),
        case.get("pattern", patterns[target]),
        tmp_path / "config",
    )

    assert completed.returncode == 2
    assert completed.stderr == ""
    assert payload["error"] == "context_rule_state_error"
    assert case["error"] in payload["message"]
    assert "no changes applied" in payload["message"]
    assert _database_snapshot(db_path) == before
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before_hash
    assert _loaded_patterns(db_path) == set(patterns.values())


def test_state_domain_help_distinguishes_null_and_literal_global():
    help_text = create_argument_parser().format_help()
    assert "SQL NULL" in help_text
    assert "domain:global" in help_text


def test_parser_accepts_state_identity_and_db_arguments(tmp_path):
    parser = create_argument_parser()
    args = parser.parse_args([
        "--disable-context-rule",
        "7",
        "--db",
        str(tmp_path / "db with spaces.sqlite"),
        "--context-rule-domain",
        "project-alpha",
        "--context-rule-pattern",
        TARGET_PATTERN,
        "--reason",
        REASON,
        "--json",
    ])
    assert args.disable_context_rule == 7
    assert args.enable_context_rule is None
    assert args.db_path.endswith("db with spaces.sqlite")
    assert args.context_rule_domain == "project-alpha"
    assert args.context_rule_pattern == TARGET_PATTERN
    assert args.reason == REASON
    assert args.json_output is True


def test_cli_missing_reason_fails_before_db_write(state_case, capsys):
    _service, db_path, target_id, _other_id = state_case
    before_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
    parser = create_argument_parser()
    args = parser.parse_args([
        "--disable-context-rule",
        str(target_id),
        "--db",
        str(db_path),
        "--context-rule-domain",
        "project-alpha",
        "--context-rule-pattern",
        TARGET_PATTERN,
        "--json",
    ])
    with pytest.raises(SystemExit) as exit_info:
        cmd_disable_context_rule(args)
    assert exit_info.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "context_rule_state_error"
    assert "--reason" in payload["message"]
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before_hash


def test_existing_context_rule_list_parser_is_unchanged():
    args = create_argument_parser().parse_args(["--list-context-rules", "--all"])
    assert args.list_context_rules is True
    assert args.all is True
    assert args.disable_context_rule is None
    assert args.enable_context_rule is None
