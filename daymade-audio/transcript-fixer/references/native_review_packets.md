# Native review packets and recovery

Use this route for multi-file Full-tier reviews, split transcripts, or a review
resumed after interruption. Keep ordinary short Fast-tier work on its existing
linear path. The helper freezes the expected file set, creates bounded packets,
and validates returned results. It does not call a model, choose corrections,
edit transcripts, enqueue candidates, or declare transcript quality complete.

## Prepare the complete scope once

Use final canonical paths after Stage 1 and the first Native pass. Supply **every
file in the authorized batch**, including the Fast files excluded from independent
review. Choose the tier from vocabulary and stakes, not from a desire to reduce
the remaining work. Resolve relative input paths against the manifest directory.

```json
{
  "files": [
    {"file": "transcripts/planning.md", "tier": "full"},
    {"file": "transcripts/short-memo.md", "tier": "fast",
     "reason": "Plain two-person memo; Fast Native pass already completed."}
  ]
}
```

```bash
uv run scripts/native_review.py prepare \
  --manifest review-files.json --output native-review-run
```

Preparation validates every source before creating the run directory. Existing
run directories are refused: resume them with `check`. `sources/` preserves exact
UTF-8 bytes, including CRLF. Keep the input manifest in place: its hash binds the
declared scope, so editing the plan alone cannot silently drop a file or change
its tier. `plan.json` records source hashes, all files, explicit
Fast exclusions, and the expected segments. `packets/` contains numbered source
lines with file-absolute, one-based line numbers. `results/` starts empty.

Defaults limit each segment to 900 source lines and 18,000 Unicode characters,
with up to 50 overlapping lines. These are input budgets, not token estimates;
packet headers and line-number prefixes add some text. Adjust `--max-lines`,
`--max-chars`, and `--overlap` explicitly when necessary. A single source line
larger than the character budget is refused before writing; raise the budget or
use a separately verified segmentation method without silently renumbering text.

## Give each fresh reviewer one packet

Supply the packet, the relevant raw baseline/diff, the exact-file queue readback,
and already-confirmed corrections. Queue status and `resolved_text` outrank a
reviewer's preferred wording. Have the reviewer read its whole assigned packet
and return one JSON file under `results/`:

```json
{
  "segment_id": "file-0001-1-120",
  "sha256": "copy the source sha256 from the packet header",
  "start": 1,
  "end": 120,
  "read_complete": true,
  "residuals": [
    {"line": 42, "original": "exact suspect span", "suggested": "candidate",
     "reason": "Plausible sound confusion plus a specific source/context anchor."}
  ]
}
```

Copy the assigned identifiers and bounds exactly; the example values above are
illustrative. An explicit `residuals: []` is valid after a complete read. An empty
file, truncated JSON, missing completion flag, or a summary without the requested
rows is an unfinished result.

Require literal spans, not a paraphrase, “two occurrences” annotations, or a
whole sentence reconstructed for fluency. A reviewer must distinguish a plausible
ASR confusion from a speaker's repetition, false start, metaphor, factual error,
or unusual but intelligible word. An unknown entity alone is not a residual.
High confidence and a grammatical replacement are not evidence. Preserve speaker
labels, timestamps, user verdicts, and the correction ledger.

## Validate, then adjudicate

```bash
uv run scripts/native_review.py check --run native-review-run
```

The checker verifies snapshot and packet integrity, the expected coverage union,
result IDs/hashes/bounds, every literal span at its stated line, and whether the
current canonical files still match the reviewed snapshots. It deduplicates exact
overlap rows while retaining different suggestions for the same occurrence.
`occurrences_on_line` exposes repeated spans; it never selects one to edit.

| Result | Action |
|---|---|
| Exit 0, `ready_for_adjudication: true` | Adjudicate all residuals against raw text and the evidence ladder. This is not a quality verdict. |
| Exit 1 | Inspect `missing_segments`, `invalid_results`, and `changed_sources`; retain the valid results and repair only the listed gaps. |
| Exit 2 | Fix malformed/unreadable plan or source data before proceeding. |
| All files explicitly Fast | No independent review was required; the helper returns not-ready rather than manufacturing a cold-review pass. |

Review flags attest that the reviewer read its assignment. The checker cannot
prove that reading occurred or that a proposed correction is true. It always
returns `quality_complete: false`. Validate **before** applying corrections;
after intended edits, the old snapshot is historical evidence, not a byte match
for the new file. Preserve the adjudication/diff and verify the changed content
under the existing finalization workflow rather than relaunching every reader.

Do not import the residual table wholesale into the persistent queue. Reject
unsupported rewrites, apply sound-supported corrections, and enqueue only the
remaining actual uncertainties through the existing `--enqueue-review` interface.
Use `--resolve-review` for existing deferrals. Its action pack validates all
actions for that item before writing; it is not a transaction across unrelated
review rows or files. If using a local edit script, validate every proposed span
and disposition before its first write, then preserve speaker/timestamp lines.

## Resume and close

Run `check` before launching reviewers after a quota reset, timeout, or context
handoff. An earlier quota failure is not current availability evidence. Reuse
valid results; retry only missing or failed assignments. Remove or replace an
invalid result only after preserving evidence needed to diagnose it. Conflicting
results for one segment require explicit reconciliation, not last-file-wins.

Keep three states separate in the final handoff: independent review coverage,
the exact-file queue's pending verdicts, and the owning repository's archival or
publication state. A pushed file may still be a draft. Use current queue readbacks
and the caller's Git workflow; this helper neither publishes nor grants approval.

## Design sources

- [Anthropic Skill authoring: verifiable intermediate outputs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices#create-verifiable-intermediate-outputs)
  motivates validating structured plans before side effects.
- [W3C Web Annotation: quote and position selectors](https://www.w3.org/TR/annotation-model/#text-quote-selector)
  distinguishes quoted text from mutable positions. This helper uses literal text,
  explicit line positions, and byte hashes; it is not a JSON-LD implementation.
