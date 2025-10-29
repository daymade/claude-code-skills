#!/usr/bin/env python3
"""
Audit Log Retention Management Module

CRITICAL FIX (P1-11): Production-grade audit log retention and compliance

Features:
- Configurable retention policies per entity type
- Automatic cleanup of expired logs
- Archive capability for long-term storage
- Compliance reporting (GDPR, SOX, etc.)
- Selective retention based on criticality
- Restoration from archives

Compliance Standards:
- GDPR: Right to erasure, data minimization
- SOX: 7-year retention for financial records
- HIPAA: 6-year retention for healthcare data
- Industry best practices

Author: Chief Engineer (ISTJ, 20 years experience)
Date: 2025-10-29
Priority: P1 - High
"""

from __future__ import annotations

import gzip
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Final
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class RetentionPeriod(Enum):
    """Standard retention periods"""
    SHORT = 30  # 30 days - operational logs
    MEDIUM = 90  # 90 days - default
    LONG = 180  # 180 days - 6 months
    ANNUAL = 365  # 1 year
    COMPLIANCE_SOX = 2555  # 7 years for SOX compliance
    COMPLIANCE_HIPAA = 2190  # 6 years for HIPAA
    PERMANENT = -1  # Never delete


class CleanupStrategy(Enum):
    """Cleanup strategies"""
    DELETE = "delete"  # Permanent deletion
    ARCHIVE = "archive"  # Move to archive before deletion
    ANONYMIZE = "anonymize"  # Remove PII, keep metadata


@dataclass
class RetentionPolicy:
    """Retention policy configuration"""
    entity_type: str
    retention_days: int
    strategy: CleanupStrategy = CleanupStrategy.ARCHIVE
    critical_action_retention_days: Optional[int] = None  # Extended retention for critical actions
    is_active: bool = True
    description: Optional[str] = None

    def __post_init__(self):
        """Validate retention policy"""
        if self.retention_days < -1:
            raise ValueError("retention_days must be -1 (permanent) or positive")
        if self.critical_action_retention_days and self.critical_action_retention_days < self.retention_days:
            raise ValueError("critical_action_retention_days must be >= retention_days")


@dataclass
class CleanupResult:
    """Result of cleanup operation"""
    entity_type: str
    records_scanned: int
    records_deleted: int
    records_archived: int
    records_anonymized: int
    execution_time_ms: int
    errors: List[str]
    success: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class ComplianceReport:
    """Compliance report for audit purposes"""
    report_date: datetime
    total_audit_logs: int
    oldest_log_date: Optional[datetime]
    newest_log_date: Optional[datetime]
    logs_by_entity_type: Dict[str, int]
    retention_violations: List[str]
    archived_logs_count: int
    storage_size_mb: float
    is_compliant: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = asdict(self)
        result['report_date'] = self.report_date.isoformat()
        if self.oldest_log_date:
            result['oldest_log_date'] = self.oldest_log_date.isoformat()
        if self.newest_log_date:
            result['newest_log_date'] = self.newest_log_date.isoformat()
        return result


# Critical actions that require extended retention
CRITICAL_ACTIONS: Final[set] = {
    'delete_correction',
    'update_correction',
    'approve_learned_suggestion',
    'reject_learned_suggestion',
    'system_config_change',
    'migration_applied',
    'security_event',
}


