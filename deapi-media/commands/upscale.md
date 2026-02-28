---
name: upscale
description: Upscale and enhance image resolution using AI
argument-hint: <image-url> [--scale 2|4]
---

# Image Upscaling via deAPI

Upscale image: **$ARGUMENTS**

## Step 1: Parse arguments

Extract from `$ARGUMENTS`:
- `image`: Image file path or URL (required)
- `--scale`: Upscale factor - `2` (2x, default) or `4` (4x)

**Model options (based on scale):**
| Scale | Model | Result |
|-------|-------|--------|
| `2` | `RealESRGAN_x2` | 2x resolution (e.g., 512→1024) |
| `4` | `RealESRGAN_x4` | 4x resolution (e.g., 512→2048) |

## Step 2: Send request

**Note:** This endpoint requires `multipart/form-data` with file upload.

```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/img-upscale" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -F "image=@{local_file_path}" \
  -F "model=RealESRGAN_x4"
```

If user provides a URL, first download the image:
```bash
curl -s -o /tmp/upscale_image.png "{image_url}"
```
Then use `/tmp/upscale_image.png` as the file path.

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
1. Get upscaled image URL from `result_url`
2. Show original vs new dimensions
3. Provide download link to user

## Step 5: Offer follow-up

Ask user:
- "Would you like to upscale further (if 2x was used)?"
- "Should I remove the background from this image?"
- "Would you like to process another image?"

## Error handling

| Error | Action |
|-------|--------|
| 401 Unauthorized | Check if `$DEAPI_API_KEY` is set correctly |
| 429 Rate Limited | Wait 60s and retry |
| 500 Server Error | Wait 30s and retry once |
| Invalid URL | Ask user to verify the image URL |
| Image too large | 4x upscaling has size limits; suggest 2x instead |
| Unsupported format | Convert to PNG/JPG first |
