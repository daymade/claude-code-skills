---
name: transcript-fixer
description: Corrects speech-to-text transcription errors using dictionary rules and AI-powered analysis. Builds personalized correction databases that learn from each fix, and auto-loads person-name ASR variants from your people roster. Triggers when working with ASR/STT output containing recognition errors, homophones, garbled technical terms, person-name errors, or Chinese/English mixed content. Also triggers on requests to clean up meeting notes, lecture transcripts, interview recordings, or any text produced by speech recognition. Use this skill even when the user just says "fix this transcript", "clean up these meeting notes", or mentions garbled names without invoking ASR specifically.
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

# Single file — Stage 1 runs in SAFE MODE by default: only low-risk
# (non-word, high-confidence) corrections auto-apply. Medium/high-risk ones
# (common words, <=2-char, real-word fragments) are written to
# *_needs_review.md for you / the AI pass to judge, not applied silently.
uv run scripts/fix_transcription.py --input meeting.md --stage 1

# Apply EVERY risk level (the pre-safe-mode behavior). Higher false-positive
# risk — only when the dictionary's domain matches this transcript.
uv run scripts/fix_transcription.py --input meeting.md --stage 1 --apply-all

# Dry run: preview all Stage 1 changes (with risk levels) without writing *_stage1.md
uv run scripts/fix_transcription.py --input meeting.md --stage 1 --dry-run

# Extract likely ASR errors without applying any corrections
uv run scripts/fix_transcription.py --extract-uncertain -i meeting.md -o ./review

