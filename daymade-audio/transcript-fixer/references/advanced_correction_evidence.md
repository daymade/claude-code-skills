# Advanced correction evidence

Read the matching section when the transcript contains load-bearing numbers, a second recording, an authorized clip-level recognizer cross-check, in-room written artifacts, or a multi-file batch.

## Contents

- Common ASR error families
- Numeric consistency and audio verification
- One recording, two engines (clip-level cross-check)
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

**Coverage is a separate claim from item correctness.** A clip can settle one
anchored name or number; a handful of clips cannot prove that a two-hour
transcript was checked end to end. For a high-stakes request to produce a
higher-quality or complete transcript, designate one canonical body, run an
independent ASR across the complete clearest/canonical recording by loading
**`/daymade-audio:asr-transcribe-to-text`** and using its full-file route, then compare
the complete overlap from every additional recording. Bring over only a
genuinely non-overlapping tail; never interleave two bodies or their speaker
labels. If the independent ASR covered only selected clips, say `sampled
cross-check only — incomplete` and keep the whole-transcript completion gate
open. Prefer a recognizer different from the canonical body's producer. A
full-file run with the same recognizer proves coverage, not independent recognizer
agreement, so label that evidence boundary instead of calling it corroboration.

**Entity disagreement is a human gate, not a vote.** When channels produce
different plausible people, companies, products, or places and the local
authority ladder does not settle the slot, collect the forks into one shortlist
and ask the user. This is mandatory for person names. After the user confirms
that two legitimate forms are aliases for the same person, preserve the form
actually spoken in each utterance; identity equivalence does not authorize
normalizing one valid alias into another.

**Queue presence is not issue resolution.** A native pass can correctly detect
a nonsense span and enqueue it while the canonical body still contains that
span verbatim. Before claiming a higher-quality or final transcript, re-list
the queue against the exact canonical file and require zero `pending` rows. If
any remain, enumerate them and label the artifact `draft / unresolved —
incomplete`; never translate “the tool caught it” into “the transcript fixed
it.” When independent channels support different plausible replacements, the
row stays pending until evidence or the human settles it — recognizer count is
not a verdict.

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

### One recording, two engines — the cross-check you can run yourself

The two-recordings rule above needs a second recording, and the artifact rule
below needs somebody to have photographed the board. Neither is available on a
typical call. A second recognizer from a genuinely different family can still
provide useful, partially independent evidence from the same signal. This is a
clip-level application of recognizer-output comparison, not proof: correlated
training data and shared acoustic ambiguity can make two engines agree while
both are wrong.

This fills a real gap in the paths above, not a duplicate of them. Whole-file
independent ASR is the answer to "produce a better complete transcript"; the
dashboard's `Q` is the answer to "let a human hear this one utterance." Neither
is the answer to "the agent is stuck on one word right now" — which is precisely
where an agent, out of cheaper options and under delivery pressure, starts
reasoning from world knowledge and writes a fluent wrong guess. **That is the
failure this section exists to prevent: it gives an exhausted search ladder a
sanctioned next step.**

**Method.** This route requires `ffmpeg` and `ffprobe` plus a recognizer whose
family and authorization are already known. Check those prerequisites before
starting; do not install a model, download weights, or send audio externally just
because this section names the capability.

- **Get the source audio** from whichever channel owns the recording — the
  meeting platform's API, the local file the transcript came from, the
  recorder's export. `fetch_minute_audio.py` implements one such platform; the
  method is not limited to it. For a Feishu/Lark minute, run the bundled helper
  only under the already-authorized owning profile and require its timeline
  verification before using the file:

  ~~~bash
  uv run scripts/fetch_minute_audio.py --token <minute-token> \
    --profile <authorized-profile> --output <session.m4a> \
    --transcript <transcript.md>
  ~~~

  `ffmpeg -ss` counts from the start of the media file. Before trusting a
  transcript timestamp, calibrate one timestamp whose neighbouring words you can
  hear; a trimmed recording or wall-clock timestamp uses a different clock and
  otherwise reproduces the same mis-cut failure this rung is meant to prevent.
- **Cut two clips, not one.** A tight cut (~±5 s around the token) stops a
  second engine from being dragged by surrounding context into "repairing" the
  token into something fluent. A medium cut (~±20 s) keeps enough acoustic
  context that the tight clip's own truncation doesn't distort it. A mismatch
  between the two windows is itself a signal. Mono 16 kHz is what engines want; the
  preprocessing is owned by `/daymade-audio:asr-transcribe-to-text`.
