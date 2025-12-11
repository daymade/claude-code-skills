# Dictionary Iteration Workflow

The core value of transcript-fixer is building a personalized correction dictionary that improves over time.

## The Core Loop

```
┌─────────────────────────────────────────────────┐
│  1. Fix transcript (manual or Stage 3)          │
│                    ↓                            │
│  2. Identify new ASR errors during fixing       │
│                    ↓                            │
│  3. IMMEDIATELY save to dictionary              │
│                    ↓                            │
│  4. Next time: Stage 1 auto-corrects these      │
└─────────────────────────────────────────────────┘
```

**Key principle**: Every correction you make should be saved to the dictionary. This transforms one-time work into permanent value.

## Workflow Checklist

Copy this checklist when correcting transcripts:

```
Correction Progress:
- [ ] Run correction: --input file.md --stage 3
- [ ] Review output file for remaining ASR errors
- [ ] Fix errors manually with Edit tool
- [ ] Save EACH correction to dictionary with --add
- [ ] Verify with --list that corrections were saved
- [ ] Next time: Stage 1 handles these automatically
```

## Save Corrections Immediately

After fixing any transcript, save corrections:

```bash
# Single correction
uv run scripts/fix_transcription.py --add "错误词" "正确词" --domain general

# Multiple corrections - run command for each
uv run scripts/fix_transcription.py --add "片片总" "翩翩总" --domain general
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
| `火星加速器` | Custom Chinese domain name (any valid name works) |

```bash
# Domain-specific correction
uv run scripts/fix_transcription.py --add "股价系统" "框架系统" --domain embodied_ai
uv run scripts/fix_transcription.py --add "片片总" "翩翩总" --domain 火星加速器
```

## Common ASR Error Patterns

Build your dictionary with these common patterns:

| Type | Examples |
|------|----------|
| **Homophones** | 赢→营, 减→剪, 被看→被砍, 营业→营的 |
| **Names** | 片片→翩翩, 亮亮→亮哥 |
| **Technical** | 巨升智能→具身智能, 股价→框架 |
| **English** | log→vlog |
| **Broken words** | 姐弟→结业, 单反→单访 |

## When GLM API Fails

If you see `[CLAUDE_FALLBACK]` output, the GLM API is unavailable.

Steps:
1. Claude Code should analyze the text directly for ASR errors
2. Fix using Edit tool
3. **MUST save corrections to dictionary** - this is critical
4. Dictionary corrections work even without AI

## Auto-Learning Feature

After running Stage 3 multiple times:

```bash
# Check learned patterns
uv run scripts/fix_transcription.py --review-learned

# Approve high-confidence patterns
uv run scripts/fix_transcription.py --approve "错误词" "正确词"
```

Patterns appearing ≥3 times at ≥80% confidence are suggested for review.

## Best Practices

1. **Save immediately**: Don't batch corrections - save each one right after fixing
2. **Be specific**: Use exact phrases, not partial words
3. **Use domains**: Organize corrections by topic for better precision
4. **Verify**: Always run --list to confirm saves
5. **Review suggestions**: Periodically check --review-learned for auto-detected patterns
