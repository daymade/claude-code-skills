---
name: transcript-fixer
description: >-
  Corrects speech-to-text transcription errors using dictionary rules and Claude's built-in AI (no external API key required — Native AI Correction is the DEFAULT). Stage 3 API is a backup for automation without Claude Code. Builds personalized correction databases that learn from each fix, auto-loads person-name ASR variants from your people roster, and reads per-domain context files that prime the AI pass for context-dependent homophones. Triggers when working with ASR/STT output containing recognition errors, homophones, garbled technical terms, person-name errors, or Chinese/English mixed content. Also triggers on requests to clean up meeting notes, lecture transcripts, interview recordings, or any text produced by speech recognition. Use this skill even when the user just says "fix this transcript", "clean up these meeting notes", or mentions garbled names without invoking ASR specifically.
---

# Transcript Fixer

**默认模式：Claude 内置 AI（Native AI Correction）——无需任何外部 API key。**
Stage 1 字典纠错（免费、即时）→ Claude 自己读原文做智能纠错 → compound 进字典。
Stage 3 API 仅用于无 Claude Code 的自动化批处理场景（备选）。

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

# Trust ONE project domain's rules (recommended for batches): rules of the
# domain you explicitly pass via --domain apply at every risk level — they were
# hand-confirmed for this project's vocabulary, so domain match = trust. The
# roster and everything else keep safe-mode deferral. One pass instead of three
# (safe run -> review sidecar -> --apply-all rerun).
uv run scripts/fix_transcription.py --input meeting.md --stage 1 --domain myproject --apply-domain

# Apply EVERY risk level regardless of origin (the pre-safe-mode behavior).
# Higher false-positive risk — only when you've reviewed ALL loaded rules.
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

After Stage 1, Claude reads the output and fixes remaining ASR errors natively (no API key needed). The full method — triage by confidence, verify-don't-guess, second pass, needs-checking list — is in **Native AI Correction** below; read that section as the source of truth. For a quick, clean transcript it collapses to: read the domain's context file if one exists (`~/.transcript-fixer/contexts/<domain>.md`) → read the whole thing → fix the obvious one-off errors inline → `--add` any recurring or project-specific ones (especially names) to a `--domain` dictionary so they auto-fix next time (see "Project-Specific & Person-Name Corrections").

See `references/example_session.md` for a concrete input/output walkthrough.

### ⚠️ Stage 3 API — 备选方案（仅限无 Claude Code 的自动化批处理）

**如果你正在 Claude Code 里运行此 skill，跳过本节——直接用上面的 Stage 1 + Native AI Correction，不要跑 `--stage 3`。**
Stage 3 是给 CI/脚本/无 Claude 环境的批量自动化用的，需要额外配置 GLM API key。

```bash
# 备选: 仅限无 Claude Code 的批处理
export GLM_API_KEY="<api-key>"  # From https://open.bigmodel.cn/
uv run scripts/fix_transcript_enhanced.py input.md --output ./corrected
```

See `references/installation_setup.md` for the full config-file format and `references/glm_api_setup.md` for GLM endpoint details.

## Core Workflow

Two-phase pipeline with persistent learning:

1. **Initialize** (once): `uv run scripts/fix_transcription.py --init`
2. **Add domain corrections**: `--add "错误词" "正确词" --domain <domain>`
3. **Phase 1 — Dictionary**: `--input file.md --stage 1` (instant, free)
4. **Phase 2 — AI Correction（默认: Claude 内置 AI）**: Claude reads the Stage 1 output and fixes remaining errors natively — **this is the primary path, no API key needed**. The full method is under **Native AI Correction** below. 备选: `--stage 3` API 模式仅限无 Claude Code 的自动化批处理(需额外配置 GLM API key——见上方 §⚠️ Stage 3 API)。**在 Claude Code 内不要跑 `--stage 3`。**
5. **Save stable patterns**: `--add "错误词" "正确词"` after each session
6. **Review learned patterns**: `--review-learned` and `--approve` high-confidence suggestions

