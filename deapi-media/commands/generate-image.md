---
name: generate-image
description: Generate images from text prompts using Flux Klein, Flux Schnell, or ZImageTurbo models
argument-hint: <prompt> [--model klein|flux|turbo] [--size 512|768|1024]
---

# Image Generation via deAPI

Generate image from prompt: **$ARGUMENTS**

## Step 1: Parse arguments

Extract from `$ARGUMENTS`:
- `prompt`: The text description (required)
- `--model`: `klein` (default, recommended), `flux` (higher max resolution), or `turbo` (fastest)
- `--size`: `512`, `768`, or `1024` (default: 1024). Klein supports up to 1536.

## Step 2: Send request

```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/txt2img" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "{prompt}",
    "model": "{model_name}",
    "width": {size},
    "height": {size},
    "steps": {steps},
    "seed": {random_seed}
  }'
```

**Model mapping:**
| User flag | API model name | Steps | Max size | Info |
|-----------|----------------|-------|----------|------|
| `klein` (default) | `Flux_2_Klein_4B_BF16` | 4 (fixed) | 1536 | Recommended, txt2img + img2img, multi-image |
| `flux` | `Flux1schnell` | 4-10 (default: 4) | 2048 | Higher max resolution |
| `turbo` | `ZImageTurbo_INT8` | 4-10 (default: 4) | 1024 | Fastest |

**Klein model limits:**
- Resolution: 256-1536px (step: 16)
- Steps: 4 (fixed)
- Guidance: not supported (parameter ignored)

**Important:** Generate a random seed (0-999999) for each request.

**Note:** Klein does not support `guidance` parameter - omit it or it will be ignored.

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

When `status = "done"`:
1. Get image URL from `result_url`
2. Display/download the generated image
3. Show the image to the user

## Step 5: Offer follow-up

Ask user:
- "Would you like variations with a modified prompt?"
- "Should I upscale this image?"
- "Would you like to transform this with additional images?" (Klein supports up to 3 input images in img2img)

## Error handling

| Error | Action |
|-------|--------|
| 401 Unauthorized | Check if `$DEAPI_API_KEY` is set correctly |
| 429 Rate Limited | Wait 60s and retry |
| 500 Server Error | Wait 30s and retry once |
| Empty prompt | Ask user to provide a description |
| NSFW rejected | Inform user, suggest alternative prompt |
