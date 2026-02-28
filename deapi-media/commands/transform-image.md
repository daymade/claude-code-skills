---
name: transform-image
description: Transform images with style transfer and AI modifications
argument-hint: <image-url> <style-prompt> [--model klein|qwen]
---

# Image Transformation via deAPI

Transform image: **$ARGUMENTS**

## Step 1: Parse arguments

Extract from `$ARGUMENTS`:
- `image_url`: URL(s) to source image(s) - Klein supports up to 3 images (required)
- `style_prompt`: Description of desired transformation (required)
- `--model`: `klein` (default, faster, multi-image) or `qwen` (higher steps, more control)

**Example style prompts:**
- "convert to watercolor painting"
- "make it look like a vintage photograph"
- "transform into anime style"
- "add cyberpunk neon aesthetic"
- "combine these images into one scene" (multi-image with Klein)

## Step 2: Send request

**Note:** This endpoint requires `multipart/form-data` with file upload.

If user provides URL(s), first download the image(s):
```bash
curl -s -o /tmp/transform_image1.png "{image_url_1}"
curl -s -o /tmp/transform_image2.png "{image_url_2}"  # optional
curl -s -o /tmp/transform_image3.png "{image_url_3}"  # optional
```

Then send the transformation request:

```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/img2img" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -F "image=@{local_file_path_1}" \
  -F "image=@{local_file_path_2}" \
  -F "image=@{local_file_path_3}" \
  -F "prompt={style_prompt}" \
  -F "model={model_name}" \
  -F "guidance={guidance}" \
  -F "steps={steps}" \
  -F "seed={random_seed}"
```

**Model mapping:**
| User flag | API model name | Steps | Guidance | Max images | Info |
|-----------|----------------|-------|----------|------------|------|
| `klein` (default) | `Flux_2_Klein_4B_BF16` | 4 (fixed) | ignored | 3 | Faster, multi-image support |
| `qwen` | `QwenImageEdit_Plus_NF4` | 10-50 (default: 20) | 7.5 | 1 | More control, higher fidelity |

**Klein model limits:**
- Resolution: 256-1536px (step: 16)
- Steps: 4 (fixed)
- Guidance: not supported
- Max input images: 3

**Parameters:**
| Parameter | Klein | Qwen | Description |
|-----------|-------|------|-------------|
| `guidance` | ignored | 7.5 | Prompt adherence (1-20) |
| `steps` | 4 (fixed) | 20 | Inference steps |
| `seed` | random | random | For reproducibility (0-999999) |

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
1. Get transformed image URL from `result_url`
2. Display before/after comparison if possible
3. Provide download link to user

## Step 5: Offer follow-up

Ask user:
- "Would you like to try a different style?"
- "Should I add more input images?" (Klein only, up to 3)
- "Would you like to upscale the result?"

## Error handling

| Error | Action |
|-------|--------|
| 401 Unauthorized | Check if `$DEAPI_API_KEY` is set correctly |
| 429 Rate Limited | Wait 60s and retry |
| 500 Server Error | Wait 30s and retry once |
| Invalid URL | Ask user to verify the image URL |
| Missing prompt | Ask user to describe desired transformation |
| Too many images | Klein max 3, Qwen max 1 |
| NSFW rejected | Inform user, suggest alternative style |