- ⚠️ **A long turn's timestamp marks the turn's start, not the token's.** Cut
  from the line's timestamp on a multi-minute turn and the clip can end tens of
  seconds before the word ever arrives. You then read "the engine didn't produce
  that token" as evidence, when you simply never played the right audio.
  Three things make this tractable:
  - **Estimate the offset by position in the turn**, since speech rate within one
    turn is roughly constant: `token_start ≈ turn_start + (characters before the
    token ÷ characters in the turn) × turn_duration`, where `turn_duration` is the
    next speaker timestamp minus this one. For the final timestamped turn (or a
    one-speaker file with no later timestamp), read the media duration and use
    `audio_duration - turn_start` instead:

    ~~~bash
    ffprobe -v error -show_entries format=duration \
      -of default=noprint_wrappers=1:nokey=1 <source-audio>
    ~~~

    If neither a later timestamp nor media duration is available, do not invent a
    duration: enqueue the token or ask once. Widen the window rather than trusting
    the estimate — a ±20 s cut absorbs a sizeable error.
  - **Cut with the offsets you computed**, mono 16 kHz. Clamp each start at zero
    and use distinct filenames; otherwise the medium cut can overwrite the tight
    one and make a clip look as though it corroborated itself:

    ~~~bash
    TOKEN_START_SECONDS=123.456  # replace with the computed offset
    SOURCE_AUDIO=/tmp/session.m4a
    TIGHT_CLIP=/tmp/clip-tight.wav
    MEDIUM_CLIP=/tmp/clip-medium.wav
    tight_start="$(awk -v t="$TOKEN_START_SECONDS" 'BEGIN{s=t-5; if(s<0)s=0; printf "%.3f",s}')"
    medium_start="$(awk -v t="$TOKEN_START_SECONDS" 'BEGIN{s=t-20; if(s<0)s=0; printf "%.3f",s}')"
    ffmpeg -y -ss "$tight_start" -t 10 -i "$SOURCE_AUDIO" \
      -ac 1 -ar 16000 -c:a pcm_s16le "$TIGHT_CLIP"
    ffmpeg -y -ss "$medium_start" -t 40 -i "$SOURCE_AUDIO" \
      -ac 1 -ar 16000 -c:a pcm_s16le "$MEDIUM_CLIP"
    ~~~

  - **Distinguish "I missed the token" from "the engines disagree"** — otherwise a
    mis-cut reads as a finding. Check the returned text for the words that
    *surround* the token in the transcript: absent → the window was wrong, re-cut;
    present while the token itself differs → that is a real disagreement. **Stop
    after two re-cuts** that still don't land the token: at that point the anchor
    itself is unreliable, so enqueue the item rather than cutting indefinitely.
    If the tight and medium windows yield different readings, that is
    non-convergence; never choose the window whose answer you prefer.
