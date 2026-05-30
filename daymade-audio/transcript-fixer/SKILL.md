---
name: transcript-fixer
description: Corrects speech-to-text transcription errors using dictionary rules and AI-powered analysis. Builds personalized correction databases that learn from each fix. Triggers when working with ASR/STT output containing recognition errors, homophones, garbled technical terms, or Chinese/English mixed content. Also triggers on requests to clean up meeting notes, lecture transcripts, interview recordings, or any text produced by speech recognition. Use this skill even when the user just says "fix this transcript" or "clean up these meeting notes" without mentioning ASR specifically.
---

# Transcript Fixer

Two-phase correction pipeline: deterministic dictionary rules (instant, free) followed by AI-powered error detection. Corrections accumulate in `~/.transcript-fixer/corrections.db`, improving accuracy over time.

**What each phase is actually good at** (calibration, not a rule): the dictionary shines on *recurring* errors — product names, common homophones, anything you've corrected before — at zero cost and zero latency. But on a fresh database, on high-quality ASR (e.g. transcripts from a strong engine like Whisper, Otter, or Feishu / Tencent-Meeting), or in specialized domains (finance, medical, legal), the dictionary often matches almost nothing — the errors that remain are proper nouns and domain terms it has never seen. There, the AI pass does essentially all the real work. Treat Stage 1 as a cheap pre-filter for known repeats, not as the primary corrector, and don't be alarmed when it changes only a handful of lines on a clean transcript.

## Prerequisites

