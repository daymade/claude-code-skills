# stepaudio-2.5-asr API Reference

Exact request/response shapes for `stepaudio-2.5-asr`. Verified 2026-04-23 against the live StepFun API. Read this when calling the API by hand (curl, custom HTTP client) instead of using the bundled `scripts/asr_transcribe.py`.

## Endpoint (NOT the one you'd guess)

```
POST https://api.stepfun.com/v1/audio/asr/sse
Content-Type: application/json
Accept: text/event-stream
Authorization: Bearer <STEPFUN_API_KEY>
```

**Do NOT** send `stepaudio-2.5-asr` to `/v1/audio/transcriptions` — that endpoint serves the older `step-asr` / `step-asr-1.1` family and returns a misleading `model stepaudio-2.5-asr not supported` error which looks identical to a permission/whitelist error. See `known_issues.md` for the full diagnostic trail.

## Request body

```json
{
  "audio": {
    "data": "<base64-encoded audio bytes>",
    "input": {
      "transcription": {
        "language": "zh",
        "model": "stepaudio-2.5-asr",
        "enable_itn": true
      },
      "format": {
        "type": "mp3"
      }
    }
  }
}
```

| Path | Required | Type | Notes |
|---|---|---|---|
| `audio.data` | yes | string | base64-encoded audio bytes. Accepts mp3, wav, ogg, opus (in ogg container), pcm |
| `audio.input.transcription.language` | yes | string | `zh` or `en`. Dialects and Japanese are not officially supported |
| `audio.input.transcription.model` | yes | string | Must be `stepaudio-2.5-asr` |
| `audio.input.transcription.enable_itn` | no | bool | Inverse text normalization (数字→words). Default true |
| `audio.input.format.type` | yes | string | `mp3` / `wav` / `ogg` / `pcm` |
| `audio.input.format.rate` | pcm only | int | Sample rate (required for raw PCM) |
| `audio.input.format.channel` | pcm only | int | Channel count (required for raw PCM) |
| `audio.input.format.bits` | optional | int | Sample depth, default 16 |

## Response — SSE stream

The response is a Server-Sent Events stream. Each line is either empty or starts with `data: `. Three event types:

```
data: {"type":"transcript.text.delta","meta":{...},"delta":"你好，"}

data: {"type":"transcript.text.delta","meta":{...},"delta":"我是蕾格。"}

data: {"type":"transcript.text.done","meta":{...},"text":"你好，我是蕾格。","usage":{"type":"tokens","input_tokens":69,"input_token_details":{"text_tokens":69,"audio_tokens":0},"output_tokens":9,"total_tokens":78}}
```

| Event type | Meaning | How to handle |
|---|---|---|
| `transcript.text.delta` | Incremental piece of the transcription | Concatenate for progressive UI; optional if you only need final text |
| `transcript.text.done` | Final, full transcription + usage | Take `text` as the authoritative result. Also contains `usage` for billing/telemetry |
| `error` | Server-side error mid-stream | Abort and propagate `message` to the caller |

## Capacity

- 32K context window
- Audio ≤ 30 min can be sent in a single call
- No client-side chunking needed for long audio (unlike step-asr)
- RTF 85-101× on Chinese speech verified 2026-04-23

## Known error responses

```json
{"error":{"message":"model stepaudio-2.5-asr not supported","type":"request_params_invalid"}}
```
→ Wrong endpoint. Switch from `/v1/audio/transcriptions` to `/v1/audio/asr/sse`.

```
data: {"type":"error","message":"content blocked ..."}
```
→ Content censorship (rare on ASR). Same triggers as TTS (death/disappearance/political terms).

## Comparison with sibling and legacy endpoints

| Model | Endpoint | Request format |
|---|---|---|
| `stepaudio-2.5-asr` (this skill) | `/v1/audio/asr/sse` | JSON + base64 audio + SSE response |
| `stepaudio-2.5-tts` (sibling, see `stepfun-tts` skill) | `/v1/audio/speech` | JSON with `instruction` (no `voice_label`) |
| `step-asr` / `step-asr-1.1` (legacy) | `/v1/audio/transcriptions` | multipart/form-data |
| `step-tts-2` / `step-tts-mini` (legacy) | `/v1/audio/speech` | JSON with `voice_label` |

Legacy `step-asr-1.1` is the fallback when `stepaudio-2.5-asr` hits the repetition-hallucination edge case (see `known_issues.md`). The endpoint and body shape are entirely different — multipart upload to `/v1/audio/transcriptions`, no SSE.

## Auth and key handling

- Key header: `Authorization: Bearer <key>`
- Keys can be retrieved at https://platform.stepfun.com/ → API Keys
- "Plan" keys (cheaper subscription) are **restricted** to text models on `api.stepfun.com/step_plan`. They **cannot** call audio endpoints. Use a "Normal" key for ASR calls.
- Same key works for both TTS and ASR — no separate scopes

## Rate / throughput notes (observed, not officially documented)

- Long audio ASR (17 min) has succeeded with `timeout=1200` in the bundled script
- ~400ms sleep between sequential requests avoids 429s in batch processing
- Single TCP connection per request — SSE stream is closed after `transcript.text.done`
