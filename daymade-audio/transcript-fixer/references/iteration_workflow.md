# Dictionary Iteration Workflow

The core value of transcript-fixer is building a personalized correction dictionary that improves over time.

## The Core Loop

```
┌─────────────────────────────────────────────────┐
│  1. Fix transcript (Stage 1 + Native AI)        │
│                    ↓                            │
│  2. Identify new ASR errors during fixing       │
│                    ↓                            │
│  3. Route only reusable learning to its home    │
│                    ↓                            │
│  4. Next time: Stage 1 auto-corrects these      │
└─────────────────────────────────────────────────┘
```

**Key principle**: Every stable, reusable ASR correction you make should be saved to the dictionary. This transforms one-time work into permanent value without polluting the database.

## Workflow Checklist

Copy this checklist when correcting transcripts:

```
Correction Progress:
- [ ] Run Stage 1 with the explicit project domain + --apply-domain --json
- [ ] Read the domain context and the entire transcript
- [ ] Run Native AI Correction; leave uncertain text unchanged and enqueue it
- [ ] Run trap-scan and verify the final diff
- [ ] Fix every confirmed occurrence in the exact transcript file
- [ ] Classify each verdict: file-only / dictionary / roster / context
- [ ] Persist only stable reusable learning; leave one-off wording file-local
- [ ] Verify any reusable state you intentionally wrote
```

## Route Learning Immediately

After fixing a transcript, classify the correction before writing reusable state.
Use `--add` only for a stable recurring FROM→TO pattern with a controlled false-positive
surface. A rare sentence-local mishearing is already complete once the exact file is
fixed; adding it to the dictionary creates blast radius without future value.

```bash
# Single correction
uv run scripts/fix_transcription.py --add "错误词" "正确词" --domain general

# Multiple corrections - run command for each
uv run scripts/fix_transcription.py --add "<garbled-name>" "<canonical-name>" --domain <project>
uv run scripts/fix_transcription.py --add "姐弟" "结业" --domain general
uv run scripts/fix_transcription.py --add "自杀性" "自嗨性" --domain general
uv run scripts/fix_transcription.py --add "被看" "被砍" --domain general
uv run scripts/fix_transcription.py --add "单反过" "单访过" --domain general
```

## Verify Dictionary

Always verify corrections were saved:

```bash
# List all corrections in current domain
uv run scripts/fix_transcription.py --list

# Direct database query
sqlite3 ~/.transcript-fixer/corrections.db \
  "SELECT from_text, to_text, domain FROM active_corrections ORDER BY added_at DESC LIMIT 10;"
```

## Domain Selection

Choose the right domain for corrections:

| Domain | Use Case |
|--------|----------|
| `general` | Common ASR errors, names, general vocabulary |
| `embodied_ai` | 具身智能、机器人、AI 相关术语 |
| `finance` | 财务、投资、金融术语 |
| `medical` | 医疗、健康相关术语 |
| `示例项目` | Custom Chinese domain name (any valid name works) |

```bash
# Domain-specific correction
uv run scripts/fix_transcription.py --add "巨升智能" "具身智能" --domain embodied_ai
uv run scripts/fix_transcription.py --add "<garbled-name>" "<canonical-name>" --domain 示例项目
```

## Common ASR Error Patterns

Safe dictionary candidates are **non-words and garbled fragments** — a rule fires the same way every time with zero false-positive risk. Common-word homophones are NOT safe dictionary rules:

| Type | Examples | Home |
|------|----------|------|
| **Broken / non-words** | 姐弟→结业, 单反→单访, 巨升智能→具身智能 | Dictionary (`--add`) — safe |
| **English garbles** | log→vlog, cloucode→Claude Code | Dictionary — safe |
| **Person / project names** | `<garbled-name>`→`<canonical-name>` | Project `--domain` (isolated), not `general` |
| **Common-word homophones** | 减→剪, 赢→营, 营业→营的 | ❌ NOT the dictionary — the "from" side is a real word (减少/输赢/营业), so a blanket rule corrupts other sentences. Route to the domain **context file** with its disambiguating cue (`domain_context_guide.md`). |

Rule of thumb: if the "from" side is real text in some other reading, it does not belong in the dictionary. (Mirrors the decision matrix in [dictionary_identity_and_context.md](dictionary_identity_and_context.md) plus `false_positive_guide.md`.)

## When the optional GLM API route fails

The GLM API is an agent-less automation route, not the default workflow.

Steps:
1. Keep the original text unchanged; do not treat fallback output as corrected
2. When an agent is available, run Native AI Correction instead
3. Fix only evidence-backed ASR errors
4. **MUST save stable corrections to their dictionary/roster/context destination**

## Auto-Learning Feature

After repeated correction sessions (Native AI or the optional API route):

```bash
# Check learned patterns
uv run scripts/fix_transcription.py --review-learned

# Approve high-confidence patterns
uv run scripts/fix_transcription.py --approve "错误词" "正确词"
```

Patterns appearing ≥3 times at ≥80% confidence are suggested for review.

## Best Practices

1. **Classify immediately**: Fix the exact file now; persist only corrections that independently qualify as reusable
2. **Be specific**: Use exact phrases, not partial words
3. **Use domains**: Organize corrections by topic for better precision
4. **Verify**: Always run --list to confirm saves
5. **Review suggestions**: Periodically check --review-learned for auto-detected patterns

## What NOT to Save to Dictionary

Do **not** save these as reusable dictionary entries:

- Full-sentence deletions
- One-off section headers or meeting-specific boilerplate
- Context-only disambiguations such as `cloud -> Claude` when `cloud` can also be legitimate
- File-local cleanup after section splitting or timestamp rebasing
