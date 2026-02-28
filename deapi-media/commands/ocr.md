---
name: ocr
description: Extract text from images using AI-powered OCR
argument-hint: <image-url>
---

# OCR (Image to Text) via deAPI

Extract text from image: **$ARGUMENTS**

## Step 1: Validate input

Verify `$ARGUMENTS` is a valid image file path or URL:
- Supported formats: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.bmp`
- If URL provided, download the file first

## Step 2: Send request

**Note:** This endpoint requires `multipart/form-data` with file upload.

```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/img2txt" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -F "image=@{local_file_path}" \
  -F "model=Nanonets_Ocr_S_F16"
```

If user provides a URL, first download the image:
```bash
curl -s -o /tmp/ocr_image.png "{image_url}"
```
Then use `/tmp/ocr_image.png` as the file path.

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
1. Get extracted text from response or `result_url`
2. Present text in clean, formatted manner
3. Preserve original structure (paragraphs, lists) where possible

## Step 5: Offer follow-up

Ask user:
- "Would you like me to summarize this text?"
- "Should I translate this to another language?"
- "Would you like to extract text from another image?"

## Error handling

| Error | Action |
|-------|--------|
| 401 Unauthorized | Check if `$DEAPI_API_KEY` is set correctly |
| 429 Rate Limited | Wait 60s and retry |
| 500 Server Error | Wait 30s and retry once |
| Invalid URL | Ask user to verify the image URL |
| No text found | Inform user the image may not contain readable text |
| Image too large | Suggest resizing or cropping the image |
