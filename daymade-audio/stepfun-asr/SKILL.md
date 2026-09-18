---
name: stepfun-asr
description: Transcribe audio with StepFun's stepaudio-3-asr-max — an SSE endpoint (NOT /v1/audio/transcriptions), single call handles long audio with no client-side chunking. Use when transcribing Chinese / English audio with StepFun, when long-form recordings (5-30 min) need to land in one request, when migrating from step-asr / step-asr-1.1 / stepaudio-2.5-asr, or when hitting the misleading `model stepaudio-3-asr-max not supported` error (which actually means wrong endpoint). Triggers on 阶跃 ASR, StepFun ASR, stepaudio-3-asr-max, stepaudio-2.5-asr, 转录, 语音识别, 长音频转写, 语音转文字. For TTS with the sibling stepaudio-3-tts model, use the stepfun-tts skill instead.
---

# StepFun stepaudio-3-asr-max

Transcribe audio with StepFun's `stepaudio-3-asr-max` (StepAudio 3, released 2026-09-15, verified 2026-09-16; supersedes `stepaudio-2.5-asr` on the same endpoint). Long audio in one call, no chunking — but **only** if the request hits the right endpoint with the right body shape. The wrong endpoint returns an error that looks identical to "model doesn't exist", which is the #1 reason this skill exists.

> Companion: for TTS with `stepaudio-3-tts` (the sibling model), use the `stepfun-tts` skill — they share an API key but live on different endpoints with different body shapes.

## Why this skill exists — three traps that cost hours

1. **Wrong endpoint, wrong error**. `stepaudio-3-asr-max` does **not** live on `/v1/audio/transcriptions` (that endpoint serves the older `step-asr` family). It lives on `/v1/audio/asr/sse` — SSE streaming, JSON body, base64 audio. Sending it to the wrong endpoint returns `{"error":{"message":"model stepaudio-3-asr-max not supported"}}`, which is **identical in structure** to a genuinely nonexistent model name. People waste hours filing whitelist tickets.

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

Per-word timestamps need no flag — `--json` always carries `segments`:

```json
"segments": [{"text": "Understand ", "start_ms": 228, "end_ms": 1108}, ...]
```

One entry per word, monotonic. A few words share their predecessor's timestamp (the server
flushes in blocks), which is fine for locating a moment but not for forced alignment.

To use an older model:

```bash
python3 scripts/asr_transcribe.py /path/to/audio.mp3 --model stepaudio-2.5-asr
```

The script handles base64 encoding, the nested `{audio: {data, input: {transcription, format}}}` body, SSE parsing, and the misleading-endpoint pitfall. Prefer it over hand-rolled HTTP calls unless integrating into a larger pipeline.

## Decision table

| Scenario | Action |
|---|---|
| Short clip (< 5 min), Chinese or English, mp3/wav/ogg/opus | `python3 scripts/asr_transcribe.py audio.mp3` |
| Long audio (5-30 min) | Same script — 32K context handles it in a single call, no chunking needed |
| Audio > 30 min | Split with ffmpeg before sending; the API rejects oversized payloads |
| Need usage/billing data | Add `--json` to capture `usage.input_tokens` / `usage.total_tokens` from `transcript.text.done` |
| Need to know when each word was said | `--json`, read `segments`. On by default |
| **Need speaker labels (who said what)** | **Not this endpoint.** Use `/v1/audio/asr/file/submit` with `enable_speaker_info` — requires a publicly fetchable audio URL (base64 is rejected). See `references/api_reference.md` |
| `--model stepaudio-2-asr-pro` returns `internal error` | That model is not usable on `/v1/audio/asr/sse` (measured 2026-09-18); use the default or `stepaudio-2.5-asr` |
| Highly repetitive content (same phrase 5+ times, > 90s) | Cross-validate with `step-asr-1.1` — see repetition hallucination in `references/known_issues.md` (2.5-era issue, unverified on v3) |
| Hit `model stepaudio-3-asr-max not supported` | Wrong endpoint. Switch from `/v1/audio/transcriptions` to `/v1/audio/asr/sse` |
| Hit silent 4xx auth failure | Verify your key is "Normal" not "Plan" — Plan keys cannot call audio endpoints |
| Need to write raw HTTP (no Python) | Read `references/api_reference.md` for exact JSON body and SSE event shapes |

## Parameters are free — never omit one silently

Sending more request parameters costs nothing: billing is per audio-hour. So the default is
**send everything useful**, and every field we do *not* send has to carry a written reason in
`REQUEST_PARAMS` at the top of `scripts/asr_transcribe.py`.

```bash
python3 scripts/check_params.py            # diff official field table vs REQUEST_PARAMS
python3 scripts/check_params.py --selftest # calibrate the check before trusting it
```

Two guards, one per direction:

- **Request side** — `check_params.py` fetches the official field table and fails if it lists
  a field `REQUEST_PARAMS` does not mention. `--selftest` calibrates both ways: the real
  manifest must pass (no false alarms), and a manifest with `enable_timestamp` removed must
  be caught (the actual historical gap — per-word timestamps were missing for months because
  only the *response* field table was ever read).
- **Response side** — the parser reports `unhandled_response_fields` for anything the server
  sends that it does not consume, because that is what the timestamp gap looked like from
  this side: `start_time`/`end_time` arrived on every delta and were thrown away.

## Supported audio formats

The script auto-detects from extension; pass `--format` to override:

| Extension | Format flag | Notes |
|---|---|---|
| `.mp3` | `mp3` | Most common, default |
| `.wav` | `wav` | Lossless |
| `.ogg` | `ogg` | OGG container |
| `.opus` | `ogg` | Opus codec in OGG container — pass through unchanged |
| `.pcm` | `pcm` | Raw PCM — also pass `--rate`, `--bits`, `--channel` (and `--codec`) |

For mp4/m4a/webm/etc., transcode to one of the above first via ffmpeg. Production pipelines often pre-transcode everything to OGG/Opus 16kHz mono to minimize base64 payload size.

## Capacity and performance

v3 spot measurements (verified 2026-09-16): 10s clip → 1.1s, 53s real-world clip → 2.6s (~20× RTF). v2.5-era baseline for reference (2026-04-23, same endpoint): 32K context window, ~85-101× RTF on 17.4 min audio, single-call ceiling ≈ 30 min — treat 30 min as the working ceiling for v3 until re-probed, and re-measure before quoting long-audio numbers.

## Common error patterns

| Error response | Actual cause | Fix |
|---|---|---|
| `"model stepaudio-3-asr-max not supported"` on `/v1/audio/transcriptions` | Wrong endpoint | Switch to `/v1/audio/asr/sse` (script does this) |
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

## Pricing (verified 2026-09-16, volatile)

`stepaudio-3-asr-max`: 2.8 元/小时 (official model page, 2026-09-16). The older `stepaudio-2.5-asr` remains served on the same endpoint as a fallback. Re-verify at https://platform.stepfun.com/docs/zh/guides/pricing/details before quoting to stakeholders.

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

