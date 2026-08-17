---
name: transcript-fixer
description: >-
  Corrects speech-to-text transcription errors using dictionary rules and Claude's built-in AI (no external API key required — Native AI Correction is the DEFAULT). Stage 1 alone is not the job. Stage 3 API is a backup for automation without Claude Code. Builds personalized correction databases that learn from each fix, auto-loads person-name ASR variants from your people roster, and reads per-domain context files that prime the AI pass for context-dependent homophones. Triggers when working with ASR/STT output containing recognition errors, homophones, garbled technical terms, person-name errors, or Chinese/English mixed content. Also triggers on requests to clean up meeting notes, lecture transcripts, interview recordings, or any text produced by speech recognition. Use this skill even when the user just says "fix this transcript", "clean up these meeting notes", or mentions garbled names without invoking ASR specifically.
---

# Transcript Fixer

**默认模式：Claude 内置 AI（Native AI Correction）——无需任何外部 API key。**
Stage 1 字典纠错（免费、即时）→ Claude 自己读原文做智能纠错 → compound 进字典。
Stage 3 API 仅用于无 Claude Code 的自动化批处理场景（备选）。

Two-phase correction pipeline: deterministic dictionary rules (instant, free) followed by AI-powered error detection. Corrections accumulate in `~/.transcript-fixer/corrections.db`, improving accuracy over time.

**What each phase is actually good at** (calibration, not a rule): the dictionary shines on *recurring* errors — product names, common homophones, anything you've corrected before — at zero cost and zero latency. But on a fresh database, on high-quality ASR (e.g. transcripts from a strong engine like Whisper, Otter, or Feishu / Tencent-Meeting), or in specialized domains (finance, medical, legal), the dictionary often matches almost nothing — the errors that remain are proper nouns and domain terms it has never seen. There, the AI pass does essentially all the real work. Treat Stage 1 as a cheap pre-filter for known repeats, not as the primary corrector, and don't be alarmed when it changes only a handful of lines on a clean transcript.

## Prerequisites

