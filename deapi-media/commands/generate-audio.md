---
name: generate-audio
description: Convert text to speech using 54+ AI voices in 8 languages
argument-hint: <text> [--voice af_bella]
---

# Text-to-Speech via deAPI

Generate audio from text: **$ARGUMENTS**

## Step 1: Parse arguments

Extract from `$ARGUMENTS`:
- `text`: The text to convert to speech (required)
- `--voice`: Voice ID (default: `af_bella`)

**54+ voices in 8 languages.** Voice ID format: `{lang}{gender}_{name}`
- Lang: `a`=American, `b`=British, `j`=Japanese, `z`=Chinese, `e`=Spanish, `f`=French, `h`=Hindi, `i`=Italian, `p`=Portuguese
- Gender: `f`=female, `m`=male

**Popular voices:**
| Voice ID | Language | Description |
|----------|----------|-------------|
| `af_bella` | American EN | Warm, friendly (best quality) |
| `af_heart` | American EN | Expressive, emotional |
| `af_nicole` | American EN | Professional |
| `af_sarah` | American EN | Casual |
| `am_adam` | American EN | Deep, authoritative |
| `am_michael` | American EN | Energetic |
| `bf_emma` | British EN | Elegant (best British) |
| `bf_isabella` | British EN | Refined |
| `bm_george` | British EN | Sophisticated |
| `jf_alpha` | Japanese | Natural Japanese female |
| `zf_xiaobei` | Chinese | Mandarin female |
| `ef_dora` | Spanish | Spanish female |
| `ff_siwis` | French | French female (best quality) |
| `hf_alpha` | Hindi | Hindi female |
| `if_sara` | Italian | Italian female |
| `pf_dora` | Portuguese | Brazilian Portuguese female |

Full list: [Kokoro VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)

## Step 2: Send request

```bash
curl -s -X POST "https://api.deapi.ai/api/v1/client/txt2audio" \
  -H "Authorization: Bearer $DEAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "{text}",
    "voice": "{voice}",
    "model": "Kokoro",
    "lang": "{lang_code}",
    "speed": 1.0,
    "format": "mp3",
    "sample_rate": 24000
  }'
```

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `lang` | auto from voice | Language code: `en-us`, `en-gb`, `ja`, `zh`, `es`, `fr`, `hi`, `it`, `pt-br` |
| `speed` | `1.0` | Speech speed (0.5-2.0) |
| `format` | `mp3` | Output format: `mp3`, `wav`, `flac`, `ogg` |
| `sample_rate` | `24000` | Sample rate: `22050`, `24000`, `44100`, `48000` |

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
1. Get audio URL from `result_url`
2. Provide download link to user
3. Show audio duration if available

## Step 5: Offer follow-up

Ask user:
- "Would you like to try a different voice?"
- "Should I generate this in another language?"
- "Would you like to adjust the text?"

## Error handling

| Error | Action |
|-------|--------|
| 401 Unauthorized | Check if `$DEAPI_API_KEY` is set correctly |
| 429 Rate Limited | Wait 60s and retry |
| 500 Server Error | Wait 30s and retry once |
| Empty text | Ask user to provide text to convert |
| Invalid voice | Show available voices, ask user to choose |
| Text too long | Suggest splitting into smaller segments |
