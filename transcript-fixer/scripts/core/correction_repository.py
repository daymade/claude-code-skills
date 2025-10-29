#!/usr/bin/env python3
"""
Correction Repository - SQLite Data Access Layer

SINGLE RESPONSIBILITY: Manage database operations with ACID guarantees

Thread-safe, transactional, and follows Repository pattern.
All database operations are atomic and properly handle errors.
"""

from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from contextlib import contextmanager
from dataclasses import dataclass, asdict
import threading

# CRITICAL FIX: Import thread-safe connection pool
from .connection_pool import ConnectionPool, PoolExhaustedError

# CRITICAL FIX: Import domain validation (SQL injection prevention)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.domain_validator import (
    validate_domain,
    validate_source,
    validate_correction_inputs,
    validate_confidence,
    ValidationError as DomainValidationError
)

logger = logging.getLogger(__name__)


@dataclass
class Correction:
    """Correction entity"""
    id: Optional[int]
    from_text: str
    to_text: str
    domain: str
    source: str  # 'manual' | 'learned' | 'imported'
    confidence: float
    added_by: Optional[str]
    added_at: str
    usage_count: int
    last_used: Optional[str]
    notes: Optional[str]
    is_active: bool


@dataclass
class ContextRule:
    """Context-aware rule entity"""
    id: Optional[int]
    pattern: str
    replacement: str
    description: Optional[str]
    priority: int
    is_active: bool
    added_at: str
    added_by: Optional[str]


@dataclass
class LearnedSuggestion:
    """Learned pattern suggestion"""
    id: Optional[int]
    from_text: str
    to_text: str
    domain: str
    frequency: int
    confidence: float
    first_seen: str
    last_seen: str
    status: str  # 'pending' | 'approved' | 'rejected'
    reviewed_at: Optional[str]
    reviewed_by: Optional[str]


class DatabaseError(Exception):
    """Base exception for database errors"""
    pass


class ValidationError(DatabaseError):
    """Data validation error"""
    pass


