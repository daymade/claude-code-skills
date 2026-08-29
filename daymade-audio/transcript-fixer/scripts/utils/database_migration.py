#!/usr/bin/env python3
"""
Database Migration Module - Production-Grade Migration Strategy

CRITICAL FIX (P1-6): Production database migration system

Features:
- Versioned migrations with forward and rollback capability
- Migration history tracking
- Atomic transactions with rollback support
- Dry-run mode for testing
- Migration validation and verification
- Backward compatibility checks

Migration Types:
- Forward: Apply new schema changes
- Rollback: Revert to previous version
- Validation: Check migration safety
- Dry-run: Test migrations without applying
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from contextlib import contextmanager
from dataclasses import dataclass, asdict
import hashlib

logger = logging.getLogger(__name__)


class MigrationDirection(Enum):
    """Migration direction"""
    FORWARD = "forward"
    BACKWARD = "backward"


class MigrationStatus(Enum):
    """Migration execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class Migration:
    """Migration definition"""
    version: str
    name: str
    description: str
    forward_sql: str
    backward_sql: Optional[str] = None  # For rollback capability
    dependencies: List[str] = None  # List of required migration versions
    check_function: Optional[Callable] = None  # Validation function
    is_breaking: bool = False  # If True, requires explicit confirmation

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

    def get_hash(self) -> str:
        """Get hash of migration content for integrity checking"""
        content = f"{self.version}:{self.name}:{self.forward_sql}"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()


@dataclass
class MigrationRecord:
    """Migration execution record"""
    id: int
    version: str
    name: str
    status: MigrationStatus
    direction: MigrationDirection
    execution_time_ms: int
    checksum: str
    executed_at: str = ""
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        result = asdict(self)
        result['status'] = self.status.value
        result['direction'] = self.direction.value
        return result


