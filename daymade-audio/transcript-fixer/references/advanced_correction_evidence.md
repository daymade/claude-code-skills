# Advanced correction evidence

Read the matching section when the transcript contains load-bearing numbers, a second recording, in-room written artifacts, or a multi-file batch.

## Contents

- Common ASR error families
- Numeric consistency and audio verification
- Whiteboard and slide-photo evidence
- Efficient batch correction
- Large-batch agent constraints

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

Person names and company names also produce consistent ASR errors across sessions — route confirmed variants through [dictionary_identity_and_context.md](dictionary_identity_and_context.md), using a project domain or people roster rather than a global rule.

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
transcript's `audio:` frontmatter (see [review_queue_dashboard.md](review_queue_dashboard.md)), enqueue the number as a review item, and press `Q` in the review
dashboard — it plays exactly the anchored utterance, so you hear the digits
spoken instead of re-reading them. For names and terms rather than numbers, a
photographed in-room artifact can stand in as the second system — see "In-room
artifacts are another independent engine" below.

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

### In-room artifacts are another independent engine (whiteboard and slide photos)

The two-recordings rule above has a cross-modal sibling. When the meeting
produced a written artifact — a whiteboard, a flip chart, a projected slide — a
photo of it is an independent recognizer alongside the recording(s): the second
engine when you have one recording, the third when you have two. Handwriting
fails on strokes (illegible scrawl) and ASR fails on sounds (homophones), so in
principle their errors are largely uncorrelated — that is the mechanism claim;
the yield reported at the end is one observed case (n=1), not a measured rate.

Ask for the artifact before triaging: does a photo of the board or slides
exist? A minutes-pipeline transcript often has the meeting's attachments
nearby; if the owner is not obvious, ask rather than guess. Then locate the
segment where the artifact was **created** — search the transcript for the
artifact's own phrases, falling back to photo-talk cues, the photo file's
timestamp against the transcript timeline, or speaker-turn structure. A
zero-hit grep for a board word is an instrument report, not absence: the
board's words are exactly what ASR may have garbled. And note the photo you
hold may have been taken later than any photo-talk in the text — the talk
locates the writing moment, not necessarily this shot.

Prefer phrase-matching and treat the timestamp fallback as the weakest of the
four, because for relayed media it is not merely absent but *systematically
wrong*: a photo forwarded through a chat app carries the **re-export** time,
not the capture time. Measured on one WeChat-relayed board photo, both the
filesystem creation date and the ms-epoch embedded in its `mmexport…`
filename decoded to the same value — the moment it was re-downloaded, hours
after the meeting it documented. Leaning on that would have placed the
artifact *after* the discussion and argued against a pairing that
phrase-matching then confirmed. So when the file's time says "later," treat
that as unresolved rather than as evidence, and go find the phrases.

**Work board-first, and remember a garbled name reads as fluent text, not as
noise.** For each board token, find the moment it was written and ask what in
that utterance corresponds to it. The ASR side of a name garble is usually a
fluent, semantically unrelated phrase sitting in the right slot (a latin
company name arriving as an ordinary two-word Chinese phrase) — so test the
slot; scanning for gibberish finds nothing. Four outcomes:

- **Speech garbled, board legible** — the board spelling wins *only when the
  writer plausibly knows the canonical form* (their own org, their client, a
  name they use daily). A name the writer first heard in that same meeting is
  a same-source error — the writer may have misheard it too — not a second
  engine: route it to the queue. Where this anchor holds and the raw text
  confirms it, it discharges [native_ai_full_workflow.md](native_ai_full_workflow.md)
  step 6's route-to-queue exception for that item; absent it, that exception stands.
- **Board illegible, speech clear** — the spoken words resolve the scrawl.
- **Both channels carry a plausible but different reading** of the same slot —
  that is a disagreement, never a garble-resolution, even when one side looks
  stronger. Enqueue it as an uncertain item ([native_ai_full_workflow.md](native_ai_full_workflow.md)
  step 7,
  `kind: entity`); in a batch it also joins the batch strategy's step-7
  shortlist below.
- **Only one channel has the item at all** (a board word nobody spoke, a
  spoken name never written) — single-source: a lead, not a confirmation.

A fix anchored by both channels clears the bar two independent recognizers
set — **but evidence strength does not change destination routing**. The
The matrix in [dictionary_identity_and_context.md](dictionary_identity_and_context.md) applies in full: real-name /
real-brand rows stay ❌ no matter how well anchored; deterministic non-word
fixes go to `--add` / the roster, context-dependent ones to the domain context
file; the FROM-side collision check and corpus probe still run. When recording
the fix, note which two channels anchored it in the destination itself (the
context file's trap line or the roster's variant line — e.g. `双证:白板+口述
2026-08`).

Observed once (2026-08, one 8-minute write-while-talking segment × one phone
photo): four transcript fixes anchored by the board — two of them company
names neither engine had settled alone — plus three board scrawls resolved
from speech, and one both-sides-plausible disagreement correctly left open.

