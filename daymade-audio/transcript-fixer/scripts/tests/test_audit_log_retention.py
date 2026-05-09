#!/usr/bin/env python3
"""
Comprehensive tests for Audit Log Retention Management (P1-11)

Test Coverage:
1. Retention policy enforcement
2. Cleanup strategies (DELETE, ARCHIVE, ANONYMIZE)
3. Critical action extended retention
4. Compliance reporting
5. Archive creation and restoration
6. Dry-run mode
7. Transaction safety
8. Error handling

Author: Chief Engineer (ISTJ, 20 years experience)
Date: 2025-10-29
"""

import gzip
import json
import pytest
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.audit_log_retention import (
    AuditLogRetentionManager,
    RetentionPolicy,
    RetentionPeriod,
    CleanupStrategy,
    CleanupResult,
    ComplianceReport,
    CRITICAL_ACTIONS,
    get_retention_manager,
    reset_retention_manager,
)


@pytest.fixture
def test_db(tmp_path):
    """Create test database with schema"""
    db_path = tmp_path / "test_retention.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create audit_log table
    cursor.execute("""
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            user TEXT,
            details TEXT,
            success INTEGER DEFAULT 1,
            error_message TEXT
        )
    """)

    # Create retention_policies table
    cursor.execute("""
        CREATE TABLE retention_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT UNIQUE NOT NULL,
            retention_days INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1,
            description TEXT
        )
    """)

    # Create cleanup_history table
    cursor.execute("""
        CREATE TABLE cleanup_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            records_deleted INTEGER DEFAULT 0,
            execution_time_ms INTEGER DEFAULT 0,
            success INTEGER DEFAULT 1,
            error_message TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def retention_manager(test_db, tmp_path):
    """Create retention manager instance"""
    archive_dir = tmp_path / "archives"
    manager = AuditLogRetentionManager(test_db, archive_dir)
    yield manager
    reset_retention_manager()


def insert_audit_log(
    db_path: Path,
    action: str,
    entity_type: str,
    days_ago: int,
    entity_id: int = 1,
    user: str = "test_user"
) -> int:
    """Helper to insert audit log entry"""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    timestamp = (datetime.now() - timedelta(days=days_ago)).isoformat()

    cursor.execute("""
        INSERT INTO audit_log (timestamp, action, entity_type, entity_id, user, details, success)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    """, (timestamp, action, entity_type, entity_id, user, json.dumps({"key": "value"})))

    log_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return log_id


# =============================================================================
# Test Group 1: Retention Policy Enforcement
# =============================================================================

def test_default_retention_policies(retention_manager):
    """Test that default retention policies are loaded correctly"""
    policies = retention_manager.load_retention_policies()

    # Check default policies exist
    assert 'correction' in policies
    assert 'suggestion' in policies
    assert 'system' in policies
    assert 'migration' in policies

    # Check correction policy
    assert policies['correction'].retention_days == RetentionPeriod.ANNUAL.value
    assert policies['correction'].strategy == CleanupStrategy.ARCHIVE
    assert policies['correction'].critical_action_retention_days == RetentionPeriod.COMPLIANCE_SOX.value


def test_custom_retention_policy_from_database(test_db, retention_manager):
    """Test loading custom retention policies from database"""
    # Insert custom policy
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO retention_policies (entity_type, retention_days, is_active, description)
        VALUES ('custom_entity', 60, 1, 'Custom test policy')
    """)
    conn.commit()
    conn.close()

    # Load policies
    policies = retention_manager.load_retention_policies()

    # Check custom policy
    assert 'custom_entity' in policies
    assert policies['custom_entity'].retention_days == 60
    assert policies['custom_entity'].is_active is True


def test_retention_policy_validation():
    """Test retention policy validation"""
    # Valid policy
    policy = RetentionPolicy(
        entity_type='test',
        retention_days=30,
        strategy=CleanupStrategy.ARCHIVE
    )
    assert policy.retention_days == 30

    # Invalid: negative days (except -1)
    with pytest.raises(ValueError, match="retention_days must be -1"):
        RetentionPolicy(
            entity_type='test',
            retention_days=-5,
            strategy=CleanupStrategy.DELETE
        )

    # Invalid: critical retention shorter than regular
    with pytest.raises(ValueError, match="critical_action_retention_days must be"):
        RetentionPolicy(
            entity_type='test',
            retention_days=365,
            critical_action_retention_days=30,  # Shorter than retention_days
            strategy=CleanupStrategy.ARCHIVE
        )


