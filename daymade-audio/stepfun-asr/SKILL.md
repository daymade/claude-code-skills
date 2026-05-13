---
name: stepfun-asr
description: Transcribe audio with StepFun's stepaudio-2.5-asr — an SSE endpoint (NOT /v1/audio/transcriptions) with 32K context, ~85-101x RTF on long audio, and a single-call ceiling around 30 minutes (no client-side chunking). Use when transcribing Chinese / English audio with StepFun, when long-form recordings (5-30 min) need to land in one request, when migrating from step-asr / step-asr-1.1, or when hitting the misleading `model stepaudio-2.5-asr not supported` error (which actually means wrong endpoint). Triggers on 阶跃 ASR, StepFun ASR, stepaudio-2.5-asr, 转录, 语音识别, 长音频转写, 语音转文字. For TTS with the sibling stepaudio-2.5-tts model, use the stepfun-tts skill instead.
---

# StepFun stepaudio-2.5-asr

Transcribe audio with StepFun's `stepaudio-2.5-asr` (released 2026-04, verified 2026-04-23). Long audio in one call, no chunking — but **only** if the request hits the right endpoint with the right body shape. The wrong endpoint returns an error that looks identical to "model doesn't exist", which is the #1 reason this skill exists.

> Companion: for TTS with `stepaudio-2.5-tts` (the sibling model), use the `stepfun-tts` skill — they share an API key but live on different endpoints with different body shapes.

## Why this skill exists — three traps that cost hours

1. **Wrong endpoint, wrong error**. `stepaudio-2.5-asr` does **not** live on `/v1/audio/transcriptions` (that endpoint serves the older `step-asr` family). It lives on `/v1/audio/asr/sse` — SSE streaming, JSON body, base64 audio. Sending it to the wrong endpoint returns `{"error":{"message":"model stepaudio-2.5-asr not supported"}}`, which is **identical in structure** to a genuinely nonexistent model name. People waste hours filing whitelist tickets.

2. **Plan key vs Normal key, silent failure**. StepFun's "Plan" subscription keys (cheap, text-only) cannot call audio endpoints, but the failure manifests as a 4xx with no auth-shaped error message. If your account has a Plan subscription, you need a separate "Normal" key from the same console.

3. **SSE error events are real**. Censorship can fire on the ASR side too (rarely). Don't assume only `transcript.text.delta` and `transcript.text.done` events arrive — handle `type: error` events in the stream or you'll silently drop them.

## Config and auth

API key resolves in this order (fail-fast, no defaults):

1. `$STEPFUN_API_KEY` environment variable
2. `${CLAUDE_PLUGIN_DATA}/config.json` with `{"api_key": "..."}` (cross-session persistence)

First-time setup:

```bash
mkdir -p "${CLAUDE_PLUGIN_DATA}" && cat > "${CLAUDE_PLUGIN_DATA}/config.json" <<EOF
{"api_key": "<paste Normal key here>"}
EOF
```

If the user has not set a key, ask them to paste it — do not guess or use a placeholder. Get keys at https://platform.stepfun.com/ → API Keys. **Use a Normal key, not a Plan key.**

## Quick start — single file

```bash
python3 scripts/asr_transcribe.py /path/to/audio.mp3
```

Output: plain text transcription on stdout.

For machine-readable output with usage / timing:

```bash
python3 scripts/asr_transcribe.py /path/to/audio.mp3 --json
```

For non-Chinese audio:

```bash
python3 scripts/asr_transcribe.py /path/to/audio.mp3 --language en
```

The script handles base64 encoding, the nested `{audio: {data, input: {transcription, format}}}` body, SSE parsing, and the misleading-endpoint pitfall. Prefer it over hand-rolled HTTP calls unless integrating into a larger pipeline.

## Decision table

| Scenario | Action |
|---|---|
| Short clip (< 5 min), Chinese or English, mp3/wav/ogg/opus | `python3 scripts/asr_transcribe.py audio.mp3` |
| Long audio (5-30 min) | Same script — 32K context handles it in a single call, no chunking needed |
| Audio > 30 min | Split with ffmpeg before sending; the API rejects oversized payloads |
| Need usage/billing data | Add `--json` to capture `usage.input_tokens` / `usage.total_tokens` from `transcript.text.done` |
| Highly repetitive content (same phrase 5+ times, > 90s) | Cross-validate with `step-asr-1.1` — see repetition hallucination in `references/known_issues.md` |
| Hit `model stepaudio-2.5-asr not supported` | Wrong endpoint. Switch from `/v1/audio/transcriptions` to `/v1/audio/asr/sse` |
| Hit silent 4xx auth failure | Verify your key is "Normal" not "Plan" — Plan keys cannot call audio endpoints |
| Need to write raw HTTP (no Python) | Read `references/api_reference.md` for exact JSON body and SSE event shapes |

