---
name: remove-bg
description: Remove background from images using AI
argument-hint: <image-url>
---

# Background Removal via deAPI

Remove background from image: **$ARGUMENTS**

## Step 1: Validate input

Verify `$ARGUMENTS` is a valid image file path or URL:
- Supported formats: `.png`, `.jpg`, `.jpeg`, `.webp`
- If URL provided, download the file first
- Best results with clear subject/foreground

## Step 2: Send request

**Note:** This endpoint requires `multipart/form-data` with file upload.

```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/img-rmbg" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -F "image=@{local_file_path}" \
  -F "model=Ben2"
```

If user provides a URL, first download the image:
```bash
curl -s -o /tmp/rmbg_image.png "{image_url}"
```
Then use `/tmp/rmbg_image.png` as the file path.

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
1. Get processed image URL from `result_url`
2. Result is PNG with transparent background
3. Provide download link to user

## Step 5: Offer follow-up

Ask user:
- "Would you like to add a new background color?"
- "Should I process another image?"
- "Would you like to resize the result?"

## Error handling

| Error | Action |
|-------|--------|
| 401 Unauthorized | Check if `$DEAPI_API_KEY` is set correctly |
| 429 Rate Limited | Wait 60s and retry |
| 500 Server Error | Wait 30s and retry once |
| Invalid URL | Ask user to verify the image URL |
| No subject detected | Image may lack clear foreground; suggest different image |
| Image too large | Suggest resizing before processing |