All scripts use PEP 723 inline metadata — `uv run` auto-installs dependencies. Requires `uv` ([install guide](https://docs.astral.sh/uv/getting-started/installation/)).

The commands below use relative script paths (`scripts/<name>.py`), so they only work from the skill's own directory — and in agent harnesses the shell's working directory resets between calls, which surfaces as `Failed to spawn: scripts/fix_transcription.py` on the very first command. **Take the skill directory from the "Base directory for this skill" line printed when this skill was invoked**, and either `cd` there in the same command or prefix every script path with it. Do not rely on `$CLAUDE_SKILL_DIR` — it is unset in at least some harnesses (verified 2026-08), so a command built on it fails with the same error it was meant to prevent. If you no longer have the invocation line, `find -L ~/.claude ~/.codex -name SKILL.md -path '*transcript-fixer*'` locates the bundle — but it returns dozens of hits — every installed *version*, plus backups, staging copies and pre-edit snapshots — and the first is not the newest. Skip any path containing `skill-before`, `-workspace`, `source-sync-backups`, `.tmp` or `.staging`. Among what remains, prefer the highest version directory; some installs (a marketplace checkout, another agent's skills dir) carry no version at all, so if you end up choosing between those, take the one with the newest mtime and sanity-check it against this file's content before trusting it.

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

# Sibling domains load together (comma-separated) — one project's vocabulary
# often lives in several domains that grew at different times (myproject,
# myproject-alt, ...), and a transcript that straddles them should be fixed in
# ONE pass, not one rerun each. --apply-domain trusts the whole union.
uv run scripts/fix_transcription.py --input meeting.md --stage 1 --domain myproject,myproject-alt --apply-domain

# Which domains does this project even have? A 0-correction run prints the
# hint listing every OTHER domain with its rule count — read it, then rerun
# with the siblings added. (Write commands like --add stay single-domain.)

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

# ⚠️ STOP — Stage 1 alone is NOT the job. It is the pre-filter, not the
# corrector: on clean ASR (Feishu / Tencent / Whisper) the dictionary often
# matches almost nothing, and the Native AI pass below does essentially all
# the real work. Reporting "transcript clean" after Stage 1 alone is the
# recurring failure this skill exists to prevent (real case, 2026-08: an
# ingest pipeline ran Stage 1 on a 73-min transcript, got 0 hits, declared
# it clean — 54 errors were later found by the native pass it skipped).
# "The dictionary applied N fixes" does not change this either.
# "Done" = Stage 1 → Native AI Correction → --add the confirmed fixes.
```

After Stage 1, Claude reads the output and fixes remaining ASR errors natively (no API key needed) — **this is the primary path, and skipping it is not a valid shortcut, even for a quick transcript** (a "quick, clean" transcript is exactly where the dictionary is weakest and the native read matters most). The full method — triage by confidence, verify-don't-guess, second pass, needs-checking list — is in **Native AI Correction** below; read that section as the source of truth. For a quick, clean transcript it collapses to: read the domain's context file if one exists (`~/.transcript-fixer/contexts/<domain>.md`) → read the whole thing → fix the obvious one-off errors inline → `--add` any recurring or project-specific ones (especially names) to a `--domain` dictionary so they auto-fix next time (see "Project-Specific & Person-Name Corrections"). **If you are finishing after Stage 1, name explicitly why the native pass does not apply — "the pipeline ran the script" is not a reason.** The only valid exemptions: the human user explicitly scoped this one run to the dictionary pass (a caller pipeline's standing "run Stage 1" wiring is NOT this exemption — see "When called by another skill" below), or you have evidence the native pass already ran on this transcript (a dated note in the file or the ingest log). "The transcript looked short/clean", "the dictionary already applied N fixes", and "I'm in a hurry" are not exemptions — they are the failure.

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
- **Report false positives**: `--report-false-positive "<from_text>" "<to_text>" -d domain` disables a bad dictionary rule (pass the rule's stored from→to pair — for a false-positive rule that's the reverse of semantic wrong→right; see Native AI Correction step 2).
- **Audit for risky rules**: `--audit` flags existing rules that look like false-positive sources (common words, ≤2-char, substring collisions, and — with jieba — 4+ char real-word phrases). **It is advisory: it surfaces candidates, it does NOT disable anything.** Disabling is a human decision — review each hit by hand and back up the DB first, because the audit cannot know your context and mislabels a large fraction of good rules (e.g. `GDP 5.5→GPT 5.5` looks wrong generically but is a correct fix for an AI-heavy user). See `references/false_positive_guide.md`.

### When called by another skill (cross-skill invocation contract)

This skill is often wired into another skill's ingest pipeline — e.g. a meeting-sync skill runs Stage 1 as a pre-classify hook before filing the transcript. That caller pipeline changes one assumption that bites silently, so a caller MUST follow this contract or it will hit one of two verified failures: it will run Stage 1, apply almost nothing, and report success (deferred corrections silently discarded — the next section) — or it will run Stage 1, skip the native pass entirely, and report the transcript clean (the "**Stage 1 is the whole script call**" paragraph below). **This contract has TWO MUSTs; complying with only the first one ships the second failure with a false sense of having done it right.**

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

**Stage 1 is the whole script call — it must not be the whole job.** The contract above keeps Stage 1 from silently dropping its own corrections; it says nothing about the pass that does most of the work on a clean transcript. A caller that stops after Stage 1 ships a transcript the native AI pass never read and reports it as clean. So the caller's ingest step MUST either run the Native AI Correction pass itself (hand the filed transcript to an agent (possibly this one) with **this skill loaded** — the skill, not just the script path; agent-less CI automation completes through the Stage 3 API pass above instead) or surface "Stage 1 only" to the user as an incomplete state, never as success. And note the trap in how this skill gets wired: a caller that references it by script path alone (e.g. a `transcript_fixer.script_path` config entry) never loads this file, so every contract in it — this one included — is invisible to that run. Wiring the script path without wiring the skill is exactly the configuration that produced the 2026-08 "0 hits, declared clean, 54 errors missed" incident.

**After fixing, always save reusable corrections to dictionary.** The skill's core value — see `references/iteration_workflow.md` for the complete checklist.

### Dictionary Addition After Fixing

After native AI correction, review all applied fixes and decide which to save. Use this decision matrix:

| Pattern type | Example | Action |
|-------------|---------|--------|
| Non-word → correct term | 克劳锐→Claude, cloucode→Claude Code | ✅ Add (zero false positive risk) |
| Rare word → correct term | 拉行链→LangChain, 哈金费斯→Hugging Face | ✅ Add (verify it's not a real word first) |
| Person/company name ASR error | 卡帕西→Karpathy, Anthropics→Anthropic | For **important recurring people**, add to your **people roster** instead (see "People Roster" below) — it carries relationship context and survives DB resets. For one-off names: ✅ `--add --domain` (stable, unique) |
| Common word → context word | 争→蒸, 减→剪, affect→effect | ❌ Never add as a rule — record the trap + its disambiguating cue in the domain's context file instead (see "Domain Correction Contexts") |
| Real brand → different brand | Xcode→Claude Code, Clover→Claude | ❌ Skip (real words in other contexts) |
| Real name → different real name | `李明`→`黎明` (two real people in different projects) | ❌ Never a rule — same hazard as real brand → brand, but it corrupts a real person's name. Domain context trap with a disambiguating cue instead (see the user-verdict refinements in Native AI Correction step 4) |

**The middle path, and it applies to exactly one of the ❌ rows.** The
*common word → context word* row (`争`→`蒸`) forbids a **bare** common word as a
rule, because it fires everywhere the word is legitimately used. It does not
forbid the same fix carried by enough surrounding text that the phrase only
occurs in the mishearing — `村里商量` → `<name>商量` is defensible where bare
`村里` would be reckless. **The *real name → different real name* row is not
relaxed by this and never anchored into the dictionary**: keep it in the domain
context file as the row itself says.

That exclusion holds because **the validator cannot be trusted either way on a
person's name.** `--add` runs a jieba check that warns when the FROM side
decomposes into all-known words, and whether a name counts as "known" is an
accident of jieba's dictionary: measured, `李娜商量` warns (`李娜` has frequency
438) while `张伟商量` is silent (`张伟` is out-of-vocabulary, frequency 0). So a
name-anchored rule that passes quietly tells you nothing, and one that warns
tells you nothing either. With no reliable signal on the class whose blast radius
is a real person's name in every future transcript, the row stays out. (The same
reasoning excludes the *real brand → different brand* row: `Xcode`→`Claude Code`
is right in one project and destroys a build log in the next, and no validator
knows which one you are in.)

**Warning versus error, because they end differently.** A `valid_phrase` warning
means *review this by hand*, **not** *it was rejected* — the rule is added and
`--add` exits 0. `common_word` and `both_common` are **errors**: `--add` exits 1
and writes nothing, and `--force` is the only way past. `substring_collision`
is *both*, depending on which branch fires — a hit against the curated collision
map is an error, while the broader dynamic check is only a warning and the rule
lands. So read the exit status rather than the noise: a loud add may have
succeeded, and a rule you believe you saved may not be in the database at all.
Reach for `--force` only after reading *which* check objected, since it silences
the blocking ones too.

One caveat decides whether an anchored rule is worth adding: anchor to a
**recurring collocation**, not to a one-off sentence fragment. A snippet of one
particular sentence never matches again — it costs a dictionary row, compounds
nothing, and dead rows are what make a domain slow to load and hard to audit.
When even a collocation would be too narrow, the trap belongs in the domain
context file with its disambiguating cue.

**Measure the corpus before you add — the validators can't see your project.**
The built-in safety checks answer "is this a real word in Chinese"; they cannot
answer the question that actually decides a project-domain rule: *"when this
word appears in THIS project's transcripts, is it ever the real meaning?"* That
is empirical, and the evidence is one command away:

```bash
# How does this term actually appear across the project's transcripts?
uv run scripts/fix_transcription.py --probe "候选误识词" --corpus /path/to/transcripts/

# Or probe as part of the add itself (prints the evidence before writing):
uv run scripts/fix_transcription.py --add "候选误识词" "正确词" --domain myproject \
  --check-corpus --corpus /path/to/transcripts/
```

The probe prints per-file counts plus sampled context windows, with the
decision rule attached: every sampled occurrence an ASR error → a bare rule is
safe; any real meaning present → anchored form, or don't add (record the trap
in the domain context file instead); zero occurrences → a bare rule is
zero-risk but compounds nothing. The surprise this kills: intuition says "this
is obviously an error form", and a 30-second sweep finds the word carrying
perfectly real meanings all over the corpus — or the reverse, a "real word"
whose every single in-corpus occurrence is the mishearing, making the bare
rule safe where a word-checker would have scared you off it.

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
(One scope note: the context check only runs when the original occurs MORE
THAN ONCE — a unique occurrence has no look-alike to refuse, so a
single-occurrence edit applies without consulting the snippet.)

**When the guard refuses: `--reanchor-review` repairs the item.** A refusal is
not a dead end and NOT a cue to hand-edit the file around the queue — that
leaves the item pending forever and the edit unaudited. Run the re-anchor and
then verdict again:

```bash
uv run scripts/fix_transcription.py --reanchor-review <id> [<id>...]
# file itself is gone (moved/renamed/cleaned)? add search root(s):
uv run scripts/fix_transcription.py --reanchor-review <id> --reanchor-root <dir-with-transcripts>
```

Two drift shapes are repaired against current disk state, both fail-closed:
**context/line drift** (file edited since enqueue — re-locates `original` in
the file, preferring lines that still match the RECORDED context snippet over
mere distance, refreshes line + verbatim context) and **file gone** (searches
the recorded parent dir plus every `--reanchor-root` for `*.md` containing
`original`; exactly one candidate re-points the anchor, zero changes nothing,
and multiple asks for `--reanchor-to FILE` — the explicit-target form, which
is itself refused if `original` is not in it). After a successful re-anchor,
the guard's context check passes and `A`/`W`/CLI resolve proceed normally
(explicit action packs get their `file_edit` path rewritten to the new file).
The refusal messages themselves name this command. (Root-caused 2026-08-03: an item
enqueued with a PARAPHRASED context could never be verdicted — the human's
override died at the guard and the file got hand-edited around the queue
before this command existed.)

**Promote each `decision_note`; the queue only stores it.** The dashboard's
备注 field and the CLI's `--note` record the reviewer's reason, but neither
turns that reason into a reusable rule. After a review batch, inspect the full
queue JSON:

```bash
uv run scripts/fix_transcription.py --list-review --review-status all --json
```

The human-readable list never prints `decision_note`. Human-readable
`--show-review` prints it only after an item leaves `pending`; JSON always
carries the field, including on an item that `reopen` returned to `pending`.
Inspect every item with a non-empty note, regardless of status, and do not
pre-project a field list that could discard a field the reviewer supplied.

Route the note by meaning rather than by verdict:

| The note says | Promote it to | Do not |
|---|---|---|
| an apparent error is an intentional, context-dependent substitution | the domain context file, with the cue that distinguishes when to preserve it | use `--add`, which would rewrite the text |
| a dictionary rule fired where it should not | `--report-false-positive "<from>" "<to>" -d <domain>` | leave the rule active behind a context note |
| a stable FROM→TO correction will recur in this domain | `--add "<from>" "<to>" --domain <project>`, subject to the real-word rules below | |
| a recurring person's name has a non-obvious spelling | the people roster, which is hand-edited | |

A `decision_note` is never an action. A preplanned `append_note` action runs
only when its item is `accepted`; `overridden` drops suggestion-specific
`dict_add` and `append_note` actions, while `kept_original` and `skipped` run
no actions. Explicitly promote the note after the verdict. This is the same
gap as **"An override does not compound on its own"** below: corrected text
stops at `resolved_text`, and the reason stops at `decision_note`.

**Enqueue validates anchors verbatim — authoring errors die at enqueue, not
at verdict.** When an item declares a readable `file`, `--enqueue-review`
checks that `original` (and `context`, if given) literally appears in it, and
repairs a line hint that points beyond the resolve window (±3 lines) of a
UNIQUE match (a hint inside the window works as-is and is left alone; repairs
are printed to stderr). Anything else is REJECTED on the spot with the
reason, and the run exits 3 — the JSON carries the rejects under
`rejected_unanchored` (items under `added` WERE enqueued; fix the rejects and
re-enqueue them). `context` must be copied verbatim from the file; a
paraphrase drifts the anchor at the first surrounding edit. (Files that don't
exist yet are not validated — e.g. items enqueued for a file on another
machine; the resolve-time guard owns that case. `stage1_deferred` items are
also exempt — their `from_text` is the engine's evolving text after earlier
rules applied in-memory, legitimately not in the input file yet.)

**One verdict fixes one occurrence — sweep the siblings yourself.** A resolved
item edits exactly one span. When the original text occurs several times the
guard does not edit them all: it picks the occurrence nearest the recorded line
hint whose context matches, and refuses (`re_anchor_needed`) when it cannot
choose — no line hint at all, nothing matching near the hint, or two occurrences
equally near it. Either way the other occurrences are left standing,
**including on the very line the verdict just edited**, which is
where a repeated name is most likely. Measured on one real batch: ten items
resolved, four of them left six more occurrences behind, two of those on a line a
verdict had already touched. So a verdict batch has a second half:

```bash
# 1. See what was actually decided. The default listing shows PENDING only —
#    the items you just resolved are precisely the ones it hides.
uv run scripts/fix_transcription.py --list-review --review-status accepted
uv run scripts/fix_transcription.py --list-review --review-status overridden
# 2. Read the verdict that was recorded, per item.
uv run scripts/fix_transcription.py --show-review <id> --json
```

**Take the replacement from `resolved_text`, never from the listing line.** On
an override the human's typed text lands in `resolved_text` while
`suggested_text` still holds the suggestion they *rejected* — and the
human-readable listing prints the suggestion. Propagating from that line pushes
the rejected answer into every remaining occurrence, which is worse than leaving
them alone. An override is free text, so read it before propagating: a typo
typed once otherwise becomes a typo in five places.

Fix the remaining occurrences with Edit, or a `sed` scoped to that **one file**
— this is within-file propagation of a decision a human already made, not the
cross-file find-and-replace the batch rules forbid — then re-grep to confirm.

**Sweep `entity`-kind items only.** A `homophone` or `wording` verdict is a
judgement about *that sentence* — those are the context-dependent class step 5
says to anchor to surrounding text, and the class the `争`→`蒸` row keeps out of
blanket rules. Propagating one across a file is the mistake the dictionary matrix
exists to prevent.

**And within `entity`, a verdict settles the entity, not every token that sounds
like it** — this is step 4's carve-out, unchanged. An occurrence that is a
*referred-to* third party rather than the person being addressed ("I'll ask
`<token>` from the bank") can legitimately need the opposite answer: leave it and
enqueue it on its own. A verdict the human reached **by listening to one clip**
deserves the same caution — those seconds of audio settle that utterance, and a
second occurrence is a second utterance. Sweep the occurrences that are plainly
the same entity in the same sense; that is the ordinary case, and the one the
measurement above counted.

**Sweep after the whole batch is resolved, not between verdicts.** A swept
occurrence that a still-pending item is anchored to will fail that item's guard
(`re_anchor_needed`, exit 2) and have to be re-enqueued.

**An override does not compound on its own — finish it with `--add`.** On
`overridden` the queue drops the `dict_add` / `append_note` actions (they were
planned for the suggestion the human rejected), so the strongest signal in the
whole loop — a human personally correcting the AI — is the one case that never
reaches the dictionary unless you put it there:
`--add "<original>" "<resolved_text>" --domain <project>`, subject to the
real-word rules above.

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
---
date: 2026-08-02
minute_token: abc123
audio: /absolute/path/to/recording.m4a
---
```

The `audio:` line is the one you add; the others stand for whatever the
transcript already carries. It is written **bare on purpose** — see below, and
note that this example is copied verbatim often enough that a trailing `#`
annotation on that line has shipped as a real bug more than once.

**Add the line to the block the transcript already has — do not append a second
one.** A synced transcript normally arrives with frontmatter (`date`,
`minute_token`, `participants`…), and the parser stops at the first `---`
terminator it meets, so a second block below it is never read.

**Write the value bare — no trailing comment.** The parser takes everything after
the first colon (`line.split(":", 1)[1].strip()`) and does not strip `#`, so
`audio: /path/x.m4a  # same timeline` becomes a path ending in `# same timeline`,
which does not exist. Same for the block's shape: it must open at line 1, be
closed by its `---`, and the key must sit unindented.

Every one of those mistakes fails the same way — the card shows **no play button
and no error**, which reads exactly like "this transcript has no audio." If a
card you expected to have audio doesn't, suspect the frontmatter before you
suspect the recording.

The file must be on the **same timeline the transcript's timestamps refer to** —
the exact file fed to the ASR. A transcript produced from a 1.3x-speed input
pairs only with the 1.3x file; pairing it with the original makes every clip play
the wrong seconds.

The dashboard derives the clip window from the speaker-timestamp lines
(`<speaker> HH:MM:SS.mmm`) around the anchor, streams the file with HTTP Range
(instant seek, no full download), and plays just that utterance; `± 3s` widens
the window when the cut lands mid-sentence. Verify the timeline pairing once
per recording source (`ffprobe` duration ≈ the transcript's last timestamp) —
a mismatched speed rate plays the wrong seconds everywhere.

**Wiring audio for a Feishu-minute transcript** (the common case when the
transcript came from a minutes-sync pipeline) — use the bundled script, which
does the download, the timeline check, and prints the frontmatter line:

```bash
uv run scripts/fetch_minute_audio.py \
  --token <minute-token> --profile <lark-cli-profile> \
  --output ~/.transcript-fixer/cache/audio/<name>.m4a \
  --transcript <path/to/transcript.md>
```

**Both arguments come from outside the transcript's body.** `--token` is the
`minute_token:` field in the transcript's own frontmatter (a minutes-sync
pipeline writes it there; if it is absent, the minute URL's last path segment is
the same value). `--profile` is a lark-cli profile name — list them with
`lark-cli profile list` and pick the one belonging to the account that owns the
recording; the transcript does not record it, so if the owner is not obvious,
ask rather than guess (a wrong profile fails in the silent way described below).

Keep the audio outside the docs repo — a media blob should not ride into its git.

**Exit codes** — check the status, not the output: diagnostics go to stderr while
the `audio:` line goes to stdout, so a run that verified nothing still prints a
usable-looking line.

| code | meaning |
|---|---|
| `0` | verified — audio and transcript share a timeline |
| `1` | timeline mismatch: a file downloaded, but do **not** wire it |
| `2` | downloaded, pairing unverified — `ffprobe` absent or its output unusable, no `--transcript`, the transcript has no `<speaker> HH:MM:SS.mmm` lines, or every one of them is `00:00:00` (argparse also exits 2 on a malformed invocation; its message says so) |
| `3` | nothing usable produced — bad `--transcript` path (checked before any network work), or the fetch failed: lark-cli errored, curl failed, the download was too small, or **the `--profile` cannot read this minute**, which is the most common cause and is not a bad token |

A `2` caused by missing speaker-timestamp lines is worth stopping for rather than
working around: the dashboard builds its clip windows from those same lines, so
audio wired to such a transcript has nothing to play.

**The by-hand route**, for when lark-cli is unavailable or the script fails:

```bash
mkdir -p ~/.transcript-fixer/cache/audio && cd $_   # --output below accepts only
                                                    # a relative path inside the
                                                    # CURRENT dir ("../" refused)
LARK_CLI_NO_PROXY=1 lark-cli minutes +download \
  --minute-tokens <token> --profile <profile> --output ./audio.m4a
# If that trips the SSRF guard, take the signed URL and fetch it yourself.
# Parse the envelope as JSON — a regex scrape leaves escapes literal and
# truncates the URL at its first parameter:
URL=$(LARK_CLI_NO_PROXY=1 lark-cli minutes +download \
        --minute-tokens <token> --profile <profile> --url-only \
      | python3 -c 'import sys,json
raw = sys.stdin.read()                      # the CLI may print prose around the
s, e = raw.find("{"), raw.rfind("}")        # JSON, so isolate the object first
print(json.loads(raw[s:e+1])["data"]["download_url"])')
[ -n "$URL" ] || { echo "no download_url — check the profile"; exit 3; }
curl -sSL --noproxy '*' -o audio.m4a "$URL"
# Verify the pairing yourself: compare the duration against the transcript's
# LAST speaker timestamp. Treat a gap over max(60s, 5% of that timestamp) as a
# mismatch — recordings usually run a minute or two past the last utterance,
# but a speed-rate mismatch shows up as a large proportional gap.
ffprobe -v quiet -show_entries format=duration -of csv=p=0 audio.m4a
```

Three things the script encodes, each of which is a real failure by hand:

- **lark-cli's own SSRF guard refuses its own download host.** The error is
  `blocked download URL: local/internal host is not allowed` — Feishu's
  signed-download domain is literally named `internal-api-drive-stream.…` and
  the `internal-` prefix trips the guard. The fallback is `--url-only` plus your
  own `curl -L`, which is what the script runs.
- **The `--url-only` envelope is real JSON — parse it, don't pattern-match it.**
  The URL lives at `data.download_url` (nested, not top level), and a regex
  scrape leaves JSON escapes such as `&` literal, producing a URL that
  truncates at its first parameter and downloads a redirect stub instead of
  audio. `json.loads` handles this natively and a hand-rolled extraction is
  where the escaping bug comes from.
- **A minute is a per-tenant, per-user resource, so the `--profile` is the part
  that usually fails, not the token.** A profile from another tenant — or one
  the minute was never shared with — authenticates fine and still returns no
  `download_url`. Pass the profile belonging to the account that owns the
  recording.

Wire the audio **before** enqueueing items you intend to have judged by ear
(step 4 routes cross-language proper nouns there) — otherwise the reviewer opens
a card with no play button and no way to answer the question you asked.

**Stage 1 integration**: safe-mode deferrals are auto-enqueued
(`source: stage1_deferred`) at run time, so a caller discarding the sidecar no
longer loses them. Exception: an input under the OS temp dir is NOT enqueued
(the anchor would be a dead pointer once the staging copy vanishes) — the
`--json` `deferred` count still reports those to the caller, and the additive
`review_enqueued` field says how many landed in the queue.

## False Positive Prevention

Adding wrong dictionary rules silently corrupts future transcripts. **Read `references/false_positive_guide.md` before adding any correction rule**, especially for short words (≤2 chars) or common Chinese words that appear correctly in normal text.

## Project-Specific & Person-Name Corrections (`--domain` isolation)

The most important pattern for **recurring, project-specific errors** — person names, project jargon, shelf codenames — is the `--domain` flag. It is also the *answer* to the false-positive worry above: a person-name fix that's right **in your project** (a teammate's name the ASR keeps garbling) might collide with a real, differently-spelled person in someone else's transcript — so it must NOT go into the global (`general`) dictionary.

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
### Nina Zhao
- **ASR 变体**: Nena, 妮娜

### 小雨
- **ASR 变体**: 晓雨, 小宇老师
```

Both example shapes are worth copying. An English given name spoken inside
Chinese speech produces *two* kinds of variant — a misspelling (`Nena`) and a
Chinese transliteration (`妮娜`) — and a Chinese nickname produces homophone
variants plus honorific forms (`小宇老师`). List every form you have actually
seen; each one is a rule that fires for free.

**Setup** (once):
```bash
# Edit ~/.transcript-fixer/config.json and add:
#   "paths": { "people_roster_path": "/path/to/people.md" }
```

After this, every `--stage 1` run automatically merges roster corrections
(in-memory only — never written to DB). The DB always wins on conflicts, so the
roster fills gaps without overriding hand-tuned entries. See
`scripts/core/people_roster.py` for the parser.

**Precedence has three layers, and the third one is domain-scoped while the
roster is global** — the asymmetry is what surprises people:

1. A DB rule active in the run's domain wins.
2. Otherwise the roster supplies the pair.
3. **Unless** the pair is disabled in the run's domain — then the roster copy is
   suppressed too, and the run prints `🚫 People roster: N variant(s) suppressed`.

Layer 3 is per-domain, so retiring a pair with `--report-false-positive
--domain A` does **not** retire it under `--domain B`: the roster is global and
nothing vetoes it there, so the rule keeps firing in B. That is intended (a
false positive in one domain is often correct in another), but it means "I
disabled it and it still fires" almost always means *a different domain* —
check that before editing the roster, which stops the pair everywhere at once,
including in other projects sharing the same file. `--report-false-positive`
now names the domains where the pair is still active, and exits `3` (already
disabled here) or `4` (roster-only, no DB row to disable) so automation can
tell those apart from a real failure.

**When to use the roster vs `--add` to DB:**

| Person | Go to | Why |
|--------|-------|-----|
| Long-term recurring (coworker, client, family, workshop attendee) | **people.md** | SSOT with relationship context; survives DB resets |
| One-off / minor name | **DB** (`--add --domain`) | Quick, no context needed |

**Name-variant explosion — one person, every initial consonant.** A person
whose name a diarizer labels once can still shatter in the body into a whole
family of variants, sometimes across *different initial consonants* (h/f/w/g/zh
all heard for one surname in a single 56-minute call — real case 2026-08-08:
one speaker surfaced under seven different surname-initials). This is not a bug
to chase per-variant; it is the canonical-name problem in disguise. Handle it
as a unit:

1. **Fix the canonical FIRST** — ask the user or use a confirmed
   human-annotated diarization label, settle one spelling, and only then sweep.
   An auto-assigned label, or one whose provenance is unknown, remains a
   candidate and must follow the verification ladder below. A variant family
   resolved without a canonical produces seven half-fixes and a confused roster.
2. **Sweep every variant in the file in ONE pass** (single-file `sed` with all
   variants in one command, then re-grep to zero), not variant-by-variant.
3. **Record the whole family in the roster's `ASR 变体` line** — every form
   you actually saw, including the weird ones. The next transcript will
   produce new members of the family, and the roster is what keeps the
   canonical stable while the family grows.
4. **Honorific forms (`X老师` / `X总`) are variants too** — an honorific is
   what a speaker actually said, so never *replace* it with the bare name, but
   the surname inside it gets the same sweep and the same roster entry.

**Mid-turn verdicts compound immediately — never defer them.** When the user
answers a name/number question while you are still working (a mid-message
correction, a one-word answer to your shortlist), the verdict is the strongest
source in the whole loop and costs nothing to bank: fix the file, `--add` the
confirmed variant, and update the roster/context in the SAME turn — not "after
the batch", which is where deferrals die. Four mid-turn verdicts in one real
batch session all compounded the turn they were given (2026-08-08), including
one that corrected the reviewer's own stale training data about a version
number. A user verdict that contradicts your search results is the verdict
winning, not an anomaly to double-check.

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
2. Verify Stage 1 — diff against the original. If the dictionary introduced false positives, work from the **original** file instead and apply your edits there. **A false positive here is debt you owe the dictionary**: the same bad rule fires on every future transcript until retired, so the moment you spot one — a rule that turned correct speech wrong, especially "real-word → real-word" rules (both sides are valid-word-shaped, so the non-word guard doesn't catch them; and under `--apply-domain` every matching rule applies regardless of its risk class) — e.g. a `买买→卖卖` rule rewrote a correct "买买工作流" into "卖卖工作流" — disable it in the same session with `--report-false-positive <from_text> <to_text> -d <domain>` — pass the rule's stored from→to pair exactly as Stage 1's `*_changes.md` shows it (the From/To columns) or as it sits in the dictionary, NOT "wrong-word → right-word" semantics. The direction is counter-intuitive for a false positive: the `买买→卖卖` rule stored `from=买买, to=卖卖` (it rewrote a correct 买买 into a wrong 卖卖), so you pass `"买买" "卖卖"` — the rule's stored from→to pair, which is what the tool keys on. One call disables the rule and lowers its confidence (the tool prints "The rule has been disabled"); it will not fire on the next transcript. If the word is genuinely *ambiguous* (correct in some contexts, wrong only here) rather than plain wrong, don't disable the rule — record the disambiguating cue in the domain context file instead. Fixing this transcript while leaving the trap armed guarantees the next one trips it too.
   **And when the input already passed through an automated corrector** (a sync pipeline's pre-classify stage, a previous Stage 3 API run), your input is NOT raw ASR — upstream corrections are baked in with no evidence trail. Before triaging, diff against the raw source (the caller's raw transcript — sync engines typically keep one alongside the corrected copy, e.g. `transcript_raw.txt` — or re-pull from the source API). Two things fall out of that diff, in opposite directions: **(a)** every upstream entity swap is itself a suspect in step 4's triage, because an upstream AI "correction" can be a fluent wrong guess — real case: raw ASR 「新的车辆」 was "smoothed" by a pipeline AI into 「新出来的反馈」 (grammatical, plausible, wrong: the speaker said a near-homophone name), and only the raw diff caught it; **(b)** what upstream already fixed correctly is settled — check the diff *before* proposing a fix that's already applied, or you redo work and risk "fixing" a correct form back to a wrong one

   **How to judge each upstream change — the one test that works, and the one that doesn't.** Run the *sound-distance* test from step 6 on every upstream edit, in the direction it is written there: **if the two sides are too far apart phonetically for any ASR to have produced the swap, it is not a correction — it is the model rewriting what the speaker said, and it gets reverted.** An ASR mishears sounds; it does not exchange a word for a synonym, and it does not change a pronoun. Two shapes recur, and neither looks like an error on the page:
   - **A term swapped for a plausible near-synonym.** The two words share no sounds, so no engine could have confused them — and the give-away is corpus-level: the replacement appears nowhere else in the project's material, while the original is that project's standard vocabulary (a term an earlier meeting defined). Grep both forms across the corpus before accepting either.
   - **A pronoun or subject rewritten.** Reads *more* logical than the original, and silently reassigns who a statement is about — which is a fact change, not a transcription fix. Pronouns in most languages are phonetically unrelated to each other; an engine that mishears one for another would be mangling the whole sentence.

   **Why this needs its own test rather than your judgment: an upstream corrector optimizes for fluency, so everything it emits reads well — which makes "does the result make sense?" a check with zero discriminating power against exactly this failure.** You cannot read your way to catching it, and the smoother the pipeline, the more confident the wrong text looks. The diff is the only instrument that sees it. Two consequences worth planning around: run the diff *before* your own read-through, so upstream's edits arrive as candidates rather than as the text you are proof-reading; and when you do revert one, sweep whatever you have already written that quoted the corrupted form (step 9's derived-document sweep — notes and summaries written from the pre-revert text carry the same corruption, and unlike the transcript they carry no marker saying so).
3. **Load the domain's priors, then read the entire transcript.** If `~/.transcript-fixer/contexts/<domain>.md` exists for this transcript's domain, read it first — it primes which homophone traps to suspect and names the authoritative sources for step 4's ladder (see "Domain Correction Contexts" above). Then read the **entire** transcript before proposing corrections — later context disambiguates earlier errors (a name garbled near the start often becomes obvious later). For large files, read in chunks but finish the whole thing before deciding anything
4. **Triage each candidate error into one of three buckets** — this triage is the part that takes judgment. **First override three reflexes that repeatedly misfile names** (all three are real, recurring failures — they send a fixable name straight to "ask the user"):
   - **Speaker labels first — the transcript usually already holds the names.**
     Before searching anywhere, collect the set of speaker labels in the file;
     if a garbled token matches one by SOUND, it is almost certainly that same
     person, and the label carries the spelling — a label is copied from a name
     *registry* (a human annotating the recording, or the attendee list /
     voiceprint enrollment a diarizer matched against), while the body is raw
     ASR of a spoken sound. Four qualifiers, and the first one is not optional.
     **(a) Apply it only to a name being ADDRESSED or SELF-INTRODUCED, never one
     being REFERRED TO.** "hi, <token>" and "my name is <token>" identify a
     speaker; "I'll ask <token> from the bank" identifies a third party who may
     merely *sound* like one — and rewriting them to a speaker's name corrupts a
     real person, the exact hazard the dictionary table calls "Real name →
     different real name ❌ Never a rule". Two acoustically identical tokens in
     one file can need opposite answers for this reason alone, so a referred-to
     name keeps walking the ladder rather than resolving here.
     **(b) Match against ALL labels — including, but not limited to, the one
     above the block** — a garbled name usually sits in a block spoken by
     someone else (`A` greeting `B`), and sometimes in that speaker's own block
     (a self-introduction). **(c) The label settles WHO; the roster still
     settles the canonical spelling** — a hand-typed `Joe` normalizes to the
     roster's `Jo`, spelling only, never length. **(d) Labels annotated by a
     human are a human identification: apply them, and do NOT put that name on
     the needs-checking list or ask the user to confirm it — they answered it by
     labeling it.** (Real case: walked the whole ladder on a name printed above
     every one of that speaker's blocks, found nothing, then asked the user to
     confirm it. They had labeled it themselves.)
     When you cannot tell whether labels were hand-annotated or auto-assigned,
     **assume auto-assigned**: voiceprint matching can attach a perfectly
     spelled name to the wrong speaker, and that never looks garbled — so treat
     the label as a strong candidate to confirm through the ladder, not as a
     stop condition. Fall through to the ladder for `说话人 N` / `Speaker N`,
     role labels (`主持人` / `Interviewer`), a third party who is not one of the
     speakers, or a label that is itself visibly garbled. Fix the **body** only
     — never edit a label or reassign who said what — keep the edit minimal
     (do not expand a given name into a full name nobody said), and `--add` the
     confirmed variant to a `--domain` so the next transcript fixes it free.
   - **Judge ASR errors by SOUND, not by glyphs.** Chinese ASR errors are homophone / near-homophone substitutions, so decide "same entity?" by pronunciation, not by whether the characters match exactly. A name that comes through as `X小Y` when the roster or dictionary already holds `X晓Y` (小/晓 are the same sound) is the **same person → Confident fix** — do NOT downgrade it to Uncertain just because 小≠晓 on the page. Same logic for a foreign name whose syllables all map by sound to a near-homophone transliteration. The dictionary having a sound-alike canonical is *evidence for* the fix, not a mismatch to be dismissed.
   - **But sound similarity is *sufficient* evidence of identity, not *necessary* — and the exception is a whole class, not a rarity.** A name spoken in one language while the engine transcribes another (an English given name inside Chinese speech, a transliterated surname) can come out phonetically **unrelated** to its canonical form, and — worse — as something that reads like a perfectly ordinary *different* real name. In one measured case a single person surfaced as three separate tokens, none a near-homophone of her name and each plausible as somebody else entirely; the tokens were recognizable only because all three sat where the same absent principal belonged, and what *confirmed* them was the human listening to those seconds of audio.
     **This does not reopen the (a) bullet above.** That rule forbids resolving a *referred-to* token into one of the **speakers'** names, using speaker labels as the source — the failure mode where a third party gets overwritten with whoever is in the room. This class is the opposite direction: the token resolves to a known **non-speaker** whose canonical form comes from the roster or the project's ledger, and it is settled by the human's ear rather than by a label. Where the two are hard to tell apart, the (a) bullet wins and the token keeps walking the ladder.
     So a candidate that fails the sound test but sits in a known person's slot is **neither dismissed nor rewritten**: enqueue it as `kind: entity` for audio verification (the dashboard's `Q` is the instrument for exactly this). Put your best candidate in `suggested` even when you doubt it — an item with no suggestion cannot be accepted at all (`--decision accepted` errors on it), so the reviewer would be forced to retype the answer for every card. Wire the transcript's audio *before* enqueueing (see the dashboard's audio section): the frontmatter is read live at view time, so adding it later does light up the play button — but editing the transcript shifts line numbers against the ±3-line window each item's anchor was recorded with, which is the expensive half to undo.
   - **A name you can't place defaults to the search ladder below, NOT to asking the user.** "Only the user knows this name" is the single most common wrong reflex. The canonical spelling is almost always already on this machine under a **different project's domain** — so you must query **all** domains at once (the cross-domain SQL in the ladder below), not the one domain you happened to pass to `--stage 1`, which may be brand-new and empty. Querying only that one and giving up looks exactly like "I checked" while finding nothing that was right there.
   - **Confident fix** — non-words, obvious garbling, product-name variants you already recognize, or a homophone that's unambiguous in context (`their`→`there` where context forces it; `彭波`→`彭博` when every other mention already reads `彭博`). Apply directly (step 5).
   - **Needs verification** — a proper noun you can't confirm from context: a person / company / ticker / product / place name (a misheard drug name in a medical interview, a researcher's surname in a podcast, a ticker on an earnings call), or any term you can't point to a specific source for — even one you think you recognize ("I'm pretty sure" is exactly how wrong names slip in). **Resolve it through a local-first search ladder before asking the user.** For project / personal entities the authoritative spelling almost always already lives on this machine, and WebSearch is near-useless on internal names — it returns wrong same-name people, or nothing — and worse, a fluent wrong guess becomes a confident fix that's hard to catch later. Search in this order:


      0. **People roster** — `people.md` (or wherever `people_roster_path` in
         `~/.transcript-fixer/config.json` points). This is your curated SSOT
         of long-term recurring people with their ASR variants annotated under
         `- **ASR 变体**:`. A garbled name that already maps to a canonical
         person here — e.g. `Nena`→`Nina Zhao`, `小宇老师`→`小雨` — is a
         Confident fix: apply immediately. **This one step replaces asking the
         user for every name they've already documented.** Skip only for
         transcripts whose speakers are confirmed NOT in the roster.
      1. **All domains of `corrections.db`, not just the current `--domain`.** The same entity shatters into different ASR variants across projects, and every prior fix already collapsed them to the canonical name — so the answer is often sitting in another domain you didn't pass to `--stage 1`. Checking only the current domain and giving up is the recurring failure mode.
         `sqlite3 ~/.transcript-fixer/corrections.db "SELECT from_text, to_text, domain FROM active_corrections WHERE to_text LIKE '%<fragment>%' OR from_text LIKE '%<fragment>%';"`
      2. **Project delivery docs & the alias ledger** — cost reports, review sheets, deliverables, PKM notes for that project. These are human-written correct spellings, the strongest possible source. `grep -rl "<fragment>" <project-dir>` then read the hits. (The domain context file you loaded before triage usually names the project's alias ledger explicitly — start there.) **Read every name table the ledger holds, not just the one that looks like "the speaker list."** A project's people are almost always split across role-based tables — internal speakers, external collaborators, client-side, vendor/dealer-side, attendees — and the person you're chasing often lives in a sibling table you didn't open. If a name you end up confirming wasn't reachable from the context file's name-source manifest, that manifest is incomplete: add the missing table to it so the next run can't miss it. (See `domain_context_guide.md` Rule 6 for the failure case this prevents.)
      3. **Local tool / gateway / client configs — for product, model, and tool-vocabulary garbles.** A transcript full of product/model/endpoint talk usually has its ground truth sitting in the user's own client configs on this machine: LLM gateway profiles (model IDs, base URLs), editor/IDE settings, CLI config stores, API client presets. These are machine-readable, current, and exact — a model name garbled five different ways resolves byte-for-byte against the config's own model list, including non-obvious suffixes (real case: `cloud fiber5` / `飞豹五` / `FIVE5EM` in a call about configuring a model-gateway client; the client's local DB listed `claude-fable-5` with a 1M-context flag — every variant collapsed, including `EM`→`1M`). Generic recipe: locate the config for the tool being discussed (well-known config home, its sqlite/json store), match the garbled token against its real identifiers by sound, and treat a config entry as near-authoritative — the user reads IDs off that screen while speaking; ASR only hears sounds. ⚠️ Config stores can hold secrets: read the fields you need (model names, URLs), never copy keys/tokens into the transcript, the dictionary, or your summary.
      4. **Chat-history timeline cross-reference — for who-was-actually-on-the-call.** When participant identity matters (a diarization label is a bare English first name, or `Speaker N`, and the body never says the full name), the strongest local evidence is the user's own chat history *around the meeting window*: people send each other the meeting link and the artifacts discussed mid-call (config strings, files, links). Search the chat archive for a **distinctive string the transcript itself contains** (a domain, a model ID, a codename spoken during the call), restricted to the meeting's date window; the chat that holds it at that time is almost certainly the other party, and the messages around it ("joining now", the invite one minute before start) settle identity **without inferring anything from transcript content** — this is timeline evidence, not guessing who a speaker sounds like. It also byte-verifies any exact string the chat contains (an ID pasted mid-call confirms its own spelling). Reserve for identity/label questions — ordinary spelling needs are cheaper through rungs 0–2. Real shape: diarization said `Kevin`; searching the gateway URL spoken in the call surfaced a DM that received the invite one minute before start and the three exact config strings mid-call — `Kevin` resolved to the DM's full display name, and two garbled surname addressings in the body were corrected to the evidenced surname.
      5. **Memory** (`~/.claude/.../memory/`) — project relationship maps and person profiles often record canonical names explicitly.
      6. **WebSearch** — only for genuinely public entities (a public-company ticker, a known researcher, a drug name). Skip for anything project-internal.

      Only after all of these strike out do you ask the user — and by then you've shown the entity isn't already recorded on this machine, which makes the ask legitimate. A confirmed result becomes a Confident fix; if the search *can't* confirm it, it drops to Uncertain. **Batch these**: collect the unique unknowns and run the ladder once per unique entity, not once per occurrence. **When asking for a canonical person name, always preserve an escape hatch outside your shortlist** — include an `Other / none of these` path (or verify the UI supplies one) that accepts the user's exact free-text spelling. A single local occurrence can justify putting a candidate on the list, but not making the list exhaustive: the real canonical may be an English name while every candidate you found is a Chinese transliteration.

      **And when the user answers, their verdict is ✅ authoritative — the strongest source in this whole loop — and it compounds three ways in the same session.** A user who says "X is actually Y (my colleague on team Z)" has handed you a source stronger than any local document. Cash it in immediately: ① apply the fix; ② persist the variant where it compounds — an important recurring person goes to the **people roster** (per the roster-vs-DB table above), a project term or one-off name goes to `--add ... --domain <project>` (the same ASR will mishear the same name again next week); ③ record it in the ledger / roster / domain context with the user's words, the date, and a ✅ "user-confirmed" marker — no later session should re-ask. Two refinements learned the hard way:
      - **Collision-check the FROM side before dict-adding.** If the garbled string is itself a real person's name elsewhere in your world (another project's roster holds a *different* real `李明`), a `李明`→`黎明` dictionary rule will corrupt that person's future transcripts. That fix belongs in the domain context file as a trap with its disambiguating cue ("in editing-team context, `李明` = `黎明`"), never in the dictionary.
      - **Confirmed-correct entities deserve a note too.** When the user confirms a name is right as-is ("he's a real blogger, spelled exactly like that"), record the verdict (one line in the domain context or roster). An unrecorded "correct as-is" is a question the next run will burn five minutes re-asking.
   - **Uncertain** — you suspect an error but can't confirm it even after searching (a syllable that maps to several real entities; a structurally broken sentence). **Leave the original text exactly as-is** and record it in the needs-checking list (step 7). A fluent-but-wrong "fix" is harder to catch downstream than an obvious garble — silence beats a confident guess.
5. Apply the confident fixes efficiently:
   - **Global replacements** (unique non-words like "克劳锐"→"Claude"): if it recurs across transcripts — most product/name garbles do — `--add` it to a `--domain` so it compounds to every future run; for a genuinely one-off term, one `sed -i ''` with multiple `-e` flags
   - **Context-dependent** (a word that's only wrong in one context, like "争"→"蒸" in a distillation discussion): sed with a longer surrounding phrase for uniqueness, or the Edit tool
   - **Common-word batch where most occurrences are the domain term but a few are genuine** (a high-frequency word the domain repurposes in *most* of its occurrences, yet not all — the residual real uses are exactly what a common word is for). Never blind `replace_all`. First `grep -n` every occurrence and judge each from its sentence. When the large majority share the domain meaning and only one or two are real, the efficient shape is: `replace_all` the word to the domain term, then `Edit` those one or two genuine-usage sites back — faster and less error-prone than N separate Edits, and the re-grep below catches any misjudgment. Real case: `公开` across 11 lines of a sales call — 10 were 工勘 (the field-survey sales-funnel stage) and one was a real "公开的渠道"; `replace_all` → 工勘, then revert the single "公开的渠道". (The domain term itself still doesn't go in the dictionary when the source word is common — record it as a context trap per "Domain Correction Contexts"; this bullet is only about *applying* the fix within one transcript.)
   - Re-grep each changed term afterward to confirm it landed and didn't hit look-alikes you meant to keep
6. **Second pass — catch what one read missed.** A single linear read reliably leaves residue: an idiom degraded into a near-homophone, a term wrong in just one spot among many correct ones, an acronym misheard as another. Always re-scan once for leftovers. A cheap targeted variant comes first: **trap-scan** — scan the file for every trap pattern the domain's context file documents (the recurring homophones this domain is known to produce). Run it mechanically, not as a hand-rolled grep loop (a 30-trap context file is 30+ greps by hand, and the list is exactly what a tired operator truncates):

   ```bash
   uv run scripts/fix_transcription.py --scan-traps \
     --context-file ~/.transcript-fixer/contexts/<domain>.md -i meeting.md
   ```

   Every documented trap comes back with line number + context window, confirmed-correct records (`**X = 真实实体，勿修**`) are reported as keep-as-is so you stop re-investigating settled questions, and the no-hit list makes "scanned and absent" distinguishable from "never scanned". Thirty seconds checks exactly the errors this domain makes; a clean trap-scan plus your first pass is enough for fast tier. For a long or high-stakes transcript, *also* spawn an independent subagent (Task) to re-read the corrected file cold — fresh eyes with no memory of your first pass catch what you've read past. **The subagent's job is to *return a residual list*, not to re-narrate the transcript.** Give it an output format and a hard cap, because a subagent that thinks aloud line-by-line will blow its own context window before finishing (one real second-pass run on a 1131-line transcript hit the 32k token ceiling mid-scan and returned nothing usable). The correct prompt shape:
   - Scope it to exactly one file, forbid editing and cross-file grep.
   - Hand it the already-corrected terms as a do-not-re-report list (you fixed those; only *new* residuals are useful).
   - Demand a compact table only — `line | original ≤20 chars | suspected | one-line reason | confidence` — and tell it to stop after the list, no prose preamble, no per-line stream-of-consciousness, no re-deriving corrections it has already made.
   **Completion requires a usable review result, not merely a successful process status.** The reviewer must cover the whole file and return either the requested residual table or an explicit `no new residuals`; an empty, malformed, or truncated response is a failed pass and must be retried with a fresh reviewer. A retryable subagent failure does not satisfy this pass either. If the failure says it is retryable or provides a retry delay (for example an HTTP timeout with `retry_after`), wait at least that long and retry the fresh-context review. Only treat the subagent path as unavailable when the tool truly cannot run (for example, these instructions are already executing inside a subagent that cannot spawn another). A targeted trap-scan or grep for known variants remains useful, but **it is not an independent re-read**: it can confirm that known error families are gone and structurally cannot discover the first reader's blind spots. In one production run, replacing a timed-out fresh review with known-pattern grep reported clean; retrying the cold review surfaced 26 additional candidates.
   Then adjudicate each residual — the subagent's list is **candidates, not conclusions** (one real run: 10 rows → 4 accepted). Run each through step-4 triage, plus these heuristics, all production-validated:
   - **Accept — near-homophone + in-document self-proof.** `利智回购`→`离职回购` when the same table of contents a few lines earlier already reads `离职回购`: near-sound plus the correct form inside the same file settles it. Referent-locked homophones likewise (`他`→`它` when the antecedent is a document, not a person).
   - **Reject — sound distance falsifies too.** The sound test cuts both ways: near-sound is evidence *for* a fix (step 4); implausible-sound is evidence *against*. `代号`→`代码` (hào/mǎ) and `一撮`→`一坨` (cuō/tuó) are not swaps ASR makes — that candidate is the reviewer over-reading, not the engine mishearing. **The exception is step 4's cross-language proper-noun class**: a foreign name spoken inside another language can legitimately land far from its canonical sound. Don't reject those here — route them to the queue for audio verification instead. The exception is defined by *kind*, not by rarity, and it takes **both** of step 4's conditions: the candidate is a proper noun that could have been spoken in a different language from the one being transcribed, **and** it sits in the slot of someone the project already knows. Both → route it to the queue whatever the sound distance. Either one missing → this rejection rule applies, as it does to every common word and every same-language homophone.
   - **Reject — the ASR-capability counter-check (a strong prior, not a proof).** If the same engine rendered the word correctly elsewhere in the same transcript, the word is demonstrably inside this engine's recognition range for this audio — so a different rendering nearby is *more likely* what the speaker actually said, and the bar for "fixing" it jumps. (Candidate `一条`→`一坨`: `一坨` was recognized correctly a few lines earlier, and `一条` is itself a colloquially valid measure phrase — the two together reject the fix.) Keep it probabilistic: the same engine genuinely can shatter one name into a dozen variants (see Project-Specific corrections) — the counter-check weighs most when both the correct form and the candidate are common words the engine handles routinely, least when they're rare proper nouns.
   - **Reject — intelligible real words.** `一撮` is a perfectly good measure word; don't rewrite readable speech just to make a running metaphor consistent. Only fix what the speaker plausibly didn't say.
   - **Reject — evidence-free reconstruction.** A proposed fix with no phonetic basis (`半`→`分`) is a guess about meaning, not a correction.
   - **Minimal edit.** Fix the misrecognized word; never insert unspoken words (`打完`→`打算` ✓; rewriting as `打算怎么` inserts a `怎么` the speaker never uttered ✗).
   - **Prefer the smallest edit that explains the error — rank candidates by phonetic distance before you judge any of them.** The rule above bounds how *much* one candidate may change; this one decides *which* candidate wins when several would read fine. ASR errors are small perturbations — the engine maps a heard sound to the nearest word it knows — so among candidates that all make sense, the one changing the fewest phonemes is almost always what was said. Useful fingerprint in Mandarin: **a reduplicated or multi-syllable tail surviving intact while only the leading syllable differs** points at an initial-consonant confusion (retroflex/alveolar `sh`/`s`, `zh`/`z`, `ch`/`c`, and the `n`/`l`, `f`/`h` pairs), so search same-final/different-initial candidates *before* concluding the whole word was misheard.
     **Where this fails is not while you generate candidates — it's while you audit text that is already there** (an upstream correction, or a fix you accepted on the first pass). Reviewing existing text puts you in verify-mode: you ask "is this reasonable?", it is, and you move on — never noticing you were handed one candidate rather than a ranked set. A candidate that rewrites three syllables can be perfectly idiomatic *and* be a rewrite; the only thing that separates it from the one-phoneme candidate is that you generated both and compared. So when auditing any already-applied correction, force the question: **is there a smaller edit that also explains this?** If you cannot answer it, you have validated rather than verified.
   A second-pass subagent that returns 8 sharp rows beats one that returns 8000 tokens of narration every time. Task works when you're in the main context; if it truly isn't available — e.g. these instructions are themselves running inside a subagent, which can't spawn another — do one more thorough line-by-line re-read yourself from the corrected artifact. Do not substitute a known-pattern grep and call it a re-read. Never skip the second pass over a missing tool.
7. **Emit a needs-checking list AND enqueue it** — the chat summary alone evaporates when the session ends, so every *Uncertain* item gets dual-written: (a) in your chat summary to the human — line number, the original text you left in place, what you suspect, why you couldn't confirm it; (b) into the persistent review queue via `--enqueue-review items.json` (see "Review Queue & Dashboard" above; item field/alias schema: `references/script_parameters.md` §Review Queue Item Schema — unknown keys are silently dropped, so write `line`, not `line_hint`) with the same fields plus a proposed action pack, so the human can one-keystroke-resolve it later in the dashboard — or a later agent session can close it with new evidence (`--resolve-review ID --decision … --note "<evidence>"`). Entity/name questions get `kind: entity` (they compound into the dictionary/roster, so they lead the queue); pure phrasing doubts get `kind: wording`. If nothing is uncertain, say so. A minimal `items.json` for `--enqueue-review` (one object per uncertain item; `suggested` may be empty when you have no candidate — the dashboard lets a human fill it later):

   ```json
   [
     {"file": "/abs/path/to/the/transcript.md", "line": 142,
      "original": "<garbled-name>", "suggested": "", "kind": "entity",
      "context": "<the whole sentence the token sits in, copied VERBATIM from the file>",
      "evidence": "speaker-label fragment near line 142; not in roster or project alias ledger — needs user confirmation"}
   ]
   ```
   **`file` is the key that makes the other two work, and omitting it fails silently in the worst direction.** Both guarantees below are gated on it (`review_queue.py:212` and `:793` each test `file_path` first):
   - *Verbatim-anchor rejection.* With `file` set, a `context` that is not a literal substring of that file is **rejected at enqueue** (exit 3) — so an authoring error dies immediately instead of at verdict time. With `file` absent there is no file to check against, so a paraphrased `context` is accepted and the drift surfaces much later.
   - *The default edit.* With `file` set and no explicit action pack, an accept runs a single `file_edit(old=original, new=suggested)`. With `file` absent the accept still records the verdict and still exits 0 — **and never touches the transcript.** Nothing errors; the queue just says `accepted` while the file is unchanged.

   Two key names, both of which the silent-drop rule above catches one field over: the verdict is `suggested` (alias of `suggested_text`), **not `suggestion`** — the wrong spelling costs you the dashboard's Accept button, and `--resolve-review` then refuses with *"item N has no suggestion to accept"*. The action pack's key is `actions`, **not `action_pack`**; it is optional — supply it only when accept should also `dict_add` / `append_note`. Full field/alias table: `references/script_parameters.md` §Review Queue Item Schema.

   **`original` carries only the suspect token, never the whole sentence** — the sentence goes in `context`. Whatever you put in `original` is what a dashboard verdict will *replace wholesale*: an accept does `file_edit(old=original, new=suggested)`, and an override swaps the entire `original` span for the human's typed text. If `original` is a full clause like 「我们的民宿就完了」 and the human types the two-character brand 「栖云」, the clause is gone — that is a real 2026-07 incident (#24), and the lost words had to be re-added by hand. `original: "民宿的误写词"` + `context: "…我们的民宿就完了"` would have made the same verdict correct by default. (The dashboard now shows the full replacement span above the override input and warns on suspiciously short replacements — but the right granularity at enqueue is the fix that costs nothing.)
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
   - **Sweep what was already DERIVED from this transcript — the correction does not travel on its own.** A transcript is not a terminal artifact: within hours of landing it gets mined into notes, decision logs, analyses, summaries, and outbound messages. Every one of those was written from the *uncorrected* text, so a name you fix today is still wrong in each of them — and unlike the transcript, they carry no timestamp telling a reader the spelling is suspect. Measured case: a misheard person-name reached two analysis documents and was one draft away from a message going to the very people being discussed.
     Scope it deliberately. **Only entity corrections** (names, companies, products — never phrasing, which is sentence-local by definition). **Search the project the transcript belongs to, not the whole knowledge base** — a repo-wide sweep will hit unrelated projects where the "old form" may be a *different real person*, which is the one outcome worse than not sweeping. Use **`grep -rn`, not `git grep`**: `git grep` searches tracked files only, and a document written hours ago — this bullet's entire scenario — is exactly the untracked case (`git grep --untracked` if you want the repo-aware version).
     **Exclude the evidence trail** rather than "fixing" it: the raw ASR baseline (`transcript_raw.txt` and friends) that step 2's upstream-diff depends on, and the `_needs_review.md` / `_changes.md` sidecars, all hold the old form *on purpose* — rewriting them destroys the next run's ability to diff against raw. (Queue items are unaffected either way: they anchor to the transcript itself, and they live in SQLite where a file grep cannot reach them.)
     Review each hit rather than blind-replacing — this is a supervised pass over a handful of documents, not the unconstrained cross-file `sed` the batch-workflow rules forbid.
   - **The habit that prevents the next one** — not an action in this run, a rule for whatever you do with the transcript afterwards: when you quote a proper noun *out of* a transcript into a note, report or message, look it up in the people roster or the project's alias ledger before you paste it. The sweep above is a recovery path, and it is only ever needed because that lookup didn't happen when the name was first carried out. Same ladder as step 4, applied at export time instead of at correction time.
9b. **Moving or rewriting the transcript strands whatever is still in the queue.** Items record the transcript's absolute path and resolve against it, so a **rename** (step 10) leaves every pending item pointing at a path that no longer exists — the verdict then fails with `file gone: <path> — the transcript moved since enqueue`, which names the cause but has no fix command behind it: the CLI can enqueue, list, show and resolve, and there is no re-anchor or delete. A **promote** (step 9's primary path) is subtler: the file still exists, so items fail later on anchor text or context drift instead. Two consequences worth planning around. **Rename first if you are going to rename at all** — before the enqueue in step 7, not after; deferrals auto-enqueued during Stage 1 are already recorded against whatever name the file had then, so a transcript you intend to rename should get its final name before its first Stage 1 run. **And if items are already stranded, the only exits are to resolve them `kept_original`/`skipped`** (both run no actions and can't fail an anchor) **or to re-enqueue equivalents against the new path** — the stale ones stay pending forever otherwise. Archiving is different and safe by itself: a `cp` leaves the original in place, so anchors keep working; what it does mean is that verdicts applied afterwards fix only the working copy while the archived one keeps the error — the same "the correction doesn't travel" problem the derived-document sweep above exists for.
10. **Filename hygiene — rename machine-generated gibberish before archiving.** A transcript whose filename is a raw ASR artifact, device tag, or opaque timestamp hash (`TX02_MIC021_20260720_095909_1.3x.md`, `soundcore Work_01-01 10-36.md`, `07-12-2026 20.07.md`) is not a useful artifact. Rename it to a human-readable form before the file enters a shared repo: `YYYY-MM-DD-HH-MM-<topic-or-speaker-summary>.md`, using Chinese or short English as appropriate to the project. The bar: a human should be able to identify the meeting from the filename alone. If the content clearly belongs to one business line, also encode that in the slug when the repo convention allows it.
11. Save stable patterns to the dictionary (see "Dictionary Addition" above)
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
| AI | a 夜, a 爱, ai, 阿伊 — two-letter English terms get heard as phonetic syllables when spoken mid-sentence in Chinese speech ("All in a 夜吧" = "All in AI 吧", user-confirmed 2026-08-08) |
| skill | SQL, SKU, 死抠 — same two-letter splitting, `skill` is a high-frequency word in AI-tool conversations (SQL/SKU are real words elsewhere — context-judge, never a bare dictionary rule) |

**The two-letter-English-in-Chinese-speech pattern generalizes**: `AI` / `skill` / `SDK` / `API` spoken inside a Chinese sentence are short enough that ASR maps them to any near-sounding syllables (including whole-word confusions like `a 夜`). When a transcript is about AI tooling and a syllable string reads as meaningless Chinese but sits where an English abbreviation belongs, run the abbreviation hypothesis first — then confirm by sound distance before fixing.

Person names and company names also produce consistent ASR errors across sessions — always add confirmed name corrections to the dictionary, and for project-specific names use `--domain <project>` to keep them isolated (see "Project-Specific & Person-Name Corrections").

### Numbers: the category the dictionary structurally cannot fix

A dictionary rule needs the error to be *stable* — one wrong string, one right
string. Numeric errors have no stable mapping (`80` becomes `800` in one
recording and `18` in the next), so no amount of dictionary work reaches them.
They are also the errors that cost the most. The ASR literature on
entity-level error consistently ranks numbers and named entities as the worst
categories — far worse than headline WER suggests — and reports numeral
*continuation* tokens (the digits after the first) as worse still than the
leading digit. That ordering is the load-bearing claim here, and it matches what
you will see in practice: the first digit group is usually right and the tail is
where it breaks, which is exactly why a wrong number still reads fluently.
(Specific percentages circulate in secondary summaries of this literature; they
are not reproduced here because they were not verified against the primary
sources. Search "ASR named entity error rate" / "entity-preserved ASR" if you
want the numbers with their datasets attached.)

Three sub-classes, each needing a different check. None can be auto-applied —
a number can only be resolved by evidence, never by pattern:

| Sub-class | What it looks like | How to settle it |
|---|---|---|
| **Magnitude** | the same amount restated with an extra or missing zero | arithmetic against a figure stated elsewhere in the same passage; or the second recording (below) |
| **Measure word dropped** | `30+` where the speaker said "30 家/个" (nobody says "plus" aloud) | the scanner below finds these (`orphan-plus`); the measure word is then usually recoverable from the object in the same clause |
| **Polarity inverted** | a stated *ceiling* transcribed as a *floor* — "只能给 N" arriving as "超过 N…保底" | scan the same session for the other statements of that number; the one carrying a limiting modal (只能/最多/至多/封顶/不超过/至少/起码/超过/保底/最少 — the script prints this same list) is almost always the true one, because a speaker states a bound once and paraphrases it loosely afterwards |

Polarity is the dangerous one and the one no tool catches: the sentence is
grammatical, the number is right, and the meaning is reversed. It is worth a
deliberate read whenever a number in the transcript will end up in a decision
document — a price, a cap, a share, a deadline.

**Two recordings of one meeting are the strongest evidence you will get.** When
a session was captured by two independent systems (two platforms, or a platform
plus a local recorder), their numeric errors are uncorrelated, so disagreement
localises the error and agreement settles it. This is the manual, two-system
case of ROVER (Recognizer Output Voting Error Reduction, NIST 1997) — worth
knowing by name, because the published work explains why voting across systems
beats improving any one of them. Do not discard a "redundant" second recording
of a meeting you already have; it is a reference transcript for exactly the
values that matter most. If only one recording exists and a number is
load-bearing, settle it by ear through the path this skill already has: wire the
transcript's `audio:` frontmatter (see "Wiring audio for a Feishu-minute
transcript"), enqueue the number as a review item, and press `Q` in the review
dashboard — it plays exactly the anchored utterance, so you hear the digits
spoken instead of re-reading them.

**Numeric-slot damage — when a replacement overshoots into a number.** A
distinct failure with the same symptom: a global replace aimed at something else
lands inside a numeral. The classic trigger is relabelling a speaker whose
diarization label is a bare digit — replacing that digit globally fixes the
speaker lines and quietly corrupts every number containing it (`21 册`,
`3+1`, `8.8 折`, and the date in the title all lose a digit to a name). The
transcript still reads fluently; only the numbers are wrong. A dictionary rule
that overshoots produces the same signature.

```bash
# Scan for canonical terms sitting where a digit belongs. The needle list is the
# dictionary's own to_text values — the strings this toolchain writes INTO
# transcripts are exactly the ones that shouldn't be inside a number.
uv run scripts/scan_numeric_consistency.py transcript.md --domain <project>
```

Everything it prints is a **candidate to read**, never an edit to apply — and
the polarity class is deliberately not automated, because a check that fires on
healthy input is one people stop running.

What you can verify yourself: `scripts/tests/test_numeric_consistency.py` pins
both halves of that promise on synthetic fixtures — every damage shape above is
detected, and the healthy-input shapes that killed two earlier versions of this
scanner (a term merely co-occurring with digits, a term *before* a digit, a
title's leading date, a timezone offset) stay silent. Run it with
`uv run --with pytest python -m pytest scripts/tests/test_numeric_consistency.py`.
The false-positive *rate* behind those choices was measured on a private
transcript corpus that cannot ship, so the rate is not reproducible here — the
behaviour it bought is.

### Efficient Batch Fix Strategy

When fixing multiple files (e.g., 5 transcripts from one day):

0. **Diff raw for every file BEFORE touching anything** — if the batch came from a pipeline whose pre-classify stage ran an automated corrector, the filed copies are NOT raw ASR: upstream edits are baked in with no evidence trail, and every one of them is itself a suspect (an upstream AI "correction" can be a fluent wrong guess — grammar-perfect, wrong). Compare each filed transcript against its raw source (sync engines usually keep `transcript_raw.txt` alongside, or re-pull from the source API) and triage every upstream change FIRST: sound-distance test per change, revert the rewrites, treat the confirmed ones as settled (never re-propose them). This is the batch-scale version of the single-file upstream-diff in Native AI Correction step 2 — for a batch it is step 0, because everything you read afterwards is colored by whether you are reading raw or corrected text.
1. **Stage 1 in parallel**: run all files through dictionary at once
2. **Read all files first**: build a mental model of speakers, topics, and recurring terms before fixing anything
3. **Compile a global correction list**: many errors repeat across files from the same session (same speakers, same topics). **If an error recurs — especially a person name or project term — `--add` it to a project `--domain` (see "Project-Specific & Person-Name Corrections" above) instead of replacing it inline; it then auto-fixes every future file, not just this batch.**
4. **Apply the remaining one-off corrections** (sed with multiple `-e` flags, for genuinely non-recurring fixes only), then per-file context-dependent fixes
5. **Verify all diffs**, archive all final files and clean up sidecars, then do one dictionary addition pass
6. **Run the trap-scan** (Native AI Correction step 6) across the whole batch once — the domain's documented homophone traps, mechanically, after your read-through, to catch what the read missed
7. **Reconcile your uncertains against the user in ONE pass, then compound immediately** — a batch produces a shortlist of unverifiable candidates (a garbled name, a version number your training data contradicts, a name variant you cannot canonicalize). Present the whole shortlist at once (not item-by-item as you go): the user can hear the audio / know the person, and each verdict lands the same way — fix the file, `--add` the confirmed variant to the `--domain` dictionary, and record it in the people roster or domain context in the same session. Four such mid-turn verdicts in one real session (2026-08-08) all compounded the same turn they were given. A version-number claim your training data contradicts is NOT an error until the user says so — "the current date is 2026, v4 exists" outranks a stale recollection of when v3 shipped; present, don't pre-judge.

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
- `fetch_minute_audio.py` — Fetch a Feishu/Lark minute's audio, verify it shares the transcript's timeline, print the `audio:` frontmatter line (wires up dashboard `Q` playback)

**References** (load as needed):
- **Safety**: `false_positive_guide.md` (read before adding rules), `database_schema.md` (read before DB ops)
- **Workflow**: `iteration_workflow.md`, `workflow_guide.md`, `example_session.md`, `example_session_dji_minutes.md` (recorder→妙记 full-session case: in-document self-proof chains, second-pass rejection criteria, enqueue granularity), `domain_context_guide.md` (format + template for per-domain context files)
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
