# StepAudio 2.5 API Reference

Exact request/response shapes for `stepaudio-2.5-tts` and `stepaudio-2.5-asr`. Verified 2026-04-23 against the live StepFun API. Read this when you need to call the API by hand (curl, custom HTTP client) instead of using the bundled scripts.

## TTS — `stepaudio-2.5-tts`

### Endpoint

```
POST https://api.stepfun.com/v1/audio/speech
Content-Type: application/json
Authorization: Bearer <STEPFUN_API_KEY>
```

### Request body

```json
{
  "model": "stepaudio-2.5-tts",
  "input": "你好，我是蕾格。",
  "voice": "shuangkuaijiejie",
  "response_format": "mp3",
  "speed": 1.0,
  "volume": 1.0,
  "instruction": "克制的悲伤，语气低沉柔弱"
}
```

| Field | Required | Type | Notes |
|---|---|---|---|
| `model` | yes | string | Must be `stepaudio-2.5-tts` |
| `input` | yes | string | ≤1000 chars; can contain inline `(directive)` parentheses |
| `voice` | yes | string | e.g. `shuangkuaijiejie`. Zero-shot clones use the clone's ID |
| `response_format` | yes | string | `mp3` (default), `wav`, or `opus` |
| `speed` | no | float | 0.5-2.0, default 1.0 |
| `volume` | no | float | 0.0-2.0, default 1.0 |
| `instruction` | no | string | Global tone directive, natural language, ≤200 chars |
| `voice_label` | — | — | **DO NOT SEND**. Returns `voice_label is not supported for v2 models`. Belongs to step-tts-2 |

### Inline directives inside `input`

Parentheses `()` in the `input` are consumed as TTS control signals, not pronounced. Examples that work:

- `(停顿一下)` — insert a pause
- `(轻声)` — reduce volume / breathy
- `(加重)` — stress the following word
- `(试探着问)` — apply a tone shift mid-sentence
- `(突然沉下来)` — emotion pivot

You can mix `instruction` (global tone) with inline `()` (per-phrase micro-control):

```json
{
  "instruction": "富有情绪弧线的独白",
  "input": "(试探着问)你好吗？(开心地)太好了！(突然沉下来)不过...我快要消失了。"
}
```

### Response

On success: binary audio stream in the requested `response_format`. HTTP 200. No JSON wrapper. Save the body directly as `.mp3`/`.wav`/`.opus`.

### Known error responses

```json
{"error":{"message":"voice_label is not supported for v2 models","type":"request_params_invalid"}}
```
→ Remove `voice_label`, use `instruction` instead.

```json
{"error":{"message":"The content you provided or machine outputted is blocked.","type":"censorship_block"}}
```
→ Content triggered censorship. Common triggers: 死, 消失, politically sensitive terms. See `known_issues.md`.

## ASR — `stepaudio-2.5-asr`

### Endpoint (NOT the one you'd guess)

```
POST https://api.stepfun.com/v1/audio/asr/sse
Content-Type: application/json
Accept: text/event-stream
Authorization: Bearer <STEPFUN_API_KEY>
```

**Do NOT** send `stepaudio-2.5-asr` to `/v1/audio/transcriptions` — that endpoint only serves the older `step-asr` / `step-asr-1.1` family, and returns a misleading `model stepaudio-2.5-asr not supported` which looks identical to a permission/whitelist error. See `known_issues.md` for the full diagnostic trail.

### Request body

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

### Response — SSE stream

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

### Capacity

- 32K context window
- Audio ≤ 30 min can be sent in a single call
- No client-side chunking needed for long audio (unlike step-asr)
- RTF 85-101× on Chinese speech verified 2026-04-23

### Known error responses

```json
{"error":{"message":"model stepaudio-2.5-asr not supported","type":"request_params_invalid"}}
```
→ Wrong endpoint. Switch from `/v1/audio/transcriptions` to `/v1/audio/asr/sse`.

```
data: {"type":"error","message":"content blocked ..."}
```
→ Content censorship (rare on ASR). Same triggers as TTS.

## Comparison with legacy endpoints (for reference)

| Model | Endpoint | Request format |
|---|---|---|
| `step-tts-2` / `step-tts-mini` | `/v1/audio/speech` | JSON with `voice_label` |
| `stepaudio-2.5-tts` | `/v1/audio/speech` | JSON with `instruction` (no voice_label) |
| `step-asr` / `step-asr-1.1` | `/v1/audio/transcriptions` | multipart/form-data |
| `stepaudio-2.5-asr` | `/v1/audio/asr/sse` | JSON + base64 audio + SSE response |

Legacy endpoints (`step-*`) still work. They're the baseline in `references/migration_from_v2.md` and the fallback choice when `stepaudio-2.5-*` hits `censorship_block` or the 2.5 ASR repetition-hallucination edge case.

## Auth and key handling

- Key header: `Authorization: Bearer <key>`
- Keys can be retrieved at https://platform.stepfun.com/ → API Keys
- "Plan" keys (cheaper subscription) are **restricted** to text models on `api.stepfun.com/step_plan`. They **cannot** call audio endpoints. Use a "Normal" key for all TTS/ASR calls.
- Same key works for both TTS and ASR — no separate scopes

## Rate / throughput notes (observed, not officially documented)

- ~400ms sleep between batch requests avoids 429s in practice
- Long audio ASR (17 min) has succeeded with `timeout=1200`
- MP3 responses consistently at 128kbps 24kHz mono (TTS default)
