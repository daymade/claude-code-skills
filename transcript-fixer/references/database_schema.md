# Database Schema Reference

**MUST read this before any database operations.**

Database location: `~/.transcript-fixer/corrections.db`

## Core Tables

### corrections

Main storage for correction mappings.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| from_text | TEXT | Error text to match (NOT NULL) |
| to_text | TEXT | Correct replacement (NOT NULL) |
| domain | TEXT | Domain: general, embodied_ai, finance, medical |
| source | TEXT | 'manual', 'learned', 'imported' |
| confidence | REAL | 0.0-1.0 |
| added_by | TEXT | Username |
| added_at | TIMESTAMP | Creation time |
| usage_count | INTEGER | Times this correction was applied |
| last_used | TIMESTAMP | Last time used |
| notes | TEXT | Optional notes |
| is_active | BOOLEAN | Active flag (1=active, 0=disabled) |

**Constraint**: `UNIQUE(from_text, domain)`

### context_rules

Regex-based context-aware correction rules.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| pattern | TEXT | Regex pattern (UNIQUE) |
| replacement | TEXT | Replacement text |
| description | TEXT | Rule description |
| priority | INTEGER | Higher = processed first |
| is_active | BOOLEAN | Active flag |

### learned_suggestions

AI-learned patterns pending user review.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| from_text | TEXT | Detected error |
| to_text | TEXT | Suggested correction |
| domain | TEXT | Domain |
| frequency | INTEGER | Occurrence count (≥1) |
| confidence | REAL | AI confidence (0.0-1.0) |
| first_seen | TIMESTAMP | First occurrence |
| last_seen | TIMESTAMP | Last occurrence |
| status | TEXT | 'pending', 'approved', 'rejected' |
| reviewed_at | TIMESTAMP | Review time |
| reviewed_by | TEXT | Reviewer |

**Constraint**: `UNIQUE(from_text, to_text, domain)`

### correction_history

Audit log for all correction runs.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| filename | TEXT | Input file name |
| domain | TEXT | Domain used |
| run_timestamp | TIMESTAMP | When run |
| original_length | INTEGER | Original text length |
| stage1_changes | INTEGER | Dictionary changes count |
| stage2_changes | INTEGER | AI changes count |
| model | TEXT | AI model used |
| execution_time_ms | INTEGER | Processing time |
| success | BOOLEAN | Success flag |
| error_message | TEXT | Error if failed |

### correction_changes

Detailed changes made in each correction run.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| history_id | INTEGER | FK → correction_history.id |
| line_number | INTEGER | Line where change occurred |
| from_text | TEXT | Original text |
| to_text | TEXT | Corrected text |
| rule_type | TEXT | 'context', 'dictionary', 'ai' |
| rule_id | INTEGER | Reference to rule used |
| context_before | TEXT | Text before change |
| context_after | TEXT | Text after change |

### system_config

Key-value configuration store.

| Column | Type | Description |
|--------|------|-------------|
| key | TEXT | Config key (PRIMARY KEY) |
| value | TEXT | Config value |
| value_type | TEXT | 'string', 'int', 'float', 'boolean', 'json' |
| description | TEXT | What this config does |
| updated_at | TIMESTAMP | Last update |

**Default configs**:
- `schema_version`: '2.0'
- `api_model`: 'GLM-4.6'
- `learning_frequency_threshold`: 3
- `learning_confidence_threshold`: 0.8
- `history_retention_days`: 90

### audit_log

Comprehensive operations trail.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| timestamp | TIMESTAMP | When occurred |
| action | TEXT | Action type |
| entity_type | TEXT | Table affected |
| entity_id | INTEGER | Row ID |
| user | TEXT | Who did it |
| details | TEXT | JSON details |
| success | BOOLEAN | Success flag |
| error_message | TEXT | Error if failed |

## Views

### active_corrections

Active corrections only, ordered by domain and from_text.

```sql
SELECT * FROM active_corrections;
```

### pending_suggestions

Suggestions awaiting review, with example count.

```sql
SELECT * FROM pending_suggestions WHERE confidence > 0.8;
```

### correction_statistics

Statistics per domain.

```sql
SELECT * FROM correction_statistics;
```

## Common Queries

```sql
-- List all active corrections
SELECT from_text, to_text, domain FROM active_corrections;

-- Check pending high-confidence suggestions
SELECT * FROM pending_suggestions WHERE confidence > 0.8 ORDER BY frequency DESC;

-- Domain statistics
SELECT domain, total_corrections, total_usage FROM correction_statistics;

-- Recent correction history
SELECT filename, stage1_changes, stage2_changes, run_timestamp
FROM correction_history
ORDER BY run_timestamp DESC LIMIT 10;

-- Add new correction (use CLI instead for safety)
INSERT INTO corrections (from_text, to_text, domain, source, confidence, added_by)
VALUES ('错误词', '正确词', 'general', 'manual', 1.0, 'tiansheng');

-- Disable a correction
UPDATE corrections SET is_active = 0 WHERE id = ?;
```

## Schema Version

Check current version:
```sql
SELECT value FROM system_config WHERE key = 'schema_version';
```

For complete schema including indexes and constraints, see `scripts/core/schema.sql`.
