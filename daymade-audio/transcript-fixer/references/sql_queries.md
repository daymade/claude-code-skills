# SQL Query Reference

Database location: `~/.transcript-fixer/corrections.db`

## Basic Operations

### Add Corrections

```sql
-- Add a correction
INSERT INTO corrections (from_text, to_text, domain, source)
VALUES ('巨升智能', '具身智能', 'embodied_ai', 'manual');

INSERT INTO corrections (from_text, to_text, domain, source)
VALUES ('奇迹创坛', '奇绩创坛', 'general', 'manual');
```

### View Corrections

```sql
-- View all active corrections
SELECT from_text, to_text, domain, source, usage_count
FROM active_corrections
ORDER BY domain, from_text;

-- View corrections for specific domain
SELECT from_text, to_text, usage_count, added_at
FROM active_corrections
WHERE domain = 'embodied_ai';
```

## Context Rules

### Add Context-Aware Rules

```sql
-- Add regex-based context rule
INSERT INTO context_rules (pattern, replacement, description, priority)
VALUES ('巨升方向', '具身方向', '巨升→具身', 10);

INSERT INTO context_rules (pattern, replacement, description, priority)
VALUES ('近距离的去看', '近距离地去看', '的→地 副词修饰', 5);
```

### View Rules

```sql
-- View all active context rules (ordered by priority)
SELECT pattern, replacement, description, priority
FROM context_rules
WHERE is_active = 1
ORDER BY priority DESC;
```

## Statistics

```sql
-- View correction statistics by domain
SELECT * FROM correction_statistics;

-- Count corrections by source
SELECT source, COUNT(*) as count, SUM(usage_count) as total_usage
FROM corrections
WHERE is_active = 1
GROUP BY source;

-- Most frequently used corrections
SELECT from_text, to_text, domain, usage_count, last_used
FROM corrections
WHERE is_active = 1 AND usage_count > 0
ORDER BY usage_count DESC
LIMIT 10;
```

## Learning and Suggestions

### View Suggestions

```sql
-- View pending suggestions
SELECT * FROM pending_suggestions;

-- View high-confidence suggestions
SELECT from_text, to_text, domain, frequency, confidence
FROM learned_suggestions
WHERE status = 'pending' AND confidence >= 0.8
ORDER BY confidence DESC, frequency DESC;
```

### Approve Suggestions

```sql
-- Insert into corrections
INSERT INTO corrections (from_text, to_text, domain, source, confidence)
SELECT from_text, to_text, domain, 'learned', confidence
FROM learned_suggestions
WHERE id = 1;

-- Mark as approved
UPDATE learned_suggestions
SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP
WHERE id = 1;
```

## History and Audit

```sql
-- View recent correction runs
SELECT filename, domain, stage1_changes, stage2_changes, run_timestamp
FROM correction_history
ORDER BY run_timestamp DESC
LIMIT 10;

-- View detailed changes for a specific run
SELECT ch.line_number, ch.from_text, ch.to_text, ch.rule_type
FROM correction_changes ch
JOIN correction_history h ON ch.history_id = h.id
WHERE h.filename = 'meeting.md'
ORDER BY ch.line_number;

-- Calculate success rate
SELECT
    COUNT(*) as total_runs,
    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
    ROUND(100.0 * SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM correction_history;
```

## Maintenance

```sql
-- Deactivate (soft delete) a correction
UPDATE corrections
SET is_active = 0
WHERE from_text = '错误词' AND domain = 'general';

-- Reactivate a correction
UPDATE corrections
SET is_active = 1
WHERE from_text = '错误词' AND domain = 'general';

-- Update correction confidence
UPDATE corrections
SET confidence = 0.95
WHERE from_text = '巨升' AND to_text = '具身';

-- Delete old history (older than 90 days)
DELETE FROM correction_history
WHERE run_timestamp < datetime('now', '-90 days');

-- Reclaim space
VACUUM;
```

## System Configuration

```sql
-- View system configuration
SELECT key, value, description FROM system_config;

-- Update configuration
UPDATE system_config
SET value = '5'
WHERE key = 'learning_frequency_threshold';

-- Check schema version
SELECT value FROM system_config WHERE key = 'schema_version';
```

## Export

```sql
-- Export corrections as CSV
.mode csv
.headers on
.output corrections_export.csv
SELECT from_text, to_text, domain, source, confidence, usage_count, added_at
FROM active_corrections;
.output stdout
```

For JSON export, use Python script with `service.export_corrections()` instead.

## See Also

- `references/file_formats.md` - Complete database schema documentation
- `references/quick_reference.md` - CLI command quick reference
- `SKILL.md` - Main user documentation