class AuditLogRetentionManager:
    """
    Production-grade audit log retention management

    Features:
    - Automatic cleanup based on retention policies
    - Archival to compressed files
    - Compliance reporting
    - Selective retention for critical actions
    - Transaction safety
    """

    def __init__(self, db_path: Path, archive_dir: Optional[Path] = None):
        """
        Initialize retention manager

        Args:
            db_path: Path to SQLite database
            archive_dir: Directory for archived logs (defaults to db_path.parent / 'archives')
        """
        self.db_path = Path(db_path)
        self.archive_dir = archive_dir or (self.db_path.parent / "archives")
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Default retention policies (can be overridden in database)
        self.default_policies = {
            'correction': RetentionPolicy(
                entity_type='correction',
                retention_days=RetentionPeriod.ANNUAL.value,
                strategy=CleanupStrategy.ARCHIVE,
                critical_action_retention_days=RetentionPeriod.COMPLIANCE_SOX.value,
                description='Correction operations'
            ),
            'suggestion': RetentionPolicy(
                entity_type='suggestion',
                retention_days=RetentionPeriod.MEDIUM.value,
                strategy=CleanupStrategy.ARCHIVE,
                description='Learning suggestions'
            ),
            'system': RetentionPolicy(
                entity_type='system',
                retention_days=RetentionPeriod.COMPLIANCE_SOX.value,
                strategy=CleanupStrategy.ARCHIVE,
                description='System configuration changes'
            ),
            'migration': RetentionPolicy(
                entity_type='migration',
                retention_days=RetentionPeriod.PERMANENT.value,
                strategy=CleanupStrategy.ARCHIVE,
                description='Database migrations'
            ),
        }

    @contextmanager
    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self):
        """Transaction context manager"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN")
            try:
                yield cursor
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def load_retention_policies(self) -> Dict[str, RetentionPolicy]:
        """
        Load retention policies from database

        Returns:
            Dictionary of policies by entity_type
        """
        policies = dict(self.default_policies)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT entity_type, retention_days, is_active, description
                    FROM retention_policies
                    WHERE is_active = 1
                """)

                for row in cursor.fetchall():
                    entity_type = row['entity_type']
                    # Update default policy or create new one
                    if entity_type in policies:
                        policies[entity_type].retention_days = row['retention_days']
                        policies[entity_type].is_active = bool(row['is_active'])
                    else:
                        policies[entity_type] = RetentionPolicy(
                            entity_type=entity_type,
                            retention_days=row['retention_days'],
                            is_active=bool(row['is_active']),
                            description=row['description']
                        )

        except sqlite3.Error as e:
            logger.warning(f"Failed to load retention policies from database: {e}")
            # Continue with default policies

        return policies

    def _archive_logs(self, logs: List[Dict[str, Any]], entity_type: str) -> Path:
        """
        Archive logs to compressed file

        Args:
            logs: List of log records
            entity_type: Entity type being archived

        Returns:
            Path to archive file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = self.archive_dir / f"audit_log_{entity_type}_{timestamp}.json.gz"

        with gzip.open(archive_file, 'wt', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, default=str)

        logger.info(f"Archived {len(logs)} logs to {archive_file}")
        return archive_file

    def _anonymize_log(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Anonymize log record (remove PII while keeping metadata)

        Args:
            log: Log record

        Returns:
            Anonymized log record
        """
        anonymized = dict(log)

        # Remove/mask PII fields
        if 'user' in anonymized and anonymized['user']:
            anonymized['user'] = 'ANONYMIZED'

        if 'details' in anonymized and anonymized['details']:
            # Keep only non-PII metadata
            try:
                details = json.loads(anonymized['details'])
                # Remove potential PII
                for key in list(details.keys()):
                    if any(pii in key.lower() for pii in ['email', 'name', 'ip', 'address']):
                        details[key] = 'ANONYMIZED'
                anonymized['details'] = json.dumps(details)
            except (json.JSONDecodeError, TypeError):
                anonymized['details'] = 'ANONYMIZED'

        return anonymized

    def cleanup_expired_logs(
        self,
        entity_type: Optional[str] = None,
        dry_run: bool = False
    ) -> List[CleanupResult]:
        """
        Clean up expired audit logs based on retention policies

        Args:
            entity_type: Specific entity type to clean (None for all)
            dry_run: If True, only simulate without actual deletion

        Returns:
            List of cleanup results per entity type
        """
        policies = self.load_retention_policies()
        results = []

        # Filter policies
        if entity_type:
            if entity_type not in policies:
                logger.warning(f"No retention policy found for entity_type: {entity_type}")
                return results
            policies = {entity_type: policies[entity_type]}

        for entity_type, policy in policies.items():
            if not policy.is_active:
                logger.info(f"Skipping inactive policy for {entity_type}")
                continue

            if policy.retention_days == RetentionPeriod.PERMANENT.value:
                logger.info(f"Permanent retention for {entity_type}, skipping cleanup")
                continue

            result = self._cleanup_entity_type(policy, dry_run)
            results.append(result)

        return results

    def _cleanup_entity_type(
        self,
        policy: RetentionPolicy,
        dry_run: bool = False
    ) -> CleanupResult:
        """
        Clean up logs for specific entity type

        Args:
            policy: Retention policy to apply
            dry_run: Simulation mode

        Returns:
            Cleanup result
        """
        start_time = datetime.now()
        entity_type = policy.entity_type
        errors = []

        records_scanned = 0
        records_deleted = 0
        records_archived = 0
        records_anonymized = 0

        try:
            # Calculate cutoff date
            cutoff_date = datetime.now() - timedelta(days=policy.retention_days)

            # Extended retention for critical actions
            critical_cutoff_date = None
            if policy.critical_action_retention_days:
                critical_cutoff_date = datetime.now() - timedelta(
                    days=policy.critical_action_retention_days
                )

            with self._transaction() as cursor:
                # Find expired logs
                cursor.execute("""
                    SELECT * FROM audit_log
                    WHERE entity_type = ?
                    AND timestamp < ?
                    ORDER BY timestamp ASC
                """, (entity_type, cutoff_date.isoformat()))

                expired_logs = [dict(row) for row in cursor.fetchall()]
                records_scanned = len(expired_logs)

                if records_scanned == 0:
                    logger.info(f"No expired logs found for {entity_type}")
                    return CleanupResult(
                        entity_type=entity_type,
                        records_scanned=0,
                        records_deleted=0,
                        records_archived=0,
                        records_anonymized=0,
                        execution_time_ms=0,
                        errors=[],
                        success=True
                    )

                # Filter out critical actions with extended retention
                logs_to_process = []
                for log in expired_logs:
                    action = log.get('action', '')
                    if action in CRITICAL_ACTIONS and critical_cutoff_date:
                        log_date = datetime.fromisoformat(log['timestamp'])
                        if log_date >= critical_cutoff_date:
                            # Skip - still within critical retention period
                            continue
                    logs_to_process.append(log)

                if not logs_to_process:
                    logger.info(f"All expired logs for {entity_type} are critical, skipping")
                    return CleanupResult(
                        entity_type=entity_type,
                        records_scanned=records_scanned,
                        records_deleted=0,
                        records_archived=0,
                        records_anonymized=0,
                        execution_time_ms=0,
                        errors=[],
                        success=True
                    )

                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would process {len(logs_to_process)} logs "
                        f"for {entity_type} with strategy {policy.strategy.value}"
                    )
                    return CleanupResult(
                        entity_type=entity_type,
                        records_scanned=records_scanned,
                        records_deleted=len(logs_to_process) if policy.strategy == CleanupStrategy.DELETE else 0,
                        records_archived=len(logs_to_process) if policy.strategy == CleanupStrategy.ARCHIVE else 0,
                        records_anonymized=len(logs_to_process) if policy.strategy == CleanupStrategy.ANONYMIZE else 0,
                        execution_time_ms=0,
                        errors=[],
                        success=True
                    )

                # Execute cleanup strategy
                log_ids = [log['id'] for log in logs_to_process]

                if policy.strategy == CleanupStrategy.ARCHIVE:
                    # Archive before deletion
                    try:
                        archive_path = self._archive_logs(logs_to_process, entity_type)
                        records_archived = len(logs_to_process)
                        logger.info(f"Archived to {archive_path}")
                    except Exception as e:
                        errors.append(f"Archive failed: {e}")
                        raise

                    # Delete archived logs
                    cursor.execute(f"""
                        DELETE FROM audit_log
                        WHERE id IN ({','.join('?' * len(log_ids))})
                    """, log_ids)
                    records_deleted = cursor.rowcount

                elif policy.strategy == CleanupStrategy.DELETE:
                    # Direct deletion (permanent)
                    cursor.execute(f"""
                        DELETE FROM audit_log
                        WHERE id IN ({','.join('?' * len(log_ids))})
                    """, log_ids)
                    records_deleted = cursor.rowcount

                elif policy.strategy == CleanupStrategy.ANONYMIZE:
                    # Anonymize in place
                    for log in logs_to_process:
                        anonymized = self._anonymize_log(log)
                        cursor.execute("""
                            UPDATE audit_log
                            SET user = ?, details = ?
                            WHERE id = ?
                        """, (anonymized['user'], anonymized['details'], log['id']))
                    records_anonymized = len(logs_to_process)

                # Record cleanup in history
                execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

                cursor.execute("""
                    INSERT INTO cleanup_history
                    (entity_type, records_deleted, execution_time_ms, success)
                    VALUES (?, ?, ?, 1)
                """, (entity_type, records_deleted + records_anonymized, execution_time_ms))

                logger.info(
                    f"Cleanup completed for {entity_type}: "
                    f"deleted={records_deleted}, archived={records_archived}, "
                    f"anonymized={records_anonymized}"
                )

        except Exception as e:
            logger.error(f"Cleanup failed for {entity_type}: {e}")
            errors.append(str(e))

            # Record failure in history
            try:
                with self._transaction() as cursor:
                    execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                    cursor.execute("""
                        INSERT INTO cleanup_history
                        (entity_type, records_deleted, execution_time_ms, success, error_message)
                        VALUES (?, 0, ?, 0, ?)
                    """, (entity_type, execution_time_ms, str(e)))
            except Exception:
                pass  # Best effort

            return CleanupResult(
                entity_type=entity_type,
                records_scanned=records_scanned,
                records_deleted=0,
                records_archived=0,
                records_anonymized=0,
                execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000),
                errors=errors,
                success=False
            )

        execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return CleanupResult(
            entity_type=entity_type,
            records_scanned=records_scanned,
            records_deleted=records_deleted,
            records_archived=records_archived,
            records_anonymized=records_anonymized,
            execution_time_ms=execution_time_ms,
            errors=errors,
            success=len(errors) == 0
        )

    def generate_compliance_report(self) -> ComplianceReport:
        """
        Generate compliance report for audit purposes

        Returns:
            Compliance report with statistics and violations
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total audit logs
            cursor.execute("SELECT COUNT(*) as count FROM audit_log")
            total_logs = cursor.fetchone()['count']

            # Date range
            cursor.execute("""
                SELECT
                    MIN(timestamp) as oldest,
                    MAX(timestamp) as newest
                FROM audit_log
            """)
            row = cursor.fetchone()
            oldest_log_date = datetime.fromisoformat(row['oldest']) if row['oldest'] else None
            newest_log_date = datetime.fromisoformat(row['newest']) if row['newest'] else None

            # Logs by entity type
            cursor.execute("""
                SELECT entity_type, COUNT(*) as count
                FROM audit_log
                GROUP BY entity_type
            """)
            logs_by_entity_type = {row['entity_type']: row['count'] for row in cursor.fetchall()}

            # Check for retention violations
            violations = []
            policies = self.load_retention_policies()

            for entity_type, policy in policies.items():
                if policy.retention_days == RetentionPeriod.PERMANENT.value:
                    continue

                cutoff_date = datetime.now() - timedelta(days=policy.retention_days)

                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM audit_log
                    WHERE entity_type = ? AND timestamp < ?
                """, (entity_type, cutoff_date.isoformat()))

                expired_count = cursor.fetchone()['count']
                if expired_count > 0:
                    violations.append(
                        f"{entity_type}: {expired_count} logs exceed retention period "
                        f"of {policy.retention_days} days"
                    )

            # Archived logs count (count .gz files)
            archived_count = len(list(self.archive_dir.glob("audit_log_*.json.gz")))

            # Storage size
            storage_size_mb = 0.0
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
            storage_size_mb = db_size / (1024 * 1024)

            # Archive size
            for archive_file in self.archive_dir.glob("*.gz"):
                storage_size_mb += archive_file.stat().st_size / (1024 * 1024)

            is_compliant = len(violations) == 0

            return ComplianceReport(
                report_date=datetime.now(),
                total_audit_logs=total_logs,
                oldest_log_date=oldest_log_date,
                newest_log_date=newest_log_date,
                logs_by_entity_type=logs_by_entity_type,
                retention_violations=violations,
                archived_logs_count=archived_count,
                storage_size_mb=round(storage_size_mb, 2),
                is_compliant=is_compliant
            )

    def restore_from_archive(
        self,
        archive_file: Path,
        verify_only: bool = False
    ) -> int:
        """
        Restore logs from archive file

        Args:
            archive_file: Path to archive file
            verify_only: If True, only verify archive integrity

        Returns:
            Number of logs restored (or that would be restored)
        """
        if not archive_file.exists():
            raise FileNotFoundError(f"Archive file not found: {archive_file}")

        try:
            with gzip.open(archive_file, 'rt', encoding='utf-8') as f:
                logs = json.load(f)

            if verify_only:
                logger.info(f"Archive {archive_file.name} contains {len(logs)} logs")
                return len(logs)

            # Restore logs
            with self._transaction() as cursor:
                restored_count = 0
                for log in logs:
                    # Check if log already exists
                    cursor.execute("""
                        SELECT id FROM audit_log
                        WHERE id = ?
                    """, (log['id'],))

                    if cursor.fetchone():
                        continue  # Skip duplicates

                    # Insert log
                    cursor.execute("""
                        INSERT INTO audit_log
                        (id, timestamp, action, entity_type, entity_id, user, details, success, error_message)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        log['id'],
                        log['timestamp'],
                        log['action'],
                        log['entity_type'],
                        log.get('entity_id'),
                        log.get('user'),
                        log.get('details'),
                        log.get('success', 1),
                        log.get('error_message')
                    ))
                    restored_count += 1

                logger.info(f"Restored {restored_count} logs from {archive_file.name}")
                return restored_count

        except Exception as e:
            logger.error(f"Failed to restore from archive {archive_file}: {e}")
            raise


# Global instance for convenience
_global_manager: Optional[AuditLogRetentionManager] = None


def get_retention_manager(
    db_path: Optional[Path] = None,
    archive_dir: Optional[Path] = None
) -> AuditLogRetentionManager:
    """
    Get global retention manager instance (singleton pattern)

    Args:
        db_path: Database path (only used on first call)
        archive_dir: Archive directory (only used on first call)

    Returns:
        Global AuditLogRetentionManager instance
    """
    global _global_manager

    if _global_manager is None:
        if db_path is None:
            from utils.config import get_config
            config = get_config()
            db_path = config.database.path

        _global_manager = AuditLogRetentionManager(db_path, archive_dir)

    return _global_manager


def reset_retention_manager() -> None:
    """Reset global retention manager (mainly for testing)"""
    global _global_manager
    _global_manager = None
