#!/usr/bin/env python3
"""
Migration Definitions - Database Schema Migrations

This module contains all database migrations for the transcript-fixer system.

Migrations are defined here to ensure version control and proper migration ordering.
Each migration has:
- Unique version number
- Forward SQL
- Optional backward SQL (for rollback)
- Dependencies on previous versions
- Validation functions
"""

from __future__ import annotations

import sqlite3
import logging
from typing import Dict, Any, Tuple, Optional

from .database_migration import Migration

logger = logging.getLogger(__name__)


def _validate_schema_2_0(conn: sqlite3.Connection, migration: Migration) -> Tuple[bool, str]:
    """Validate that schema v2.0 is correctly applied"""
    cursor = conn.cursor()

    # Check if all tables exist
    expected_tables = {
        'corrections', 'context_rules', 'correction_history',
        'correction_changes', 'learned_suggestions',
        'suggestion_examples', 'system_config', 'audit_log'
    }

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}

    missing_tables = expected_tables - existing_tables
    if missing_tables:
        return False, f"Missing tables: {missing_tables}"

    # Check system_config has required entries
    cursor.execute("SELECT key FROM system_config WHERE key = 'schema_version'")
    if not cursor.fetchone():
        return False, "Missing schema_version in system_config"

    return True, "Schema validation passed"


# Migration from no schema to v1.0 (basic structure)
MIGRATION_V1_0 = Migration(
    version="1.0",
    name="Initial Database Schema",
    description="Create basic tables for correction storage",
    forward_sql="""
    -- Enable foreign keys
    PRAGMA foreign_keys = ON;

    -- Table: corrections
    CREATE TABLE corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_text TEXT NOT NULL,
        to_text TEXT NOT NULL,
        domain TEXT NOT NULL DEFAULT 'general',
        source TEXT NOT NULL CHECK(source IN ('manual', 'learned', 'imported')),
        confidence REAL NOT NULL DEFAULT 1.0 CHECK(confidence >= 0.0 AND confidence <= 1.0),
        added_by TEXT,
        added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        usage_count INTEGER NOT NULL DEFAULT 0 CHECK(usage_count >= 0),
        last_used TIMESTAMP,
        notes TEXT,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        UNIQUE(from_text, domain)
    );

    -- Table: correction_history
    CREATE TABLE correction_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        domain TEXT NOT NULL,
        run_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        original_length INTEGER NOT NULL CHECK(original_length >= 0),
        stage1_changes INTEGER NOT NULL DEFAULT 0 CHECK(stage1_changes >= 0),
        stage2_changes INTEGER NOT NULL DEFAULT 0 CHECK(stage2_changes >= 0),
        model TEXT,
        execution_time_ms INTEGER CHECK(execution_time_ms >= 0),
        success BOOLEAN NOT NULL DEFAULT 1,
        error_message TEXT
    );

    -- Insert initial system config
    CREATE TABLE system_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        value_type TEXT NOT NULL CHECK(value_type IN ('string', 'int', 'float', 'boolean', 'json')),
        description TEXT,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    INSERT OR IGNORE INTO system_config (key, value, value_type, description) VALUES
        ('schema_version', '1.0', 'string', 'Database schema version'),
        ('api_provider', 'GLM', 'string', 'API provider name'),
        ('api_model', 'GLM-4.6', 'string', 'Default AI model');

    -- Create indexes
    CREATE INDEX idx_corrections_domain ON corrections(domain);
    CREATE INDEX idx_corrections_source ON corrections(source);
    CREATE INDEX idx_corrections_added_at ON corrections(added_at);
    CREATE INDEX idx_corrections_is_active ON corrections(is_active);
    CREATE INDEX idx_corrections_from_text ON corrections(from_text);
    CREATE INDEX idx_history_run_timestamp ON correction_history(run_timestamp DESC);
    CREATE INDEX idx_history_domain ON correction_history(domain);
    CREATE INDEX idx_history_success ON correction_history(success);
    """,
    backward_sql="""
    -- Drop indexes
    DROP INDEX IF EXISTS idx_corrections_domain;
    DROP INDEX IF EXISTS idx_corrections_source;
    DROP INDEX IF EXISTS idx_corrections_added_at;
    DROP INDEX IF EXISTS idx_corrections_is_active;
    DROP INDEX IF EXISTS idx_corrections_from_text;
    DROP INDEX IF EXISTS idx_history_run_timestamp;
    DROP INDEX IF EXISTS idx_history_domain;
    DROP INDEX IF EXISTS idx_history_success;

    -- Drop tables
    DROP TABLE IF EXISTS correction_history;
    DROP TABLE IF EXISTS corrections;
    DROP TABLE IF EXISTS system_config;
    """,
    dependencies=[],
    check_function=None
)