## Supported audio formats

The script auto-detects from extension; pass `--format` to override:

| Extension | Format flag | Notes |
|---|---|---|
| `.mp3` | `mp3` | Most common, default |
| `.wav` | `wav` | Lossless |
| `.ogg` | `ogg` | OGG container |
| `.opus` | `ogg` | Opus codec in OGG container — pass through unchanged |
| `.pcm` | `pcm` | Raw PCM — also requires `format.rate`, `format.channel`, `format.bits` (see API reference) |

For mp4/m4a/webm/etc., transcode to one of the above first via ffmpeg. Production pipelines often pre-transcode everything to OGG/Opus 16kHz mono to minimize base64 payload size.

## Capacity and performance (verified 2026-04-23)

- **32K context window** — single-call upper limit, no chunking needed for ≤ 30 min audio
- **~85-101× RTF** on long audio (17.4 min audio → 10.4s wall clock)
- **~5.3× speedup vs step-asr-1.1** at the 100s+ length range
- **Only ~2× speedup** at the 5-15s range — the LLM spin-up cost dominates short clips. If your workload is many short clips, the migration ROI is modest

## Common error patterns

| Error response | Actual cause | Fix |
|---|---|---|
| `"model stepaudio-2.5-asr not supported"` on `/v1/audio/transcriptions` | Wrong endpoint | Switch to `/v1/audio/asr/sse` (script does this) |
| Silent 4xx with no auth message | Using a "Plan" key on audio endpoint | Get a "Normal" key from the StepFun console |
| ASR returns 3-4× expected character count | Repetition hallucination on highly-repetitive audio | Cross-validate with `step-asr-1.1`; see `references/known_issues.md` |
| `data: {"type":"error","message":"content blocked..."}` mid-stream | Censorship fired on user-uploaded content | Handle SSE `error` event explicitly; don't assume only `delta`/`done` arrive |

More edge cases in `references/known_issues.md`.

## Design invariants (do not break)

1. **Always pass through SSE** — don't try to buffer the response with a non-streaming client. The model emits `transcript.text.delta` for long audio; `transcript.text.done` carries the authoritative full text and `usage`. Reject the SSE format entirely and you'll get nothing.
2. **Take final text from `transcript.text.done.text`** — concatenated deltas can drift on edge cases. Deltas are for progressive UI; the `done` event is the source of truth.
3. **Handle `error` events in the stream** — don't treat the SSE stream as if only success events arrive. A blocked-content event mid-stream returns `type: error` with no `done` event.
4. **Fail-fast on missing API key** — never default to a placeholder or empty string. The script does this; preserve the behavior in any wrapper.

## When to read references

- `references/api_reference.md` — exact JSON request body, all fields, all SSE event types, response examples. Read when writing raw HTTP calls instead of using the bundled script.
- `references/known_issues.md` — repetition hallucination details, the wrong-endpoint diagnostic trail, Plan-vs-Normal key gotcha, ASR-side censorship handling, pricing opacity. Read when debugging anomalous output or evaluating whether to migrate from `step-asr-1.1`.

## Pricing (verified 2026-04-23, volatile)

`stepaudio-2.5-asr` is in invitation beta as of 2026-04-23 — no public per-minute rate. The `step-asr-1.1` baseline is 2.2 元/小时. The invitation PDF mentions "成本直降 80%" implying ~0.4 元/小时, but this is not yet on the pricing page. Re-verify at https://platform.stepfun.com/docs/zh/guides/pricing/details before quoting to stakeholders.

## Next Step

ASR transcripts almost always benefit from one of two downstream steps. After producing the transcript, suggest the natural next skill:

```
Transcription complete. The output is raw text from the model — common next steps:

Options:
A) transcript-fixer — clean up ASR errors (homophones, segmentation, filler words). Recommended if the recording is a real-world conversation, podcast, or interview rather than read-aloud text
B) meeting-minutes-taker — turn the transcript into structured minutes with decisions, action items, and speaker attribution. Recommended if the recording is a meeting
C) No thanks — the raw transcript is what I needed
```

Skip the suggestion when the user has already specified the downstream tool, or when the transcription was clearly a one-off lookup (e.g., "what does this 15-second clip say?").

