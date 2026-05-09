-- Transcript Fixer Database Schema v2.0
-- Migration from JSON to SQLite for ACID compliance and scalability
-- Author: ISTJ Chief Engineer
-- Date: 2025-01-28

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Table: corrections
-- Stores all correction mappings with metadata
CREATE TABLE IF NOT EXISTS corrections (
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

CREATE INDEX IF NOT EXISTS idx_corrections_domain ON corrections(domain);
CREATE INDEX IF NOT EXISTS idx_corrections_source ON corrections(source);
CREATE INDEX IF NOT EXISTS idx_corrections_added_at ON corrections(added_at);
CREATE INDEX IF NOT EXISTS idx_corrections_is_active ON corrections(is_active);
CREATE INDEX IF NOT EXISTS idx_corrections_from_text ON corrections(from_text);

-- Table: context_rules
-- Regex-based context-aware correction rules
CREATE TABLE IF NOT EXISTS context_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    replacement TEXT NOT NULL,
    description TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    added_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_context_rules_priority ON context_rules(priority DESC);
CREATE INDEX IF NOT EXISTS idx_context_rules_is_active ON context_rules(is_active);

-- Table: correction_history
-- Audit log for all correction runs
CREATE TABLE IF NOT EXISTS correction_history (
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

CREATE INDEX IF NOT EXISTS idx_history_run_timestamp ON correction_history(run_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_history_domain ON correction_history(domain);
CREATE INDEX IF NOT EXISTS idx_history_success ON correction_history(success);

-- Table: correction_changes
-- Detailed changes made in each correction run
CREATE TABLE IF NOT EXISTS correction_changes (
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

CREATE INDEX IF NOT EXISTS idx_changes_history_id ON correction_changes(history_id);
CREATE INDEX IF NOT EXISTS idx_changes_rule_type ON correction_changes(rule_type);

-- Table: learned_suggestions
-- AI-learned patterns pending user review
CREATE TABLE IF NOT EXISTS learned_suggestions (
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

CREATE INDEX IF NOT EXISTS idx_suggestions_status ON learned_suggestions(status);
CREATE INDEX IF NOT EXISTS idx_suggestions_domain ON learned_suggestions(domain);
CREATE INDEX IF NOT EXISTS idx_suggestions_confidence ON learned_suggestions(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_suggestions_frequency ON learned_suggestions(frequency DESC);

-- Table: suggestion_examples
-- Example occurrences of learned patterns
CREATE TABLE IF NOT EXISTS suggestion_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    line_number INTEGER,
    context TEXT NOT NULL,
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (suggestion_id) REFERENCES learned_suggestions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_examples_suggestion_id ON suggestion_examples(suggestion_id);

-- Table: system_config
-- System configuration and preferences
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    value_type TEXT NOT NULL CHECK(value_type IN ('string', 'int', 'float', 'boolean', 'json')),
    description TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Insert default configuration
INSERT OR IGNORE INTO system_config (key, value, value_type, description) VALUES
    ('schema_version', '2.0', 'string', 'Database schema version'),
    ('api_provider', 'GLM', 'string', 'API provider name'),
    ('api_model', 'GLM-4.6', 'string', 'Default AI model'),
    ('api_base_url', 'https://open.bigmodel.cn/api/anthropic', 'string', 'API endpoint URL'),
    ('default_domain', 'general', 'string', 'Default correction domain'),
    ('auto_learn_enabled', 'true', 'boolean', 'Enable automatic pattern learning'),
    ('backup_enabled', 'true', 'boolean', 'Create backups before operations'),
    ('learning_frequency_threshold', '3', 'int', 'Min frequency for learned suggestions'),
    ('learning_confidence_threshold', '0.8', 'float', 'Min confidence for learned suggestions'),
    ('history_retention_days', '90', 'int', 'Days to retain correction history'),
    ('max_correction_length', '1000', 'int', 'Maximum length for correction text');

-- Table: audit_log
-- Comprehensive audit trail for all operations
CREATE TABLE IF NOT EXISTS audit_log (
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

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_entity_type ON audit_log(entity_type);
CREATE INDEX IF NOT EXISTS idx_audit_success ON audit_log(success);

-- View: active_corrections
-- Quick access to active corrections
CREATE VIEW IF NOT EXISTS active_corrections AS
SELECT
    id,
    from_text,
    to_text,
    domain,
    source,
    confidence,
    usage_count,
    last_used,
    added_at
FROM corrections
WHERE is_active = 1
ORDER BY domain, from_text;

-- View: pending_suggestions
-- Quick access to suggestions pending review
CREATE VIEW IF NOT EXISTS pending_suggestions AS
SELECT
    s.id,
    s.from_text,
    s.to_text,
    s.domain,
    s.frequency,
    s.confidence,
    s.first_seen,
    s.last_seen,
    COUNT(e.id) as example_count
FROM learned_suggestions s
LEFT JOIN suggestion_examples e ON s.id = e.suggestion_id
WHERE s.status = 'pending'
GROUP BY s.id
ORDER BY s.confidence DESC, s.frequency DESC;

-- View: correction_statistics
-- Statistics per domain
CREATE VIEW IF NOT EXISTS correction_statistics AS
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
