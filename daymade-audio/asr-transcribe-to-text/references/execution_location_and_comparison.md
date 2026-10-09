---
name: execution-location-and-comparison
description: >-
  Choose an existing ASR execution location from source placement, reusable text,
  permissions and measured end-to-end quality. Read before choosing local versus
  remote GPU, comparing short speech or long recordings, or reusing ASR results.
---

# Choose where to transcribe

Use this procedure after the owning workflow has ruled out a verified current
transcript. The operator selects among existing authorized routes; the tools
below do not install a model, create a queue or mutate a shared service.

## Reuse before moving bytes

1. Check the owning project's catalog and source identity for human-reviewed
   text. Use that artifact unless an independent comparison was requested.
2. Check the selected producer's receipts and checkpoints. Match source bytes,
   producer/model contract, artifact hashes and requested output obligations.
   A plain-text receipt does not establish timestamps or speaker accuracy.
3. Resume incomplete work through that producer. Keep validated completed
   chunks; do not download the original or regenerate every leg merely because
   a search projection or a reader wrapper is missing.
4. For an unmatched artifact, preserve it as an unverified reference. Do not
   relabel it as a cache hit or erase an existing manual correction.

The local MLX and speaker scripts already own their cache identities and
checkpoint validation; use [the local guide](local_mlx_guide.md) for their
recovery steps. The remote plain-text runner validates its own receipt before an
upload and reuses a matching existing result. It does not import other producers'
caches. Existing text with missing or changed provenance is preserved and reported
as blocked; use a fresh output for comparison. `--force` explicitly replaces that
destination and must not erase a human-reviewed canonical transcript.

## Choose with current observations

Record where the source already lives, which routes can read it without copying,
the requested output (full text, timestamps, speakers), processing permission,
and observed producer/device identity. Inspect only the declared services and
assets; no discovery of unrelated hosts or colleagues' machines.

Prefer an eligible route next to the audio when there is no comparative evidence.
This is a reversible default that avoids a transfer, not a performance claim.
Override it when an actual same-source comparison shows that transfer, queue,
cold start, inference, output transfer and required alignment together finish
sooner while preserving the required quality. Leave missing durations unknown;
do not estimate a winner from GPU name, an old realtime multiplier or free VRAM.
CPU decode, hashing and text checks are allowed; CPU model inference is refused.

Reuse a compatible warm shared ASR service when its actual loaded model and
CUDA device are observed. Do not unload, restart or replace someone else's model
to manufacture a cold baseline. A cold state may be measured only when the
authorized task itself encounters it. A process list or `/models` response
alone does not prove execution device or recognition quality.

## Run the remote text leg

Use the existing `config.json` endpoint/model/noproxy/max_timeout fields. For
self-hosted GPU use, additionally set `self_hosted: true` and an explicit
`health_url` supported by that service. The health contract is a JSON object
with `status: "ok"`, nonempty `model_loaded` and a CUDA `device`. If the service
does not expose this evidence, report the unsupported identity check; use its
existing operator-owned verification path rather than inventing field values.
Health checks have their own bounded deadline, optionally overridden by a finite
positive `health_timeout`; transcription retains `max_timeout`. Read defaults
from the runner rather than copying a timeout into deployment notes.
Optionally set `expected_runtime_model` to an exact observed model ID when the
task requires it. The requested `model` may be a service alias; it is not proof
of the actual loaded model or revision. Preserve an exposed `model_revision`;
otherwise the receipt leaves the revision unknown.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/transcribe_remote.py \
  INPUT_AUDIO OUTPUT.txt --config "${CLAUDE_PLUGIN_DATA}/config.json"
