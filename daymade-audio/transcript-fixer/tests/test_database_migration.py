#!/usr/bin/env python3
"""Deterministic regressions for the SQLite migration runner."""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from utils.database_migration import DatabaseMigrationManager, Migration
from utils.migrations import ALL_MIGRATIONS


class DatabaseMigrationManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "migrations.db"

    def test_forward_chain_satisfies_dependencies_applied_in_same_run(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        manager.register_migration(Migration(
            version="1.0",
            name="create demo",
            description="create the base table",
            forward_sql="CREATE TABLE demo (id INTEGER PRIMARY KEY);",
        ))
        manager.register_migration(Migration(
            version="2.0",
            name="add label",
            description="extend the table",
            forward_sql="ALTER TABLE demo ADD COLUMN label TEXT;",
            dependencies=["1.0"],
        ))

        manager.migrate_to_version("2.0")

        self.assertEqual(manager.get_current_version(), "2.0")
        with sqlite3.connect(self.db_path) as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(demo)")]
            history = connection.execute(
                "SELECT version, status FROM schema_migrations ORDER BY id"
            ).fetchall()
        self.assertEqual(columns, ["id", "label"])
        self.assertEqual(history[-2:], [("1.0", "completed"), ("2.0", "completed")])

    def test_matching_existing_simple_column_is_idempotent(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE demo (id INTEGER, label TEXT)")
        manager.register_migration(Migration(
            version="1.0",
            name="existing column",
            description="the exact simple column already exists",
            forward_sql=(
                "-- schema.sql already supplied the compatible column\n"
                "ALTER TABLE demo ADD COLUMN label TEXT;"
            ),
        ))

        manager.migrate_to_version("1.0")

        self.assertEqual(manager.get_current_version(), "1.0")

    def test_incompatible_existing_column_fails_and_records_failure(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE demo (id INTEGER, label INTEGER)")
        manager.register_migration(Migration(
            version="1.0",
            name="requires text",
            description="existing INTEGER is not equivalent to TEXT",
            forward_sql="ALTER TABLE demo ADD COLUMN label TEXT;",
        ))

        with self.assertRaisesRegex(RuntimeError, "duplicate column name"):
            manager.migrate_to_version("1.0")

        with sqlite3.connect(self.db_path) as connection:
            column_type = connection.execute(
                "SELECT type FROM pragma_table_info('demo') WHERE name = 'label'"
            ).fetchone()[0]
            history = connection.execute(
                "SELECT status FROM schema_migrations WHERE version = '1.0'"
            ).fetchone()
        self.assertEqual(column_type, "INTEGER")
        self.assertEqual(history, ("failed",))

    def test_collated_existing_column_is_not_equivalent_to_plain_text(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "CREATE TABLE context_rules (id INTEGER, domain TEXT COLLATE NOCASE)"
            )
        manager.register_migration(Migration(
            version="1.0",
            name="requires plain text",
            description="collation changes equality semantics",
            forward_sql="ALTER TABLE context_rules ADD COLUMN domain TEXT;",
        ))

        with self.assertRaisesRegex(RuntimeError, "duplicate column name"):
            manager.migrate_to_version("1.0")

        with sqlite3.connect(self.db_path) as connection:
            schema = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'context_rules'"
            ).fetchone()[0]
            history = connection.execute(
                "SELECT status FROM schema_migrations WHERE version = '1.0'"
            ).fetchone()
        self.assertIn("domain TEXT COLLATE NOCASE", schema)
        self.assertEqual(history, ("failed",))

    def test_table_constraint_on_existing_column_fails_closed(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE context_rules (
                    id INTEGER,
                    domain TEXT,
                    UNIQUE(domain)
                )
                """
            )
        manager.register_migration(Migration(
            version="1.0",
            name="requires unconstrained text",
            description="table constraints are part of column semantics",
            forward_sql="ALTER TABLE context_rules ADD COLUMN domain TEXT;",
        ))

        with self.assertRaisesRegex(RuntimeError, "duplicate column name"):
            manager.migrate_to_version("1.0")

        with sqlite3.connect(self.db_path) as connection:
            history = connection.execute(
                "SELECT status FROM schema_migrations WHERE version = '1.0'"
            ).fetchone()
        self.assertEqual(history, ("failed",))

    def test_existing_table_is_not_assumed_compatible(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE demo (id TEXT)")
        manager.register_migration(Migration(
            version="1.0",
            name="requires another table shape",
            description="same name is not schema equivalence",
            forward_sql="CREATE TABLE demo (id INTEGER);",
        ))

        with self.assertRaisesRegex(RuntimeError, "already exists"):
            manager.migrate_to_version("1.0")

        with sqlite3.connect(self.db_path) as connection:
            history = connection.execute(
                "SELECT status FROM schema_migrations WHERE version = '1.0'"
            ).fetchone()
        self.assertEqual(history, ("failed",))

    def test_unrelated_operational_error_persists_failed_history(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        manager.register_migration(Migration(
            version="1.0",
            name="missing table",
            description="must fail and remain auditable",
            forward_sql="SELECT * FROM definitely_missing;",
        ))

        with self.assertRaisesRegex(RuntimeError, "definitely_missing"):
            manager.migrate_to_version("1.0")

        with sqlite3.connect(self.db_path) as connection:
            history = connection.execute(
                """
                SELECT status, direction, error_message
                FROM schema_migrations WHERE version = '1.0'
                """
            ).fetchone()
        self.assertEqual(history[0:2], ("failed", "forward"))
        self.assertIn("definitely_missing", history[2])

    def test_failed_rollback_preserves_applied_version_and_records_attempt(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        manager.register_migration(Migration(
            version="1.0",
            name="rollback failure",
            description="failed rollback must not falsify current state",
            forward_sql="CREATE TABLE demo (id INTEGER);",
            backward_sql="DROP TABLE demo; SELECT * FROM definitely_missing;",
        ))
        manager.migrate_to_version("1.0")

        with self.assertRaisesRegex(RuntimeError, "definitely_missing"):
            manager.rollback_migration("1.0")

        self.assertEqual(manager.get_current_version(), "1.0")
        with sqlite3.connect(self.db_path) as connection:
            demo_exists = connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'demo'"
            ).fetchone()[0]
            record = connection.execute(
                """
                SELECT status, direction, error_message, details
                FROM schema_migrations WHERE version = '1.0'
                """
            ).fetchone()
        details = json.loads(record[3])
        self.assertEqual(demo_exists, 1)
        self.assertEqual(record[0:2], ("completed", "forward"))
        self.assertIn("Backward migration attempt failed", record[2])
        self.assertEqual(
            details["last_failed_attempt"]["direction"],
            "backward",
        )
        self.assertIn(
            "definitely_missing",
            details["last_failed_attempt"]["error_message"],
        )

    def test_successful_rollback_marks_version_backward(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        manager.register_migration(Migration(
            version="1.0",
            name="rollback success",
            description="successful rollback leaves the previous version current",
            forward_sql="CREATE TABLE demo (id INTEGER);",
            backward_sql="DROP TABLE demo;",
        ))
        manager.migrate_to_version("1.0")

        manager.rollback_migration("1.0")

        self.assertEqual(manager.get_current_version(), "0.0")
        with sqlite3.connect(self.db_path) as connection:
            demo_exists = connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'demo'"
            ).fetchone()[0]
            record = connection.execute(
                "SELECT status, direction FROM schema_migrations WHERE version = '1.0'"
            ).fetchone()
        self.assertEqual(demo_exists, 0)
        self.assertEqual(record, ("completed", "backward"))

    def test_lone_zero_seed_upgrades_from_legacy_schema_version(self) -> None:
        first_manager = DatabaseMigrationManager(self.db_path)
        self.assertEqual(first_manager.get_current_version(), "0.0")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE corrections (id INTEGER)")
            connection.execute("CREATE TABLE correction_history (id INTEGER)")
            connection.execute("CREATE TABLE system_config (key TEXT PRIMARY KEY, value TEXT)")
            connection.execute(
                "INSERT INTO system_config (key, value) VALUES ('schema_version', '1.0')"
            )

        upgraded_manager = DatabaseMigrationManager(self.db_path)

        self.assertEqual(upgraded_manager.get_current_version(), "1.0")
        with sqlite3.connect(self.db_path) as connection:
            history = connection.execute(
                "SELECT version, name, checksum FROM schema_migrations"
            ).fetchall()
        self.assertEqual(
            history,
            [("1.0", "Imported legacy schema state", "legacy-schema-version")],
        )

    def test_hand_edited_zero_seed_is_not_promoted(self) -> None:
        first_manager = DatabaseMigrationManager(self.db_path)
        self.assertEqual(first_manager.get_current_version(), "0.0")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE corrections (id INTEGER)")
            connection.execute("CREATE TABLE correction_history (id INTEGER)")
            connection.execute("CREATE TABLE system_config (key TEXT PRIMARY KEY, value TEXT)")
            connection.execute(
                "INSERT INTO system_config (key, value) VALUES ('schema_version', '1.0')"
            )
            connection.execute(
                "UPDATE schema_migrations SET checksum = 'hand-edited'"
            )

        manager = DatabaseMigrationManager(self.db_path)

        self.assertEqual(manager.get_current_version(), "0.0")
        with sqlite3.connect(self.db_path) as connection:
            record = connection.execute(
                "SELECT version, name, checksum FROM schema_migrations"
            ).fetchone()
        self.assertEqual(record, ("0.0", "Initial empty schema", "hand-edited"))

    def test_hand_edited_sentinel_version_does_not_skip_migrations(self) -> None:
        DatabaseMigrationManager(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE corrections (id INTEGER)")
            connection.execute("CREATE TABLE correction_history (id INTEGER)")
            connection.execute("CREATE TABLE system_config (key TEXT PRIMARY KEY, value TEXT)")
            connection.execute(
                "INSERT INTO system_config (key, value) VALUES ('schema_version', '1.0')"
            )
            connection.execute(
                "UPDATE schema_migrations SET version = '2.0'"
            )

        manager = DatabaseMigrationManager(self.db_path)
        manager.register_migration(Migration(
            version="1.0",
            name="known migration",
            description="must remain pending after sentinel tampering",
            forward_sql="CREATE TABLE required_by_migration (id INTEGER);",
        ))

        self.assertEqual(manager.get_current_version(), "0.0")
        self.assertEqual(
            [migration.version for migration in manager.get_pending_migrations()],
            ["1.0"],
        )

    def test_modified_imported_baseline_is_not_current(self) -> None:
        DatabaseMigrationManager(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE corrections (id INTEGER)")
            connection.execute("CREATE TABLE correction_history (id INTEGER)")
            connection.execute("CREATE TABLE system_config (key TEXT PRIMARY KEY, value TEXT)")
            connection.execute(
                "INSERT INTO system_config (key, value) VALUES ('schema_version', '1.0')"
            )
        manager = DatabaseMigrationManager(self.db_path)
        self.assertEqual(manager.get_current_version(), "1.0")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE schema_migrations SET version = '2.0'"
            )

        reloaded = DatabaseMigrationManager(self.db_path)

        self.assertEqual(reloaded.get_current_version(), "0.0")

    def test_incomplete_system_config_keeps_zero_seed(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE system_config (key TEXT PRIMARY KEY)")

        manager = DatabaseMigrationManager(self.db_path)

        self.assertEqual(manager.get_current_version(), "0.0")

    def test_duplicate_legacy_version_rows_keep_zero_seed(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE corrections (id INTEGER)")
            connection.execute("CREATE TABLE correction_history (id INTEGER)")
            connection.execute("CREATE TABLE system_config (key TEXT, value TEXT)")
            connection.execute(
                "INSERT INTO system_config (key, value) VALUES ('schema_version', '1.0')"
            )
            connection.execute(
                "INSERT INTO system_config (key, value) VALUES ('schema_version', '2.0')"
            )

        manager = DatabaseMigrationManager(self.db_path)

        self.assertEqual(manager.get_current_version(), "0.0")

    def test_unknown_legacy_version_does_not_skip_migrations(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE corrections (id INTEGER)")
            connection.execute("CREATE TABLE correction_history (id INTEGER)")
            connection.execute("CREATE TABLE system_config (key TEXT PRIMARY KEY, value TEXT)")
            connection.execute(
                "INSERT INTO system_config (key, value) VALUES ('schema_version', '99.0')"
            )

        manager = DatabaseMigrationManager(self.db_path)

        self.assertEqual(manager.get_current_version(), "0.0")

    def test_schema_built_database_migrates_from_legacy_2_0_to_2_4(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1] / "scripts" / "core" / "schema.sql"
        )
        with sqlite3.connect(self.db_path) as connection:
            connection.executescript(schema_path.read_text(encoding="utf-8"))
            connection.execute(
                """
                INSERT INTO system_config (key, value, value_type, description)
                VALUES ('schema_version', '2.0', 'string', 'Database schema version')
                """
            )

        # Reproduce the sentinel written by historical migration runners.
        DatabaseMigrationManager(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                UPDATE schema_migrations
                SET version = '0.0', name = 'Initial empty schema', checksum = 'empty'
                """
            )

        manager = DatabaseMigrationManager(self.db_path)
        for migration in ALL_MIGRATIONS:
            manager.register_migration(migration)
        manager.migrate_to_version("2.4")

        self.assertEqual(manager.get_current_version(), "2.4")
        with sqlite3.connect(self.db_path) as connection:
            domain = connection.execute(
                "SELECT type FROM pragma_table_info('context_rules') WHERE name = 'domain'"
            ).fetchone()
            retention = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name = 'retention_policies'
                """
            ).fetchone()
            domain_index = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'index' AND name = 'idx_context_rules_domain'
                """
            ).fetchone()
        self.assertEqual(domain, ("TEXT",))
        self.assertEqual(retention, ("retention_policies",))
        self.assertEqual(domain_index, ("idx_context_rules_domain",))

    def test_current_version_uses_insertion_order_for_timestamp_ties(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE schema_migrations SET executed_at = '2026-08-29 00:00:00'"
            )
            for version in ("1.0", "2.0"):
                connection.execute(
                    """
                    INSERT INTO schema_migrations
                    (version, name, status, direction, execution_time_ms, checksum, executed_at)
                    VALUES (?, ?, 'completed', 'forward', 0, ?, '2026-08-29 00:00:00')
                    """,
                    (version, version, version),
                )

        self.assertEqual(manager.get_current_version(), "2.0")


if __name__ == "__main__":
    unittest.main()
