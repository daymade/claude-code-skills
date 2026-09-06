# Quick Reference

> Inside Claude/Codex, use Stage 1 plus Native AI Correction. Stage 2/3 examples
> elsewhere in the bundle are for agent-less API automation. Prefer the CLI over
> direct SQL writes; read `database_schema.md` before any custom query.

**Storage**: transcript-fixer uses SQLite database for corrections storage.

**Database location**: `~/.transcript-fixer/corrections.db`

## Quick Start Examples

### Adding Corrections via CLI

```bash
# Add a simple correction
uv run scripts/fix_transcription.py --add "巨升智能" "具身智能" --domain embodied_ai

# Add corrections for specific domain
uv run scripts/fix_transcription.py --add "奇迹创坛" "奇绩创坛" --domain general
uv run scripts/fix_transcription.py --add "矩阵公司" "初创公司" --domain general

# Measure the corpus BEFORE adding (real-meaning frequency + sampled context):
uv run scripts/fix_transcription.py --probe "候选误识词" --corpus /path/to/transcripts/
# Same evidence inline during the add (advisory, never blocks):
uv run scripts/fix_transcription.py --add "候选误识词" "正确词" --domain myproject --check-corpus --corpus /path/to/transcripts/
```

### Stage 1 with Sibling Domains

```bash
# One pass over several sibling project domains; --apply-domain trusts the union
uv run scripts/fix_transcription.py -i meeting.md --stage 1 --domain myproject,myproject-alt --apply-domain

# Native-pass trap-scan: every trap the domain context file documents, located
# with line + context (replaces the per-trap manual grep loop)
uv run scripts/fix_transcription.py --scan-traps --context-file ~/.transcript-fixer/contexts/myproject.md -i meeting.md
```

### Adding Corrections via SQL

```bash
sqlite3 ~/.transcript-fixer/corrections.db

# Insert corrections
INSERT INTO corrections (from_text, to_text, domain, source)
VALUES ('巨升智能', '具身智能', 'embodied_ai', 'manual');

INSERT INTO corrections (from_text, to_text, domain, source)
VALUES ('巨升', '具身', 'embodied_ai', 'manual');

INSERT INTO corrections (from_text, to_text, domain, source)
VALUES ('奇迹创坛', '奇绩创坛', 'general', 'manual');

# Exit
.quit
```

### Adding Context Rules via SQL

Context rules use regex patterns for context-aware corrections:

```bash
sqlite3 ~/.transcript-fixer/corrections.db

# Add context-aware rules
INSERT INTO context_rules (pattern, replacement, description, priority)
VALUES ('巨升方向', '具身方向', '巨升→具身', 10);

INSERT INTO context_rules (pattern, replacement, description, priority)
VALUES ('巨升现在', '具身现在', '巨升→具身', 10);

INSERT INTO context_rules (pattern, replacement, description, priority)
VALUES ('近距离的去看', '近距离地去看', '的→地 副词修饰', 5);

# Exit
.quit
```

### Adding Corrections via Python API

Save as `add_corrections.py` and run with `uv run add_corrections.py`:

```python
#!/usr/bin/env -S uv run
from pathlib import Path
from core import CorrectionRepository, CorrectionService

# Initialize service
db_path = Path.home() / ".transcript-fixer" / "corrections.db"
repository = CorrectionRepository(db_path)
service = CorrectionService(repository)

# Add corrections
corrections = [
    ("巨升智能", "具身智能", "embodied_ai"),   # non-word → term: safe
    ("巨升", "具身", "embodied_ai"),
    ("奇迹创坛", "奇绩创坛", "general"),        # garbled proper noun → correct name: safe
    # NOTE: a common real word that's only wrong in one context (an everyday
    # homophone, a word that clashes with a ticker/name) does NOT belong here —
    # a "general" rule on it corrupts every transcript where the word is correct.
    # Route those to the domain context file (domain_context_guide.md), and
    # person/project names to a project --domain, never "general".
]

for from_text, to_text, domain in corrections:
    service.add_correction(from_text, to_text, domain)
    print(f"✅ Added: '{from_text}' → '{to_text}' (domain: {domain})")

# Close connection
service.close()
```

## Bulk Import Example

Use the provided bulk import script for importing multiple corrections:

```bash
uv run scripts/examples/bulk_import.py
```

## Querying the Database

### View Active Corrections

```bash
sqlite3 ~/.transcript-fixer/corrections.db "SELECT from_text, to_text, domain FROM active_corrections;"
```

### View Statistics

```bash
sqlite3 ~/.transcript-fixer/corrections.db "SELECT * FROM correction_statistics;"
```

### View Context Rules

```bash
sqlite3 ~/.transcript-fixer/corrections.db "SELECT pattern, replacement, priority FROM context_rules WHERE is_active = 1 ORDER BY priority DESC;"
```

## Lookup and sidecar closure

```bash
# Every existing claim on a term (dictionary active/disabled, context rules, roster, queue)
uv run scripts/fix_transcription.py --lookup "候选词"

# Decide whether one finished transcript's review sidecars are closed (exit 0 closed / 1 open / 2 blocked)
uv run scripts/fix_transcription.py --close-sidecars --input "/absolute/canonical.md" --dry-run
uv run scripts/fix_transcription.py --close-sidecars --input "/absolute/canonical.md" \
  --decide-raw kept_original --by reviewer --note "子串误命中"   # record verdicts for rowless entries, then remove
```

## Review Queue

Uncertain corrections wait in a persistent queue for a human verdict (full
semantics: [review_queue_dashboard.md](review_queue_dashboard.md); storage
shape: `database_schema.md`).

```bash
# What's waiting? (priority-sorted: entity names first)
uv run scripts/fix_transcription.py --list-review

# This transcript only — use after the human says they finished marking
uv run scripts/fix_transcription.py \
  --list-review --review-file "/absolute/canonical.md" \
  --review-status all --json

# Inspect one item (evidence + proposed action pack)
uv run scripts/fix_transcription.py --show-review 12

# Verdicts
uv run scripts/fix_transcription.py --resolve-review 12 --decision accepted --by reviewer
uv run scripts/fix_transcription.py --resolve-review 12 --decision overridden --override-to "正确词"
uv run scripts/fix_transcription.py --resolve-review 12 --decision kept_original   # transcript was right
uv run scripts/fix_transcription.py --resolve-review 12 --decision reopen          # undo

# Enqueue from a JSON file or stdin
uv run scripts/fix_transcription.py --enqueue-review items.json --json
```

## See Also

- `references/file_formats.md` - Complete database schema documentation
- `references/script_parameters.md` - CLI command reference
- `SKILL.md` - Main user documentation
