# Script Parameters Reference

Detailed command-line parameters and usage examples for transcript-fixer Python scripts.

> **Route warning:** this file documents the CLI surface, including legacy API
> stages. Inside Claude Code, the recommended workflow is explicit Stage 1 plus
> Native AI Correction; the parser's default `--stage 3` is backward-compatible
> CLI behavior, not the recommended skill route. Stage 3 is for automation that
> has no Claude/Codex agent available.

## Table of Contents

- [fix_transcription.py](#fixtranscriptionpy) - Main correction pipeline
  - [Syntax](#syntax)
  - [Parameters](#parameters)
  - [Review Queue Item Schema](#review-queue-item-schema)
  - [Usage Examples](#usage-examples)
- [fix_transcript_timestamps.py](#fix_transcript_timestampspy) - Normalize/repair speaker timestamps
- [split_transcript_sections.py](#split_transcript_sectionspy) - Split transcript into named sections
- [generate_word_diff.py](#generate_word_diffpy) - Generate word-level HTML diff
- [generate_diff_report.py](#generate_diff_reportpy) - Generate multi-format comparison report
- [Common Workflows](#common-workflows)
- [Exit Codes](#exit-codes)
- [Environment Variables](#environment-variables)

---

## fix_transcription.py

Main correction pipeline script supporting three processing stages.

### Syntax

```bash
uv run scripts/fix_transcription.py --input <file> --stage <1|2|3> [--output <dir|file.md>]
```

### Parameters

- `--input, -i` (required): Input Markdown file path
- `--stage, -s` (optional): Stage to execute (default: 3)
  - `1` = Dictionary corrections only
  - `2` = Stage 1 dictionary pass followed by API AI correction
  - `3` = Stage 1 + API AI correction + diff report
- `--output, -o` (optional): Where results are written — accepts either a **directory** (the sidecars `<stem>_stage1.md` / `_changes.md` / `_needs_review.md` are written into it) **or a file path** ending in `.md`/`.markdown`/`.txt` that is not an existing directory (the corrected Stage 1 output is written directly to that exact file). Defaults to the input file's directory. Every "Saved" / report line prints the full resolved path, so a misdirected output is visible immediately. (Passing a file path used to silently `mkdir` a directory of that name and hide the output inside it — fixed.)
- `--domain, -d` (optional): Restrict to one correction domain (default: all domains). Accepts a comma-separated list (`--domain myproject,myproject-alt`): every listed domain's rules load as one union for Stage 1, and `--apply-domain` trusts the whole union. Write commands (`--add`, `--approve`, `--add-context-rule`) still require exactly one domain and fail fast on a list. Domain naming also scopes two more things at Stage 1: context rules (global rules always load; a domain-named rule loads only when its domain is active) and **trap demotion** — when `~/.transcript-fixer/contexts/<domain>.md` exists, traps annotated `禁裸词`/`禁入词典` and confirmed-correct （勿修） records demote any same-FROM dictionary rule to safe-mode deferral (beating `--apply-domain` trust-flattening; `--apply-all` still overrides). Without `--domain` no veto fires (a whole-library run has no owner to veto with); in a multi-domain union the veto applies by FROM across the whole union, regardless of which named domain owns the rule or the context file. Demotions are printed on stderr (`🛡️ Trap demotion: N rule(s)…`), never silent.
- `--apply-all` (optional): Opt out of the default safe mode and apply every risk level (low/medium/high). Higher false-positive risk — see false_positive_guide.md.
- `--review` (deprecated): No-op kept for backward compatibility; safe mode is now the default.
- `--dry-run` (optional): Preview Stage 1 changes to `*_dryrun.md` without writing `*_stage1.md`.
- `--changes-file` (optional): Always write `*_changes.md` (already on by default in safe mode).
- `--json` (optional): Emit the original six fields (`applied`, `deferred`, `output_path`, `needs_review_path`, `input_unchanged`, `review_enqueued`) plus `stage1_only_incomplete`, `stage2_total_chunks`, `stage2_failed_chunks`, `stage2_degraded`, and `boundary_refused` (dictionary matches the word-boundary check refused — neither applied nor deferred; `0` under `--apply-all`, which switches the check off). All eleven fields are always present. Stage 1 reports `stage1_only_incomplete=true`, both Stage 2 counters as `0`, and `stage2_degraded=false`; the caller must run Native AI or explicitly choose the agent-less Stage 2/3 route before claiming end-to-end completion. Stage 2/3 replace the telemetry defaults with the actual API outcome. Any failed chunk is retained from source and makes `stage2_degraded` true, so automation must not equate exit 0 with a fully corrected API pass.

**Evidence commands** (read-only; turn the native pass's manual grep loops into single invocations — semantics in [native_ai_full_workflow.md](native_ai_full_workflow.md) steps 4-6):

- `--scan-traps --context-file <domain-context.md> -i <transcript>`: parse every `**误识 → 正确**` entry out of a domain context file and locate each variant in the transcript (line number + context window), grouped by entry. Legacy `≈` entries use the same left-observed/right-intended convention. Wrap an exact multi-word FROM variant in backticks (for example `` `CC 思维链` ``); bare whitespace remains unparseable. `**X = …勿修…**` confirmed-correct records are reported as keep-as-is. A single-line leading-frontmatter value under `asr_note` is excluded because it intentionally quotes old forms as correction provenance; multi-line YAML ledger values are not masked. Keywords, titles, and body text remain in scope. Entries with zero hits are listed so "scanned and absent" is distinguishable from "never scanned". Bullets the parser could not turn into a scannable entry at all are reported **first**, under `⚠️ N documented trap(s) NOT scanned` — one line per bullet, so the count is bullets rather than internal reasons. With `--json` the same information is the `unparsed` key: a list of `{raw, fragment, reason}`. A machine caller reading only `hits`/`no_hit` concludes "no traps here" from a scan that never looked at some of them, which is exactly the coverage gap this key exists to close. Shapes that stay deliberately silent (they are not coverage gaps): a rejected variant sitting beside a good one, Han-only prose split by a space, and an annotation parenthesis that cites or exemplifies the same rule
- `--probe <term> --corpus <dir>`: the term's real-meaning frequency across every `*.md` under the corpus dir (recursive) — per-file counts + sampled context windows + the verdict criterion (all-error → bare rule safe / any real meaning → anchored or do-not-add / zero → safe but compounds nothing)
- `--check-corpus` (with `--add`): run the same probe on the FROM term before the rule is written; advisory, never blocks. Requires `--corpus`
- `--json` works with both: one machine-readable result line on stdout

**Context rules** (regex rules applied before the dictionary at Stage 1; domain-scoped since schema v2.4 — run pending migrations first or `--add-context-rule` fails with the direction):

- `--add-context-rule PATTERN REPLACEMENT [--domain <project>] [--description TEXT] [--priority N]`: add a context-aware regex rule. PATTERN is a Python regex (validated at write time); omitting `--domain` writes a global rule that applies to every domain. Duplicate patterns and un-migrated databases are hard errors. Use it for corrections that are right only inside a specific recurring phrase — the middle channel between a bare dictionary rule and a prose context trap.
- `--list-context-rules [--domain <project>] [--all] [--json]`: list rules; `--domain` shows global rules plus that domain's, `--all` includes disabled ones.
- On a database not yet migrated to v2.4 there is no `domain` column, so by construction every rule is global: loading keeps the legacy behavior and never crashes; only `--add-context-rule` refuses, naming the migration.

**Review queue** (persistent store for uncertain corrections; semantics in [review_queue_dashboard.md](review_queue_dashboard.md)):

- `--enqueue-review JSON_PATH`: Enqueue items from a JSON file (`-` = stdin). Item fields: `{original, suggested?, file?, line?, context?, kind?, domain?, evidence?, actions?, priority?, source?}` — full field/alias table + gotchas in [Review Queue Item Schema](#review-queue-item-schema) below
- `--list-review`: List queue items, priority-sorted (filters: `--review-status pending|accepted|overridden|kept_original|skipped|all` default pending; `--domain`; `--review-source native_pass|stage1_deferred|learned_suggestion|manual`; `--review-file FILE` exact resolved transcript path). With `--review-file`, both `items` and `stats` are scoped to that one file; use `stats.pending_total == 0` as the final human-review gate.
- `--show-review ID`: One item in full (evidence + proposed action pack)
- `--reanchor-review ID [ID...]`: Re-anchor pending item(s) whose transcript drifted or moved since enqueue (refresh line/context verbatim from the current file; when the file is gone, search `--reanchor-root DIR` + the recorded parent dir for `*.md` containing the original text — unique candidate re-points the anchor, ambiguous asks for `--reanchor-to FILE` which names the target explicitly and is refused if the original is not in it)
- `--resolve-review ID --decision accepted|overridden|kept_original|skipped|reopen`: Record a verdict and execute the action pack (`overridden` requires `--override-to TEXT`; `--note` free-text evidence; `--by` reviewer name; `reopen` reverts applied edits and re-pends the item). When the resolved text is already in place — a hand edit landed before the verdict and the recorded context reappears with the text in its slot — `accepted` and `overridden` record the verdict without writing and log `already in place at the anchor — recorded without writing`; the original still within the resolve window of the hint outside the suggestion, a third form in that slot (anywhere at the matched neighbour width, or near the hint at any width down to two characters a side), or an edit touching the slot's neighbours still exits 2 with `re_anchor_needed`, and the message names which
- `--json` works with all five: one machine-readable result line on stdout

**Sidecar closure and lookup**:

- `--close-sidecars --input FILE [--output DIR] [--dry-run] [--json]`: decide whether the review sidecars beside `FILE` (or in `DIR`, which must exist — exit 2 `output_not_found` otherwise; the JSON `dir` field names the directory searched) are closed and remove them. Every `*_changes.md`/`*_needs_review.md` entry is re-read against the transcript with the `asr_note` ledger masked (`applied` / still the original / original absent from the whole file) and against the review queue rows for that exact resolved path (one row answers one occurrence, matched by nearest line across every entry of the pair; a pending row blocks). An entry counts as closed when its anchor reads with the suggestion, when the original form no longer appears anywhere in the ledger-masked transcript, or when a decided (non-pending) queue row for the same FROM→TO pair in this file answers it — one row per occurrence, consumed nearest-line first, because the queue keys rows by line as well as by pair; an entry whose FROM→TO rule has since been disabled as a false positive, with no active row left in the consulted scope (`--domain` when given, else every domain), is `disabled` (closed: no longer a question) — a matched queue row still wins over that; an entry whose original still appears in the file and has no row of its own is `undecided`. Verdicts: `closed` removes `_changes.md`, `_needs_review.md`, `_uncertain.md`, `_对比.html` and any `_stage1.md`/`_stage2.md`/`_dryrun.md` older than the transcript; `open` (undecided entries or pending rows) removes nothing and lists them; `blocked` removes nothing — a `_stage1.md` newer than the transcript (unpromoted, take the plain Stage 1 rerun), or a report whose declared `Total changes` exceeds the entries the parser reads or that has no header at all (`report_unparsed` names it; an unreadable report is evidence, not an empty one). `--dry-run` computes the verdict without deleting or recording anything.
- `--decide-raw kept_original|skipped [--by WHO] [--note TEXT] [--domain D]`: with `--close-sidecars`, record that verdict through the review queue for entries that still read as the original and have no row (enqueued as `stage1_deferred` under `--domain`, default `general`, then resolved), so the closure carries an audit trail. Ignored in `--dry-run`.
- `--discard-unpromoted`: with `--close-sidecars`, also remove a `_stage2.md`/`_dryrun.md` newer than the transcript; otherwise such run outputs are retained and named in `retained`.
- `--lookup TERM [--domain D] [--json]` (a blank TERM is a usage error, exit 2): every existing claim on a term — dictionary rules where it is FROM or TO (active and disabled; `--domain` narrows this section), context rules (`--domain` shows global plus the named domains; `--domain a,b` is accepted), roster-loaded name variants from the configured people roster, and review-queue rows (`original`/`suggested`). ASCII matching is case-insensitive. Prints `no trace anywhere` when every section is empty.

### Review Queue Item Schema

`--enqueue-review` accepts a JSON array of items (or `{"items": [...]}`). Only `original` is required. **Unknown keys are silently ignored** — a typo'd field name (e.g. `line_hint` instead of `line`) drops the value with no warning, and the item enqueues without that anchor. If the anchor matters, spot-check with `--show-review <id>` after enqueueing (real incident: an item enqueued with `line_hint` lost its line anchor silently).

| Canonical field | Alias | Required | Notes |
|---|---|---|---|
| `original_text` | `original` | ✅ | The transcript text left in place (non-whitespace) |
| `suggested_text` | `suggested` | | Pre-filled verdict; may be empty for a pure "is this right?" item |
| `file` | `file_path` | | Transcript the item anchors to; items anchored to **temp-dir paths are skipped entirely** — never enqueued (the anchor would be a dead pointer once the staging copy vanishes) |
| `line` | `line_number` | | Integer line hint for the anchor window |
| `context` | `context_snippet` | | Nearby text used to re-anchor if the file drifted since enqueue |
| `kind` | | | `entity` / `unknown` lead (compound into dict/roster); `homophone` / `wording` trail |
| `domain` | | | Default `general`; CLI `--domain` supplies it only for items that don't set their own (per-item `domain` wins — the CLI uses `setdefault`) |
| `source` | | | Default `manual`; `stage1_deferred` is set by Stage 1 safe mode |
| `evidence` | | | What the search ladder found (rendered on the review card) |
| `actions` | | | Action pack (`file_edit` / `dict_add` / `append_note`) run on accept; empty + file anchor + non-empty `suggested` = a single `file_edit` on accept (an empty `suggested` with no action pack errors at resolve time, not enqueue time) |
| `priority` | | | Default derived from `kind` |

Dedup key: `(file_path, original_text, suggested_text, domain, line_number)` — the same correction on two different lines is **two distinct review questions** (each gets its own window-scoped edit); re-enqueueing an already-answered item is skipped as a duplicate.

### Usage Examples

**Run dictionary corrections only:**
```bash
uv run scripts/fix_transcription.py --input meeting.md --stage 1
```

Output: `meeting_stage1.md` (only when corrections were applied — a 0-correction run writes no `_stage1.md`; safe-mode deferrals go to `_needs_review.md`)

**Run the API correction route (Stage 1 runs first automatically):**
```bash
uv run scripts/fix_transcription.py --input meeting.md --stage 2
```

Output: `meeting_stage2.md`

**Run complete pipeline:**
```bash
uv run scripts/fix_transcription.py --input meeting.md --stage 3
```

Outputs:
- `meeting_stage1.md` (when Stage 1 applied corrections; skipped on a 0-correction run)
- `meeting_stage2.md`

**Custom output directory** (sidecars written into it):
```bash
uv run scripts/fix_transcription.py --input meeting.md --stage 3 --output ./corrections
```

**Write the corrected Stage 1 output to a specific file** (a `.md`/`.markdown`/`.txt` path that is not an existing directory):
```bash
uv run scripts/fix_transcription.py --input meeting.md --stage 1 --output ./meeting.fixed.md
```

### Exit Codes

- `0` - Success
- `1` - Missing required parameters, file not found, or API key not configured (Stage 2/3)
- `2` - `--resolve-review` refused because the anchor text no longer matches the target file (re-anchor needed; nothing was applied — fail closed); also `--reanchor-review` when every requested id failed
- `3` - `--enqueue-review` rejected one or more items whose `original`/`context` is not verbatim in the declared file (see `rejected_unanchored` in the JSON; items in `added` WERE enqueued — fix the rejects and re-enqueue them)
- API request failures do **not** get a dedicated exit code — the pipeline keeps the original text and prints a warning (see [SKILL.md](../SKILL.md)「Agent-less API route」)

`--close-sidecars` uses `0` = `closed` (evidence removed), `1` = `open` (undecided entries or pending rows; nothing removed), `2` = `blocked` (unpromoted `_stage1.md`, an unreadable report, missing `--input`, or file not found); the JSON `verdict` field carries the same word.

`--report-false-positive` carries its own codes, because a caller could not
otherwise tell "I disabled it just now" from "it was already off" — both used
to return `0`:

- `0` - disabled by this run
- `1` - no such pair in this domain. Names the domains where it IS active, if any
- `2` - bad input: more than one `--domain` (disabling is per-domain), or a malformed domain name. Previously a bare traceback with empty stdout and exit `1`
- `3` - already disabled in this domain — nothing to do. Not an error
- `4` - supplied only by the people roster; no database row exists to disable. The message gives both ways forward (scope it to this domain with `--add` first, or remove the variant from the roster to stop it everywhere)

None of these paths writes `No active rule` to stderr any more: that warning
fires inside the service layer when it finds nothing, and it contradicted every
stdout message above, so a caller capturing `2>&1` saw both and one grepping for
it misread a normal outcome as fatal.

## fix_transcript_timestamps.py

Normalize speaker timestamp lines such as `说话人A 00:21` or `Speaker 7 01:31:10`.

### Syntax

```bash
uv run scripts/fix_transcript_timestamps.py <file> [--output FILE | --in-place | --check]
```

### Key Parameters

- `--format {hhmmss,preserve}`: output timestamp style
- `--rebase-to-zero`: reset the first detected speaker timestamp to `00:00:00`
- `--rollover-backjump-seconds`: threshold for treating `59:58 -> 00:05` as a new hour
- `--jitter-seconds`: tolerated small backward jitter before flagging anomaly

### Usage Examples

```bash
# Normalize mixed MM:SS / HH:MM:SS
uv run scripts/fix_transcript_timestamps.py meeting.txt --in-place

# Rebase a split transcript so it starts at 00:00:00
uv run scripts/fix_transcript_timestamps.py workshop-class.txt --in-place --rebase-to-zero

# Only inspect anomalies, do not write
uv run scripts/fix_transcript_timestamps.py meeting.txt --check
```

## split_transcript_sections.py

Split a transcript into named sections using marker phrases. Useful for workshop transcripts that include setup chat, class, and debrief in one file.

### Syntax

```bash
uv run scripts/split_transcript_sections.py <file> \
  --first-section-name <name> \
  --section "Name::Marker" \
  --section "Name::Marker"
```

### Usage Example

```bash
uv run scripts/split_transcript_sections.py workshop.txt \
  --first-section-name "课前聊天" \
  --section "正式上课::好，无缝切换嘛。对。那个曹总连上了吗？那个网页。" \
  --section "课后复盘::我们复盘一下。" \
  --rebase-to-zero
```

## generate_word_diff.py

Word-level HTML diff generator for comparing original and corrected transcripts.

### Syntax

```bash
uv run scripts/generate_word_diff.py <original_file> <corrected_file> [output_file]
```

### Parameters

- `original_file` (required): Original transcript file path
- `corrected_file` (required): Corrected transcript file path
- `output_file` (optional): Output HTML path (defaults to `<corrected_file>.diff.html`)

### Usage Examples

**Basic usage:**
```bash
uv run scripts/generate_word_diff.py meeting.md meeting_stage2.md comparison.html
```

**Review Stage 1 output:**
```bash
uv run scripts/generate_word_diff.py meeting.md meeting_stage1.md stage1_comparison.html
```

### Output

Generates an HTML file with color-coded word-level additions/deletions. Recommended for human review.

### Exit Codes

- `0` - Success
- `1` - Missing required parameters or file not found

## generate_diff_report.py

Generate a comprehensive comparison report across four formats: Markdown summary, unified diff, HTML side-by-side comparison, and inline marked text.

### Syntax

```bash
uv run scripts/generate_diff_report.py <original_file> <stage1_file> <stage2_file> [-o <output_dir>]
```

### Parameters

- `original_file` (required): Original transcript file path
- `stage1_file` (required): Stage 1 (dictionary) corrected file path
- `stage2_file` (required): Stage 2 (AI) corrected file path
- `-o, --output-dir` (optional): Output directory (defaults to the original file's directory)

### Usage Example

```bash
uv run scripts/fix_transcription.py --input meeting.md --stage 3
uv run scripts/generate_diff_report.py \
  meeting.md \
  meeting_stage1.md \
  meeting_stage2.md \
  -o ./diff_reports
```

### Output

Generates four files in the output directory:

- `<name>_对比报告.md` — Markdown summary report with change statistics
- `<name>_unified.diff` — Git-style unified diff
- `<name>_对比.html` — Side-by-side HTML comparison
- `<name>_行内对比.txt` — Inline marked comparison text

### Exit Codes

- `0` - Success
- `1` - Missing required parameters or file not found

## Common Workflows

### Testing dictionary changes inside an agent session

Test dictionary updates before the Native AI pass:

```bash
# 1. Add the rule (dictionary lives in SQLite, not a source variable):
#    uv run scripts/fix_transcription.py --add "错误词" "正确词" --domain <domain>
# 2. Run Stage 1 only
uv run scripts/fix_transcription.py --input meeting.md --stage 1

# 3. Review output
cat meeting_stage1.md

# 4. If satisfied, perform Native AI Correction with SKILL.md loaded.
```

### Agent-less API batch processing

Process multiple transcripts in sequence:

```bash
for file in transcripts/*.md; do
    uv run scripts/fix_transcription.py --input "$file" --stage 3
done
```

### Agent-less API review cycle

Generate and open word-level diff immediately after correction:

```bash
# Run corrections
uv run scripts/fix_transcription.py --input meeting.md --stage 3

# Generate and open diff (args: original, corrected, output.html)
uv run scripts/generate_word_diff.py meeting.md meeting_stage2.md meeting_diff.html

open meeting_diff.html  # macOS
# xdg-open meeting_diff.html  # Linux
# start meeting_diff.html  # Windows
```

## Environment Variables

The canonical source for configuration is `~/.transcript-fixer/config.json`. Environment variables are supported only as explicit overrides:

- `GLM_API_KEY` — override the GLM API key
- `ANTHROPIC_API_KEY` — alternative override name
- `ANTHROPIC_BASE_URL` — override the API base URL
- `TRANSCRIPT_FIXER_CONFIG_DIR` — change the config directory (default: `~/.transcript-fixer`)
- `TRANSCRIPT_FIXER_DB_PATH` — override the SQLite database path

For normal use, write the API key to `~/.transcript-fixer/config.json` instead of exporting it.