# =============================================================================
# Test Group 2: Cleanup Strategies
# =============================================================================

def test_cleanup_strategy_delete(test_db, retention_manager):
    """Test DELETE cleanup strategy (permanent deletion)"""
    # Insert old logs
    for i in range(5):
        insert_audit_log(test_db, 'test_action', 'correction', days_ago=400)

    # Override policy to use DELETE strategy
    retention_manager.default_policies['correction'].strategy = CleanupStrategy.DELETE
    retention_manager.default_policies['correction'].retention_days = 365

    # Run cleanup
    results = retention_manager.cleanup_expired_logs(entity_type='correction')

    assert len(results) == 1
    result = results[0]
    assert result.entity_type == 'correction'
    assert result.records_deleted == 5
    assert result.records_archived == 0
    assert result.success is True

    # Verify logs are deleted
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type = 'correction'")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 0


def test_cleanup_strategy_archive(test_db, retention_manager):
    """Test ARCHIVE cleanup strategy (archive then delete)"""
    # Insert old logs
    log_ids = []
    for i in range(5):
        log_id = insert_audit_log(test_db, 'test_action', 'suggestion', days_ago=100)
        log_ids.append(log_id)

    # Override policy
    retention_manager.default_policies['suggestion'].strategy = CleanupStrategy.ARCHIVE
    retention_manager.default_policies['suggestion'].retention_days = 90

    # Run cleanup
    results = retention_manager.cleanup_expired_logs(entity_type='suggestion')

    assert len(results) == 1
    result = results[0]
    assert result.entity_type == 'suggestion'
    assert result.records_deleted == 5
    assert result.records_archived == 5
    assert result.success is True

    # Verify archive file exists
    archive_files = list(retention_manager.archive_dir.glob("audit_log_suggestion_*.json.gz"))
    assert len(archive_files) == 1

    # Verify archive content
    with gzip.open(archive_files[0], 'rt', encoding='utf-8') as f:
        archived_logs = json.load(f)

    assert len(archived_logs) == 5
    assert all(log['id'] in log_ids for log in archived_logs)


def test_cleanup_strategy_anonymize(test_db, retention_manager):
    """Test ANONYMIZE cleanup strategy (remove PII, keep metadata)"""
    # Insert old logs with user info
    for i in range(3):
        insert_audit_log(
            test_db,
            'test_action',
            'correction',
            days_ago=400,
            user=f'user_{i}@example.com'
        )

    # Override policy
    retention_manager.default_policies['correction'].strategy = CleanupStrategy.ANONYMIZE
    retention_manager.default_policies['correction'].retention_days = 365

    # Run cleanup
    results = retention_manager.cleanup_expired_logs(entity_type='correction')

    assert len(results) == 1
    result = results[0]
    assert result.entity_type == 'correction'
    assert result.records_anonymized == 3
    assert result.records_deleted == 0
    assert result.success is True

    # Verify logs are anonymized
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT user FROM audit_log WHERE entity_type = 'correction'")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()

    assert all(user == 'ANONYMIZED' for user in users)


# =============================================================================
# Test Group 3: Critical Action Extended Retention
# =============================================================================

def test_critical_action_extended_retention(test_db, retention_manager):
    """Test that critical actions have extended retention"""
    # Insert regular and critical actions (both old)
    insert_audit_log(test_db, 'regular_action', 'correction', days_ago=400)
    insert_audit_log(test_db, 'delete_correction', 'correction', days_ago=400)  # Critical

    # Override policy with extended retention for critical actions
    retention_manager.default_policies['correction'].retention_days = 365  # 1 year
    retention_manager.default_policies['correction'].critical_action_retention_days = 2555  # 7 years (SOX)
    retention_manager.default_policies['correction'].strategy = CleanupStrategy.DELETE

    # Run cleanup
    results = retention_manager.cleanup_expired_logs(entity_type='correction')

    # Only regular action should be deleted
    assert results[0].records_deleted == 1

    # Verify critical action is still there
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT action FROM audit_log WHERE entity_type = 'correction'")
    actions = [row[0] for row in cursor.fetchall()]
    conn.close()

    assert 'delete_correction' in actions
    assert 'regular_action' not in actions