- **Use an engine from a different family than the one that produced the
  transcript** — the same constraint the whole-file rule above states. Re-running
  the same engine reproduces its own error, and two builds of the same family are
  weak evidence. Use the second recognizer only when the current authorization
  already covers its local or external execution; otherwise enqueue the item or
  ask once rather than silently spending money or sending audio away. Route an
  authorized clip through
  `/daymade-audio:asr-transcribe-to-text` and take its plain-text opt-out
  (`--no-diarization`) — speaker diarization on a ten-second clip is noise.
  **Find out what produced the canonical text before you pick the second engine**:
  the transcript's frontmatter or the project's ingest log normally names it (a
  meeting platform's built-in ASR, a local model run). When nothing records it,
  one extra result cannot establish cross-family agreement: use two clip engines
  known to differ by construction, or keep the token Uncertain. When provenance
  is known, the transcript producer plus one different-family clip result is the
  minimum pair; the transcript text is evidence only after neighbouring words
  prove the clip is aligned. **If the only recognizer available is the one that
  produced the transcript**, you may still cut and read the clip yourself, but
  say so: that run is not independent corroboration, the token stays Uncertain,
  and the boundary gets stated the same way the whole-file rule states it.

**Reading the result — and the first row's limit matters more than the row:**

| Engines | Verdict |
|---|---|
| **Agree on token X** | The sound is strongly corroborated, not proven. Reject an unsupported rewrite of X into something that sounds different. If X is unfamiliar, keep it unchanged while checking an authority that is permitted for that token. |
| **Disagree, and one reading is settled by the in-document self-proof** — step 6's three conditions, all required: the proof occurrence is verified in the **raw** text, only one of the candidates occurs correctly, and the passage is genuinely *about* that referent | Minimal edit to that reading, recorded like any other fix. **Person names are excluded from this row** — they go to the human gate whatever the clip says. |
| **Don't converge** | Keep the original, enqueue it (the review queue), and wire the clip so a human listens once instead of the agent guessing four times. |

**For an alphabetic token, try an exact local search before the clip.** An
acronym, ticker, or model ID is often written byte-for-byte in project docs,
configs, or the domain ledger; that local lookup is cheaper and does not expose
an unknown internal token to an external service. Use WebSearch only when
existing evidence makes the entity public, or the user explicitly authorizes the
lookup. Whatever a search returns, it licenses no expansion: keep the token the
speaker uttered rather than replacing it with a full phrase.

**Agreement corroborates the sound, not the word.** Cross-family convergence is
evidence about what was pronounced; it does not choose which written word that
pronunciation denotes. For an alphabetic token — an acronym, ticker, or model
ID — sound and spelling are often the same object, so the evidence is stronger.
For a Mandarin homophone it settles much less: engines agreeing on `lì zhì`
leaves `利智` / `离职` entirely open, and the correct written form may be a
homophone neither engine produced. Use the first row only to reject unsupported
sound-distant rewrites; it never overrides in-document self-proof or the human
gate for person names. Tone alone is not sound distance for this decision: a
tone-only difference remains a homophone question for the local authority ladder.

**Cost boundary.** One token costs a download plus several ASR passes. Spend it
only on a **load-bearing** token — one naming an entity, carrying a number, or
anchoring a claim someone will act on — and only after the cheaper rungs have
struck out. Firing it at ordinary disfluency is the over-armed check that trains
operators to skip gates.

That definition asks what the token *is*, which is exactly what you don't know in
the case this rung exists for. Use the operational form instead: **an unresolvable
non-word sitting in a document that will drive a decision is load-bearing by
default** — the cost of one clip is small against a wrong entity in a deliverable.
What the boundary actually excludes is the residue you *can* already read: filler,
repetition, an intelligible common word you merely find inelegant.

**Coverage is still a separate claim.** Clips constrain their own anchors and
nothing else; the completeness rule above is unchanged by this section.

**Example.** If both tight and medium clips return the same unfamiliar
alphabetic token and its neighbouring words prove the window is correct, keep
that token unchanged and search the permitted local authorities for its exact
spelling. Do not replace it with a familiar phrase merely because the phrase
fits the topic.

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
7. **Reconcile your uncertains against the user in ONE pass, then route each verdict** — a batch produces a shortlist of unverifiable candidates (a garbled name, a version number your training data contradicts, a name variant you cannot canonicalize). Present the whole shortlist at once (not item-by-item as you go): the user can hear the audio / know the person. Fix every confirmed occurrence immediately, then use the destination matrix in `SKILL.md`: only recurring deterministic garbles go to `--add`; important people go to the roster; contextual traps go to the domain context; rare sentence-local errors stay file-only. A human verdict proves the occurrence, not the replacement's reusability. Only after every item represented by a retained `*_changes.md` / `*_needs_review.md` report has an explicit disposition may that report be removed. `--close-sidecars --input <file>` decides that mechanically and removes the reports on `closed` (script_parameters.md). A version-number claim your training data contradicts is NOT an error until the user says so — "the current date is 2026, v4 exists" outranks a stale recollection of when v3 shipped; present, don't pre-judge.

### Parallel via Dynamic Workflow (large batches)

For a large batch (10+ files), a Dynamic Workflow — one subagent per file, running in parallel — is faster than a shell loop and gives each file full AI attention. Four rules earned the hard way; skipping any of them has caused real damage:

1. **Hardcode the file list into the script — don't pass it through `args`.** A Workflow `args` array of strings containing non-ASCII characters, brackets, or path separators can silently arrive empty: the script sees zero files, no agents spawn, and it exits instantly with something like "no files". Plain alphanumeric tokens pass fine, but file paths should go straight into a `const FILES = [...]` literal in the script body, guarded with `if (!FILES.length) return`.

2. **Scope each agent to exactly one file, and forbid cross-file `grep -r` / `sed` in its prompt.** Left unconstrained, an agent will turn a local fix ("this garbled term → correct term, here") into a global search-and-replace and edit unrelated files that were never part of the batch. State the single file path and an explicit "only edit this one file" instruction.

3. **After the batch, verify with `git diff` before trusting it** (works when the files are under version control):
   - `git diff --name-only` against your intended list — this catches any agent that strayed outside its assigned file. Stop and inspect each stray under the repository's own worktree-safety process; never run a blanket `git checkout`/restore that can discard another writer's work.
   - `grep` the deleted (`-`) lines for invariants that must never change. For speaker-diarized transcripts, that invariant is the **speaker-label lines** — an ASR fix should only ever touch spoken content, never alter or reassign who-said-what. Confirm zero speaker lines were deleted or changed.

4. **Run the aggregated dictionary suggestions through the false-positive filter before saving any of them.** Parallel agents collectively propose far more rules than are safe — and they don't see each other's suggestions, so duplicates and overreach pile up. Keep only unambiguous **non-word → correct-term** mappings. Drop anything whose "from" side is a real word in some context: a common word, or a term that's only wrong inside one domain. A global dictionary rule on a real word silently corrupts every future transcript — exactly what [false_positive_guide.md](false_positive_guide.md) warns about. (In one real batch, ~80 raw suggestions collapsed to ~18 safe ones after this filter.)