**Domains**: `general`, `embodied_ai`, `finance`, `medical`, `tech`, or custom (e.g., `legal`, `gaming`)
**Learning**: Repeated AI corrections are written to SQLite history; `--review-learned` turns high-confidence repeated patterns into pending suggestions, and `--approve FROM TO` promotes the exact suggestion into the dictionary.

### New safety & review commands

- **Safe mode is the Stage 1 default**: only low-risk (non-word, high-confidence) corrections auto-apply; medium/high-risk ones (common words, ≤2-char, real-word fragments) are tracked to `*_needs_review.md` instead of being applied silently. So **`Applied: 0` on a clean transcript is correct, not a bug** — the risky rules are waiting in `*_needs_review.md` for you or the AI pass to judge. Pass `--apply-all` to apply every risk level (the old behavior); `--review` is kept as a deprecated no-op. This reconnects the risk classifier that was being computed and then ignored — but it does NOT eliminate every false positive: rules whose `from_text` is a 4+ char valid phrase are still graded low and auto-apply (see `references/false_positive_guide.md` → "The 4+ char real-word blind spot").
- **Preview changes before applying**: `--dry-run` writes `*_dryrun.md` with every planned Stage 1 change and its risk level.
- **Always-on changes report**: `--changes-file` writes `*_changes.md` with before/after/risk for every correction (on by default in safe mode).
- **Machine-readable status for callers** (`--json`): prints ONE line of `{applied, deferred, output_path, needs_review_path, input_unchanged, review_enqueued}` on stdout (the human-readable log is routed to stderr for that run). Consumers read this instead of inferring a no-op from whether `*_stage1.md` exists on disk — `input_unchanged: true` (or `output_path: null`) **is** the authoritative no-op signal for a domain. This is a cross-skill contract (a caller's pre-classify chain consumes it); keep the field names and semantics stable (`review_enqueued` was added additively: how many safe-mode deferrals landed in the persistent review queue — see "Review Queue & Dashboard"). Without `--json` the human-readable output is unchanged.
- **Extract uncertain ASR tokens**: `--extract-uncertain -i file.md` writes `*_uncertain.md` with likely errors (short all-caps tokens, transliteration fragments, repeated words) without changing the file.
- **Load domain presets**: `--load-presets tech` imports a curated set of tech/Claude Code ASR corrections.
- **Report false positives**: `--report-false-positive "错误词" "正确词" -d domain` disables a bad dictionary rule and lowers its confidence.
- **Audit for risky rules**: `--audit` flags existing rules that look like false-positive sources (common words, ≤2-char, substring collisions, and — with jieba — 4+ char real-word phrases). **It is advisory: it surfaces candidates, it does NOT disable anything.** Disabling is a human decision — review each hit by hand and back up the DB first, because the audit cannot know your context and mislabels a large fraction of good rules (e.g. `GDP 5.5→GPT 5.5` looks wrong generically but is a correct fix for an AI-heavy user). See `references/false_positive_guide.md`.

### When called by another skill (cross-skill invocation contract)

This skill is often wired into another skill's ingest pipeline — e.g. a meeting-sync skill runs Stage 1 as a pre-classify hook before filing the transcript. That caller pipeline changes one assumption that bites silently, so a caller MUST follow this contract or it will run Stage 1, apply almost nothing, and report success.

**The failure mode (verified, reproducible).** Safe mode defers medium/high-risk corrections to `*_needs_review.md` rather than applying them. On a single file you edit by hand, that's fine — you read the sidecar next. But a caller pipeline typically runs transcript-fixer inside a `TemporaryDirectory` and reads only the corrected `transcript.txt` back out. **The `*_needs_review.md` sidecar lives in that temp dir and is deleted with it** — so 95%+ of the dictionary's corrections silently vanish while the run reports "complete." Real measurement on a 95-minute transcript with a 108-rule domain: safe mode applied **2/108**, deferred **106 to a sidecar that was immediately discarded**. The run looked clean; only ~2% of known corrections landed. The user then had to run transcript-fixer a second time by hand to get the other 98%.

**Caller rule — pass `--apply-domain` for hand-confirmed project domains.** The domains a pipeline wires in (its config `domains:` list) are exactly the domains whose rules a human already curated for that project's vocabulary. A domain match there is not a guess — it's a confirmed fix — so the pipeline should trust it the same way a batch run does:

```bash
# CORRECT for a caller pipeline — trust the configured project domains
uv run scripts/fix_transcription.py --input "$staged" --stage 1 \
  --domain "$domain" --apply-domain --json
```

With `--apply-domain`, the same 108-rule run applies **97/97 at low risk** instead of 2/108. The `general` domain (catch-all, lower curation) can stay in safe mode — only the project-specific domains earned full trust. If a caller cannot pass `--apply-domain`, it MUST instead read `deferred` from the `--json` status object and either persist the `*_needs_review.md` sidecar to a non-temp location for a downstream pass, or surface a non-zero `deferred` count to the user as a failure. Silently dropping deferred corrections and reporting success is the bug.

**The `--json` status line is the contract surface.** It prints `{applied, deferred, output_path, needs_review_path, input_unchanged}` on one stdout line. `deferred` is the number that must not be silently lost. `input_unchanged: true` / `output_path: null` is the authoritative "0 corrections this domain" signal — do NOT infer no-op from whether `*_stage1.md` exists on disk (the file-presence check is what once aborted the whole chain and dropped corrections). Keep these field names and semantics stable; a caller's pre-classify chain depends on them.

**The complementary side: keep the dictionary warm.** A caller pipeline that trusts `--apply-domain` only delivers value to the degree its project domain is populated. Every confirmed correction the downstream native pass makes should be `--add`ed back to that domain (`--add "ASR-variant" "correct" --domain <project>`), so the next ingest auto-fixes it and the native pass keeps getting lighter. A cold domain + `--apply-domain` still applies almost nothing — the fix is `--apply-domain` *and* ongoing `--add` discipline together.

**After fixing, always save reusable corrections to dictionary.** The skill's core value — see `references/iteration_workflow.md` for the complete checklist.

### Dictionary Addition After Fixing

After native AI correction, review all applied fixes and decide which to save. Use this decision matrix:

| Pattern type | Example | Action |
|-------------|---------|--------|
| Non-word → correct term | 克劳锐→Claude, cloucode→Claude Code | ✅ Add (zero false positive risk) |
| Rare word → correct term | 拉行链→LangChain, 哈金费斯→Hugging Face | ✅ Add (verify it's not a real word first) |
| Person/company name ASR error | 卡帕西→Karpathy, Anthropics→Anthropic | For **important recurring people**, add to your **people roster** instead (see "People Roster" above) — it carries relationship context and survives DB resets. For one-off names: ✅ `--add --domain` (stable, unique) |
| Common word → context word | 争→蒸, 减→剪, affect→effect | ❌ Never add as a rule — record the trap + its disambiguating cue in the domain's context file instead (see "Domain Correction Contexts") |
| Real brand → different brand | Xcode→Claude Code, Clover→Claude | ❌ Skip (real words in other contexts) |

Batch add multiple corrections in one session:
```bash
uv run scripts/fix_transcription.py --add "错误1" "正确1" --domain tech
uv run scripts/fix_transcription.py --add "错误2" "正确2" --domain business
# Chain with && for efficiency
```

## Review Queue & Dashboard (uncertain items → one-keystroke verdicts)

Confirmed corrections compound through the dictionary; **uncertain** ones used to
evaporate — the native pass listed them in chat (gone when the session ends),
safe-mode deferrals sat in a `*_needs_review.md` sidecar (discarded by temp-dir
callers), and learned suggestions waited behind a CLI nobody ran. The review
queue gives all three one persistent home in `corrections.db` (`review_items`),
and the dashboard makes deciding them nearly free — that friction is what stood
between "AI suspects an error" and "the dictionary learns the answer."

**Queue CLI** (all support `--json`):

```bash
# Enqueue uncertain items (native pass step 7 does this; '-' reads stdin)
uv run scripts/fix_transcription.py --enqueue-review items.json
# Inspect
uv run scripts/fix_transcription.py --list-review            # pending, priority-sorted
uv run scripts/fix_transcription.py --show-review 12         # full evidence + action pack
# Decide (agent path — humans use the dashboard)
uv run scripts/fix_transcription.py --resolve-review 12 --decision accepted --by reviewer
uv run scripts/fix_transcription.py --resolve-review 12 --decision overridden --override-to "正确词" --note "<evidence>"
uv run scripts/fix_transcription.py --resolve-review 12 --decision kept_original   # transcript was right
uv run scripts/fix_transcription.py --resolve-review 12 --decision reopen          # undo (reverts applied edits)
```

Each item carries: the original text (left untouched in the file), a pre-filled
suggestion, `kind` (`entity`/`unknown` lead the queue — they compound into
dictionary+roster; `homophone`/`wording` trail), the evidence your search ladder
produced, and an optional **action pack** executed on accept: `file_edit`
(replace in the transcript), `dict_add` (add to a `--domain` dictionary),
`append_note` (add a trap line to a domain context file). No action pack + a
file anchor = the default single `file_edit`.

**Fail-closed anchor guard**: the whole action pack is planned in memory
against the CURRENT file state (each edit validated against the content as the
pack's previous actions left it), and only when every action plans successfully
does anything reach disk — original text missing (file edited since enqueue),
ambiguous (multiple occurrences with no unique winner near the line hint), or a
drifted context (no nearby line matches the snippet recorded at enqueue) →
nothing is written, the CLI exits 2 with a `{"error": "re_anchor_needed"}`
status object, and the item stays pending. A wrong auto-edit is worse than a
missed one. Machine callers should parse the stdout `error` field rather than
the bare return code (argparse usage errors also exit 2). On `overridden`, only
retargeted `file_edit`s run — suggestion-specific `dict_add`/`append_note`
actions are dropped (they were planned for a suggestion the human rejected).

**Dashboard** (single reviewer, local):

```bash
uv run scripts/review-dashboard/server.py   # opens http://127.0.0.1:8767
```

Prodigy-style single-focus card: live file context with the anchor line
highlighted, suggestion pre-filled, evidence shown, keyboard-first —
`Q` play the utterance · `A` accept · `R` original-is-correct · `W` override
(type the right text) · `S` skip/can't judge · `Z` undo · `↑↓`/`J K` navigate
(verdict keys deliberately cluster on the left hand; the right hand stays on
the mouse). Env knobs: `REVIEW_DASHBOARD_PORT` (default 8767),
`REVIEW_DASHBOARD_NO_BROWSER=1` to skip auto-opening a browser tab.
Reads go straight to the DB (read-only); **every write shells out to the CLI**,
so the state machine, anchor guards, and audit log stay the single source of
truth, and agent (CLI) and human (page) are equal writers.

**Audio playback (`Q`)** — often the reviewer can't judge a garbled utterance
from text alone; hearing the original second settles it. A transcript opts in
by declaring its recording EXPLICITLY in frontmatter (no implicit directory
scanning — if the field is absent, the card simply has no play button):

```yaml
audio: /absolute/path/to/recording.m4a   # MUST be the SAME timeline the
                                         # transcript timestamps refer to (e.g.
                                         # the exact file fed to the ASR — a
                                         # 1.3x-speed ASR input pairs with a
                                         # transcript on the 1.3x timeline)
```

The dashboard derives the clip window from the speaker-timestamp lines
(`<speaker> HH:MM:SS.mmm`) around the anchor, streams the file with HTTP Range
(instant seek, no full download), and plays just that utterance; `± 3s` widens
the window when the cut lands mid-sentence. Verify the timeline pairing once
per recording source (`ffprobe` duration ≈ the transcript's last timestamp) —
a mismatched speed rate plays the wrong seconds everywhere.

**Stage 1 integration**: safe-mode deferrals are auto-enqueued
(`source: stage1_deferred`) at run time, so a caller discarding the sidecar no
longer loses them. Exception: an input under the OS temp dir is NOT enqueued
(the anchor would be a dead pointer once the staging copy vanishes) — the
`--json` `deferred` count still reports those to the caller, and the additive
`review_enqueued` field says how many landed in the queue.

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

## Domain Correction Contexts (per-domain AI priors)

The dictionary handles deterministic replacements; the people roster handles names. A third class of error can't safely live in either: **context-dependent homophones** — words that are only wrong in a particular discussion context. Think `减`→`剪` in a meeting about producing N video clips per day, or a finance call where a common word collides with a ticker nickname. A dictionary rule on a common word silently corrupts every other transcript, and a generic AI pass lacks the domain prior to fix it confidently — it either guesses wrong or leaves it for the human. (Real case: a transcript had four `减到 N 条` occurrences that all meant `剪到`; the AI pass suspected but wouldn't touch them without a domain prior, and the user had to fix them by hand.)

Domain context files close this gap. One markdown file per domain, in **user space** next to your `corrections.db` and `people.md` (never inside the skill bundle — it survives skill updates and keeps project knowledge private):

```
~/.transcript-fixer/contexts/<domain>.md
```

(If you relocated the config dir via `TRANSCRIPT_FIXER_CONFIG_DIR`, contexts live under that dir's `contexts/`.)

During native correction (see workflow below), read the transcript's domain context file before triaging. It should contain three things:

1. **One line of business context** — what this domain's recordings are usually about
2. **Known homophone traps** — each with the *contextual cue* that disambiguates it ("when the sentence is about producing/editing clips, `剪` is intended"), optionally with a dated real example
3. **Pointers to authoritative name sources** — the project's alias ledger, the relevant people-roster section, existing DB domains — so the verification ladder (step 4 below) knows where to look first

What must NOT go in a context file: hard replacement rules. `减→剪` as a rule belongs in NEITHER the context file NOR the dictionary — the file primes your judgment with priors and cues; it never authorizes blind replacement. Every fix still goes through the confidence triage below.

Maintenance loop (mirrors the dictionary's `--add` habit): when a native session surfaces a **context-dependent** recurring error — you fixed it here, and it'll recur in this domain's future transcripts — append it to the domain's context file with its disambiguating cue. Deterministic non-word/name fixes keep going to `--add --domain` / the roster as before.

Format and a worked template: `references/domain_context_guide.md`.

Note: contexts are consumed by the **native workflow** (the agent reads the file — no code involved). API mode (`--stage 2/3`, the backup channel) does not inject them yet; if that channel gets completed, the same files should feed its prompt.

## Native AI Correction (Default Mode)

When running inside Claude Code, use Claude's own language understanding for Phase 2 — on high-quality ASR this is where almost all the real correction happens. **Scale the effort to the transcript.** Don't turn a 10-second memo into a research project, but don't starve a 90-minute strategy call either. Pick the tier from the recording's shape, not your mood:

| Signal | **Fast tier** (minutes, not hours) | **Full tier** (the whole ladder earns its keep) |
|---|---|---|
| Length | short (≤ ~15 min / a few hundred lines) | long (30+ min / 1000+ lines) |
| Speakers | one or two, names you already know | 3+ speakers, or unfamiliar names |
| Vocabulary | plain language, no domain jargon | domain-heavy (finance/medical/legal/project codenames) or many proper nouns |
| Stakes | internal memo, throwaway | client-facing, committed to a shared repo, drives a decision |

- **Fast tier** — Stage 1 (`--apply-domain`), read the domain context file if one exists, read the whole thing once, fix the obvious one-off errors inline, `--add` any recurring/project-specific term to a `--domain`. **Skip:** the cross-domain name ladder, the second-pass subagent, the needs-checking ceremony. One linear pass, done.
- **Full tier** — everything below: full triage with the name-verification ladder, the independent second-pass subagent, and an explicit needs-checking list. The effort is justified because a long/domain-heavy transcript has both more errors *and* harder-to-confirm ones, and a wrong proper noun committed to a shared repo propagates.

A recording can be long but still fast-tier (two known speakers, plain language) or short but full-tier (a 5-minute call full of unfamiliar drug names that feed a report). Let the *vocabulary and stakes* call the tier, with length as a tiebreaker — that's where the real work is.

**Correction scope includes the metadata lines, not just the body.** A filed transcript usually carries ASR-derived metadata — a `Keywords:` line, frontmatter, a title — and those lines contain the *same* recognition errors as the spoken body (e.g. a `Keywords:` line still listing `克劳锐` when every body mention was already corrected to `Claude`). Fix them with the same rules. There is no "metadata is sacred, leave it" exception: the metadata is a search/grep surface too, and a keyword left in its ASR-garbled form will silently fail every future `grep Claude` while the body looks clean. When you re-grep the final file to confirm a correction landed, include the metadata lines in that check.

1. Run Stage 1 (dictionary) on all files (parallel if multiple)
2. Verify Stage 1 — diff against the original. If the dictionary introduced false positives, work from the **original** file instead and apply your edits there
3. **Load the domain's priors, then read the entire transcript.** If `~/.transcript-fixer/contexts/<domain>.md` exists for this transcript's domain, read it first — it primes which homophone traps to suspect and names the authoritative sources for step 4's ladder (see "Domain Correction Contexts" above). Then read the **entire** transcript before proposing corrections — later context disambiguates earlier errors (a name garbled near the start often becomes obvious later). For large files, read in chunks but finish the whole thing before deciding anything
4. **Triage each candidate error into one of three buckets** — this triage is the part that takes judgment. **First override two reflexes that repeatedly misfile names** (both are real, recurring failures — they send a fixable name straight to "ask the user"):
   - **Judge ASR errors by SOUND, not by glyphs.** Chinese ASR errors are homophone / near-homophone substitutions, so decide "same entity?" by pronunciation, not by whether the characters match exactly. A name that comes through as `X小Y` when the roster or dictionary already holds `X晓Y` (小/晓 are the same sound) is the **same person → Confident fix** — do NOT downgrade it to Uncertain just because 小≠晓 on the page. Same logic for a foreign name whose syllables all map by sound to a near-homophone transliteration. The dictionary having a sound-alike canonical is *evidence for* the fix, not a mismatch to be dismissed.
   - **A name you can't place defaults to the search ladder below, NOT to asking the user.** "Only the user knows this name" is the single most common wrong reflex. The canonical spelling is almost always already on this machine under a **different project's domain** — so you must query **all** domains at once (step 4.1's cross-domain SQL), not the one domain you happened to pass to `--stage 1`, which may be brand-new and empty. Querying only that one and giving up looks exactly like "I checked" while finding nothing that was right there.
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
      2. **Project delivery docs & the alias ledger** — cost reports, review sheets, deliverables, PKM notes for that project. These are human-written correct spellings, the strongest possible source. `grep -rl "<fragment>" <project-dir>` then read the hits. (The domain context file from step 3 usually names the project's alias ledger explicitly — start there.) **Read every name table the ledger holds, not just the one that looks like "the speaker list."** A project's people are almost always split across role-based tables — internal speakers, external collaborators, client-side, vendor/dealer-side, attendees — and the person you're chasing often lives in a sibling table you didn't open. If a name you end up confirming wasn't reachable from the context file's name-source manifest, that manifest is incomplete: add the missing table to it so the next run can't miss it. (See `domain_context_guide.md` Rule 6 for the failure case this prevents.)
      3. **Memory** (`~/.claude/.../memory/`) — project relationship maps and person profiles often record canonical names explicitly.
      4. **WebSearch** — only for genuinely public entities (a public-company ticker, a known researcher, a drug name). Skip for anything project-internal.

      Only after all of these strike out do you ask the user — and by then you've shown the entity isn't already recorded on this machine, which makes the ask legitimate. A confirmed result becomes a Confident fix; if the search *can't* confirm it, it drops to Uncertain. **Batch these**: collect the unique unknowns and run the ladder once per unique entity, not once per occurrence.
   - **Uncertain** — you suspect an error but can't confirm it even after searching (a syllable that maps to several real entities; a structurally broken sentence). **Leave the original text exactly as-is** and record it in the needs-checking list (step 7). A fluent-but-wrong "fix" is harder to catch downstream than an obvious garble — silence beats a confident guess.
5. Apply the confident fixes efficiently:
   - **Global replacements** (unique non-words like "克劳锐"→"Claude"): if it recurs across transcripts — most product/name garbles do — `--add` it to a `--domain` so it compounds to every future run; for a genuinely one-off term, one `sed -i ''` with multiple `-e` flags
   - **Context-dependent** (a word that's only wrong in one context, like "争"→"蒸" in a distillation discussion): sed with a longer surrounding phrase for uniqueness, or the Edit tool
   - Re-grep each changed term afterward to confirm it landed and didn't hit look-alikes you meant to keep
6. **Second pass — catch what one read missed.** A single linear read reliably leaves residue: an idiom degraded into a near-homophone, a term wrong in just one spot among many correct ones, an acronym misheard as another. Always re-scan once for leftovers. For a long or high-stakes transcript, *also* spawn an independent subagent (Task) to re-read the corrected file cold — fresh eyes with no memory of your first pass catch what you've read past. **The subagent's job is to *return a residual list*, not to re-narrate the transcript.** Give it an output format and a hard cap, because a subagent that thinks aloud line-by-line will blow its own context window before finishing (one real second-pass run on a 1131-line transcript hit the 32k token ceiling mid-scan and returned nothing usable). The correct prompt shape:
   - Scope it to exactly one file, forbid editing and cross-file grep.
   - Hand it the already-corrected terms as a do-not-re-report list (you fixed those; only *new* residuals are useful).
   - Demand a compact table only — `line | original ≤20 chars | suspected | one-line reason | confidence` — and tell it to stop after the list, no prose preamble, no per-line stream-of-consciousness, no re-deriving corrections it has already made.
   Then run each residual back through step-4 triage (fix / search / log). A second-pass subagent that returns 8 sharp rows beats one that returns 8000 tokens of narration every time. Task works when you're in the main context; if it isn't available — e.g. these instructions are themselves running inside a subagent, which can't spawn another — just do one more thorough independent re-read yourself. Never skip the second pass over a missing tool.
7. **Emit a needs-checking list AND enqueue it** — the chat summary alone evaporates when the session ends, so every *Uncertain* item gets dual-written: (a) in your chat summary to the human — line number, the original text you left in place, what you suspect, why you couldn't confirm it; (b) into the persistent review queue via `--enqueue-review items.json` (see "Review Queue & Dashboard" below) with the same fields plus a proposed action pack, so the human can one-keystroke-resolve it later in the dashboard — or a later agent session can close it with new evidence (`--resolve-review ID --decision … --note "<evidence>"`). Entity/name questions get `kind: entity` (they compound into the dictionary/roster, so they lead the queue); pure phrasing doubts get `kind: wording`. If nothing is uncertain, say so.
8. Verify with diff against the file you actually edited (`diff <original> <your-working-file>`) — every change should trace back to a triage decision
9. Finalize and archive:
   - **Primary path (recommended):** Re-run `--stage 1` on the original `file.md` — **plain, without `--apply-all`** (an explicit `--apply-all` always runs corrections and never finalizes, so a stale sidecar can't silently swallow the run). If `file_stage1.md` is newer than `file.md`, transcript-fixer automatically promotes it to `file.md` and removes the intermediate sidecars (`_stage1.md`, `_stage2.md`, `_dryrun.md`, `_changes.md`, `_needs_review.md`, `_uncertain.md`, `_对比.html`). This is the default way to finalize; it is atomic, preserves manual edits (it skips promotion when `file.md` is newer), and avoids macOS `mv` alias hazards.
   - **Native AI-correction mode** (you edited `file.md` directly — the default workflow above): `file.md` is already the final output. No promotion is needed or possible (the promote guard correctly skips it because `file.md` is newer than any sidecar), so just re-run `--stage 1` once to confirm. A **0-correction re-run writes no `_stage1.md`**, and when nothing was deferred it writes no report sidecars either — clean directory, `file.md` ready to archive. (If medium/high-risk dictionary matches remain in the text — e.g. ones you judged false positives and deliberately kept — `_changes.md`/`_needs_review.md` re-emerge each run listing them; that's the deferral report, not a failed finalize. Delete them once you've dispositioned the items.) If a re-run does find corrections, apply the ones you want into `file.md`, then re-run.
   - **Manual fallback** (only when you need full control, or `file.md` has been edited since Stage 1 ran): Save the corrected content back to the original `file.md`. (`file_stage1.md` is only a reference/diff; do not edit it as the final output.) Then `cp file.md` to `next/00-Transcripts/YYYY-MM/` (or your archive location) and delete the local sidecars with a Python one-liner:
     ```bash
     uv run python -c "
     from pathlib import Path
     stem = 'meeting'
     for suffix in ['_stage1.md','_dryrun.md','_changes.md','_needs_review.md','_uncertain.md','_stage2.md','_对比.html']:
         p = Path(f'{stem}{suffix}')
         p.exists() and p.unlink()
     "
     ```
   - Keep or move the original `.txt` to the archive if you want it; otherwise delete it.
   - Re-grep the final file for a correction you know you applied to confirm the corrected version landed.
10. **Filename hygiene — rename machine-generated gibberish before archiving.** A transcript whose filename is a raw ASR artifact, device tag, or opaque timestamp hash (`TX02_MIC021_20260720_095909_1.3x.md`, `soundcore Work_01-01 10-36.md`, `07-12-2026 20.07.md`) is not a useful artifact. Rename it to a human-readable form before the file enters a shared repo: `YYYY-MM-DD-HH-MM-<topic-or-speaker-summary>.md`, using Chinese or short English as appropriate to the project. The bar: a human should be able to identify the meeting from the filename alone. If the content clearly belongs to one business line, also encode that in the slug when the repo convention allows it.
11. Save stable patterns to the dictionary (see "Dictionary Addition" below)
12. Strip any remaining Stage 1 false positives from the final file before archiving

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
5. **Verify all diffs**, archive all final files and clean up sidecars, then do one dictionary addition pass

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

In native mode, edit the original file directly and use it as the final output; `*_stage1.md` is a disposable diff/reference (see the Native AI Correction workflow). **Re-running plain `--stage 1` (no `--apply-all`) auto-promotes `*_stage1.md` to the original file and cleans up sidecars** when it is newer than the input file; this is the recommended finalize path. `--apply-all` never takes the promote path — it always runs corrections. A **0-correction** run (clean transcript, or a native re-run after the input was edited) never writes `_stage1.md` (it would just duplicate the input); when nothing was deferred either, no report sidecars are written at all. When safe mode does defer medium/high rules, `_changes.md` and `_needs_review.md` still write — they are the deferral report.

## Database Operations

**Read `references/database_schema.md` before writing any custom query** — the column names are not what you'd guess. The correction columns are **`from_text` / `to_text`** (not `wrong_term`/`correct_term`, not `original`/`corrected`). Guessing column names is the most common way these queries fail with "no such column".

```bash
# Share domain dictionaries through JSON exports
uv run scripts/fix_transcription.py --export tech_corrections.json --domain tech
uv run scripts/fix_transcription.py --import tech_corrections.json --domain tech --merge

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
- **Workflow**: `iteration_workflow.md`, `workflow_guide.md`, `example_session.md`, `domain_context_guide.md` (format + template for per-domain context files)
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