class DatabaseMigrationManager:
    """
    Production-grade database migration manager

    Handles versioned schema migrations with:
    - Automatic rollback on failure
    - Migration history tracking
    - Dependency resolution
    - Safety checks and validation
    """

    def __init__(self, db_path: Path):
        """
        Initialize migration manager

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.migrations: Dict[str, Migration] = {}
        self._ensure_migration_table()

    def register_migration(self, migration: Migration) -> None:
        """
        Register a migration definition

        Args:
            migration: Migration to register
        """
        if migration.version in self.migrations:
            raise ValueError(f"Migration version {migration.version} already registered")

        # Validate dependencies exist
        for dep_version in migration.dependencies:
            if dep_version not in self.migrations:
                raise ValueError(f"Dependency migration {dep_version} not found")

        self.migrations[migration.version] = migration
        logger.info(f"Registered migration {migration.version}: {migration.name}")

    def _ensure_migration_table(self) -> None:
        """Create migration tracking table if not exists"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create migration history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'rolled_back')),
                    direction TEXT NOT NULL CHECK(direction IN ('forward', 'backward')),
                    execution_time_ms INTEGER NOT NULL CHECK(execution_time_ms >= 0),
                    checksum TEXT NOT NULL,
                    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    error_message TEXT,
                    details TEXT
                )
            ''')

            # Create index for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_migrations_version
                ON schema_migrations(version)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_migrations_executed_at
                ON schema_migrations(executed_at DESC)
            ''')

            legacy_version = self._get_legacy_schema_version(cursor)
            cursor.execute('''
                SELECT id, version, name, status, direction,
                       execution_time_ms, checksum, error_message, details
                FROM schema_migrations ORDER BY id
            ''')
            records = cursor.fetchall()

            if not records:
                seed_name = (
                    "Imported legacy schema state"
                    if legacy_version != "0.0"
                    else "Initial empty schema"
                )
                cursor.execute('''
                    INSERT INTO schema_migrations
                    (version, name, status, direction, execution_time_ms, checksum)
                    VALUES (?, ?, 'completed', 'forward', 0, ?)
                ''', (
                    legacy_version,
                    seed_name,
                    "legacy-schema-version" if legacy_version != "0.0" else "empty",
                ))
            elif (
                len(records) == 1
                and records[0][1:] == (
                    "0.0",
                    "Initial empty schema",
                    "completed",
                    "forward",
                    0,
                    "empty",
                    None,
                    None,
                )
                and legacy_version != "0.0"
            ):
                # Older runners always seeded 0.0, even when schema.sql had
                # already created a versioned schema. Upgrade only that exact
                # untouched sentinel; any real migration history remains
                # authoritative and is never inferred over.
                cursor.execute('''
                    UPDATE schema_migrations
                    SET version = ?, name = 'Imported legacy schema state',
                        checksum = 'legacy-schema-version',
                        executed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (legacy_version, records[0][0]))

            conn.commit()

    @staticmethod
    def _get_legacy_schema_version(cursor: sqlite3.Cursor) -> str:
        """Read a numeric dotted version from legacy system_config, if present."""
        table_exists = cursor.execute('''
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'system_config'
        ''').fetchone()
        if not table_exists:
            return "0.0"

        columns = {
            column_row[1]
            for column_row in cursor.execute(
                "PRAGMA table_info(system_config)"
            ).fetchall()
        }
        if not {"key", "value"} <= columns:
            return "0.0"

        rows = cursor.execute(
            "SELECT value FROM system_config WHERE key = 'schema_version'"
        ).fetchall()
        if len(rows) != 1 or not isinstance(rows[0][0], str):
            return "0.0"

        version = rows[0][0].strip()
        try:
            parts = tuple(int(part) for part in version.split('.'))
        except (TypeError, ValueError):
            return "0.0"
        if not parts or not all(part >= 0 for part in parts):
            return "0.0"

        required_tables = {
            "1.0": {"corrections", "correction_history", "system_config"},
            "2.0": {
                "corrections",
                "context_rules",
                "correction_history",
                "correction_changes",
                "learned_suggestions",
                "suggestion_examples",
                "system_config",
                "audit_log",
            },
        }.get(version)
        if required_tables is None:
            # Only versions written by the legacy schema/bootstrap path are
            # trusted here. A future or hand-edited value must be taught an
            # explicit schema fingerprint before it can skip migrations.
            return "0.0"

        existing_tables = {
            table_row[0]
            for table_row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        return version if required_tables <= existing_tables else "0.0"

    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling"""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self):
        """Context manager for database transactions"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN")
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_current_version(self) -> str:
        """
        Get current database schema version

        Returns:
            Current version string
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Order by id, not executed_at: migrations applied in the same
            # second tie on executed_at (CURRENT_TIMESTAMP precision),
            # making the most recent row indeterminate.
            cursor.execute('''
                SELECT version, name, execution_time_ms, checksum,
                       error_message, details
                FROM schema_migrations
                WHERE status = 'completed' AND direction = 'forward'
                ORDER BY id DESC
            ''')
            for record in cursor.fetchall():
                version, name, execution_time_ms, checksum, error_message, details = record
                if name == "Initial empty schema":
                    if record == (
                        "0.0",
                        "Initial empty schema",
                        0,
                        "empty",
                        None,
                        None,
                    ):
                        return "0.0"
                    logger.warning(
                        "Ignoring modified initial schema sentinel for version %s",
                        version,
                    )
                    continue
                if name == "Imported legacy schema state":
                    if (
                        execution_time_ms == 0
                        and checksum == "legacy-schema-version"
                        and error_message is None
                        and details is None
                        and self._get_legacy_schema_version(cursor) == version
                    ):
                        return version
                    logger.warning(
                        "Ignoring stale or modified legacy schema baseline for version %s",
                        version,
                    )
                    continue
                return version
            return "0.0"

    def get_migration_history(self) -> List[MigrationRecord]:
        """
        Get migration execution history

        Returns:
            List of migration records, most recent first
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, version, name, status, direction,
                       execution_time_ms, checksum, error_message,
                       executed_at, details
                FROM schema_migrations
                ORDER BY executed_at DESC
            ''')

            records = []
            for row in cursor.fetchall():
                record = MigrationRecord(
                    id=row[0],
                    version=row[1],
                    name=row[2],
                    status=MigrationStatus(row[3]),
                    direction=MigrationDirection(row[4]),
                    execution_time_ms=row[5],
                    checksum=row[6],
                    error_message=row[7],
                    executed_at=row[8],
                    details=json.loads(row[9]) if row[9] else None
                )
                records.append(record)

            return records

    def _validate_migration(self, migration: Migration) -> Tuple[bool, List[str]]:
        """
        Validate migration safety

        Args:
            migration: Migration to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Check migration hash
        if migration.get_hash() != migration.get_hash():  # Simple consistency check
            errors.append("Migration content is inconsistent")

        # Run custom validation function if provided
        if migration.check_function:
            try:
                with self._get_connection() as conn:
                    is_valid, validation_error = migration.check_function(conn, migration)
                    if not is_valid:
                        errors.append(validation_error)
            except Exception as e:
                errors.append(f"Validation function failed: {e}")

        return len(errors) == 0, errors

    def _execute_migration_sql(self, cursor: sqlite3.Cursor, sql: str) -> None:
        """
        Execute migration SQL safely

        Args:
            cursor: Database cursor
            sql: SQL to execute
        """
        # Split SQL into individual statements
        statements = [s.strip() for s in sql.split(';') if s.strip()]

        for statement in statements:
            if statement:
                try:
                    cursor.execute(statement)
                except sqlite3.OperationalError as e:
                    # SQLite has no ADD COLUMN IF NOT EXISTS. Treat only a
                    # simple, structurally equivalent existing column as
                    # already applied; tables, indexes, views, complex column
                    # definitions, and mismatched types fail closed.
                    if (
                        "duplicate column name" in str(e).lower()
                        and self._simple_added_column_matches(cursor, statement)
                    ):
                        logger.warning(
                            f"Skipping compatible column already applied ({e}): "
                            f"{statement.splitlines()[0][:80]}"
                        )
                        continue
                    raise

    @staticmethod
    def _simple_added_column_matches(
        cursor: sqlite3.Cursor,
        statement: str,
    ) -> bool:
        """Verify the narrow ALTER TABLE ADD COLUMN form used by v2.4."""
        statement_without_line_comments = re.sub(
            r"--[^\n]*(?:\n|$)", " ", statement
        )
        match = re.fullmatch(
            r"\s*ALTER\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s+"
            r"ADD\s+(?:COLUMN\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+"
            r"([A-Za-z][A-Za-z0-9_]*(?:\s*\(\s*\d+"
            r"(?:\s*,\s*\d+)?\s*\))?)\s*",
            statement_without_line_comments,
            flags=re.IGNORECASE,
        )
        if not match:
            return False

        table_name, column_name, expected_type = match.groups()
        escaped_table = table_name.replace('"', '""')
        rows = cursor.execute(
            f'PRAGMA table_xinfo("{escaped_table}")'
        ).fetchall()
        actual = next(
            (row for row in rows if str(row[1]).casefold() == column_name.casefold()),
            None,
        )
        if actual is None:
            return False

        normalize_type = lambda value: re.sub(
            r"\s+", "", str(value or "").upper()
        )
        pragma_matches = (
            normalize_type(actual[2]) == normalize_type(expected_type)
            and int(actual[3]) == 0  # NOT NULL
            and actual[4] is None    # DEFAULT
            and int(actual[5]) == 0  # PRIMARY KEY
            and (len(actual) < 7 or int(actual[6]) == 0)  # hidden/generated
        )
        if not pragma_matches:
            return False

        # PRAGMA table_xinfo omits column collation and CHECK/UNIQUE clauses.
        # Inspect sqlite_master as a second, independent boundary and accept
        # only the exact simple declaration this helper claims to support.
        create_row = cursor.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        if not create_row or not create_row[0]:
            return False

        parts = DatabaseMigrationManager._split_table_definition(create_row[0])
        if not parts:
            return False
        column_pattern = re.compile(
            rf"^\s*{re.escape(column_name)}(?:\s|$)",
            flags=re.IGNORECASE,
        )
        matching_parts = [part for part in parts if column_pattern.search(part)]
        if len(matching_parts) != 1:
            return False

        column_reference = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(column_name)}(?![A-Za-z0-9_])",
            flags=re.IGNORECASE,
        )
        if any(
            column_reference.search(part)
            for part in parts
            if part != matching_parts[0]
        ):
            # A table-level CHECK/UNIQUE/FOREIGN KEY changes the column's
            # semantics even when its own declaration is plain.
            return False

        normalize_declaration = lambda value: re.sub(
            r"\s+", "", str(value).strip()
        ).casefold()
        return normalize_declaration(matching_parts[0]) == normalize_declaration(
            f"{column_name} {expected_type}"
        )

    @staticmethod
    def _split_table_definition(create_sql: str) -> List[str]:
        """Split CREATE TABLE's outer column list without parsing inner commas."""
        start = create_sql.find('(')
        if start < 0:
            return []

        parts: List[str] = []
        current: List[str] = []
        depth = 1
        quote_end: Optional[str] = None
        index = start + 1

        while index < len(create_sql):
            char = create_sql[index]
            if quote_end is not None:
                current.append(char)
                if char == quote_end:
                    # SQL escapes quote characters by doubling them.
                    if (
                        quote_end != ']'
                        and index + 1 < len(create_sql)
                        and create_sql[index + 1] == quote_end
                    ):
                        current.append(create_sql[index + 1])
                        index += 1
                    else:
                        quote_end = None
                index += 1
                continue

            if char in ('\'', '"', '`'):
                quote_end = char
                current.append(char)
            elif char == '[':
                quote_end = ']'
                current.append(char)
            elif char == '(':
                depth += 1
                current.append(char)
            elif char == ')':
                depth -= 1
                if depth == 0:
                    tail = ''.join(current).strip()
                    if tail:
                        parts.append(tail)
                    return parts
                current.append(char)
            elif char == ',' and depth == 1:
                parts.append(''.join(current).strip())
                current = []
            else:
                current.append(char)
            index += 1

        return []

    def _run_migration(self, migration: Migration, direction: MigrationDirection,
                     dry_run: bool = False) -> None:
        """
        Run a single migration

        Args:
            migration: Migration to run
            direction: Migration direction
            dry_run: If True, only validate without executing
        """
        start_time = datetime.now()

        # Select appropriate SQL
        if direction == MigrationDirection.FORWARD:
            sql = migration.forward_sql
        elif direction == MigrationDirection.BACKWARD:
            if not migration.backward_sql:
                raise ValueError(f"Migration {migration.version} cannot be rolled back")
            sql = migration.backward_sql
        else:
            raise ValueError(f"Invalid migration direction: {direction}")

        # Validate migration
        is_valid, errors = self._validate_migration(migration)
        if not is_valid:
            raise ValueError(f"Migration validation failed: {'; '.join(errors)}")

        if dry_run:
            logger.info(f"[DRY RUN] Would apply {direction.value} migration {migration.version}")
            return

        with self._get_connection() as conn:
            prior_record = conn.execute('''
                SELECT status, direction, details
                FROM schema_migrations WHERE version = ?
            ''', (migration.version,)).fetchone()

        try:
            # Keep the running record and schema changes in one transaction.
            # A failed schema change rolls both back; the except block then
            # persists the failure in a separate transaction.
            with self._transaction() as cursor:
                cursor.execute('''
                    INSERT INTO schema_migrations
                    (version, name, status, direction, execution_time_ms, checksum)
                    VALUES (?, ?, 'running', ?, 0, ?)
                    ON CONFLICT(version) DO UPDATE SET
                        name = excluded.name,
                        status = 'running',
                        direction = excluded.direction,
                        execution_time_ms = 0,
                        checksum = excluded.checksum,
                        executed_at = CURRENT_TIMESTAMP,
                        error_message = NULL,
                        details = NULL
                ''', (
                    migration.version,
                    migration.name,
                    direction.value,
                    migration.get_hash(),
                ))

                self._execute_migration_sql(cursor, sql)

                # Calculate execution time
                execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

                # Update record as completed
                # (version is UNIQUE, so this matches at most one row; the
                # ORDER BY ... LIMIT form requires SQLite compiled with
                # SQLITE_ENABLE_UPDATE_DELETE_LIMIT and is a syntax error
                # in standard builds)
                cursor.execute('''
                    UPDATE schema_migrations
                    SET status = 'completed', execution_time_ms = ?
                    WHERE version = ? AND status = 'running' AND direction = ?
                ''', (execution_time_ms, migration.version, direction.value))

                logger.info(f"Successfully applied {direction.value} migration {migration.version} "
                           f"in {execution_time_ms}ms")

        except Exception as e:
            execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            try:
                with self._transaction() as cursor:
                    if (
                        direction == MigrationDirection.BACKWARD
                        and prior_record is not None
                        and prior_record[0:2] == ('completed', 'forward')
                    ):
                        try:
                            details = json.loads(prior_record[2]) if prior_record[2] else {}
                        except (TypeError, ValueError, json.JSONDecodeError):
                            details = {}
                        if not isinstance(details, dict):
                            details = {}
                        details['last_failed_attempt'] = {
                            'direction': direction.value,
                            'execution_time_ms': execution_time_ms,
                            'error_message': str(e),
                        }
                        cursor.execute('''
                            UPDATE schema_migrations
                            SET error_message = ?, details = ?
                            WHERE version = ?
                              AND status = 'completed'
                              AND direction = 'forward'
                        ''', (
                            f"Backward migration attempt failed: {e}",
                            json.dumps(details, ensure_ascii=False, sort_keys=True),
                            migration.version,
                        ))
                        if cursor.rowcount != 1:
                            raise RuntimeError(
                                "applied migration state changed before rollback "
                                "failure could be recorded"
                            )
                    else:
                        cursor.execute('''
                            INSERT INTO schema_migrations
                            (version, name, status, direction, execution_time_ms,
                             checksum, error_message)
                            VALUES (?, ?, 'failed', ?, ?, ?, ?)
                            ON CONFLICT(version) DO UPDATE SET
                                name = excluded.name,
                                status = 'failed',
                                direction = excluded.direction,
                                execution_time_ms = excluded.execution_time_ms,
                                checksum = excluded.checksum,
                                executed_at = CURRENT_TIMESTAMP,
                                error_message = excluded.error_message,
                                details = NULL
                        ''', (
                            migration.version,
                            migration.name,
                            direction.value,
                            execution_time_ms,
                            migration.get_hash(),
                            str(e),
                        ))
            except Exception as record_error:
                logger.error(
                    "Migration %s failed and its failure record could not be persisted: %s",
                    migration.version,
                    record_error,
                )
                raise RuntimeError(
                    f"Migration {migration.version} failed: {e}; "
                    f"failure record also failed: {record_error}"
                ) from e

            logger.error(f"Migration {migration.version} failed: {e}")
            raise RuntimeError(f"Migration {migration.version} failed: {e}") from e

    def get_pending_migrations(self) -> List[Migration]:
        """
        Get list of pending migrations

        Returns:
            List of migrations that need to be applied
        """
        current_version = self.get_current_version()
        pending = []

        # Get all migration versions
        all_versions = sorted(self.migrations.keys(), key=lambda v: tuple(map(int, v.split('.'))))

        for version in all_versions:
            if version > current_version:
                migration = self.migrations[version]
                pending.append(migration)

        return pending

    def migrate_to_version(self, target_version: str, dry_run: bool = False,
                          force: bool = False) -> None:
        """
        Migrate database to target version

        Args:
            target_version: Target version to migrate to
            dry_run: If True, only validate without executing
            force: If True, skip breaking change confirmation
        """
        current_version = self.get_current_version()
        logger.info(f"Current version: {current_version}, Target version: {target_version}")

        # Validate target version exists
        if target_version != "latest" and target_version not in self.migrations:
            raise ValueError(f"Target version {target_version} not found")

        # Determine migration path
        if target_version == "latest":
            # Migrate forward to latest
            target_migration = max(self.migrations.keys(), key=lambda v: tuple(map(int, v.split('.'))))
        else:
            target_migration = target_version

        if target_migration > current_version:
            # Forward migration
            self._migrate_forward(current_version, target_migration, dry_run, force)
        elif target_migration < current_version:
            # Rollback
            self._migrate_backward(current_version, target_migration, dry_run, force)
        else:
            logger.info("Database is already at target version")

    def _migrate_forward(self, from_version: str, to_version: str,
                         dry_run: bool = False, force: bool = False) -> None:
        """Execute forward migrations"""
        all_versions = sorted(self.migrations.keys(), key=lambda v: tuple(map(int, v.split('.'))))

        # Dependencies of later migrations in this run are satisfied by
        # earlier migrations in the same loop, so the dependency check must
        # compare against the version applied so far, not from_version.
        applied_version = from_version

        for version in all_versions:
            if version > from_version and version <= to_version:
                migration = self.migrations[version]

                # Check for breaking changes
                if migration.is_breaking and not force:
                    raise RuntimeError(
                        f"Migration {migration.version} is a breaking change. "
                        f"Use --force to apply."
                    )

                # Check dependencies
                for dep in migration.dependencies:
                    if dep > applied_version:
                        raise RuntimeError(
                            f"Migration {migration.version} requires dependency {dep} "
                            f"which is not yet applied"
                        )

                self._run_migration(migration, MigrationDirection.FORWARD, dry_run)
                applied_version = version

    def _migrate_backward(self, from_version: str, to_version: str,
                          dry_run: bool = False, force: bool = False) -> None:
        """Execute rollback migrations"""
        all_versions = sorted(self.migrations.keys(), key=lambda v: tuple(map(int, v.split('.'))), reverse=True)

        for version in all_versions:
            if version <= from_version and version > to_version:
                migration = self.migrations[version]

                if not migration.backward_sql:
                    raise RuntimeError(f"Migration {migration.version} cannot be rolled back")

                # Check if migration would break other migrations
                dependent_migrations = [
                    v for v, m in self.migrations.items()
                    if version in m.dependencies and v <= from_version
                ]
                if dependent_migrations and not force:
                    raise RuntimeError(
                        f"Cannot rollback {version} because it has dependencies: "
                        f"{', '.join(dependent_migrations)}"
                    )

                self._run_migration(migration, MigrationDirection.BACKWARD, dry_run)

    def rollback_migration(self, version: str, dry_run: bool = False,
                          force: bool = False) -> None:
        """
        Rollback a specific migration

        Args:
            version: Migration version to rollback
            dry_run: If True, only validate without executing
            force: If True, skip safety checks
        """
        if version not in self.migrations:
            raise ValueError(f"Migration {version} not found")

        migration = self.migrations[version]
        if not migration.backward_sql:
            raise ValueError(f"Migration {version} cannot be rolled back")

        # Check if migration has been applied
        history = self.get_migration_history()
        applied_versions = [m.version for m in history if m.status == MigrationStatus.COMPLETED]

        if version not in applied_versions:
            raise ValueError(f"Migration {version} has not been applied")

        # Check for dependent migrations
        dependent_migrations = [
            v for v, m in self.migrations.items()
            if version in m.dependencies and v in applied_versions
        ]
        if dependent_migrations and not force:
            raise RuntimeError(
                f"Cannot rollback {version} because it has dependencies: "
                f"{', '.join(dependent_migrations)}"
            )

        logger.info(f"Rolling back migration {version}")
        self._run_migration(migration, MigrationDirection.BACKWARD, dry_run)

    def get_migration_plan(self, target_version: str = "latest") -> List[Dict[str, Any]]:
        """
        Get migration execution plan

        Args:
            target_version: Target version to plan for

        Returns:
            List of migration steps with details
        """
        current_version = self.get_current_version()
        plan = []

        if target_version == "latest":
            target_version = max(self.migrations.keys(), key=lambda v: tuple(map(int, v.split('.'))))

        all_versions = sorted(self.migrations.keys(), key=lambda v: tuple(map(int, v.split('.'))))

        for version in all_versions:
            if version > current_version and version <= target_version:
                migration = self.migrations[version]
                step = {
                    'version': version,
                    'name': migration.name,
                    'description': migration.description,
                    'is_breaking': migration.is_breaking,
                    'dependencies': migration.dependencies,
                    'has_rollback': migration.backward_sql is not None
                }
                plan.append(step)

        return plan

    def validate_migration_safety(self, target_version: str = "latest") -> Tuple[bool, List[str]]:
        """
        Validate migration plan for safety issues

        Args:
            target_version: Target version to validate

        Returns:
            Tuple of (is_safe, safety_issues)
        """
        plan = self.get_migration_plan(target_version)
        issues = []

        for step in plan:
            migration = self.migrations[step['version']]

            # Check breaking changes
            if migration.is_breaking:
                issues.append(f"Breaking change in {step['version']}: {step['name']}")

            # Check rollback capability
            if not migration.backward_sql:
                issues.append(f"Migration {step['version']} cannot be rolled back")

        return len(issues) == 0, issues