def test_critical_actions_set_completeness():
    """Test that CRITICAL_ACTIONS set contains expected actions"""
    expected_critical = {
        'delete_correction',
        'update_correction',
        'approve_learned_suggestion',
        'reject_learned_suggestion',
        'system_config_change',
        'migration_applied',
        'security_event',
    }

    assert expected_critical.issubset(CRITICAL_ACTIONS)


# =============================================================================
# Test Group 4: Compliance Reporting
# =============================================================================

def test_compliance_report_generation(test_db, retention_manager):
    """Test compliance report generation"""
    # Insert test data
    insert_audit_log(test_db, 'action1', 'correction', days_ago=10)
    insert_audit_log(test_db, 'action2', 'suggestion', days_ago=100)
    insert_audit_log(test_db, 'action3', 'system', days_ago=200)

    # Generate report
    report = retention_manager.generate_compliance_report()

    assert isinstance(report, ComplianceReport)
    assert report.total_audit_logs == 3
    assert report.oldest_log_date is not None
    assert report.newest_log_date is not None
    assert 'correction' in report.logs_by_entity_type
    assert 'suggestion' in report.logs_by_entity_type
    assert report.storage_size_mb > 0


def test_compliance_report_detects_violations(test_db, retention_manager):
    """Test that compliance report detects retention violations"""
    # Insert expired logs
    insert_audit_log(test_db, 'old_action', 'suggestion', days_ago=100)

    # Override policy with short retention
    retention_manager.default_policies['suggestion'].retention_days = 30

    # Generate report
    report = retention_manager.generate_compliance_report()

    # Should detect violation
    assert report.is_compliant is False
    assert len(report.retention_violations) > 0
    assert 'suggestion' in report.retention_violations[0]


def test_compliance_report_no_violations(test_db, retention_manager):
    """Test compliance report with no violations"""
    # Insert recent logs
    insert_audit_log(test_db, 'recent_action', 'correction', days_ago=10)

    # Generate report
    report = retention_manager.generate_compliance_report()

    # Should be compliant
    assert report.is_compliant is True
    assert len(report.retention_violations) == 0


# =============================================================================
# Test Group 5: Archive Operations
# =============================================================================

def test_archive_creation_and_compression(test_db, retention_manager):
    """Test that archives are created and compressed correctly"""
    # Insert logs
    for i in range(10):
        insert_audit_log(test_db, f'action_{i}', 'correction', days_ago=400)

    # Override policy
    retention_manager.default_policies['correction'].retention_days = 365
    retention_manager.default_policies['correction'].strategy = CleanupStrategy.ARCHIVE

    # Run cleanup
    retention_manager.cleanup_expired_logs(entity_type='correction')

    # Check archive file
    archive_files = list(retention_manager.archive_dir.glob("audit_log_correction_*.json.gz"))
    assert len(archive_files) == 1

    archive_file = archive_files[0]

    # Verify it's a valid gzip file
    with gzip.open(archive_file, 'rt', encoding='utf-8') as f:
        logs = json.load(f)

    assert len(logs) == 10
    assert all('id' in log for log in logs)
    assert all('action' in log for log in logs)


def test_restore_from_archive(test_db, retention_manager):
    """Test restoring logs from archive"""
    # Insert and archive logs
    original_ids = []
    for i in range(5):
        log_id = insert_audit_log(test_db, f'action_{i}', 'correction', days_ago=400)
        original_ids.append(log_id)

    # Archive and delete
    retention_manager.default_policies['correction'].retention_days = 365
    retention_manager.default_policies['correction'].strategy = CleanupStrategy.ARCHIVE
    retention_manager.cleanup_expired_logs(entity_type='correction')

    # Verify logs are deleted
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type = 'correction'")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 0

    # Restore from archive
    archive_files = list(retention_manager.archive_dir.glob("audit_log_correction_*.json.gz"))
    restored_count = retention_manager.restore_from_archive(archive_files[0])

    assert restored_count == 5

    # Verify logs are restored
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM audit_log WHERE entity_type = 'correction' ORDER BY id")
    restored_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    assert sorted(restored_ids) == sorted(original_ids)


