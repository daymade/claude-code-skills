# Native correction action details

Read the named section before executing its action. The common native sequence remains in [native_ai_full_workflow.md](native_ai_full_workflow.md). Historical examples are optional [evidence](native_historical_evidence.md), not extra runtime steps.

## Native correction checklist

1. **Give the file its final name before Stage 1.** Queue anchors store absolute paths. Use a human-readable project filename before any deferral can enqueue. When the input arrives as inline text with no file yet — a slash-command argument, a pasted block — write it to a file before anything else; `--input` and the queue anchors both need a path, and a scratch location is fine when nothing downstream will archive it. No `--domain` given and none obvious from context? Omitting the flag already defaults to searching every domain (`--domain`'s own default), so don't block on picking one — run Stage 1 bare and let safe mode gate what auto-applies. If a specific candidate still needs resolving, one step of the ladder is cheap enough to keep even at fast tier though the rest of it isn't: [native_entity_triage.md](native_entity_triage.md) rung 1, a single cross-domain lookup — `--lookup "<term>"` prints every existing claim on the term (dictionary rules active or disabled, as FROM or TO; context rules; roster variants; queue rows) — not the full verification ladder the tier table tells you to skip, just that one query.
2. **Recover the raw baseline before reading a pre-corrected transcript.** If an ingest pipeline or previous API pass already touched the text, diff against the raw source first. Judge upstream edits as edits, not as ground truth.
3. **Load project priors and read the complete transcript.** Resolve the domain file through the [context location](domain_context_guide.md#location), read it when present, then read the whole transcript before deciding early ambiguities.
4. **Run Stage 1 and inspect the real result.** Prefer explicit project domains plus `--apply-domain --json`. Read `deferred` and `review_enqueued`; never silently discard the sidecar or queue gap.
5. **Diff Stage 1 against raw/original.** If a rule changed correct speech, work from the original, retire the stored pair with `--report-false-positive "<from>" "<to>" --domain <domain>`, and verify it no longer fires.
6. **Triage every candidate.**
   - Confident: the sound change is plausible and context or an authoritative local source settles it.
   - Needs verification: a person, company, product, model, ticker, place, number, or other load-bearing term without a source.
   - Uncertain: evidence does not settle it; leave the original and enqueue.
   - Multi-channel entity fork: when independent transcripts disagree on a person name or other proper noun and no local authority settles it, collect the unresolved forks and ask the human once. Do not guess, and do not treat a majority vote as identity evidence.
7. **Apply the smallest edit that explains the sound.** Do not add words the speaker did not say. Correct ASR-derived metadata too, while leaving `asr_note` intact. A Stage 1 deferral you now agree with is closed through its queue row, not re-applied with sed: `--resolve-review <id> --decision accepted` (ids from `--list-review --review-file "<absolute-canonical-file>" --json`) performs the edit, or records a fix you already applied by hand without writing. Either way the row ends `accepted`; `kept_original` asserts the transcript was right as spoken and is never the exit for a fix you applied.
8. **Run a second pass.**
   - Every tier: run `--scan-traps` and inspect both hits and `unparsed`.
   - Full tier: use fresh-context review. For a single unsplit review, assign one corrected file and require a compact residual table or explicit `no new residuals`; an empty/truncated response is a failed review.
   - For a split, multi-file, or resumed Full review, follow [native_review_packets.md](native_review_packets.md) for packet assignment, JSON results, validation, and recovery.
   - High-stakes multi-recording: a sampled clip settles only that anchored item. If the user asked for a higher-quality or complete transcript and the baseline audio is available, load **`/daymade-audio:asr-transcribe-to-text`** and run its full-file transcription path across the complete clearest/canonical recording before claiming whole-transcript coverage; otherwise report `sampled cross-check only — incomplete`. Prefer a recognizer different from the producer of the canonical body. If only the same recognizer is available, the run proves complete-source coverage but is not independent cross-recognizer corroboration; state that boundary.
9. **Enqueue every unresolved item; escalate selectively.** First apply [evidence selection and escalation](native_ai_full_workflow.md#evidence-selection-and-escalation), then follow `Review queue safety` below and [review_queue_dashboard.md](review_queue_dashboard.md). Open only this file when human review is needed. Detection and enqueueing are not correction: for a higher-quality/final claim, every queue row anchored to this exact file must leave `pending`. For human review, start the dashboard with `uv run scripts/review-dashboard/server.py --file "<absolute-canonical-file>"`; add `--item <id>` to land on one fork. If a human is unavailable, keep the artifact explicitly labeled `draft / unresolved — incomplete` and enumerate the rows; do not ship the raw suspect text under a completed quality claim.
10. **Read back the human state, then finalize.** When the human says they marked the dashboard, do not rerun ASR or ask the same questions again. First run `uv run scripts/fix_transcription.py --list-review --review-file "<absolute-canonical-file>" --review-status all --json`, apply any resulting file state, and require `stats.pending_total == 0` for that exact path; zero pending rows is required before the high-quality/final claim. Then diff the file actually edited, run numeric consistency when numbers matter, rerun plain Stage 1, re-grep known corrections, and confirm every change traces to a triage decision. Global queue counts cannot close or reopen this file's quality claim. Last, run `--close-sidecars --input "<absolute-canonical-file>"`: it re-reads every `*_changes.md`/`*_needs_review.md` entry against the file and the queue, refuses while an entry still reads as the original without a verdict or any row is pending, and removes the sidecars only when everything is closed (see `Finalization`).
    **Authority for a person-name verdict travels in `--authority` or a cited
    `--authority-record`, never in `--note`.** `--note` is your reason. The guard
    previews the cited authority; evidence is appended only with the successful
    verdict transaction, so a refused correction leaves the queue unchanged.
    Sources include roster rows, group displayName+nickName double-read, an
    explicit user decision, or audio evidence. A person-name
    `accepted`/`overridden` written without it is refused; a `kept_original` resting on
    such a source leaves the guard nothing to read and leaves `evidence` still asserting
    the enqueue-time doubt. Real case 2026-09-22: two queue rows for one nickname were
    settled with the citation in `--note`, so `--show-review` read `evidence` =
    "待用户确认" beside `decision_note` = resolved — one item carrying both "unresolved"
    and "settled" state. Repair with `--attach-authority ID --authority-text TEXT`, which
    appends and never rewrites. The two commands cannot share one line:
    `--attach-authority` and `--resolve-review` together are refused, because the natural
    one-liner "verified it, now settle it" ran only the append, printed ✅, exited 0 —
    and never recorded the verdict while telling the caller it had.
    For an explicit answer, use `--authority-record <JSON>` binding `item_id`,
    `target`, `source_ref` and exact `quote`; a bare yes also cites the original
    `question`. Inspect the actual user message first: the checker validates the
    citation's shape and scope, not its truth. A naked “用户明确回答” label, pending,
    denied, missing or empty evidence never substitutes for that source.
    Use the reference's finite affirmative-answer shapes; mentioning a target
    does not confirm it. Unsupported wording stays pending rather than being
    rewritten into a supported answer.
    When updating an existing single-line `asr_note` correction ledger, add
    `--ledger-entry` to the same verdict call: the resolved text and ledger entry
    share one file replacement. It does not create or rewrite the whole note.
    Read [cited answers and ledger writes](review_queue_dashboard.md#cited-answers-and-ledger-writes)
    for the schema and interrupted file/SQLite recovery. Inspect exit status and
    JSON/readback before downstream work; separate inspected calls, `&&` or
    checked subprocess execution stop on failure, while newline chaining can
    hide it behind a later successful command.
11. **Compound the learning in the same turn.** Route each stable pattern to its correct home; do not leave confirmed fixes only in chat. Native-pass edits never reach Stage 1's correction history, so harvest them mechanically right after the final diff:

    ~~~bash
    # Diff raw vs corrected into parseable trap candidates (review artifact —
    # you adjudicate the printed list; --write auto-appends only the recurring
    # (≥2x) non-bare candidates; --write-all also appends the one-off set)
    uv run scripts/harvest_corrections.py raw.md corrected.md \
      --context-file "<domain-context.md>"
    ~~~

    Every emitted bullet is round-trip verified through the real trap parser before printing, and pairs already documented in the context file are skipped. A pair the bullet grammar cannot carry — a side with no lexical content or a `*` in it, such as a vendor's `***` redaction mask diffed against the real word — is dropped at the noise filter, and any bullet that still fails to parse is reported on stderr and excluded rather than aborting the run. High-frequency candidates are strong traps; single-occurrence ones need a human judgment — that is why `--write` leaves them out by default — and ⚠️ 裸形 candidates are never auto-written. This replaces hand-writing trap bullets from memory.
12. **Propagate entity fixes deliberately.**

    First finish the same-file sweep: inspect `harvest_corrections.py --json`
    entries with nonzero `remaining`, then check the observed spelling family of
    each confirmed entity or technical identifier across body and ASR-derived
    metadata. Use the authoritative spelling and conventional filename casing;
    a user's informal dictation is not a request to preserve a typo. Preserve real
    alternate referents, aliases, and generic-character hits. Do not turn a
    same-file sweep into an unreviewed batch replacement or repeat settled questions. Then search
    only the owning project’s derived notes/summaries and review every hit; exclude
    raw ASR and correction sidecars because they preserve the evidence trail.

Follow [the required native sequence](native_ai_full_workflow.md) for action-time provenance, entity, cold-review and finalization references.

## Dictionary and identity safety

Read [references/false_positive_guide.md](false_positive_guide.md) and [references/dictionary_identity_and_context.md](dictionary_identity_and_context.md) before adding a rule.

| Pattern | Destination |
|---|---|
| Stable non-word or unique garble → canonical term | `--add ... --domain <project>` |
| Important recurring person and observed ASR variants | People roster |
| Correction right only inside a specific recurring phrase | `--add-context-rule PATTERN REPLACEMENT --domain <project>` (regex, domain-scoped; omit `--domain` for global) |
| Common/real word wrong only under a cue | Domain context trap, never a bare rule (a bare number or a single surname + 老师/总 is refused at roster load and by `--add` / `--import`, `--force` included) |
| Real name → different real name | Domain context + human/audio verification, never a bare rule |
| Confirmed-correct entity repeatedly reopened | Confirmed-correct context record |
| One-off sentence-local wording | Edit only; do not add |

Stage 1's match-time layer (the third of the three layers in [references/false_positive_guide.md](false_positive_guide.md): add time, apply time, match time) also refuses a dictionary match on its own at three checks before risk scoring: the superset check (the corrected form is already in place), the common-word boundary check for short rules, and the word-boundary check. That last one asks, by script, whether the match is a fragment of real words: an ASCII match with an ASCII letter directly beside it is inside a longer word (`Cloud` in `iCloud`; digits do not count, so `cloud3` still corrects); a CJK match is refused only when every segment of a dictionary-only jieba cut that overlaps it is a multi-character word and one of them crosses the match boundary (新一 in 更新|一下, 问题记 in 问题|记录, 同龄 in 同龄人) — one single-character segment under the match (巨|神智|能, 叫|新|一下|单) means an unknown fragment and the match proceeds. Refusals are counted as `Refused at word boundaries` and in the JSON `boundary_refused`, listed in the Stage 1 summary, and never deferred. The CJK half needs jieba; without it the check silently would not run, so it now says so — stderr warning, `CHECK OFF` in the summary, and `boundary_check_active: false` in the JSON, because `boundary_refused: 0` alone cannot tell a clean run from a disarmed one. A context rule (`--add-context-rule`) skips this check but still goes through risk scoring, so in safe mode its match is deferred to the review queue rather than applied — accept it there, or run `--apply-all`, which switches the check off and applies every match; `--apply-domain` keeps the check. The layers are listed in [references/false_positive_guide.md](false_positive_guide.md).

A context trap is a cue, not permission to replace blindly. Two annotation classes in a domain context file are **machine-readable vetoes that Stage 1 enforces** (when the domain is named via `--domain` — a whole-library run has no owner to veto with): a trap marked `禁裸词`/`禁入词典` demotes any dictionary rule with the same FROM to review, and a confirmed-correct （勿修） record demotes any rule whose FROM is that token — demotion beats `--apply-domain` trust-flattening, so a real-word rule (the 绿点→绿电 class: right in business context, wrong in UI context) can stay in the dictionary without firing blindly. `--apply-all` remains the operator's explicit override. Without the veto the only escape was `--report-false-positive`, which disables the rule in the contexts where it is right too. `--scan-traps` supports canonical `→` and legacy `≈` mappings with the same directional contract: left is observed ASR, right is intended text. Wrap an exact FROM phrase containing spaces in backticks:

~~~markdown
- **`CC 思维链`/`CC 思维连` → 目标术语** — only under the domain's documented cue
~~~

This demonstrates an exact ASR phrase candidate, not a person-name candidate. The domain context remains the authority for the real target and cue; the scanner only locates the literal FROM forms.

Before adding any real-word-shaped rule, measure the project corpus:

~~~bash
uv run scripts/fix_transcription.py \
  --probe "candidate" --corpus /path/to/project-transcripts/

uv run scripts/fix_transcription.py \
  --add "candidate" "canonical" --domain myproject \
  --check-corpus --corpus /path/to/project-transcripts/
~~~

User verdicts settle the occurrence immediately, but they do not make a replacement reusable. Fix the file first, then route the result through the table above: only a stable recurring pattern goes to the dictionary/roster/context; a rare sentence-local mishearing stays file-only. When the user confirms that two legitimate names or nicknames identify the same person, preserve whichever form was actually spoken and store the identity relationship as context, not as a replacement rule.

## Review queue safety

Read [references/review_queue_dashboard.md](review_queue_dashboard.md) before enqueueing or resolving.

Minimum item:

~~~json
[
  {
    "file": "/absolute/path/to/transcript.md",
    "line": 142,
    "original": "<suspect-token-only>",
    "suggested": "<best-candidate>",
    "kind": "entity",
    "context": "<verbatim sentence, or unique clause/span for same-line repeats>",
    "evidence": "<what was checked>"
  }
]
~~~

Safety rules:

- `file` is mandatory for this workflow. Without it, acceptance can record a verdict without editing the transcript.
- `original` is only the suspect token/span; never put the whole sentence there.
- `context` is copied verbatim; `line` is the key, not `line_hint`. For same-line repeats, use a unique context or add `context_offset` pointing to the intended token inside that context; see the queue reference for offset units and legacy-row repair.
- `suggested` is the key, not `suggestion`. Use `actions`, not `action_pack`.
- Inspect all `candidates` for a located occurrence and follow [candidate selection](review_queue_dashboard.md#one-occurrence-multiple-candidates) for an explicit candidate index or override. Use `--consolidate-review --review-file FILE` for a legacy batch, then repair reported ambiguous anchors explicitly. Read [written nonperson authority](review_queue_dashboard.md#written-authority-for-nonperson-names) before using that route; a system/product type alone cannot bypass person-name protection.
- Resolve one occurrence at a time; sweep sibling entity occurrences only after the whole batch is resolved.
- A `pending` row is a blocking state for a high-quality/final transcript, not proof that the issue was handled. Queue detection without a human/evidence verdict leaves the artifact incomplete.
- Read `resolved_text` after an override; the listing can still display the rejected suggestion.
- A single-line `asr_note` ledger is masked on the accept path too, so resolving an item never edits the provenance line that cites the old form. A fix you applied by hand before resolving is still closed with `--decision accepted` (or `overridden` for its override text): when the context recorded at enqueue reappears anywhere in the file with the suggestion in the slot the original occupied, the verdict is recorded without writing (`already in place at the anchor — recorded without writing`). Line drift does not matter, and neither does the original surviving in other utterances far from the hint, or inside the suggestion itself (阿里→阿里云). It fails closed with `ReAnchorNeeded`, and the message says which, for a legacy no-offset anchor when the original still sits within the resolve window of the hint outside the suggestion (the anchored utterance, or a look-alike beside it, is still garbled — settle that line on its own row or by hand, then resolve; do not `--reanchor-review` this row onto it), when the recorded neighbourhood also appears with a third form in the slot (anywhere in the file at the width that matched, or near the hint at any width down to two characters a side), or when the edit touched the characters next to the slot. What it cannot see: an anchored utterance deleted or rewritten past both neighbours while an identical one elsewhere reads corrected — that records `accepted` with nothing written, and a garble still in the file is re-deferred by the next Stage 1 run. `--reanchor-review <id>` repairs a row whose original moved or drifted and refuses one whose context already reads corrected.

**Choosing the exit when `accepted` refuses to write — three shapes, three exits.**
`accepted` is fail-closed by design: it declines to edit when the anchor is
ambiguous, and a refusal is information, not an obstacle to route around. Match
the exit to *why* it refused :

| What the refusal says | What actually happened | Correct exit |
|---|---|---|
| `anchor text not found` — original is simply gone from the file | Your earlier edit (or a sibling row's) already consumed it, and a grep of the **corrected form** confirms it landed | `skipped --note "<which row/edit consumed it; grep <newform> = N>"` |
| `anchor text appears more than once on line N` / `a different form there, so which line this row meant is ambiguous` | The line holds several instances of the variant; a whole-line replace already fixed all of them | `skipped --note "<the line-level replace that covered them; grep of both forms>"` |
| original is a **substring of a form an earlier row already replaced** (e.g. row A held `杨峰中`, this row holds `杨峰`) | The longer form went first, so this row's token vanished with it | `skipped --note "<row id that consumed it as a substring>"` |

The gate on all three is the same and it is not optional: **grep the corrected form
and confirm the old form reads zero before you close anything as `skipped`.** A
`skipped` row asserts "there is nothing left to fix here", so if the garble is
still in the file, `skipped` launders a real error into a closed row — the exact
outcome `Review queue safety` warns about. When the grep comes back non-zero, the
row is not skippable: fix the remaining occurrence by hand, then re-resolve.

`skipped` is also **not** the exit when you changed your mind and the original was
right as spoken — that is `kept_original`, and it asserts the transcript keeps the
raw form (so grep it still present). The two differ in what they claim about the
bytes on disk: `kept_original` = "original stays", `skipped` = "nothing to do,
already handled elsewhere". A row the queue can neither re-anchor nor recognise closes with `--decision skipped --note <what happened>`. `kept_original` asserts the transcript keeps the original form — never the exit for a fix you applied.
- If the file moved or drifted, run `--reanchor-review`. Add `--reanchor-root` or `--reanchor-to` when requested. Do not hand-edit around a pending item.
- Promote every `decision_note` by meaning; storing a note does not change the dictionary, roster, context, or false-positive state.
- The engine enforces the name-convergence gate at both write points: `--resolve-review --decision accepted/overridden` and a person-name-shaped `--add` refuse a target that is only someone's roster variant, or that nothing claims while the evidence names no authority (details and the sibling `--add` gates — open-row conflict, real-word probe — in [dictionary_identity_and_context.md](dictionary_identity_and_context.md)).

Core commands:

~~~bash
uv run scripts/fix_transcription.py --enqueue-review items.json
uv run scripts/fix_transcription.py \
  --list-review --review-file "<absolute-canonical-file>" \
  --review-status all --json
uv run scripts/fix_transcription.py --show-review <id> --json
uv run scripts/fix_transcription.py --reanchor-review <id>
uv run scripts/fix_transcription.py \
  --resolve-review <id> --decision accepted --by reviewer
~~~

## Numbers, artifacts, and batches

Read [references/advanced_correction_evidence.md](advanced_correction_evidence.md) when any of these conditions holds:

- A number, bound, price, share, deadline, or magnitude drives a decision.
- Two recordings exist for one meeting.
- A load-bearing name or term survived the local ladder unresolved, source audio is available, and the current authorization already permits a second recognizer.
- A whiteboard, slide, or photographed written artifact can independently settle a name/term.
- Several related files should share one correction list.
- A 10+ file batch is being delegated.

Numeric-slot scan:

~~~bash
uv run scripts/scan_numeric_consistency.py transcript.md --domain myproject
~~~

Its output is candidates, never automatic edits. For a load-bearing number, follow [evidence selection and escalation](native_ai_full_workflow.md#evidence-selection-and-escalation). When original audio is accessible, use the review dashboard to decide by ear. Otherwise retain competing readings unless other evidence settles them, and continue the remaining items; do not require export permission.

For delegated batches, every agent owns one file, cannot cross-file replace, and returns a residual list. Afterward compare `git diff --name-only` with the explicit file list and inspect every unexpected file under the repository's worktree-safety rules.

## Finalization

- Native mode edits the original file directly. Rerun plain `--stage 1` to confirm; a clean no-op writes no Stage 1 sidecar.
- When a newer `*_stage1.md` exists and the original was not edited after it, a plain Stage 1 rerun atomically promotes it and removes disposable sidecars. It retains `*_changes.md` and `*_needs_review.md`: those are review evidence, and `--close-sidecars` is the command that decides they are closed. `--apply-all` never takes this promotion path.
- Do not use the existence of an output file as the success signal; read JSON/exit status and independently read the final file.
- Preserve raw transcripts, `*_changes.md`, and `*_needs_review.md` as evidence until `--close-sidecars --input "<absolute-canonical-file>"` reports `closed`: every entry reads applied in the file (or the original form no longer appears anywhere in the ledger-masked transcript) or is answered by a decided queue row for this exact file — one row per occurrence, matched by nearest line, so a second occurrence with no row of its own stays undecided — or belongs to a FROM→TO rule that has since been disabled as a false positive (`disabled`: no longer a question), and the file has zero pending rows. It exits 1 (`open`) naming the undecided entries and pending ids, 2 (`blocked`) when a `*_stage1.md` newer than the file still awaits the plain Stage 1 rerun or a report carries entries the parser cannot read (an unreadable report is evidence, not an empty one), and 0 after removing the evidence and stale run outputs. For an entry that still reads as the original and has no row at all, `--decide-raw kept_original|skipped --by <who> --note <why>` records the verdict through the queue at closure — an audit trail, not a silent deletion. `--dry-run` shows the verdict without deleting; `--json` returns it.
- `*_stage2.md` and `*_dryrun.md` are run-scoped outputs of the API route and the preview, not archive material: promote or discard them in the session that produced them. One newer than the transcript is unpromoted — `--close-sidecars` retains it, says so, and removes it only with `--discard-unpromoted`.
- Re-grep a known corrected form in the final file and verify no correction remains only in `asr_note` or a sidecar.
- If a queued item was renamed away, repair it with `--reanchor-review` rather than resolving it with a false terminal verdict.

## Agent-less API route

Only when no Claude/Codex agent can perform Native AI Correction:

~~~bash
export GLM_API_KEY="<api-key>"
uv run scripts/fix_transcript_enhanced.py input.md --output ./corrected
~~~

The route writes `<stem>_stage2.md` beside the input. It is this run's output, not a second transcript: verify it, then promote it onto the transcript or discard it before the session ends. A `_stage2.md` left beside a transcript that is not it cannot be told apart from reviewed work a month later.

Read [references/glm_api_setup.md](glm_api_setup.md), [references/installation_setup.md](installation_setup.md), and the explicitly API-oriented portions of [references/workflow_guide.md](workflow_guide.md). When a chunk fails after retries, the API route keeps that chunk and its original surrounding separators byte-for-byte and prints a warning; if every chunk fails, the complete output equals the input. For `fix_transcription.py --stage 2|3 --json`, read the additive `stage2_total_chunks`, `stage2_failed_chunks`, and `stage2_degraded` fields: `stage2_degraded: true` is not a fully corrected run even though the safely retained artifact is emitted. The enhanced wrapper exits nonzero after writing that retained artifact when any Stage 2 chunk is degraded. Verify the output rather than assuming the warning means a corrected result exists.

The enhanced API wrapper can also add paragraph breaks, reduce repeated filler,
and present corrections for interactive review. Those are API-wrapper features;
they do not authorize Native AI to rewrite wording for fluency.

## Utility commands

~~~bash
# Extract likely errors without editing
uv run scripts/fix_transcription.py --extract-uncertain \
  --input meeting.md --output ./review

# Import curated preset rules
uv run scripts/fix_transcription.py --load-presets tech

# Repair timestamps
uv run scripts/fix_transcript_timestamps.py meeting.txt --in-place

# Split and rebase sections
uv run scripts/split_transcript_sections.py meeting.txt \
  --first-section-name "intro" \
  --section "main::<verbatim marker>" \
  --rebase-to-zero

# Word-level review diff
uv run scripts/generate_word_diff.py original.md corrected.md output.html

# Harvest native-pass edits into context-trap candidates
uv run scripts/harvest_corrections.py raw.md corrected.md \
  --context-file "<domain-context.md>" --write

# Collect clip evidence at operator-verified media positions; resolve rows separately
# Read references/advanced_correction_evidence.md before selecting the engine or clock mapping.
uv run scripts/verify_queue_audio.py \
  --transcript /abs/meeting.md --audio /abs/source.wav \
  --time-overrides /abs/verified-times.json \
  --engine-script /abs/stdout_recognizer.py --outdir /abs/audio-evidence

# Existing local MLX runner: read .txt + completion manifest, never its progress logs.
# Resolve the runner from asr-transcribe-to-text; prepare its cached model there first.
uv run scripts/verify_queue_audio.py \
  --transcript /abs/meeting.md --audio /abs/source.wav \
  --time-overrides /abs/verified-times.json \
  --engine-script /abs/transcribe_local_mlx.py --engine-format mlx-file \
  --outdir /abs/audio-evidence

# Multi-format Stage 1/API comparison report
uv run scripts/generate_diff_report.py \
  original.md original_stage1.md original_stage2.md \
  --output ./diff_reports

# Every existing claim on a term: dictionary (active/disabled), context rules, roster, queue
uv run scripts/fix_transcription.py --lookup "候选词"

# Decide whether one finished transcript's review sidecars are closed, then remove them
uv run scripts/fix_transcription.py --close-sidecars \
  --input "/absolute/meeting.md" --dry-run

# Setup health
uv run scripts/fix_transcription.py --validate
~~~

Read [references/script_parameters.md](script_parameters.md) before using less-common flags. Read [references/database_schema.md](database_schema.md) before custom SQL; correction columns are `from_text` and `to_text`.