# Batch: multiple files in parallel (use shell loop)
for f in /path/to/*.txt; do
  uv run scripts/fix_transcription.py --input "$f" --stage 1
done
```

After Stage 1, Claude reads the output and fixes remaining ASR errors natively (no API key needed). The full method — triage by confidence, verify-don't-guess, second pass, needs-checking list — is in **Native AI Correction** below; read that section as the source of truth. For a quick, clean transcript it collapses to: read the whole thing → fix the obvious one-off errors inline → `--add` any recurring or project-specific ones (especially names) to a `--domain` dictionary so they auto-fix next time (see "Project-Specific & Person-Name Corrections").

See `references/example_session.md` for a concrete input/output walkthrough.

**Alternative: API batch processing** (for automation without Claude Code):
```bash
# Recommended: store the key in the config directory
# Edit ~/.transcript-fixer/config.json and set api.api_key
# Or override with an environment variable:
export GLM_API_KEY="<api-key>"  # From https://open.bigmodel.cn/
uv run scripts/fix_transcript_enhanced.py input.md --output ./corrected
```

See `references/installation_setup.md` for the full config-file format and `references/glm_api_setup.md` for GLM endpoint details.

## Core Workflow

Two-phase pipeline with persistent learning:

1. **Initialize** (once): `uv run scripts/fix_transcription.py --init`
2. **Add domain corrections**: `--add "错误词" "正确词" --domain <domain>`
3. **Phase 1 — Dictionary**: `--input file.md --stage 1` (instant, free)
4. **Phase 2 — AI Correction**: Claude reads output and fixes errors natively, or `--stage 3` with the API key configured in `~/.transcript-fixer/config.json` for API mode
5. **Save stable patterns**: `--add "错误词" "正确词"` after each session
6. **Review learned patterns**: `--review-learned` and `--approve` high-confidence suggestions

**Domains**: `general`, `embodied_ai`, `finance`, `medical`, `tech`, or custom (e.g., `legal`, `gaming`)
**Learning**: Patterns appearing ≥3 times at ≥80% confidence auto-promote from AI to dictionary

### New safety & review commands

- **Safe mode is the Stage 1 default**: only low-risk (non-word, high-confidence) corrections auto-apply; medium/high-risk ones (common words, ≤2-char, real-word fragments) are tracked to `*_needs_review.md` instead of being applied silently. So **`Applied: 0` on a clean transcript is correct, not a bug** — the risky rules are waiting in `*_needs_review.md` for you or the AI pass to judge. Pass `--apply-all` to apply every risk level (the old behavior); `--review` is kept as a deprecated no-op. This reconnects the risk classifier that was being computed and then ignored — but it does NOT eliminate every false positive: rules whose `from_text` is a 4+ char valid phrase are still graded low and auto-apply (see `references/false_positive_guide.md` → "The 4+ char real-word blind spot").
- **Preview changes before applying**: `--dry-run` writes `*_dryrun.md` with every planned Stage 1 change and its risk level.
- **Always-on changes report**: `--changes-file` writes `*_changes.md` with before/after/risk for every correction (on by default in safe mode).
- **Extract uncertain ASR tokens**: `--extract-uncertain -i file.md` writes `*_uncertain.md` with likely errors (short all-caps tokens, transliteration fragments, repeated words) without changing the file.
- **Load domain presets**: `--load-presets tech` imports a curated set of tech/Claude Code ASR corrections.
- **Report false positives**: `--report-false-positive "错误词" "正确词" -d domain` disables a bad dictionary rule and lowers its confidence.
- **Audit for risky rules**: `--audit` flags existing rules that look like false-positive sources (common words, ≤2-char, substring collisions, and — with jieba — 4+ char real-word phrases). **It is advisory: it surfaces candidates, it does NOT disable anything.** Disabling is a human decision — review each hit by hand and back up the DB first, because the audit cannot know your context and mislabels a large fraction of good rules (e.g. `GDP 5.5→GPT 5.5` looks wrong generically but is a correct fix for an AI-heavy user). See `references/false_positive_guide.md`.

**After fixing, always save reusable corrections to dictionary.** This is the skill's core value — see `references/iteration_workflow.md` for the complete checklist.

### Dictionary Addition After Fixing

After native AI correction, review all applied fixes and decide which to save. Use this decision matrix:

| Pattern type | Example | Action |
|-------------|---------|--------|
| Non-word → correct term | 克劳锐→Claude, cloucode→Claude Code | ✅ Add (zero false positive risk) |
| Rare word → correct term | 拉行链→LangChain, 哈金费斯→Hugging Face | ✅ Add (verify it's not a real word first) |
| Person/company name ASR error | 卡帕西→Karpathy, Anthropics→Anthropic | For **important recurring people**, add to your **people roster** instead (see "People Roster" above) — it carries relationship context and survives DB resets. For one-off names: ✅ `--add --domain` (stable, unique) |
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

## Project-Specific & Person-Name Corrections (`--domain` isolation)

The most important pattern for **recurring, project-specific errors** — person names, project jargon, product codenames — is the `--domain` flag. It is also the *answer* to the false-positive worry above: a person-name fix that's right **in your project** (a teammate's name the ASR keeps garbling) might collide with a real, differently-spelled person in someone else's transcript — so it must NOT go into the global (`general`) dictionary.

`--domain` makes such rules safe by isolating them:

```bash
# Add the rule under an isolated, project-named domain (not 'general')
uv run scripts/fix_transcription.py --add "<ASR-garbled-name>" "<correct-name>" --domain <project>
# Apply ONLY that domain's rules to this project's transcripts
uv run scripts/fix_transcription.py --input meeting.md --stage 1 --domain <project>
```

A rule added under `--domain <project>` only fires when you pass `--domain <project>` at correction time. Other projects (their own domain, or default `all`) are unaffected — so even a risky short-word / common-word person-name rule is safe, because it only fires inside the project where it's correct.

### Why this beats a one-off script (the core value, do not skip)

Facing a transcript — or a whole batch — full of the same ASR-garbled names, the tempting move is a quick `sed` / `python` find-and-replace. **Don't.** That is the single biggest anti-pattern with this skill:

- A throwaway script fixes *this batch* and the knowledge then evaporates: next batch, next week, next project, you rewrite it from scratch. It does not compound.
- The dictionary **compounds**: `--add` once, and every future transcript auto-corrects via `--stage 1 --domain <project>`. Wire that one command into the project's ingest step and the names are fixed forever, for free.
- The dictionary has false-positive protection (short-word warnings, the `audit` command, `--report-false-positive`); a raw `sed` has none and will silently corrupt look-alike words.

**Rule of thumb: recurring or project-specific error → `--add ... --domain <project>` (it compounds). Never a throwaway sed/python replace.** A one-off script is acceptable only for a genuinely one-time, never-recurring fix — and even then the dictionary is usually less effort.

ASR is especially unstable on Chinese names: one person can shatter into a dozen homophone variants (in one real project a single surname+given-name was seen as 13+ `[姓变体]×[名变体]` combinations). Capture every confirmed variant with `--add --domain <project>` so they all collapse to the canonical name on every future run.


### People Roster (long-term person-name SSOT)

For **important recurring people** whose names ASR consistently garbles
(coworkers, clients, family, workshop attendees), maintain a **people roster**
markdown file — the SSOT for person names — rather than adding them one-by-one
to the DB. Transcript-fixer auto-loads person-name corrections from this roster
at Stage 1 time when `people_roster_path` is set in
`~/.transcript-fixer/config.json`.

**Roster format** (canonical: `### Name` + `- **ASR 变体**: variant1, variant2`):
```markdown
### Holly Yang
- **ASR 变体**: Hollie, 浩磊

### Jo
- **ASR 变体**: Joe, Joe 老师
```

**Setup** (once):
```bash
# Edit ~/.transcript-fixer/config.json and add:
#   "paths": { "people_roster_path": "/path/to/people.md" }
```

After this, every `--stage 1` run automatically merges roster corrections
(in-memory only — never written to DB). The DB always wins on conflicts, so the
roster fills gaps without overriding hand-tuned entries. See
`core/people_roster.py` for the parser.

**When to use the roster vs `--add` to DB:**

| Person | Go to | Why |
|--------|-------|-----|
| Long-term recurring (coworker, client, family, workshop attendee) | **people.md** | SSOT with relationship context; survives DB resets |
| One-off / minor name | **DB** (`--add --domain`) | Quick, no context needed |

## Native AI Correction (Default Mode)

When running inside Claude Code, use Claude's own language understanding for Phase 2 — on high-quality ASR this is where almost all the real correction happens. **Scale the effort to the transcript.** A short, clean recording with no proper nouns (a quick voice memo) just needs steps 1-3 plus one obvious-fix pass; skip the verification / second-pass / subagent / needs-checking machinery below, which earns its keep on long, multi-speaker, domain-heavy, or high-stakes transcripts. Don't turn a 10-second memo into a research project.

1. Run Stage 1 (dictionary) on all files (parallel if multiple)
2. Verify Stage 1 — diff against the original. If the dictionary introduced false positives, work from the **original** file instead and apply your edits there
3. Read the **entire** transcript before proposing corrections — later context disambiguates earlier errors (a name garbled near the start often becomes obvious later). For large files, read in chunks but finish the whole thing before deciding anything
4. **Triage each candidate error into one of three buckets** — this triage is the part that takes judgment:
   - **Confident fix** — non-words, obvious garbling, product-name variants you already recognize, or a homophone that's unambiguous in context (`their`→`there` where context forces it; `彭波`→`彭博` when every other mention already reads `彭博`). Apply directly (step 5).
   - **Needs verification** — a proper noun you can't confirm from context: a person / company / ticker / product / place name (a misheard drug name in a medical interview, a researcher's surname in a podcast, a ticker on an earnings call), or any term you can't point to a specific source for — even one you think you recognize ("I'm pretty sure" is exactly how wrong names slip in). **Resolve it through a local-first search ladder before asking the user.** For project / personal entities the authoritative spelling almost always already lives on this machine, and WebSearch is near-useless on internal names — it returns wrong same-name people, or nothing — and worse, a fluent wrong guess becomes a confident fix that's hard to catch later. Search in this order:


	      0. **People roster** — `people.md` (or wherever `people_roster_path` in
	         `~/.transcript-fixer/config.json` points). This is your curated SSOT
	         of long-term recurring people with their ASR variants annotated under
	         `- **ASR 变体**:`. A garbled name that already maps to a canonical
	         person here — e.g. `Hollie`→`Holly Yang`, `丛老师`→`聪聪` — is a
	         Confident fix: apply immediately. **This one step replaces asking the
	         user for every name they've already documented.** Skip only for
	         transcripts whose speakers are confirmed NOT in the roster.
      1. **All domains of `corrections.db`, not just the current `--domain`.** The same entity shatters into different ASR variants across projects, and every prior fix already collapsed them to the canonical name — so the answer is often sitting in another domain you didn't pass to `--stage 1`. Checking only the current domain and giving up is the recurring failure mode.
         `sqlite3 ~/.transcript-fixer/corrections.db "SELECT from_text, to_text, domain FROM active_corrections WHERE to_text LIKE '%<fragment>%' OR from_text LIKE '%<fragment>%';"`
      2. **Project delivery docs** — cost reports, review sheets, deliverables, PKM notes for that project. These are human-written correct spellings, the strongest possible source. `grep -rl "<fragment>" <project-dir>` then read the hits.
      3. **Memory** (`~/.claude/.../memory/`) — project relationship maps and person profiles often record canonical names explicitly.
      4. **WebSearch** — only for genuinely public entities (a public-company ticker, a known researcher, a drug name). Skip for anything project-internal.

      Only after all of these strike out do you ask the user — and by then you've shown the entity isn't already recorded on this machine, which makes the ask legitimate. A confirmed result becomes a Confident fix; if the search *can't* confirm it, it drops to Uncertain. **Batch these**: collect the unique unknowns and run the ladder once per unique entity, not once per occurrence.
   - **Uncertain** — you suspect an error but can't confirm it even after searching (a syllable that maps to several real entities; a structurally broken sentence). **Leave the original text exactly as-is** and record it in the needs-checking list (step 7). A fluent-but-wrong "fix" is harder to catch downstream than an obvious garble — silence beats a confident guess.
5. Apply the confident fixes efficiently:
   - **Global replacements** (unique non-words like "克劳锐"→"Claude"): if it recurs across transcripts — most product/name garbles do — `--add` it to a `--domain` so it compounds to every future run; for a genuinely one-off term, one `sed -i ''` with multiple `-e` flags
   - **Context-dependent** (a word that's only wrong in one context, like "争"→"蒸" in a distillation discussion): sed with a longer surrounding phrase for uniqueness, or the Edit tool
   - Re-grep each changed term afterward to confirm it landed and didn't hit look-alikes you meant to keep
6. **Second pass — catch what one read missed.** A single linear read reliably leaves residue: an idiom degraded into a near-homophone, a term wrong in just one spot among many correct ones, an acronym misheard as another. Always re-scan once for leftovers. For a long or high-stakes transcript, *also* spawn an independent subagent (Task) to re-read the corrected file cold — fresh eyes with no memory of your first pass catch what you've read past. Have it report suspected residuals **with line numbers**, then run each back through step-4 triage (fix / search / log). Task works when you're in the main context; if it isn't available — e.g. these instructions are themselves running inside a subagent, which can't spawn another — just do one more thorough independent re-read yourself. Never skip the second pass over a missing tool.
7. **Emit a needs-checking list** — in your chat summary to the human, not baked into the file — for everything still *Uncertain*: line number, the original text you left in place, what you suspect, and why you couldn't confirm it. This surfaces the few items that need a recording or source to resolve, instead of burying them or papering over them with guesses. If nothing is uncertain, say so.
8. Verify with diff against the file you actually edited (`diff <original> <your-working-file>`) — every change should trace back to a triage decision
9. Finalize: rename `*_stage1.md` → `*.md`, delete the original `.txt`. **Use `/bin/mv -f`, not a bare `mv`** — on macOS `mv` is commonly aliased to `mv -i`, which prompts before overwriting an existing target and, with no interactive answer, defaults to "no" and **skips the move while still exiting 0**. A bare `mv … && echo done` then reports success while the un-corrected file silently survives as the final output. After renaming, re-grep the final file for a correction you know you applied (e.g. a fixed name) to confirm the corrected version is what landed.
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

Person names and company names also produce consistent ASR errors across sessions — always add confirmed name corrections to the dictionary, and for project-specific names use `--domain <project>` to keep them isolated (see "Project-Specific & Person-Name Corrections").

### Efficient Batch Fix Strategy

When fixing multiple files (e.g., 5 transcripts from one day):

1. **Stage 1 in parallel**: run all files through dictionary at once
2. **Read all files first**: build a mental model of speakers, topics, and recurring terms before fixing anything
3. **Compile a global correction list**: many errors repeat across files from the same session (same speakers, same topics). **If an error recurs — especially a person name or project term — `--add` it to a project `--domain` (see "Project-Specific & Person-Name Corrections" above) instead of replacing it inline; it then auto-fixes every future file, not just this batch.**
4. **Apply the remaining one-off corrections** (sed with multiple `-e` flags, for genuinely non-recurring fixes only), then per-file context-dependent fixes
5. **Verify all diffs**, finalize all files, then do one dictionary addition pass

### Parallel via Dynamic Workflow (large batches)

For a large batch (10+ files), a Dynamic Workflow — one subagent per file, running in parallel — is faster than a shell loop and gives each file full AI attention. Four rules earned the hard way; skipping any of them has caused real damage:

1. **Hardcode the file list into the script — don't pass it through `args`.** A Workflow `args` array of strings containing non-ASCII characters, brackets, or path separators can silently arrive empty: the script sees zero files, no agents spawn, and it exits instantly with something like "no files". Plain alphanumeric tokens pass fine, but file paths should go straight into a `const FILES = [...]` literal in the script body, guarded with `if (!FILES.length) return`.

2. **Scope each agent to exactly one file, and forbid cross-file `grep -r` / `sed` in its prompt.** Left unconstrained, an agent will turn a local fix ("this garbled term → correct term, here") into a global search-and-replace and edit unrelated files that were never part of the batch. State the single file path and an explicit "only edit this one file" instruction.

3. **After the batch, verify with `git diff` before trusting it** (works when the files are under version control):
   - `git diff --name-only` against your intended list — this catches any agent that strayed outside its assigned file. `git checkout` to revert the strays.
   - `grep` the deleted (`-`) lines for invariants that must never change. For speaker-diarized transcripts, that invariant is the **speaker-label lines** — an ASR fix should only ever touch spoken content, never alter or reassign who-said-what. Confirm zero speaker lines were deleted or changed.

4. **Run the aggregated dictionary suggestions through the false-positive filter before saving any of them.** Parallel agents collectively propose far more rules than are safe — and they don't see each other's suggestions, so duplicates and overreach pile up. Keep only unambiguous **non-word → correct-term** mappings. Drop anything whose "from" side is a real word in some context: a common word, or a term that's only wrong inside one domain. A global dictionary rule on a real word silently corrupts every future transcript — exactly what `references/false_positive_guide.md` warns about. (In one real batch, ~80 raw suggestions collapsed to ~18 safe ones after this filter.)

### Enhanced Capabilities (Native Mode Only)

- **Intelligent paragraph breaks**: Add `\n\n` at logical topic transitions
- **Filler word reduction**: "这个这个这个" → "这个"
- **Interactive review**: Corrections confirmed before applying
- **Context-aware judgment**: Full document context resolves ambiguous errors

### When to Use API Mode Instead

Use the API key configured in `~/.transcript-fixer/config.json` (or the `GLM_API_KEY` / `ANTHROPIC_API_KEY` environment variable for temporary overrides) + Stage 3 for batch processing, standalone usage without Claude Code, or reproducible automated processing.

### API Fallback

When the GLM API is unavailable after retries, the script keeps the original text unchanged and prints a clear warning. If you need AI correction without an external API, run inside Claude Code and use native mode.

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

**Full multi-format diff report** (Markdown summary + unified diff + HTML + inline markers):
```bash
uv run scripts/generate_diff_report.py \
  original.md \
  original_stage1.md \
  original_stage2.md \
  -o ./diff_reports
```

## Output Files

- `*_stage1.md` — Dictionary corrections applied
- `*_stage2.md` — AI-corrected version (API mode)
- `*_changes.md` — Stage 1 report with risk levels and line context (written by default in safe mode, or with `--changes-file`)
- `*_needs_review.md` — Medium/high-risk corrections deferred in safe mode (the default)
- `*_dryrun.md` — Preview of all Stage 1 changes, annotated with which risk levels a real run would apply
- `*_uncertain.md` — Likely ASR errors extracted by `--extract-uncertain`
- `*_对比.html` — Visual diff (open in browser)

In native mode, finalize by renaming `*_stage1.md` to your desired output name (see the Native AI Correction workflow).

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
- `generate_diff_report.py` — Multi-format comparison report (Markdown, unified diff, HTML, inline markers)
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