class CorrectionRepository:
    """
    Thread-safe repository for correction storage using SQLite.

    Features:
    - ACID transactions
    - Connection pooling
    - Prepared statements (SQL injection prevention)
    - Comprehensive error handling
    - Audit logging
    """

    def __init__(self, db_path: Path, max_connections: int = 5):
        """
        Initialize repository with database path.

        CRITICAL FIX: Now uses thread-safe connection pool instead of
        unsafe ThreadLocal + check_same_thread=False pattern.

        Args:
            db_path: Path to SQLite database file
            max_connections: Maximum connections in pool (default: 5)

        Raises:
            ValueError: If max_connections < 1
            FileNotFoundError: If db_path parent doesn't exist
        """
        self.db_path = Path(db_path)

        # CRITICAL FIX: Replace unsafe ThreadLocal with connection pool
        # OLD: self._local = threading.local() + check_same_thread=False
        # NEW: Proper connection pool with thread safety enforced
        self._pool = ConnectionPool(
            db_path=self.db_path,
            max_connections=max_connections
        )

        # Ensure database schema exists
        self._ensure_database_exists()

        logger.info(f"Repository initialized with {max_connections} max connections")

    @contextmanager
    def _transaction(self):
        """
        Context manager for database transactions.

        CRITICAL FIX: Now uses connection from pool, ensuring thread safety.

        Provides ACID guarantees:
        - Atomicity: All or nothing
        - Consistency: Constraints enforced
        - Isolation: Serializable by default
        - Durability: Changes persisted to disk

        Yields:
            sqlite3.Connection: Database connection from pool

        Raises:
            DatabaseError: If transaction fails
            PoolExhaustedError: If no connection available
        """
        with self._pool.get_connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")  # Acquire write lock immediately
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction rolled back: {e}", exc_info=True)
                raise DatabaseError(f"Database operation failed: {e}") from e

    def _ensure_database_exists(self) -> None:
        """Create database schema if not exists."""
        schema_path = Path(__file__).parent / "schema.sql"

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        with self._transaction() as conn:
            conn.executescript(schema_sql)

        logger.info(f"Database initialized: {self.db_path}")

    # ==================== Correction Operations ====================

    def add_correction(
        self,
        from_text: str,
        to_text: str,
        domain: str = "general",
        source: str = "manual",
        confidence: float = 1.0,
        added_by: Optional[str] = None,
        notes: Optional[str] = None
    ) -> int:
        """
        Add a new correction with full validation.

        CRITICAL FIX: Now validates all inputs to prevent SQL injection
        and DoS attacks via excessively long inputs.

        Args:
            from_text: Original (incorrect) text
            to_text: Corrected text
            domain: Correction domain
            source: Origin of correction
            confidence: Confidence score (0.0-1.0)
            added_by: User who added it
            notes: Optional notes

        Returns:
            ID of inserted correction

        Raises:
            ValidationError: If validation fails
            DatabaseError: If database operation fails
        """
        # CRITICAL FIX: Validate all inputs before touching database
        try:
            from_text, to_text, domain, source, notes, added_by = \
                validate_correction_inputs(from_text, to_text, domain, source, notes, added_by)
            confidence = validate_confidence(confidence)
        except DomainValidationError as e:
            raise ValidationError(str(e)) from e

        with self._transaction() as conn:
            try:
                cursor = conn.execute("""
                    INSERT INTO corrections
                    (from_text, to_text, domain, source, confidence, added_by, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (from_text, to_text, domain, source, confidence, added_by, notes))

                correction_id = cursor.lastrowid

                # Audit log
                self._audit_log(
                    conn,
                    action="add_correction",
                    entity_type="correction",
                    entity_id=correction_id,
                    user=added_by,
                    details=f"Added: '{from_text}' → '{to_text}' (domain: {domain})"
                )

                logger.info(f"Added correction ID {correction_id}: {from_text} → {to_text}")
                return correction_id

            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed" in str(e):
                    # Update existing correction instead (within same transaction)
                    logger.warning(f"Correction already exists, updating: {from_text}")
                    cursor = conn.execute("""
                        UPDATE corrections
                        SET to_text = ?, source = ?, confidence = ?,
                            added_by = ?, notes = ?, added_at = CURRENT_TIMESTAMP
                        WHERE from_text = ? AND domain = ? AND is_active = 1
                    """, (to_text, source, confidence, added_by, notes, from_text, domain))

                    if cursor.rowcount > 0:
                        # Get the ID of the updated row
                        cursor = conn.execute("""
                            SELECT id FROM corrections
                            WHERE from_text = ? AND domain = ? AND is_active = 1
                        """, (from_text, domain))
                        correction_id = cursor.fetchone()[0]

                        # Audit log
                        self._audit_log(
                            conn,
                            action="update_correction",
                            entity_type="correction",
                            entity_id=correction_id,
                            user=added_by,
                            details=f"Updated: '{from_text}' → '{to_text}' (domain: {domain})"
                        )

                        logger.info(f"Updated correction ID {correction_id}: {from_text} → {to_text}")
                        return correction_id
                    else:
                        raise ValidationError(f"Correction not found: {from_text} in domain {domain}")
                raise ValidationError(f"Integrity constraint violated: {e}") from e

    def get_correction(self, from_text: str, domain: str = "general") -> Optional[Correction]:
        """Get a specific correction."""
        with self._pool.get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM corrections
                WHERE from_text = ? AND domain = ? AND is_active = 1
            """, (from_text, domain))

            row = cursor.fetchone()
            return self._row_to_correction(row) if row else None

    def get_all_corrections(self, domain: Optional[str] = None, active_only: bool = True) -> List[Correction]:
        """Get all corrections, optionally filtered by domain."""
        with self._pool.get_connection() as conn:
            if domain:
                if active_only:
                    cursor = conn.execute("""
                        SELECT * FROM corrections
                        WHERE domain = ? AND is_active = 1
                        ORDER BY from_text
                    """, (domain,))
                else:
                    cursor = conn.execute("""
                        SELECT * FROM corrections
                        WHERE domain = ?
                        ORDER BY from_text
                    """, (domain,))
            else:
                if active_only:
                    cursor = conn.execute("""
                        SELECT * FROM corrections
                        WHERE is_active = 1
                        ORDER BY domain, from_text
                    """)
                else:
                    cursor = conn.execute("""
                        SELECT * FROM corrections
                        ORDER BY domain, from_text
                    """)

            return [self._row_to_correction(row) for row in cursor.fetchall()]

    def get_corrections_dict(self, domain: str = "general") -> Dict[str, str]:
        """Get corrections as a simple dictionary for processing."""
        corrections = self.get_all_corrections(domain=domain, active_only=True)
        return {c.from_text: c.to_text for c in corrections}

    def update_correction(
        self,
        from_text: str,
        to_text: str,
        domain: str = "general",
        updated_by: Optional[str] = None
    ) -> int:
        """Update an existing correction."""
        with self._transaction() as conn:
            cursor = conn.execute("""
                UPDATE corrections
                SET to_text = ?, added_at = CURRENT_TIMESTAMP
                WHERE from_text = ? AND domain = ? AND is_active = 1
            """, (to_text, from_text, domain))

            if cursor.rowcount == 0:
                raise ValidationError(f"Correction not found: {from_text} in domain {domain}")

            # Audit log
            self._audit_log(
                conn,
                action="update_correction",
                entity_type="correction",
                user=updated_by,
                details=f"Updated: '{from_text}' → '{to_text}' (domain: {domain})"
            )

            logger.info(f"Updated correction: {from_text} → {to_text}")
            return cursor.rowcount

    def delete_correction(self, from_text: str, domain: str = "general", deleted_by: Optional[str] = None) -> bool:
        """Soft delete a correction (mark as inactive)."""
        with self._transaction() as conn:
            cursor = conn.execute("""
                UPDATE corrections
                SET is_active = 0
                WHERE from_text = ? AND domain = ? AND is_active = 1
            """, (from_text, domain))

            if cursor.rowcount > 0:
                self._audit_log(
                    conn,
                    action="delete_correction",
                    entity_type="correction",
                    user=deleted_by,
                    details=f"Deleted: '{from_text}' (domain: {domain})"
                )
                logger.info(f"Deleted correction: {from_text}")
                return True
            return False

    def increment_usage(self, from_text: str, domain: str = "general") -> None:
        """Increment usage count for a correction."""
        with self._transaction() as conn:
            conn.execute("""
                UPDATE corrections
                SET usage_count = usage_count + 1,
                    last_used = CURRENT_TIMESTAMP
                WHERE from_text = ? AND domain = ? AND is_active = 1
            """, (from_text, domain))

    # ==================== Bulk Operations ====================

    def bulk_import_corrections(
        self,
        corrections: Dict[str, str],
        domain: str = "general",
        source: str = "imported",
        imported_by: Optional[str] = None,
        merge: bool = True
    ) -> Tuple[int, int, int]:
        """
        Bulk import corrections with conflict resolution.

        Returns:
            Tuple of (inserted_count, updated_count, skipped_count)
        """
        inserted, updated, skipped = 0, 0, 0

        with self._transaction() as conn:
            for from_text, to_text in corrections.items():
                try:
                    if merge:
                        # Check if exists
                        cursor = conn.execute("""
                            SELECT id, to_text FROM corrections
                            WHERE from_text = ? AND domain = ? AND is_active = 1
                        """, (from_text, domain))
                        existing = cursor.fetchone()

                        if existing:
                            if existing['to_text'] != to_text:
                                # Update
                                conn.execute("""
                                    UPDATE corrections
                                    SET to_text = ?, source = ?, added_at = CURRENT_TIMESTAMP
                                    WHERE from_text = ? AND domain = ? AND is_active = 1
                                """, (to_text, source, from_text, domain))
                                updated += 1
                            else:
                                skipped += 1
                        else:
                            # Insert
                            conn.execute("""
                                INSERT INTO corrections
                                (from_text, to_text, domain, source, confidence, added_by)
                                VALUES (?, ?, ?, ?, 1.0, ?)
                            """, (from_text, to_text, domain, source, imported_by))
                            inserted += 1
                    else:
                        # Replace mode: just insert
                        conn.execute("""
                            INSERT OR REPLACE INTO corrections
                            (from_text, to_text, domain, source, confidence, added_by)
                            VALUES (?, ?, ?, ?, 1.0, ?)
                        """, (from_text, to_text, domain, source, imported_by))
                        inserted += 1

                except sqlite3.Error as e:
                    logger.warning(f"Failed to import '{from_text}': {e}")
                    skipped += 1

            # Audit log
            self._audit_log(
                conn,
                action="bulk_import",
                entity_type="correction",
                user=imported_by,
                details=f"Imported {inserted} new, updated {updated}, skipped {skipped} (domain: {domain})"
            )

        logger.info(f"Bulk import: {inserted} inserted, {updated} updated, {skipped} skipped")
        return (inserted, updated, skipped)

    # ==================== Helper Methods ====================

    def _row_to_correction(self, row: sqlite3.Row) -> Correction:
        """Convert database row to Correction object."""
        return Correction(
            id=row['id'],
            from_text=row['from_text'],
            to_text=row['to_text'],
            domain=row['domain'],
            source=row['source'],
            confidence=row['confidence'],
            added_by=row['added_by'],
            added_at=row['added_at'],
            usage_count=row['usage_count'],
            last_used=row['last_used'],
            notes=row['notes'],
            is_active=bool(row['is_active'])
        )

    def _audit_log(
        self,
        conn: sqlite3.Connection,
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        user: Optional[str] = None,
        details: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """Write audit log entry."""
        conn.execute("""
            INSERT INTO audit_log (action, entity_type, entity_id, user, details, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (action, entity_type, entity_id, user, details, success, error_message))

    def close(self) -> None:
        """
        Close all database connections in pool.

        CRITICAL FIX: Now closes connection pool properly.

        Call this on application shutdown to ensure clean cleanup.
        After calling, repository cannot be used anymore.
        """
        logger.info("Closing database connection pool")
        self._pool.close_all()

    def get_pool_statistics(self):
        """
        Get connection pool statistics for monitoring.

        Returns:
            PoolStatistics with current state

        Useful for:
        - Health checks
        - Monitoring dashboards
        - Debugging connection issues
        """
        return self._pool.get_statistics()