# Migration from v1.0 to v2.0 (full schema)
MIGRATION_V2_0 = Migration(
    version="2.0",
    name="Complete Schema Enhancement",
    description="Add advanced tables for learning system and audit trail",
    forward_sql="""
    -- Enable foreign keys
    PRAGMA foreign_keys = ON;

    -- Add new tables
    CREATE TABLE context_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern TEXT NOT NULL UNIQUE,
        replacement TEXT NOT NULL,
        description TEXT,
        priority INTEGER NOT NULL DEFAULT 0,
        is_active BOOLEAN NOT NULL DEFAULT 1,
        added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        added_by TEXT
    );

    CREATE TABLE correction_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        history_id INTEGER NOT NULL,
        line_number INTEGER,
        from_text TEXT NOT NULL,
        to_text TEXT NOT NULL,
        rule_type TEXT NOT NULL CHECK(rule_type IN ('context', 'dictionary', 'ai')),
        rule_id INTEGER,
        context_before TEXT,
        context_after TEXT,
        FOREIGN KEY (history_id) REFERENCES correction_history(id) ON DELETE CASCADE
    );

    CREATE TABLE learned_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_text TEXT NOT NULL,
        to_text TEXT NOT NULL,
        domain TEXT NOT NULL DEFAULT 'general',
        frequency INTEGER NOT NULL DEFAULT 1 CHECK(frequency > 0),
        confidence REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
        first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
        reviewed_at TIMESTAMP,
        reviewed_by TEXT,
        UNIQUE(from_text, to_text, domain)
    );

    CREATE TABLE suggestion_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        suggestion_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        line_number INTEGER,
        context TEXT NOT NULL,
        occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (suggestion_id) REFERENCES learned_suggestions(id) ON DELETE CASCADE
    );

    CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id INTEGER,
        user TEXT,
        details TEXT,
        success BOOLEAN NOT NULL DEFAULT 1,
        error_message TEXT
    );

    -- Create indexes
    CREATE INDEX idx_context_rules_priority ON context_rules(priority DESC);
    CREATE INDEX idx_context_rules_is_active ON context_rules(is_active);
    CREATE INDEX idx_changes_history_id ON correction_changes(history_id);
    CREATE INDEX idx_changes_rule_type ON correction_changes(rule_type);
    CREATE INDEX idx_suggestions_status ON learned_suggestions(status);
    CREATE INDEX idx_suggestions_domain ON learned_suggestions(domain);
    CREATE INDEX idx_suggestions_confidence ON learned_suggestions(confidence DESC);
    CREATE INDEX idx_suggestions_frequency ON learned_suggestions(frequency DESC);
    CREATE INDEX idx_examples_suggestion_id ON suggestion_examples(suggestion_id);
    CREATE INDEX idx_audit_timestamp ON audit_log(timestamp DESC);
    CREATE INDEX idx_audit_action ON audit_log(action);
    CREATE INDEX idx_audit_entity_type ON audit_log(entity_type);
    CREATE INDEX idx_audit_success ON audit_log(success);

    -- Create views
    CREATE VIEW active_corrections AS
    SELECT
        id, from_text, to_text, domain, source, confidence,
        usage_count, last_used, added_at
    FROM corrections
    WHERE is_active = 1
    ORDER BY domain, from_text;

    CREATE VIEW pending_suggestions AS
    SELECT
        s.id, s.from_text, s.to_text, s.domain, s.frequency,
        s.confidence, s.first_seen, s.last_seen, COUNT(e.id) as example_count
    FROM learned_suggestions s
    LEFT JOIN suggestion_examples e ON s.id = e.suggestion_id
    WHERE s.status = 'pending'
    GROUP BY s.id
    ORDER BY s.confidence DESC, s.frequency DESC;

    CREATE VIEW correction_statistics AS
    SELECT
        domain,
        COUNT(*) as total_corrections,
        COUNT(CASE WHEN source = 'manual' THEN 1 END) as manual_count,
        COUNT(CASE WHEN source = 'learned' THEN 1 END) as learned_count,
        COUNT(CASE WHEN source = 'imported' THEN 1 END) as imported_count,
        SUM(usage_count) as total_usage,
        MAX(added_at) as last_updated
    FROM corrections
    WHERE is_active = 1
    GROUP BY domain;

    -- Update system config
    UPDATE system_config SET value = '2.0' WHERE key = 'schema_version';
    INSERT OR IGNORE INTO system_config (key, value, value_type, description) VALUES
        ('api_base_url', 'https://open.bigmodel.cn/api/anthropic', 'string', 'API endpoint URL'),
        ('default_domain', 'general', 'string', 'Default correction domain'),
        ('auto_learn_enabled', 'true', 'boolean', 'Enable automatic pattern learning'),
        ('backup_enabled', 'true', 'boolean', 'Create backups before operations'),
        ('learning_frequency_threshold', '3', 'int', 'Min frequency for learned suggestions'),
        ('learning_confidence_threshold', '0.8', 'float', 'Min confidence for learned suggestions'),
        ('history_retention_days', '90', 'int', 'Days to retain correction history'),
        ('max_correction_length', '1000', 'int', 'Maximum length for correction text');
    """,
    backward_sql="""
    -- Drop views
    DROP VIEW IF EXISTS correction_statistics;
    DROP VIEW IF EXISTS pending_suggestions;
    DROP VIEW IF EXISTS active_corrections;

    -- Drop indexes
    DROP INDEX IF EXISTS idx_audit_success;
    DROP INDEX IF EXISTS idx_audit_entity_type;
    DROP INDEX IF EXISTS idx_audit_action;
    DROP INDEX IF EXISTS idx_audit_timestamp;
    DROP INDEX IF EXISTS idx_examples_suggestion_id;
    DROP INDEX IF EXISTS idx_suggestions_frequency;
    DROP INDEX IF EXISTS idx_suggestions_confidence;
    DROP INDEX IF EXISTS idx_suggestions_domain;
    DROP INDEX IF EXISTS idx_suggestions_status;
    DROP INDEX IF EXISTS idx_changes_rule_type;
    DROP INDEX IF EXISTS idx_changes_history_id;
    DROP INDEX IF EXISTS idx_context_rules_is_active;
    DROP INDEX IF EXISTS idx_context_rules_priority;

    -- Drop tables
    DROP TABLE IF EXISTS audit_log;
    DROP TABLE IF EXISTS suggestion_examples;
    DROP TABLE IF EXISTS learned_suggestions;
    DROP TABLE IF EXISTS correction_changes;
    DROP TABLE IF EXISTS context_rules;

    -- Reset schema version
    UPDATE system_config SET value = '1.0' WHERE key = 'schema_version';
    DELETE FROM system_config WHERE key IN (
        'api_base_url', 'default_domain', 'auto_learn_enabled',
        'backup_enabled', 'learning_frequency_threshold',
        'learning_confidence_threshold', 'history_retention_days',
        'max_correction_length'
    );
    """,
    dependencies=["1.0"],
    check_function=_validate_schema_2_0,
    is_breaking=False
)