def test_restore_verify_only_mode(test_db, retention_manager):
    """Test restore with verify_only flag"""
    # Create archive
    for i in range(3):
        insert_audit_log(test_db, f'action_{i}', 'suggestion', days_ago=100)

    retention_manager.default_policies['suggestion'].retention_days = 90
    retention_manager.default_policies['suggestion'].strategy = CleanupStrategy.ARCHIVE
    retention_manager.cleanup_expired_logs(entity_type='suggestion')

    # Verify archive (without restoring)
    archive_files = list(retention_manager.archive_dir.glob("audit_log_suggestion_*.json.gz"))
    count = retention_manager.restore_from_archive(archive_files[0], verify_only=True)

    assert count == 3

    # Verify logs are still deleted (not restored)
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type = 'suggestion'")
    db_count = cursor.fetchone()[0]
    conn.close()

    assert db_count == 0


def test_restore_skips_duplicates(test_db, retention_manager):
    """Test that restore skips duplicate log entries"""
    # Insert logs
    for i in range(3):
        insert_audit_log(test_db, f'action_{i}', 'correction', days_ago=400)

    # Archive
    retention_manager.default_policies['correction'].retention_days = 365
    retention_manager.default_policies['correction'].strategy = CleanupStrategy.ARCHIVE
    retention_manager.cleanup_expired_logs(entity_type='correction')

    # Restore once
    archive_files = list(retention_manager.archive_dir.glob("audit_log_correction_*.json.gz"))
    first_restore = retention_manager.restore_from_archive(archive_files[0])
    assert first_restore == 3

    # Restore again (should skip duplicates)
    second_restore = retention_manager.restore_from_archive(archive_files[0])
    assert second_restore == 0


# =============================================================================
# Test Group 6: Dry-Run Mode
# =============================================================================

def test_dry_run_mode_no_changes(test_db, retention_manager):
    """Test that dry-run mode doesn't make actual changes"""
    # Insert old logs
    for i in range(5):
        insert_audit_log(test_db, 'action', 'correction', days_ago=400)

    # Override policy
    retention_manager.default_policies['correction'].retention_days = 365
    retention_manager.default_policies['correction'].strategy = CleanupStrategy.DELETE

    # Run cleanup in dry-run mode
    results = retention_manager.cleanup_expired_logs(entity_type='correction', dry_run=True)

    assert len(results) == 1
    result = results[0]
    assert result.records_scanned == 5
    assert result.records_deleted == 5  # Would delete
    assert result.success is True

    # Verify logs are NOT actually deleted
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type = 'correction'")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 5  # Still there


def test_dry_run_mode_archive_strategy(test_db, retention_manager):
    """Test dry-run mode with ARCHIVE strategy"""
    # Insert old logs
    for i in range(3):
        insert_audit_log(test_db, 'action', 'suggestion', days_ago=100)

    # Override policy
    retention_manager.default_policies['suggestion'].retention_days = 90
    retention_manager.default_policies['suggestion'].strategy = CleanupStrategy.ARCHIVE

    # Run cleanup in dry-run mode
    results = retention_manager.cleanup_expired_logs(entity_type='suggestion', dry_run=True)

    # Check result
    result = results[0]
    assert result.records_archived == 3  # Would archive

    # Verify no archive files created
    archive_files = list(retention_manager.archive_dir.glob("audit_log_suggestion_*.json.gz"))
    assert len(archive_files) == 0


# =============================================================================
# Test Group 7: Transaction Safety
# =============================================================================

