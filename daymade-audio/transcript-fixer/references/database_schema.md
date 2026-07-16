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

**Default configs**: the authoritative default set (12 keys) lives in `scripts/core/defaults.py` (`SYSTEM_CONFIG_DEFAULTS`) — don't hand-copy it here, it drifts. Common keys include `schema_version` ('2.0'), `api_model`, `learning_frequency_threshold`, `learning_confidence_threshold`, `history_retention_days`. To see the live values: `SELECT key, value FROM system_config;`

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

### suggestion_examples

Per-occurrence context for a learned suggestion (one suggestion → many examples). FK to `learned_suggestions(id)` ON DELETE CASCADE.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| suggestion_id | INTEGER | FK → learned_suggestions.id |
| filename | TEXT | Source transcript filename |
| line_number | INTEGER | Where it occurred |
| context | TEXT | Surrounding text |
| occurred_at | TIMESTAMP | When observed |

### review_items

Persistent queue of uncertain corrections awaiting a human verdict (native-pass
uncertain items, Stage 1 safe-mode deferrals, manual entries). Behavior and
workflow live in SKILL.md's "Review Queue" section; this is the storage shape.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| created_at | TIMESTAMP | Enqueue time |
| source | TEXT | 'native_pass', 'stage1_deferred', 'learned_suggestion', 'manual' (CHECK) |
| domain | TEXT | Correction domain (default 'general') |
| file_path | TEXT | Anchored transcript file (nullable) |
| line_number | INTEGER | 1-based line hint for anchor disambiguation |
| context_snippet | TEXT | Line content recorded at enqueue time (content check on resolve) |
| original_text | TEXT | Text as it stands in the transcript (NOT NULL) |
| suggested_text | TEXT | Pre-filled suggestion (nullable — unknown-entity questions) |
| kind | TEXT | 'entity', 'homophone', 'wording', 'unknown' (CHECK; drives priority) |
| evidence | TEXT | Why suspected / what the search ladder found |
| actions_json | TEXT | JSON action pack (file_edit / dict_add / append_note) |
| priority | INTEGER | Queue order, higher first (entity 100 > unknown 90 > homophone 30 > wording 10) |
| status | TEXT | 'pending', 'accepted', 'overridden', 'kept_original', 'skipped' (CHECK) |
| decided_at | TIMESTAMP | Verdict time |
| decided_by | TEXT | Reviewer name |
| decision_note | TEXT | Free-text note recorded with the verdict |
| resolved_text | TEXT | Final text (suggestion or override) |
| applied_at | TIMESTAMP | When the action pack executed |
| apply_log | TEXT | JSON per-action execution log |

**No UNIQUE constraint** — dedupe is enforced at enqueue time on
(file_path, original_text, suggested_text, domain, line_number) across ALL
statuses, so an answered question is never re-asked. `reopen` is a decision
verb, not a status: it reverts applied edits and sets the row back to 'pending'.

Indexes: `status`, `domain`, `priority DESC`, `file_path`.

Audit trail: enqueue/resolve/reopen write `audit_log` rows with
`entity_type='review_item'`.

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
VALUES ('错误词', '正确词', 'general', 'manual', 1.0, 'user');

-- Disable a correction
UPDATE corrections SET is_active = 0 WHERE id = ?;
```

## Schema Version

Check current version:
```sql
SELECT value FROM system_config WHERE key = 'schema_version';
```

For complete schema including indexes and constraints, see `scripts/core/schema.sql`.