All scripts use PEP 723 inline metadata — `uv run` auto-installs dependencies. Requires `uv` ([install guide](https://docs.astral.sh/uv/getting-started/installation/)).

## Quick Start

```bash
# First time: Initialize database
uv run scripts/fix_transcription.py --init

# Single file
uv run scripts/fix_transcription.py --input meeting.md --stage 1

# Batch: multiple files in parallel (use shell loop)
for f in /path/to/*.txt; do
  uv run scripts/fix_transcription.py --input "$f" --stage 1
done
```

After Stage 1, Claude reads the output and fixes remaining ASR errors natively (no API key needed). The full method — triage by confidence, verify-don't-guess, second pass, needs-checking list — is in **Native AI Correction** below; read that section as the source of truth. For a quick, clean transcript it collapses to: read the whole thing → fix the obvious errors with sed → save reusable patterns to the dictionary.

See `references/example_session.md` for a concrete input/output walkthrough.

**Alternative: API batch processing** (for automation without Claude Code):
```bash
export GLM_API_KEY="<api-key>"  # From https://open.bigmodel.cn/
uv run scripts/fix_transcript_enhanced.py input.md --output ./corrected
```

## Core Workflow

Two-phase pipeline with persistent learning:

1. **Initialize** (once): `uv run scripts/fix_transcription.py --init`
2. **Add domain corrections**: `--add "错误词" "正确词" --domain <domain>`
3. **Phase 1 — Dictionary**: `--input file.md --stage 1` (instant, free)
4. **Phase 2 — AI Correction**: Claude reads output and fixes errors natively, or `--stage 3` with `GLM_API_KEY` for API mode
5. **Save stable patterns**: `--add "错误词" "正确词"` after each session
6. **Review learned patterns**: `--review-learned` and `--approve` high-confidence suggestions

**Domains**: `general`, `embodied_ai`, `finance`, `medical`, or custom (e.g., `legal`, `gaming`)
**Learning**: Patterns appearing ≥3 times at ≥80% confidence auto-promote from AI to dictionary

**After fixing, always save reusable corrections to dictionary.** This is the skill's core value — see `references/iteration_workflow.md` for the complete checklist.

### Dictionary Addition After Fixing

After native AI correction, review all applied fixes and decide which to save. Use this decision matrix:

| Pattern type | Example | Action |
|-------------|---------|--------|
| Non-word → correct term | 克劳锐→Claude, cloucode→Claude Code | ✅ Add (zero false positive risk) |
| Rare word → correct term | 拉行链→LangChain, 哈金费斯→Hugging Face | ✅ Add (verify it's not a real word first) |
| Person/company name ASR error | 卡帕西→Karpathy, Anthropics→Anthropic | ✅ Add (stable, unique) |
| Common word → context word | 争→蒸, affect→effect | ❌ Skip (high false positive risk) |
| Real brand → different brand | Xcode→Claude Code, Clover→Claude | ❌ Skip (real words in other contexts) |

Batch add multiple corrections in one session:
```bash
uv run scripts/fix_transcription.py --add "错误1" "正确1" --domain tech
uv run scripts/fix_transcription.py --add "错误2" "正确2" --domain business
# Chain with && for efficiency
```

## False Positive Prevention

Adding wrong dictionary rules silently corrupts future transcripts. **Read `references/false_positive_guide.md` before adding any correction rule**, especially for short words (≤2 chars) or common Chinese words that appear correctly in normal text.

## Native AI Correction (Default Mode)

When running inside Claude Code, use Claude's own language understanding for Phase 2 — on high-quality ASR this is where almost all the real correction happens. **Scale the effort to the transcript.** A short, clean recording with no proper nouns (a quick voice memo) just needs steps 1-3 plus one obvious-fix pass; skip the verification / second-pass / subagent / needs-checking machinery below, which earns its keep on long, multi-speaker, domain-heavy, or high-stakes transcripts. Don't turn a 10-second memo into a research project.

1. Run Stage 1 (dictionary) on all files (parallel if multiple)
2. Verify Stage 1 — diff against the original. If the dictionary introduced false positives, work from the **original** file instead and apply your edits there
3. Read the **entire** transcript before proposing corrections — later context disambiguates earlier errors (a name garbled near the start often becomes obvious later). For large files, read in chunks but finish the whole thing before deciding anything
4. **Triage each candidate error into one of three buckets** — this triage is the part that takes judgment:
   - **Confident fix** — non-words, obvious garbling, product-name variants you already recognize, or a homophone that's unambiguous in context (`their`→`there` where context forces it; `彭波`→`彭博` when every other mention already reads `彭博`). Apply directly (step 5).
   - **Needs verification** — a proper noun you can't confirm from context: a person / company / ticker / product / place name (a misheard drug name in a medical interview, a researcher's surname in a podcast, a ticker on an earnings call), or any term you can't point to a specific source for — even one you think you recognize ("I'm pretty sure" is exactly how wrong names slip in). **Search it, don't guess** — WebSearch, or a local grep if it's a project / personal entity. A confirmed result becomes a Confident fix; if the search *can't* confirm it, it drops to Uncertain. Batch these: collect the unique unknowns and look them up together, not one-by-one.
   - **Uncertain** — you suspect an error but can't confirm it even after searching (a syllable that maps to several real entities; a structurally broken sentence). **Leave the original text exactly as-is** and record it in the needs-checking list (step 7). A fluent-but-wrong "fix" is harder to catch downstream than an obvious garble — silence beats a confident guess.
5. Apply the confident fixes efficiently:
   - **Global replacements** (unique non-words like "克劳锐"→"Claude"): one `sed -i ''` with multiple `-e` flags
   - **Context-dependent** (a word that's only wrong in one context, like "争"→"蒸" in a distillation discussion): sed with a longer surrounding phrase for uniqueness, or the Edit tool
   - Re-grep each changed term afterward to confirm it landed and didn't hit look-alikes you meant to keep
6. **Second pass — catch what one read missed.** A single linear read reliably leaves residue: an idiom degraded into a near-homophone, a term wrong in just one spot among many correct ones, an acronym misheard as another. Always re-scan once for leftovers. For a long or high-stakes transcript, *also* spawn an independent subagent (Task) to re-read the corrected file cold — fresh eyes with no memory of your first pass catch what you've read past. Have it report suspected residuals **with line numbers**, then run each back through step-4 triage (fix / search / log). Task works when you're in the main context; if it isn't available — e.g. these instructions are themselves running inside a subagent, which can't spawn another — just do one more thorough independent re-read yourself. Never skip the second pass over a missing tool.
7. **Emit a needs-checking list** — in your chat summary to the human, not baked into the file — for everything still *Uncertain*: line number, the original text you left in place, what you suspect, and why you couldn't confirm it. This surfaces the few items that need a recording or source to resolve, instead of burying them or papering over them with guesses. If nothing is uncertain, say so.
8. Verify with diff against the file you actually edited (`diff <original> <your-working-file>`) — every change should trace back to a triage decision
9. Finalize: rename `*_stage1.md` → `*.md`, delete the original `.txt`
10. Save stable patterns to the dictionary (see "Dictionary Addition" below)
11. If you worked from `corrected_stage1.md`, strip any remaining Stage 1 false positives before finalizing

### Common ASR Error Patterns

AI product names are frequently garbled. These patterns recur across transcripts:

| Correct term | Common ASR variants |
|-------------|-------------------|
| Claude | cloud, Clou, calloc, 克劳锐, Clover, color |
| Claude Code | cloud code, Xcode, call code, cloucode, cloudcode, color code |
| Claude Agent SDK | cloud agent SDK |
| Opus | Opaas |
| Vibe Coding | web coding, Web coding |
| GitHub | get Hub, Git Hub |
| prototype | Pre top |

Person names and company names also produce consistent ASR errors across sessions — always add confirmed name corrections to the dictionary.

### Efficient Batch Fix Strategy

When fixing multiple files (e.g., 5 transcripts from one day):

1. **Stage 1 in parallel**: run all files through dictionary at once
2. **Read all files first**: build a mental model of speakers, topics, and recurring terms before fixing anything
3. **Compile a global correction list**: many errors repeat across files from the same session (same speakers, same topics)
4. **Apply global corrections first** (sed with multiple `-e` flags), then per-file context-dependent fixes
5. **Verify all diffs**, finalize all files, then do one dictionary addition pass

### Enhanced Capabilities (Native Mode Only)

- **Intelligent paragraph breaks**: Add `\n\n` at logical topic transitions
- **Filler word reduction**: "这个这个这个" → "这个"
- **Interactive review**: Corrections confirmed before applying
- **Context-aware judgment**: Full document context resolves ambiguous errors

### When to Use API Mode Instead

Use `GLM_API_KEY` + Stage 3 for batch processing, standalone usage without Claude Code, or reproducible automated processing.

### Legacy Fallback

When the script outputs `[CLAUDE_FALLBACK]` (GLM API error), switch to native mode automatically.

## Utility Scripts

**Timestamp repair**:
```bash
uv run scripts/fix_transcript_timestamps.py meeting.txt --in-place
```

**Split transcript into sections** (rebase each to `00:00:00`):
```bash
uv run scripts/split_transcript_sections.py meeting.txt \
  --first-section-name "intro" \
  --section "main::<verbatim line that starts the next section>" \
  --rebase-to-zero
```

**Word-level diff** (recommended for reviewing corrections):
```bash
uv run scripts/generate_word_diff.py original.md corrected.md output.html
```

## Output Files

- `*_stage1.md` — Dictionary corrections applied
- `*_corrected.txt` — Final version (native mode) or `*_stage2.md` (API mode)
- `*_对比.html` — Visual diff (open in browser)

## Database Operations

**Read `references/database_schema.md` before writing any custom query** — the column names are not what you'd guess. The correction columns are **`from_text` / `to_text`** (not `wrong_term`/`correct_term`, not `original`/`corrected`). Guessing column names is the most common way these queries fail with "no such column".

```bash
# Inspect corrections — real column names are from_text, to_text, domain
sqlite3 ~/.transcript-fixer/corrections.db "SELECT from_text, to_text, domain FROM active_corrections;"
# Count rules per domain
sqlite3 ~/.transcript-fixer/corrections.db "SELECT domain, COUNT(*) FROM active_corrections GROUP BY domain;"
# Schema version
sqlite3 ~/.transcript-fixer/corrections.db "SELECT value FROM system_config WHERE key='schema_version';"
```

## Stages

| Stage | Description | Speed | Cost |
|-------|-------------|-------|------|
| 1 | Dictionary only | Instant | Free |
| 1 + Native | Dictionary + Claude AI (default) | ~1min | Free |
| 3 | Dictionary + API AI + diff report | ~10s | API calls |

## Bundled Resources

**Scripts:**
- `fix_transcription.py` — Core CLI (dictionary, add, audit, learning)
- `fix_transcript_enhanced.py` — Enhanced wrapper for interactive use
- `fix_transcript_timestamps.py` — Timestamp normalization and repair
- `generate_word_diff.py` — Word-level diff HTML generation
- `split_transcript_sections.py` — Split transcript by marker phrases

**References** (load as needed):
- **Safety**: `false_positive_guide.md` (read before adding rules), `database_schema.md` (read before DB ops)
- **Workflow**: `iteration_workflow.md`, `workflow_guide.md`, `example_session.md`
- **CLI**: `quick_reference.md`, `script_parameters.md`
- **Advanced**: `dictionary_guide.md`, `sql_queries.md`, `architecture.md`, `best_practices.md`
- **Operations**: `troubleshooting.md`, `installation_setup.md`, `glm_api_setup.md`, `team_collaboration.md`

## Troubleshooting

`uv run scripts/fix_transcription.py --validate` checks setup health. See `references/troubleshooting.md` for detailed resolution.

## Next Step: Structure into Meeting Minutes

After correcting a transcript, if the content is from a meeting, lecture, or interview, suggest structuring it:

```
Transcript corrected: [N] errors fixed, saved to [output_path].

Want to turn this into structured meeting minutes with decisions and action items?

Options:
A) Yes — run /daymade-audio:meeting-minutes-taker (Recommended for meetings/lectures)
B) Export as PDF — run /daymade-docs:pdf-creator on the corrected text
C) No thanks — the corrected transcript is all I need
```