def test_transaction_rollback_on_archive_failure(test_db, retention_manager, monkeypatch):
    """Test that transaction rolls back if archive fails"""
    # Insert logs
    for i in range(3):
        insert_audit_log(test_db, 'action', 'correction', days_ago=400)

    # Override policy
    retention_manager.default_policies['correction'].retention_days = 365
    retention_manager.default_policies['correction'].strategy = CleanupStrategy.ARCHIVE

    # Mock _archive_logs to raise an error
    def mock_archive_logs(*args, **kwargs):
        raise IOError("Archive write failed")

    monkeypatch.setattr(retention_manager, '_archive_logs', mock_archive_logs)

    # Run cleanup (should fail)
    results = retention_manager.cleanup_expired_logs(entity_type='correction')

    assert len(results) == 1
    result = results[0]
    assert result.success is False
    assert len(result.errors) > 0

    # Verify logs are NOT deleted (transaction rolled back)
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type = 'correction'")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 3  # Still there


def test_cleanup_history_recorded(test_db, retention_manager):
    """Test that cleanup operations are recorded in history"""
    # Insert logs
    for i in range(5):
        insert_audit_log(test_db, 'action', 'correction', days_ago=400)

    # Run cleanup
    retention_manager.default_policies['correction'].retention_days = 365
    retention_manager.default_policies['correction'].strategy = CleanupStrategy.DELETE
    retention_manager.cleanup_expired_logs(entity_type='correction')

    # Check cleanup history
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT entity_type, records_deleted, success
        FROM cleanup_history
        WHERE entity_type = 'correction'
    """)
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == 'correction'
    assert row[1] == 5  # records_deleted
    assert row[2] == 1  # success


# =============================================================================
# Test Group 8: Error Handling
# =============================================================================

def test_handle_missing_archive_file(retention_manager):
    """Test error handling for missing archive file"""
    fake_archive = Path("/nonexistent/archive.json.gz")

    with pytest.raises(FileNotFoundError, match="Archive file not found"):
        retention_manager.restore_from_archive(fake_archive)


def test_handle_invalid_entity_type(retention_manager):
    """Test handling of unknown entity type"""
    results = retention_manager.cleanup_expired_logs(entity_type='nonexistent_type')

    # Should return empty results (no policy found)
    assert len(results) == 0


def test_permanent_retention_skipped(test_db, retention_manager):
    """Test that permanent retention entities are never cleaned up"""
    # Insert old migration logs
    for i in range(3):
        insert_audit_log(test_db, 'migration_applied', 'migration', days_ago=3000)  # 8+ years old

    # Migration has permanent retention by default
    results = retention_manager.cleanup_expired_logs(entity_type='migration')

    # Should skip cleanup
    assert len(results) == 0

    # Verify logs are still there
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type = 'migration'")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 3


def test_anonymize_handles_invalid_json(test_db, retention_manager):
    """Test anonymization handles invalid JSON in details field"""
    # Insert log with invalid JSON
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()

    timestamp = (datetime.now() - timedelta(days=400)).isoformat()
    cursor.execute("""
        INSERT INTO audit_log (timestamp, action, entity_type, user, details)
        VALUES (?, 'test', 'correction', 'user@example.com', 'NOT_JSON')
    """, (timestamp,))

    conn.commit()
    conn.close()

    # Run anonymization
    retention_manager.default_policies['correction'].retention_days = 365
    retention_manager.default_policies['correction'].strategy = CleanupStrategy.ANONYMIZE

    results = retention_manager.cleanup_expired_logs(entity_type='correction')

    # Should succeed without raising exception
    assert results[0].success is True
    assert results[0].records_anonymized == 1


# =============================================================================
# Test Group 9: Global Instance Management
# =============================================================================

def test_global_retention_manager_singleton(test_db, tmp_path):
    """Test global retention manager follows singleton pattern"""
    reset_retention_manager()

    archive_dir = tmp_path / "archives"

    # Get manager twice
    manager1 = get_retention_manager(test_db, archive_dir)
    manager2 = get_retention_manager()

    # Should be same instance
    assert manager1 is manager2

    # Cleanup
    reset_retention_manager()


def test_global_retention_manager_reset(test_db, tmp_path):
    """Test resetting global retention manager"""
    reset_retention_manager()

    archive_dir = tmp_path / "archives"

    # Get manager
    manager1 = get_retention_manager(test_db, archive_dir)

    # Reset
    reset_retention_manager()

    # Get new manager
    manager2 = get_retention_manager(test_db, archive_dir)

    # Should be different instance
    assert manager1 is not manager2

    # Cleanup
    reset_retention_manager()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
