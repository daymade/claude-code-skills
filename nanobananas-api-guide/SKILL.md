---
name: nanobananas-api-guide
description: "Complete guide for using the NanoBananas.AI API — image generation, video generation, pricing, authentication, and code examples in Python/Node.js/cURL. Use when building apps with NanoBananas API, checking pricing, or troubleshooting API errors."
---

# NanoBananas.AI API Guide

Your complete reference for building with the NanoBananas.AI API. Generate images and videos using state-of-the-art AI models.

**Base URL**: `https://nanobananas.ai`
**Documentation**: https://nanobananas.ai/api

---

## Authentication

All API requests require an API key via header:

```
Authorization: Bearer YOUR_API_KEY
```

Get your API key at: https://nanobananas.ai/api-keys

**Requirement**: Advanced subscription plan ($29.90/month or $269.90/year)

---

## Quick Start

### Generate an Image (30 seconds)

```bash
curl -X POST "https://nanobananas.ai/api/v1/images/generate" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "prompt=A golden retriever playing in autumn leaves, cinematic lighting"
```

### Generate a Video (2-5 minutes)

```bash
# Step 1: Submit task
curl -X POST "https://nanobananas.ai/api/v1/video/generate" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "A cat playing with a ball in slow motion", "model": "veo3"}'

# Step 2: Poll status (use task_id from step 1)
curl "https://nanobananas.ai/api/v1/video/status?task_id=YOUR_TASK_ID" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## Image Generation

### POST /api/v1/images/generate

Supports `multipart/form-data` and `application/json`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | Yes* | Image description (max 5000 chars, returns HTTP 400 if exceeded) |
| `model` | string | No | Model ID, default `gemini-2.5-flash-image-preview` |
| `image` | File/File[] | No | Reference image file(s) for img2img |
| `imageUrl` | string/string[] | No | Reference image URL(s) for img2img |
| `aspectRatio` | string | No | See aspect ratio table below |
| `img_size` | string | No | `1k` / `2k` / `4k`, default `1k` |
| `mode` | string | No | `txt2img` or `img2img` (auto-detected if omitted) |
| `hdPro` | string | No | Pass `"true"` for HD mode |
| `googleSearch` | string | No | `"true"` to enable search enhancement (Nano Banana 2 only) |

> *Either `prompt` or `image`/`imageUrl` must be provided

### Supported Image Models

| Model ID | Name | 1k | 2k | 4k | Notes |
|----------|------|-----|-----|-----|-------|
| `gemini-2.5-flash-image-preview` | Nano Banana | 10 | 15 | - | Default, fastest |
| `gemini-3.1-pro-image-preview` | Nano Banana 2 | 25 | 35 | 60 | Better quality, extended aspect ratios |
| `gemini-3-pro-image-preview` | Nano Banana Pro | 30 | 50 | 80 | Highest quality |
| `gemini-3-pro-image-preview-vip` | Nano Banana Pro VIP | 40 | 60 | 90 | Dedicated stable channel |
| `sora_image` | GPT-4o | 10 | - | - | OpenAI model |

### Aspect Ratios

**All models**: `auto`, `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`

**Nano Banana 2 additionally supports**: `4:1`, `1:4`, `8:1`, `1:8`

### Output Dimensions (img_size)

| img_size | 1:1 | 16:9 | 9:16 |
|----------|-----|------|------|
| `1k` | ~1024x1024 | ~1280x720 | ~720x1280 |
| `2k` | ~2048x2048 | ~2560x1440 | ~1440x2560 |
| `4k` | ~4096x4096 | ~3840x2160 | ~2160x3840 |

> `img_size` only applies to Nano Banana 2 / Pro / Pro VIP models.

### Image Response (200)

```json
{
  "status": 200,
  "images": ["https://img.nanobananas.ai/xxx.webp"],
  "uuid": "abc123-def456",
  "prompt": "A golden retriever...",
  "credits": { "remaining": 4500, "costCredits": 10 }
}
```

---

## Async Image Generation (Recommended for Production)

### POST /api/v1/images/async

Same parameters as `/api/v1/images/generate`. Returns immediately with a `task_id`.

```json
{
  "status": 202,
  "task_id": "abc123-def456",
  "message": "Task submitted. Use GET /api/v1/images/task-status?task_id={task_id} to poll."
}
```

### GET /api/v1/images/task-status?task_id=xxx

Poll until `status` is `completed` or `failed`.

---

## Video Generation

### POST /api/v1/video/generate

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | **Yes** | Video description (max 1500 chars) |
| `model` | string | No | `veo3` (default), `sora2`, `seedance` |
| `aspect_ratio` | string | No | `16:9`, `9:16`, `1:1` |
| `resolution` | string | No | `480p`, `720p`, `1080p` |
| `duration` | number | No | Seconds (model-dependent) |
| `image_url` | string/string[] | No | Reference image(s) for img2video |
| `image_file` | File (repeatable) | No | Upload reference files (form-data) |
| `veo3_mode` | string | No | `fast` or `pro` (Veo3 only) |
| `seedance_version` | string | No | `1.0-pro`, `1.5-pro`, `2.0-pro` |

### Video Models & Pricing

**Veo 3.1**
| Mode | Duration | Credits | Est. USD |
|------|----------|---------|----------|
| Fast | 8s | 150 | ~$0.19 |
| Pro | 8s | 750 | ~$0.94 |

**Seedance 1.0 Pro**
| Duration | 480p | 720p | 1080p |
|----------|------|------|-------|
| 5s | 30 | 60 | 120 |
| 10s | 60 | 100 | 200 |

**Seedance 1.5 Pro** (audio supported)
| Duration | Credits |
|----------|---------|
| 5s | 120 |
| 10s | 240 |
| 12s | 360 |

**Seedance 2.0 Pro** (audio + multi-image, up to 5)
| Duration | Credits |
|----------|---------|
| 15s | 1200 |

**Sora 2**
| Version | Resolution | 10s | 15s |
|---------|-----------|-----|-----|
| Stable | 720p | 180 | 360 |
| Standard | 1080p | 600 | 900 |

### Video Response (202)

```json
{
  "success": true,
  "data": {
    "task_id": "abc123-def456",
    "status": "pending",
    "credits_used": 150,
    "estimated_time": "2-5 minutes"
  }
}
```

### GET /api/v1/video/status?task_id=xxx

Poll until `status` is `completed`:

```json
{
  "success": true,
  "data": {
    "task_id": "abc123-def456",
    "status": "completed",
    "video_url": "https://video.nanobananas.ai/xxx.mp4",
    "progress": 100
  }
}
```

---

## Code Examples

### Python — Generate Image

```python
import requests