```

Expect readable `OUTPUT.txt` and `OUTPUT.txt.asr.json`. The receipt binds source,
text and runner bytes, requested model and observed runtime identity. It marks
recognition accuracy unverified. For a provider without `health_url`, identity
remains explicitly unknown; this branch does not claim verified self-hosted GPU.
HTTP errors, an error JSON inside HTTP 200, missing text, CPU self-hosted health,
source mutation and runtime model/device drift fail without a new receipt.
The runner performs no model-management requests.

Feed the text into the existing speaker pipeline's `--text-file` branch when
timestamps or speakers are required. Keep the full speaker bundle and its final
receipt as the completion artifact; do not stop at remote text.

## Compare without changing the task

Use `scripts/measure_asr.py` to wrap an existing command as a JSON argv array.
It invokes the command directly, preserves its progress/checkpoints, measures
wall time through command completion and binds source/result bytes. No shell
parsing occurs. Put private endpoints, node identities and model paths only in
local configuration or argv files outside the Skill bundle.

For each representative source, prepare:

- A fresh transcript destination, source, and argv file containing the existing
  runner command. `{source}` and `{text}` substitute exact paths. For the local
  MLX runner, set its `--output-dir` explicitly and make `--text` match its
  `<source-stem>.txt` output. For long local work, use Path L rather than forcing
  the short/medium Qwen route into an unsupported long-form guarantee.
- An independently checked original-speech reference and, when needed, a JSON
  list of load-bearing utterances: negation, numbers, proper names and decisions.
  Apply [speech-content acceptance](#accept-the-speech-content) before selecting
  a route. Do not use one model's answer as the other model's ground truth.
- An explicit task-specific maximum character error rate. No threshold is
  silently selected. The checker normalizes Unicode, case, punctuation and
  whitespace only; it preserves speech content and calculates edit distance.
  Whole-file CER is quadratic in transcript length, so use bounded representative
  audio for this check rather than an entire multi-hour transcript.

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/measure_asr.py run \
  --source SOURCE --text FRESH_OUTPUT.txt --argv ROUTE_ARGV.json \
  --output OBSERVATION.json --route ROUTE_LABEL --state unknown \
  --reference CHECKED_ORIGINAL.txt --anchors REQUIRED_UTTERANCES.json \
  --max-cer EXPLICIT_THRESHOLD

python3 ${CLAUDE_SKILL_DIR}/scripts/measure_asr.py compare \
  LOCAL_OBSERVATION.json REMOTE_OBSERVATION.json
```

Expect a per-run observation with measured wall time, source/text/reference paths
and binding hashes, state and threshold parameters. CER, missing utterances and
the quality verdict are computed for stdout and comparison; they are not
persisted in the observation. `--identity` may refer to an
existing producer receipt or observed runtime evidence; an omitted identity is
unknown, never filled from `--route`. State is an observation, not an instruction
to cold-start or reset a service. Label `warm`/`resume` only with evidence from
the producer; otherwise use `unknown`.

Repeat the commands for a short spoken message and a bounded speech-bearing
part of a long video. For the long source, also verify the chosen production
runner's beginning/middle/end and chunk seams under Step 4; a selected clip
proves only that clip. Compare identical source/reference/utterance hashes and
the same threshold. Without a checked reference and threshold, the tool reports
`quality_not_established` and selects no route. A missing required utterance or
failed CER blocks automatic selection; a passed check still needs the source
adjudication below before it can support a performance decision.

### Accept the speech content

The executing agent checks the original-speech evidence: `passed_text_check`
certifies normalized text tests, not meaning. Conversely, an exact-phrase miss
can be harmless filler variation. Inspect the matched and missed original
fragments before calling either a semantic success or a recognition error.
Freeze the reference, threshold and minimal load-bearing actions, negations,
numbers and entity relationships before either arm runs; avoid requiring
nonessential particles in a diagnostic anchor. When original audio cannot be
reviewed and no verified human transcript exists, keep the reference explicitly
unverified. Continue authorized transcription and source collection, but do not
declare semantic acceptance or a quality-qualified speed winner.

Keep errors noticed afterward in a separately labeled post-hoc diagnosis. Run
the existing checker on those anchors against the retained outputs, without new
inference, and preserve the original scores. Do not replace the frozen anchors
or present the later diagnosis as a blind result. Retain case-specific original
media, utterances and reproduction commands in the owning private evidence;
do not copy its running scores or case inventory into this reusable SOP.

The comparison prints a measured text-leg choice, not a whole-pipeline winner.
Speaker accuracy, timestamp accuracy, visual content and non-language sound
remain independent obligations. Include their required work in a separate
end-to-end task observation before changing the general execution default.
Store observations as evidence of those runs; compute comparisons on demand
instead of maintaining a current-speed table or a persisted winner.
