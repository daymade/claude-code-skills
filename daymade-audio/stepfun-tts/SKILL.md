---
name: stepfun-tts
disable-model-invocation: true
description: >-
  Generates speech with StepFun contextual TTS, including Chinese/Japanese speech,
  emotional delivery, inline natural-language directions, cloned voices and batch
  voice lines. Supports native HTTP, SSE, WebSocket and voice/file lifecycle
  requests, plus migration from step-tts-2. Use for 阶跃 TTS, 语音合成 or 配音.
  Not for transcription (use stepfun-asr).
---

# StepFun TTS

Use the bundled wrapper for synthesis and voice management. Read
[the API and control reference](references/api_reference.md) before choosing a
model, cloning a voice, adding expression controls or using streaming.
Current official documentation takes precedence over the historical probes in
the migration and troubleshooting references.

## Authentication and prerequisites

The CLI reads `STEPFUN_API_KEY`; Python calls take an explicit `api_key`.
Missing credentials fail without borrowing another account's configuration.
Use the endpoint appropriate to the account and region. The wrapper retains its
existing China endpoint default; pass `endpoint` / `api_base` explicitly for
another service host. Do not infer a key's entitlement from its name.

HTTP synthesis and the CLI use Python's standard library. WebSocket use additionally
requires `python3 -m pip install -r scripts/requirements-ws.txt`; the dependency
loads only when connecting.

## Entry points

Run from this Skill's directory, or use an absolute script path and absolute
artifact paths from another directory.

```bash
python3 scripts/tts_generate.py --text "你好" --out /tmp/hello.mp3 \
  --instruction "温暖、自然，像面对面解释"
python3 scripts/tts_generate.py --request /absolute/request.json --dry-run
python3 scripts/tts_generate.py --request /absolute/request.json \
  --out /absolute/take.wav --record /absolute/take-response.json
```

For registered consumers, load
`llmreg.wrapper_for("stepfun-tts").tts_generate`. Standalone consumers may load
`scripts/tts_generate.py` without installing llmreg. The module exposes `http`
and `ws`, plus the existing `synthesize` function. See the reference for native
body, lifecycle and event examples.

- Use `synthesize(text=...)` for the compatible convenience interface. Its
  defaults live in [the HTTP implementation](scripts/stepfun_native/http.py).
  Preset voices remain useful for generic tasks.
- Use `synthesize(request=...)` for an explicit complete native speech body.
  This mode requires its own model, input and voice; it does not substitute a
  default identity. `extra` passes native fields through without a whitelist.
  Conflicting duplicate arguments fail instead of silently overriding.
- Use `--batch input.jsonl --out-dir /absolute/new-output` for independent
  voice lines. A censored line is reported and skipped while the batch continues;
  other failures return failure. No model or voice is changed automatically.
  Global CLI options serve as batch defaults; explicit row fields take precedence.
- Use [the native reference](references/api_reference.md) for HTTP streaming,
  WebSocket events, upload, clone, preview and inventory operations.

## Expression and verification

Use `instruction` for the overall delivery and ASCII `()` inside the input for
local natural-language directions on the officially documented contextual
models. These are instructions to a generative model, not a finite stress-tag
grammar. Do not invent SSML or promise a particular word will be stressed.
Reading substitutions belong in `pronunciation_map`, not emphasis control.
Preserve the whole passage when testing passage coherence within the service's
input limit; independent-line batches serve a different job.

Keep requests, raw responses and original audio together. Read the actual
response shape: binary audio, URL JSON and SSE are different outputs. The wrapper
preserves native error bodies, headers, JSON members and stream events.
Contract tests establish transport behavior; intelligibility, identity,
continuity and expression require listening to the generated audio.

## Existing workflows and recovery

Write alternative takes to a parallel output directory; preserve the production
corpus. `scripts/ab_compare.sh` compares directory duration and size, which do
not establish listening quality. Do not silently rewrite a censored script or
switch its model/voice; report the rejected line for an explicit content decision.

Read [migration from v2](references/migration_from_v2.md) before migrating an
existing step-tts-2 corpus. It preserves the historical emotion-to-instruction
mapping, comparison layout and per-line recovery decisions; its old account,
model and price observations are not current capability authority.
Read [known issues](references/known_issues.md) when investigating censorship,
unexpected duration or legacy parameter errors, with each observation's scope.
