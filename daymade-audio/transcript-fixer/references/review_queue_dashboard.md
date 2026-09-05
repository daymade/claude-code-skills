# Review queue and dashboard workflow

Read this file when uncertain items must survive the session, when resolving or re-anchoring a queued item, or when wiring audio playback for human review.

## Contents

- Queue CLI and action-pack semantics
- Decision-note promotion
- One-occurrence verdicts and sibling sweeps
- Anchor guards and re-anchoring
- Dashboard controls and audio playback
- Feishu/Lark minute-audio wiring

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
# Enqueue uncertain items (native_ai_full_workflow.md step 7; '-' reads stdin)
uv run scripts/fix_transcription.py --enqueue-review items.json
# Inspect
uv run scripts/fix_transcription.py --list-review            # pending, priority-sorted
uv run scripts/fix_transcription.py --list-review --review-file /absolute/canonical.md --review-status all --json
uv run scripts/fix_transcription.py --show-review 12         # full evidence + action pack
# Decide (agent path — humans use the dashboard)
uv run scripts/fix_transcription.py --resolve-review 12 --decision accepted --by reviewer
uv run scripts/fix_transcription.py --resolve-review 12 --decision overridden --override-to "正确词" --note "<evidence>"
uv run scripts/fix_transcription.py --resolve-review 12 --decision kept_original   # transcript was right
uv run scripts/fix_transcription.py --resolve-review 12 --decision reopen          # undo (reverts applied edits)
```

Each item carries: the original text (left untouched in the file), a pre-filled
suggestion, `kind` (`entity`/`unknown` lead the queue because a wrong identity
has higher business impact; the verdict is still file-only unless it separately
passes the reuse matrix; `homophone`/`wording` trail), the evidence your search ladder
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
missed one. One shape is recognised instead of refused: the context recorded
at enqueue reappears in the ledger-masked file with the resolved text in the
slot the original occupied — a fix applied by hand before the verdict (the
original may survive in other utterances far from the hint, or inside the
suggestion itself). The verdict is recorded, nothing is written, and the apply
log carries `already in place at the anchor — recorded without writing`
(`reopen` then re-pends the row without reverting anything). The recognition
fails closed, and the message says which, when the original still sits within
the resolve window (±3 lines around the line hint) outside the suggestion,
when the same neighbourhood
also appears with a third form in the slot (anywhere at the matched width, or
near the hint at any width down to two characters a side), or when the edit
touched the characters next to the slot; an anchored utterance deleted or
rewritten past both neighbours while an identical one elsewhere reads corrected
cannot be told from drift and is recorded as accepted. `--reanchor-review`
refuses a row whose context already reads corrected rather than re-pointing it
at a surviving occurrence. Machine callers should parse the stdout `error`
field rather than the bare return code (argparse usage errors also exit 2). On
`overridden`, only
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
| a stable FROM→TO correction will recur in this domain | `--add "<from>" "<to>" --domain <project>`, subject to [dictionary_identity_and_context.md](dictionary_identity_and_context.md) | |
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
repairs a line hint that points beyond the resolve window of a
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
judgement about *that sentence* — those are the context-dependent class that
[native_ai_full_workflow.md](native_ai_full_workflow.md) anchors to surrounding text, and the class the `争`→`蒸` row keeps out of
blanket rules. Propagating one across a file is the mistake the dictionary matrix
exists to prevent.

**And within `entity`, a verdict settles the entity, not every token that sounds
like it** — this is the entity carve-out in [native_ai_full_workflow.md](native_ai_full_workflow.md). An occurrence that is a
*referred-to* third party rather than the person being addressed ("I'll ask
`<token>` from the bank") can legitimately need the opposite answer: leave it and
enqueue it on its own. A verdict the human reached **by listening to one clip**
deserves the same caution — those seconds of audio settle that utterance, and a
second occurrence is a second utterance. Sweep the occurrences that are plainly
the same entity in the same sense; that is the ordinary case, and the one the
measurement above counted.

**Sweep after the whole batch is resolved, not between verdicts.** A swept
occurrence that a still-pending item is anchored to is recognised by that item's
guard only when the sweep put exactly the item's suggestion there (the item then
records `accepted` without writing); a sweep to anything else fails the guard
(`re_anchor_needed`, exit 2) and the item closes with `skipped` plus a note or
is enqueued afresh.

**An override fixes this occurrence; reusable learning is a separate decision.** On
`overridden` the queue drops the `dict_add` / `append_note` actions (they were
planned for the suggestion the human rejected), so the strongest signal in the
whole loop — a human personally correcting the AI — first lands only in the
exact file. Route it through [dictionary_identity_and_context.md](dictionary_identity_and_context.md):
only a stable recurring pattern gets `--add`; a rare sentence-local correction
stops file-local, and an identity relationship belongs in roster/context rather
than a replacement rule.

**Dashboard** (single reviewer, local):

```bash
uv run scripts/review-dashboard/server.py --file "/absolute/canonical.md"
# Optional: land on one entity fork while keeping the rest of this file visible
uv run scripts/review-dashboard/server.py --file "/absolute/canonical.md" --item <id>
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

The blue scope bar is a hard review boundary: its counts and cards belong only
to that canonical path. When the human says the markings are done, read the
same scope back before doing any more transcription work:

```bash
uv run scripts/fix_transcription.py \
  --list-review --review-file "/absolute/canonical.md" \
  --review-status all --json
```

`stats.pending_total: 0` closes this file's human gate. A global pending count,
the dashboard merely being open, or the human's chat message without this
readback does not.

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
([native_ai_full_workflow.md](native_ai_full_workflow.md) routes cross-language proper nouns there) — otherwise the reviewer opens
a card with no play button and no way to answer the question you asked.

**Stage 1 integration**: safe-mode deferrals are auto-enqueued
(`source: stage1_deferred`) at run time, so a caller discarding the sidecar no
longer loses them. Exception: an input under the OS temp dir is NOT enqueued
(the anchor would be a dead pointer once the staging copy vanishes) — the
`--json` `deferred` count still reports those to the caller, and the additive
`review_enqueued` field says how many landed in the queue.