### Efficient Batch Fix Strategy

When fixing multiple files (e.g., 5 transcripts from one day):

0. **Diff raw for every file BEFORE touching anything** — if the batch came from a pipeline whose pre-classify stage ran an automated corrector, the filed copies are NOT raw ASR: upstream edits are baked in with no evidence trail, and every one of them is itself a suspect *until its provenance is checked* (an upstream AI "correction" can be a fluent wrong guess — grammar-perfect, wrong). Compare each filed transcript against its raw source (sync engines usually keep `transcript_raw.txt` alongside, or re-pull from the source API) and triage every upstream change FIRST: sound-distance test per change — after checking each swap's provenance (a dictionary rule behind it = a prior settled decision with a higher revert bar; see [native_ai_full_workflow.md](native_ai_full_workflow.md) step 2) — revert the rewrites, treat the confirmed ones as settled (never re-propose them). This is the batch-scale version of that single-file upstream-diff; for a batch it is step 0, because everything you read afterwards is colored by whether you are reading raw or corrected text.
1. **Stage 1 in parallel**: run all files through dictionary at once
2. **Read all files first**: build a mental model of speakers, topics, and recurring terms before fixing anything
3. **Compile a global correction list**: many errors repeat across files from the same session (same speakers, same topics). **If an error recurs — especially a person name or project term — route it through [dictionary_identity_and_context.md](dictionary_identity_and_context.md) instead of replacing it inline; it then compounds into future files, not just this batch.**
4. **Apply the remaining one-off corrections** (sed with multiple `-e` flags, for genuinely non-recurring fixes only), then per-file context-dependent fixes
5. **Verify all diffs**, archive all final files, and clean only disposable sidecars; retain every `*_changes.md` and `*_needs_review.md` report until step 7 closes the decisions it represents. Then do one dictionary addition pass
6. **Run the trap-scan** ([native_ai_full_workflow.md](native_ai_full_workflow.md) step 6) across the whole batch once — the domain's documented homophone traps, mechanically, after your read-through, to catch what the read missed
7. **Reconcile your uncertains against the user in ONE pass, then compound immediately** — a batch produces a shortlist of unverifiable candidates (a garbled name, a version number your training data contradicts, a name variant you cannot canonicalize). Present the whole shortlist at once (not item-by-item as you go): the user can hear the audio / know the person, and each verdict lands the same way — fix the file, `--add` the confirmed variant to the `--domain` dictionary, and record it in the people roster or domain context in the same session. Only after every item represented by a retained `*_changes.md` / `*_needs_review.md` report has an explicit disposition may that report be removed. Four such mid-turn verdicts in one real session (2026-08-08) all compounded the same turn they were given. A version-number claim your training data contradicts is NOT an error until the user says so — "the current date is 2026, v4 exists" outranks a stale recollection of when v3 shipped; present, don't pre-judge.

### Parallel via Dynamic Workflow (large batches)

For a large batch (10+ files), a Dynamic Workflow — one subagent per file, running in parallel — is faster than a shell loop and gives each file full AI attention. Four rules earned the hard way; skipping any of them has caused real damage:

1. **Hardcode the file list into the script — don't pass it through `args`.** A Workflow `args` array of strings containing non-ASCII characters, brackets, or path separators can silently arrive empty: the script sees zero files, no agents spawn, and it exits instantly with something like "no files". Plain alphanumeric tokens pass fine, but file paths should go straight into a `const FILES = [...]` literal in the script body, guarded with `if (!FILES.length) return`.

2. **Scope each agent to exactly one file, and forbid cross-file `grep -r` / `sed` in its prompt.** Left unconstrained, an agent will turn a local fix ("this garbled term → correct term, here") into a global search-and-replace and edit unrelated files that were never part of the batch. State the single file path and an explicit "only edit this one file" instruction.

3. **After the batch, verify with `git diff` before trusting it** (works when the files are under version control):
   - `git diff --name-only` against your intended list — this catches any agent that strayed outside its assigned file. Stop and inspect each stray under the repository's own worktree-safety process; never run a blanket `git checkout`/restore that can discard another writer's work.
   - `grep` the deleted (`-`) lines for invariants that must never change. For speaker-diarized transcripts, that invariant is the **speaker-label lines** — an ASR fix should only ever touch spoken content, never alter or reassign who-said-what. Confirm zero speaker lines were deleted or changed.

4. **Run the aggregated dictionary suggestions through the false-positive filter before saving any of them.** Parallel agents collectively propose far more rules than are safe — and they don't see each other's suggestions, so duplicates and overreach pile up. Keep only unambiguous **non-word → correct-term** mappings. Drop anything whose "from" side is a real word in some context: a common word, or a term that's only wrong inside one domain. A global dictionary rule on a real word silently corrupts every future transcript — exactly what [false_positive_guide.md](false_positive_guide.md) warns about. (In one real batch, ~80 raw suggestions collapsed to ~18 safe ones after this filter.)
