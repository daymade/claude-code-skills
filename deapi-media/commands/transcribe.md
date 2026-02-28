---
name: transcribe
description: Transcribes video/audio from URLs (YouTube, X, mp3, mp4, wav) using Whisper AI
argument-hint: <url>
---

# Transcription via deAPI

Transcribe media from URL: **$ARGUMENTS**

## Step 1: Determine endpoint

| URL type | Endpoint |
|----------|----------|
| `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg` | `aud2txt` |
| YouTube, X, `.mp4`, `.webm`, other video | `vid2txt` |

## Step 2: Send request

**For video:**
```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/vid2txt" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"video_url": "$ARGUMENTS", "include_ts": true, "model": "WhisperLargeV3"}'
```

**For audio:**
```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/aud2txt" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"audio_url": "$ARGUMENTS", "include_ts": true, "model": "WhisperLargeV3"}'
```

## Step 3: Poll status (feedback loop)

Extract `request_id` from response, then poll every 10 seconds:

```bash
curl -s "https://api.deapi.ai/api/v1/client/request-status/{request_id}" \
  -H "Authorization: Bearer $DEAPI_API_KEY"
```

**Status handling:**
- `processing` → wait 10s, poll again
- `done` → proceed to Step 4
- `failed` → report error message to user, STOP

## Step 4: Fetch and present result

When `status = "done"`, fetch content from `result_url` and present transcription in readable format with timestamps.

## Step 5: Offer follow-up

Ask user: "Would you like me to summarize the main points?"

## Error handling

| Error | Action |
|-------|--------|
| 401 Unauthorized | Check if `$DEAPI_API_KEY` is set correctly |
| 429 Rate Limited | Wait 60s and retry |
| 500 Server Error | Wait 30s and retry once |
| Invalid URL | Ask user to verify the URL format |
| Timeout (>5min) | Inform user, suggest trying shorter content |