API_KEY = "YOUR_API_KEY"
API_URL = "https://nanobananas.ai/api/v1/images/generate"

response = requests.post(API_URL, headers={
    "Authorization": f"Bearer {API_KEY}"
}, data={
    "prompt": "A futuristic city at sunset, cyberpunk style",
    "model": "gemini-3-pro-image-preview",
    "aspectRatio": "16:9",
    "img_size": "2k"
})

result = response.json()
if result["status"] == 200:
    print(f"Image: {result['images'][0]}")
    print(f"Credits remaining: {result['credits']['remaining']}")
```

### Python — Generate Video with Polling

```python
import requests, time

API_KEY = "YOUR_API_KEY"
BASE = "https://nanobananas.ai/api/v1"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Submit
resp = requests.post(f"{BASE}/video/generate", headers=HEADERS, json={
    "prompt": "A drone flying over a mountain landscape",
    "model": "veo3",
    "veo3_mode": "fast"
})
task_id = resp.json()["data"]["task_id"]
print(f"Task submitted: {task_id}")

# Poll
while True:
    status_resp = requests.get(f"{BASE}/video/status?task_id={task_id}", headers=HEADERS)
    data = status_resp.json()["data"]
    print(f"Status: {data['status']} | Progress: {data.get('progress', 0)}%")
    if data["status"] == "completed":
        print(f"Video URL: {data['video_url']}")
        break
    elif data["status"] == "failed":
        print(f"Failed: {data.get('error')}")
        break
    time.sleep(10)
