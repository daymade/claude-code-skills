#!/usr/bin/env python3
"""Deterministic regressions for the SQLite migration runner."""

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_migration import DatabaseMigrationManager, Migration


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

    def test_existing_table_and_column_are_idempotent(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE demo (id INTEGER, label TEXT)")
        manager.register_migration(Migration(
            version="1.0",
            name="existing schema",
            description="objects may already come from schema.sql",
            forward_sql=(
                "CREATE TABLE demo (id INTEGER);"
                "ALTER TABLE demo ADD COLUMN label TEXT;"
            ),
        ))

        manager.migrate_to_version("1.0")

        self.assertEqual(manager.get_current_version(), "1.0")

    def test_unrelated_operational_error_is_not_swallowed(self) -> None:
        manager = DatabaseMigrationManager(self.db_path)

        with self.assertRaisesRegex(sqlite3.OperationalError, "definitely_missing"):
            with manager._transaction() as cursor:
                manager._execute_migration_sql(
                    cursor,
                    "SELECT * FROM definitely_missing;",
                )

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