# Migration from v2.0 to v2.1 (add performance optimizations)
MIGRATION_V2_1 = Migration(
    version="2.1",
    name="Performance Optimizations",
    description="Add indexes and constraints for better query performance",
    forward_sql="""
    -- Add composite indexes for common queries
    CREATE INDEX idx_corrections_domain_active ON corrections(domain, is_active);
    CREATE INDEX idx_corrections_domain_from_text ON corrections(domain, from_text);
    CREATE INDEX idx_corrections_usage_count ON corrections(usage_count DESC);
    CREATE INDEX idx_corrections_last_used ON corrections(last_used DESC);

    -- Add indexes for learned_suggestions queries
    CREATE INDEX idx_suggestions_domain_status ON learned_suggestions(domain, status);
    CREATE INDEX idx_suggestions_domain_confidence ON learned_suggestions(domain, confidence DESC);
    CREATE INDEX idx_suggestions_domain_frequency ON learned_suggestions(domain, frequency DESC);

    -- Add indexes for audit_log queries
    CREATE INDEX idx_audit_timestamp_entity ON audit_log(timestamp DESC, entity_type);
    CREATE INDEX idx_audit_entity_type_id ON audit_log(entity_type, entity_id);

    -- Add composite indexes for history queries
    CREATE INDEX idx_history_domain_timestamp ON correction_history(domain, run_timestamp DESC);
    CREATE INDEX idx_history_domain_success ON correction_history(domain, success, run_timestamp DESC);

    -- Add index for frequently joined tables
    CREATE INDEX idx_changes_history_rule_type ON correction_changes(history_id, rule_type);

    -- Update system config
    INSERT OR IGNORE INTO system_config (key, value, value_type, description) VALUES
        ('performance_optimization_applied', 'true', 'boolean', 'Performance optimization v2.1 applied');
    """,
    backward_sql="""
    -- Drop indexes
    DROP INDEX IF EXISTS idx_changes_history_rule_type;
    DROP INDEX IF EXISTS idx_history_domain_success;
    DROP INDEX IF EXISTS idx_history_domain_timestamp;
    DROP INDEX IF EXISTS idx_audit_entity_type_id;
    DROP INDEX IF EXISTS idx_audit_timestamp_entity;
    DROP INDEX IF EXISTS idx_suggestions_domain_frequency;
    DROP INDEX IF EXISTS idx_suggestions_domain_confidence;
    DROP INDEX IF EXISTS idx_suggestions_domain_status;
    DROP INDEX IF EXISTS idx_corrections_last_used;
    DROP INDEX IF EXISTS idx_corrections_usage_count;
    DROP INDEX IF EXISTS idx_corrections_domain_from_text;
    DROP INDEX IF EXISTS idx_corrections_domain_active;

    -- Remove system config
    DELETE FROM system_config WHERE key = 'performance_optimization_applied';
    """,
    dependencies=["2.0"],
    check_function=None,
    is_breaking=False
)

