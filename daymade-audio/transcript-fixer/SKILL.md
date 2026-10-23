---
name: transcript-fixer
description: >-
  Corrects ASR/STT transcription errors — homophones, garbled terms, person-name errors, mixed
  Chinese/English — with dictionary rules plus Claude's built-in AI, no external API key required.
  Use to clean meeting notes, lecture transcripts, interviews or speech-recognition text, even when
  the user only says "fix this transcript". Not for structuring a clean transcript into minutes (use
  meeting-minutes-taker).
---

# Transcript Fixer

Use the correction loop:

1. Stage 1 applies deterministic, already-known corrections.
2. Native AI Correction reads the complete transcript, fixes one-off errors, verifies uncertain entities, and compounds reusable fixes.

**Native AI Correction is the default. Stage 1 alone is incomplete.** Stage 3 API exists only for automation that has no Claude/Codex agent available.

## Operating contract

- Finish Stage 1 → Native AI Correction → compound confirmed recurring fixes. Do not report a transcript clean after Stage 1 alone.
- Skip Native AI only when the human explicitly limits this run to the dictionary pass or a dated artifact proves Native AI already ran on this exact transcript.
- In Claude Code or Codex, do not run Stage 3. Use Stage 1 plus the native workflow.
- Never rewrite speech for fluency. A correction must explain a plausible ASR error and preserve who said what.
- A standard term elsewhere or a known participant is a candidate source, not proof of this occurrence's wording. Apply the occurrence-specific contrasts in [Native review packets](references/native_review_packets.md#occurrence-specific-evidence) during the first pass and cold review; retain the raw form when the discriminator is missing.
- Before accepting a name-variant match, inspect the complete company/name slot; follow [minimum occurrence checks](references/dictionary_identity_and_context.md#minimum-occurrence-checks-for-name-candidates). Ordinary wording refused by the name-shape guard uses only the bounded [written-wording route](references/review_queue_dashboard.md#written-evidence-for-ordinary-wording), never a fabricated user/audio citation.
- By default, never infer or reassign speaker identities. Preserve speaker-label lines; human-confirmed labels and user verdicts are authoritative. Only an explicit, task-scoped user grant to infer identities opens the separate derived-reader branch: read [scoped speaker inference](references/scoped_speaker_inference.md) before acting. That grant is permission to infer, not an identity confirmation or permission for other transcripts.
- Before correcting any person name, directly read both the configured global people roster and the owning project's explicit identity roster or alias ledger. Stage 1 auto-loads only global `ASR 变体` entries; it does not load project rosters or expose suppressed, disabled, and unlisted entries. If an expected source is missing or the sources conflict, leave the name unchanged and enqueue or ask once. Never use occurrence frequency as identity evidence. Read [references/dictionary_identity_and_context.md](references/dictionary_identity_and_context.md) before settling the name.
- Resolve doubts from available evidence before escalating. Audio download is one evidence channel, not a prerequisite for Native correction. When it is unavailable, follow [evidence selection and escalation](references/native_ai_full_workflow.md#evidence-selection-and-escalation); do not require the user to change download permissions or treat every pending row as a question only they can answer.
- Leave genuinely unresolved text unchanged and enqueue it. A visible garble is safer than a fluent wrong guess; a pending row records uncertainty, not an automatic human handoff.
- Treat an unfamiliar token as unknown, not as an error. Exhaust the local evidence ladder first. For a load-bearing token that remains unresolved, use the clip-level cross-recognizer rung only when source audio and a permitted second engine are already available; otherwise continue with the available evidence under the escalation policy above. Agreement from a genuinely different recognizer family strongly corroborates the sound, but never chooses between homophonic spellings or overrides the person-name gate. Read native workflow step 4, rung 7 before using it. **A backlog of exhausted pendings is the batch form of this rung**: when a native pass leaves a queue of locally-unresolvable rows, do not hand the queue to the user wholesale — check it with `verify_queue_audio.py` (one transcript, one source audio, one second engine, two clip windows per row). The script can attach acoustic evidence but never records a verdict; identical clips and readings that do not support the disputed word boundary remain pending for adjudication. The operator matrix and timestamp-mapping pitfalls live in [advanced_correction_evidence.md](references/advanced_correction_evidence.md) § Batch pending adjudication.
- Treat a single-line `asr_note` value as correction provenance: it intentionally cites old forms and is excluded from matching. Multi-line YAML ledger values are not masked; keywords, titles, other ASR-derived metadata, and body text remain in correction scope.
- Read [references/native_ai_full_workflow.md](references/native_ai_full_workflow.md) in full before performing a native pass. Contiguous, nonoverlapping reads may cover the full file; if a response is truncated, read the missing range before proceeding. An executed `cat` does not establish that its full output was received. Read the task-specific references named below before their corresponding action; use bounded, nontruncated reads for those files too.

## Run context

Run every entrypoint through `uv run`; entrypoints that need third-party Python packages declare them with PEP 723, while stdlib/internal-only utilities may omit the metadata block. Execute commands from the skill directory printed when this skill was invoked, or prefix every script path with that directory. Do not rely on `$CLAUDE_SKILL_DIR`; it is not available in every harness.

If the bundle location is genuinely unknown, use the installation-resolution procedure in [references/installation_setup.md](references/installation_setup.md). Do not select the first result from a broad `find`: caches, backups, and old versions can coexist.

## Quick start

Resolve `<domain-context.md>` through the [context location](references/domain_context_guide.md#location)
before filling the explicit file argument below.

~~~bash
# Initialize once
uv run scripts/fix_transcription.py --init

# Stage 1 for one project domain. --apply-domain trusts that explicitly
# selected, human-curated project domain at every risk level.
uv run scripts/fix_transcription.py \
  --input meeting.md --stage 1 \
  --domain myproject --apply-domain --json

# Several sibling domains may be loaded as one union.
uv run scripts/fix_transcription.py \
  --input meeting.md --stage 1 \
  --domain myproject,myproject-alt --apply-domain --json

# Preview without writing the Stage 1 output.
uv run scripts/fix_transcription.py \
  --input meeting.md --stage 1 --domain myproject --dry-run

# Scan all documented context traps after the native read-through.
uv run scripts/fix_transcription.py --scan-traps \
  --context-file "<domain-context.md>" \
  --input meeting.md
~~~

Safe mode is the Stage 1 default: low-risk rules apply; medium/high-risk matches defer to `*_needs_review.md` and the persistent review queue. `Applied: 0` is a valid result, not proof that the transcript is clean.

The Stage 1 JSON contract is:

~~~json
{
  "applied": 0,
  "deferred": 0,
  "output_path": null,
  "needs_review_path": null,
  "input_unchanged": true,
  "review_enqueued": 0,
  "stage1_only_incomplete": true,
  "stage2_total_chunks": 0,
  "stage2_failed_chunks": 0,
  "stage2_degraded": false,
  "boundary_refused": 0,
  "boundary_check_active": true
}
~~~

Read every field in the result. `boundary_refused` counts dictionary matches the word-boundary check refused this run — neither applied nor deferred, so a caller comparing runs can see why a deferral disappeared; `--apply-all` switches that check off. `stage1_only_incomplete` is additive to the original caller contract and must remain true for a Stage 1 script run; only the caller can close it by running Native AI, or by explicitly choosing the agent-less Stage 2/3 route. The `stage2_*` telemetry fields are always present: Stage 1 reports `0`, `0`, and `false`; Stage 2/3 replace them with the actual API outcome. Do not infer no-op or success from whether a sidecar exists.

For a native end-to-end example, read [references/example_session_dji_minutes.md](references/example_session_dji_minutes.md).

## Choose the route

| Route | Use when | Required reading |
|---|---|---|
| Pending continuation | Dated Native/review evidence covers this exact file; only uncertain rows remain, or the user supplies a verdict | [pending-continuation.md](references/pending-continuation.md); reuse unchanged completed coverage |
| Fast native | Short/plain transcript, known speakers, low stakes | This file + [native_ai_full_workflow.md](references/native_ai_full_workflow.md) |
| Full native | Domain-heavy, unfamiliar entities, 3+ speakers, long or decision-bearing transcript | [native_ai_full_workflow.md](references/native_ai_full_workflow.md), plus queue and evidence references below |
| Scoped speaker inference | User explicitly authorizes identity inference for this transcript/task | [scoped_speaker_inference.md](references/scoped_speaker_inference.md); keep ordinary ASR correction on the native route |
| Caller integration | Another skill or ingest pipeline invokes Stage 1 | `Cross-skill caller contract` below |
| Review queue/dashboard | Any item is uncertain or needs audio | [review_queue_dashboard.md](references/review_queue_dashboard.md) |
| Agent-less API | CI/batch automation with no agent available | [glm_api_setup.md](references/glm_api_setup.md) and [workflow_guide.md](references/workflow_guide.md) |
| Multi-file batch | Several related transcripts; especially 10+ files | [advanced_correction_evidence.md](references/advanced_correction_evidence.md) |

Use vocabulary and stakes as the primary tier signals; use length only as a tiebreaker. A five-minute medical interview can require the full tier, while a long plain two-person memo can use the fast tier.

## Native correction checklist

Read [the required native sequence](references/native_ai_full_workflow.md) in full
before correcting. It routes provenance, entity triage, edits, cold-review recovery,
queue decisions and finalization to their action-time references.

1. Give the input a final human-readable path; recover/diff raw provenance.
2. Load project context, read the whole transcript, run Stage 1 and inspect its diff.
3. Triage candidates; apply only minimal occurrence-supported corrections.
4. Run the trap scan; complete Full-tier cold review and adjudicate its residuals.
5. Resolve exact-file queue rows; read human state before repeating work.
6. Verify the edited file, require zero pending for final/high-quality claims,
   close sidecars mechanically, harvest stable patterns and review entity propagation.

Read [native action details](references/native_action_details.md#native-correction-checklist)
before the corresponding queue, learning or same-file entity-sweep action. In
particular, person-name authority belongs in `--authority`/`--authority-record`,
not `--note`; a sentence-local correction is not automatically a reusable rule.

## Cross-skill caller contract

A caller pipeline must:

1. Run Stage 1 with the explicitly configured project domain(s), `--apply-domain`, and `--json`. If `deferred > review_enqueued`, persist the review sidecar outside any temporary directory or surface the gap as failure.
2. Run Native AI with this skill loaded, or report `Stage 1 only — incomplete`. Agent-less automation may use Stage 3 instead.
3. Select the report location from the destination's storage contract. Use `--sidecar-dir DIR` for review reports while keeping run outputs under the existing `--output` contract. Omission preserves adjacent/default output behaviour; retain pending reports until `--close-sidecars` decides closure. Closure discovers registered custom report directories, or accepts `--sidecar-dir` explicitly for recovery. Never force every project to move reports into one fixed subdirectory.

Canonical call:

~~~bash
uv run scripts/fix_transcription.py \
  --input "$staged" --stage 1 \
  --domain "$domains" --apply-domain --json
~~~

A caller that wires only the script path never loads this contract. Script-path integration alone is therefore a Stage 1 prefilter, not transcript correction.

Keep project domains warm: every confirmed recurring correction from the native pass must be added back to the correct project domain, roster, or context file.

## Conditional actions

Read the matching section **before** acting; these are existing supported jobs:

| Action | Required detail |
|---|---|
| Add a dictionary/context rule, roster variant, or recurring trap | [Dictionary and identity safety](references/native_action_details.md#dictionary-and-identity-safety), [identity/context owner](references/dictionary_identity_and_context.md), [false-positive guide](references/false_positive_guide.md) |
| Enqueue, accept/override/keep/skip, attach authority, re-anchor, consolidate, or record a ledger verdict | [Review queue safety](references/native_action_details.md#review-queue-safety), [queue/dashboard](references/review_queue_dashboard.md); use [pending continuation](references/pending-continuation.md) for already-reviewed files |
| Numbers, written artifacts, parallel recordings, clip cross-checks or batches | [Numbers, artifacts, and batches](references/native_action_details.md#numbers-artifacts-and-batches), [advanced evidence](references/advanced_correction_evidence.md) |
| Promote outputs, close sidecars, archive or verify final quality | [Finalization](references/native_action_details.md#finalization), [queue/finalization detail](references/native_queue_finalization.md) |
| Agent-less API automation, including degraded output handling | [Agent-less API route](references/native_action_details.md#agent-less-api-route), [API setup](references/glm_api_setup.md), [workflow guide](references/workflow_guide.md) |
| Extract uncertainty, import presets, repair timestamps, split/rebase, diff, harvest, look up or validate setup | [Utility commands](references/native_action_details.md#utility-commands), [CLI parameters](references/script_parameters.md) |
| Compare duplicate/overlapping transcripts or parse/count speaker turns | [Transcript comparison/parsing](references/native_transcript_comparison.md) |

Detection and enqueueing are not correction. A final/high-quality claim requires
exact-file `stats.pending_total == 0`; zero pending rows is required after the
file edits are read back. An unresolved file stays `draft / unresolved — incomplete`.
A sampled clip settles only that anchored item. For high-stakes multi-recording
requests for a complete/better transcript with baseline audio available, load
`/daymade-audio:asr-transcribe-to-text` and cover the complete clearest recording;
the same recognizer proves complete-source coverage, not independent corroboration.
User verdicts settle occurrences, but they do not make a replacement reusable:
a rare sentence-local mishearing stays file-only.

## Reference map

| Need | Read |
|---|---|
| Historical incidents (optional; not a prerequisite) | [native_historical_evidence.md](references/native_historical_evidence.md) |
| Native action details and command examples | [native_action_details.md](references/native_action_details.md) |
| Raw/upstream adjudication | [native_upstream_provenance.md](references/native_upstream_provenance.md) |
| Name/token triage and local ladder | [native_entity_triage.md](references/native_entity_triage.md) |
| Minimal edits / metadata provenance | [native_correction_application.md](references/native_correction_application.md), [native_metadata_provenance.md](references/native_metadata_provenance.md) |
| Full cold review / queue and archive details | [native_second_pass.md](references/native_second_pass.md), [native_queue_finalization.md](references/native_queue_finalization.md) |
| Duplicate transcript comparison and turn parsing | [native_transcript_comparison.md](references/native_transcript_comparison.md) |
| Full native correction sequence | [native_ai_full_workflow.md](references/native_ai_full_workflow.md) |
| Explicit one-task speaker inference in a separate reader copy | [scoped_speaker_inference.md](references/scoped_speaker_inference.md) |
| Split/batch cold-review packets, result validation, and interruption recovery | [native_review_packets.md](references/native_review_packets.md) |
| Dictionary, people roster, domain contexts | [dictionary_identity_and_context.md](references/dictionary_identity_and_context.md) |
| False-positive policy | [false_positive_guide.md](references/false_positive_guide.md) |
| Queue, dashboard, audio, re-anchor | [review_queue_dashboard.md](references/review_queue_dashboard.md) |
| Resume pending evidence or apply an explicit human verdict | [pending-continuation.md](references/pending-continuation.md) |
| Numbers, photos, multi-recording, clip cross-check, batches, batch pending-queue audio adjudication | [advanced_correction_evidence.md](references/advanced_correction_evidence.md) |
| Context-file location and grammar/template | [domain_context_guide.md](references/domain_context_guide.md) |
| CLI flags and review-item schema | [script_parameters.md](references/script_parameters.md) |
| Database schema and queries | [database_schema.md](references/database_schema.md), [sql_queries.md](references/sql_queries.md) |
| Short command lookup | [quick_reference.md](references/quick_reference.md), [dictionary_guide.md](references/dictionary_guide.md) |
| Learning loop | [iteration_workflow.md](references/iteration_workflow.md) |
| Native examples | [example_session_dji_minutes.md](references/example_session_dji_minutes.md) |
| Agent-less API example/config | [example_session.md](references/example_session.md), [glm_api_setup.md](references/glm_api_setup.md), [installation_setup.md](references/installation_setup.md) |
| Architecture and formats | [architecture.md](references/architecture.md), [file_formats.md](references/file_formats.md) |
| Operational guidance | [best_practices.md](references/best_practices.md), [troubleshooting.md](references/troubleshooting.md), [team_collaboration.md](references/team_collaboration.md), [workflow_guide.md](references/workflow_guide.md) |

Bundled scripts are executed, not loaded into context. The primary entry points are `fix_transcription.py`, `scan_numeric_consistency.py`, `fetch_minute_audio.py`, `review-dashboard/server.py`, and the diff/timestamp/splitting utilities listed above.

## Handoff

After correction, hand off to `/daymade-audio:meeting-minutes-taker` only when the user wants a structured summary. Do not create meeting minutes automatically: transcript correction and summarization are separate scopes.
