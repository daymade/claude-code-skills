---
name: generate-video
description: Generate videos from text prompts or animate images
argument-hint: <prompt-or-image-url> [--mode text|image]
---

# Video Generation via deAPI

Generate video: **$ARGUMENTS**

## Step 1: Determine mode and parse arguments

**Auto-detect mode:**
- If `$ARGUMENTS` starts with `http` → Image-to-Video (`img2video`)
- Otherwise → Text-to-Video (`txt2video`)

**Override with `--mode`:**
- `--mode text`: Force text-to-video
- `--mode image`: Force image-to-video

## Step 2: Send request

**For Text-to-Video:**
```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/txt2video" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "{prompt}",
    "duration": 4,
    "fps": 24,
    "model": "Ltxv_13B_0_9_8_Distilled_FP8"
  }'
```

**For Image-to-Video (animation):**
```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/img2video" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "{image_url}",
    "motion_prompt": "gentle movement, cinematic",
    "duration": 4,
    "fps": 24
  }'
```

## Step 3: Poll status (feedback loop)

Extract `request_id` from response, then poll every 10 seconds:

```bash
curl -s "https://api.deapi.ai/api/v1/client/request-status/{request_id}" \
  -H "Authorization: Bearer $DEAPI_API_KEY"
```

**Status handling:**
- `processing` → wait 10s, poll again (video generation can take 1-3 minutes)
- `done` → proceed to Step 4
- `failed` → report error message to user, STOP

## Step 4: Fetch and present result

When `status = "done"`:
1. Get video URL from `result_url`
2. Provide download link to user
3. Show video details (duration, resolution)

## Step 5: Offer follow-up

Ask user:
- "Would you like to generate a longer version?"
- "Should I try a different motion style?"
- "Would you like to generate more variations?"

## Error handling

| Error | Action |
|-------|--------|
| 401 Unauthorized | Check if `$DEAPI_API_KEY` is set correctly |
| 429 Rate Limited | Wait 60s and retry |
| 500 Server Error | Wait 30s and retry once |
| Empty prompt | Ask user to provide a description |
| Invalid image URL | Verify URL is accessible and points to an image |
| Timeout (>5min) | Inform user, video generation is resource-intensive |