# Migration from v2.1 to v2.2 (add data retention policies)
MIGRATION_V2_2 = Migration(
    version="2.2",
    name="Data Retention Policies",
    description="Add retention policies and automatic cleanup mechanisms",
    forward_sql="""
    -- Add retention_policy table
    CREATE TABLE retention_policies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL CHECK(entity_type IN ('corrections', 'history', 'audits', 'suggestions')),
        retention_days INTEGER NOT NULL CHECK(retention_days > 0),
        is_active BOOLEAN NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        description TEXT
    );

    -- Insert default retention policies
    INSERT INTO retention_policies (entity_type, retention_days, is_active, description) VALUES
        ('history', 90, 1, 'Keep correction history for 90 days'),
        ('audits', 180, 1, 'Keep audit logs for 180 days'),
        ('suggestions', 30, 1, 'Keep rejected suggestions for 30 days'),
        ('corrections', 365, 0, 'Keep all corrections by default');

    -- Add cleanup_history table
    CREATE TABLE cleanup_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cleanup_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        entity_type TEXT NOT NULL,
        records_deleted INTEGER NOT NULL CHECK(records_deleted >= 0),
        execution_time_ms INTEGER NOT NULL CHECK(execution_time_ms >= 0),
        success BOOLEAN NOT NULL DEFAULT 1,
        error_message TEXT
    );

    -- Create indexes
    CREATE INDEX idx_retention_entity_type ON retention_policies(entity_type);
    CREATE INDEX idx_retention_is_active ON retention_policies(is_active);
    CREATE INDEX idx_cleanup_date ON cleanup_history(cleanup_date DESC);

    -- Update system config
    INSERT OR IGNORE INTO system_config (key, value, value_type, description) VALUES
        ('retention_cleanup_enabled', 'true', 'boolean', 'Enable automatic retention cleanup'),
        ('retention_cleanup_hour', '2', 'int', 'Hour of day to run cleanup (0-23)'),
        ('last_retention_cleanup', '', 'string', 'Timestamp of last retention cleanup');
    """,
    backward_sql="""
    -- Drop retention cleanup tables
    DROP TABLE IF EXISTS cleanup_history;
    DROP TABLE IF EXISTS retention_policies;

    -- Remove system config
    DELETE FROM system_config WHERE key IN (
        'retention_cleanup_enabled',
        'retention_cleanup_hour',
        'last_retention_cleanup'
    );
    """,
    dependencies=["2.1"],
    check_function=None,
    is_breaking=False
)

# Registry of all migrations
# Order matters - add new migrations at the end
ALL_MIGRATIONS = [
    MIGRATION_V1_0,
    MIGRATION_V2_0,
    MIGRATION_V2_1,
    MIGRATION_V2_2,
]

# Migration registry by version
MIGRATION_REGISTRY = {m.version: m for m in ALL_MIGRATIONS}

# Latest version
LATEST_VERSION = max(MIGRATION_REGISTRY.keys(), key=lambda v: tuple(map(int, v.split('.'))))


def get_migration(version: str) -> Migration:
    """Get migration by version"""
    if version not in MIGRATION_REGISTRY:
        raise ValueError(f"Migration version {version} not found")
    return MIGRATION_REGISTRY[version]


def get_migrations_up_to(target_version: str) -> list[Migration]:
    """Get all migrations up to target version"""
    versions = sorted(MIGRATION_REGISTRY.keys(), key=lambda v: tuple(map(int, v.split('.'))))
    result = []
    for version in versions:
        if version <= target_version:
            result.append(MIGRATION_REGISTRY[version])
    return result


def get_migrations_from(from_version: str) -> list[Migration]:
    """Get all migrations from version onwards"""
    versions = sorted(MIGRATION_REGISTRY.keys(), key=lambda v: tuple(map(int, v.split('.'))))
    result = []
    for version in versions:
        if version > from_version:
            result.append(MIGRATION_REGISTRY[version])
    return result