```

### Node.js — Generate Image

```javascript
const response = await fetch("https://nanobananas.ai/api/v1/images/generate", {
  method: "POST",
  headers: {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    prompt: "A beautiful watercolor painting of a Japanese garden",
    model: "gemini-3.1-pro-image-preview",
    aspectRatio: "1:1",
    img_size: "2k"
  })
});

const result = await response.json();
console.log("Image URL:", result.images[0]);
```

### cURL — Image-to-Image with File Upload

```bash
curl -X POST "https://nanobananas.ai/api/v1/images/generate" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "prompt=Transform this photo into an oil painting style" \
  -F "image=@photo.jpg" \
  -F "model=gemini-3-pro-image-preview" \
  -F "img_size=2k"
```

### cURL — Seedance Video with Reference Image

```bash
curl -X POST "https://nanobananas.ai/api/v1/video/generate" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "The woman walks gracefully along the beach at sunset",
    "model": "seedance",
    "seedance_version": "1.0-pro",
    "duration": 5,
    "resolution": "480p",
    "image_url": "https://example.com/reference.jpg"
  }'
```

### cURL — Seedance 2.0 with Multiple Files

```bash
curl -X POST "https://nanobananas.ai/api/v1/video/generate" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "prompt=Use @1 as opening scene, transition to @2 setting" \
  -F "model=seedance" \
  -F "seedance_version=2.0-pro" \
  -F "aspect_ratio=16:9" \
  -F "image_file=@scene1.jpg" \
  -F "image_file=@scene2.jpg" \
  -F "image_file=@background_music.mp3"
```

---

## Pricing Plans

| Plan | Price (USD) | Credits | Per 10 Credits |
|------|-------------|---------|----------------|
| Professional Monthly | $9.90/mo | 3,800 | $0.026 |
| Advanced Monthly | $29.90/mo | 18,000 | $0.017 |
| Professional Annual | $89.90/yr | 45,600 | $0.020 |
| Advanced Annual | $269.90/yr | 216,000 | $0.012 |
| One-Time Standard | $12.90 | 4,560 | $0.028 |
| One-Time Professional | $29.90 | 10,565 | $0.028 |
| One-Time Advanced | $69.90 | 24,700 | $0.028 |
| Large $200 | $200 | 120,000 (+20%) | $0.017 |
| Large $500 | $500 | 337,500 (+35%) | $0.015 |
| Large $1000 | $1,000 | 800,000 (+60%) | $0.013 |

> Failed tasks are never charged. Credits are refunded automatically.

---

## Error Handling

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Parse result |
| 202 | Task submitted (video) | Poll for status |
| 400 | Bad request / Prompt too long | Check parameters |
| 401 | Invalid API key | Check Authorization header |
| 402 | Insufficient credits | Top up credits |
| 403 | No API permission | Upgrade to Advanced plan |
| 429 | Rate limited | Wait and retry (check `Retry-After` header) |
| 500 | Server error | Retry after a few seconds |

---

## Rate Limits

Check response headers:
- `X-RateLimit-Limit` — Max requests per minute
- `X-RateLimit-Remaining` — Remaining requests
- `X-RateLimit-Reset` — Seconds until reset

---

## Tips

1. **Use async API for production** — `/api/v1/images/async` is more stable than sync
2. **Poll with 5-10s intervals** — Don't hammer the status endpoint
3. **Nano Banana 2 for wide/tall images** — Only model supporting `4:1`, `1:4`, `8:1`, `1:8`
4. **Seedance 1.0 Pro for budget video** — 480p 5s costs only 30 credits (~$0.04)
5. **Annual plans save 25%** — Advanced Annual is the best value at $0.012 per 10 credits
6. **Google Search enhancement** — Add `"googleSearch": "true"` with Nano Banana 2 for real-time context
