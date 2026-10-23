---
name: youtube-downloader
description: >-
  Fetch existing YouTube transcripts/subtitles or archive spoken video content as text,
  and download YouTube videos/audio or HLS streams (m3u8) with yt-dlp and ffmpeg.
  Use for transcript/subtitle retrieval, text-first video archiving, video/audio downloads,
  protected streams with authentication headers, and download failures including nsig,
  403 or browser-cookie issues.
---

# YouTube Downloader

## Overview

Enable reliable video and audio downloads from YouTube and HLS streaming platforms (Mux, Vimeo, etc.) using yt-dlp and ffmpeg. This skill provides workflows for:
- YouTube downloads at available quality, with optional PO token and authorized cookie recovery
- HLS stream downloads with authentication headers
- Handling protected content and troubleshooting common download failures

## Goal Split: File vs. Text (Read First)

Before downloading anything, classify the request:

- **User wants the video/audio file itself** (save it, edit it, watch offline) → continue with the download flow below, unchanged.
- **User wants the spoken content as text** (transcript, subtitles, meeting notes, archive, "what was said") → follow `references/text-first.md` FIRST: existing archived transcripts → platform transcript APIs → yt-dlp subtitle-only → authorized audio track + ASR. Do not download the full video just to obtain text.

The text-first route never blocks a file request: when the user wants the file, download it with the unchanged flow below.

## Non-Technical User Experience (Default)

Assume the user is non-technical. Do not ask them to run commands. Execute everything yourself and report progress in plain language. Avoid mentioning tooling unless the user asks.

**Default flow:**
1. Ask for the URL (if not provided).
2. Fetch video metadata (title/uploader/duration/thumbnail) and confirm it matches the user's intent.
   - If yt-dlp is blocked by “confirm you’re not a bot”, fall back to YouTube oEmbed for title/uploader/thumbnail (duration may be unknown).
3. Offer simple choices (video vs. audio-only, quality, subtitles, save location).
4. Proceed with sensible defaults if the user does not specify:
   - Video download at best quality
   - MP4 merged output
   - Single video only (no playlists)
5. Download and report the final file path, file size, and resolution (if video).

**Offer choices in user-friendly terms:**
- “Download the video in best quality (default)”
- “Download audio only (MP3)”
- “Pick a quality: 1080p / 720p / 480p / 360p”
- “Include subtitles (if available)”
- “Save to the Downloads folder (default) or tell me another folder”

**Always render the thumbnail when available:**
- If metadata includes a thumbnail URL, include it using Markdown image syntax: `![Thumbnail](URL)`.

**Ask before doing extra work:**
- Confirm playlist downloads (can be large).
- Confirm installing/upgrading dependencies if missing.
- Ask before extracting browser cookies.
- If using cookies, never mention cookie counts or raw cookie details in user-facing responses. Say “used your Chrome login session”.
- Set up a PO Token helper only after an explicit token diagnostic or a user request, and within existing installation/service authorization. If that authorization is already present, execute the recovery and resume the download. Otherwise request only the missing permission. Do not install Docker as a fallback; use the authorized browser provider when appropriate.

**Legal/Safety reminder (brief):**
- Proceed only if the user has the rights or permission to download the content.

**Response template (use plain language, no commands):**
```
![Thumbnail](THUMBNAIL_URL)

Title: …
Channel: …
Duration: …

I can help you:
1) Download the video (best quality, MP4)
2) Download audio only (MP3)
3) Pick a specific quality (1080p/720p/480p/360p)
4) Include subtitles (if available)

Where should I save it? (Default: Downloads folder)
```

**If the user says “just download”:**
- Proceed with defaults and confirm when the download finishes.
  - If blocked, classify the actual diagnostic using the SOP below and execute the applicable authorized recovery.

## Reliable Download SOP (Internal)

Read [the download SOP](references/internal-sop.md) before retrying a failure. Start with the current yt-dlp default clients and the existing network configuration. Do not require a provider, switch to Android, or extract browser cookies merely to begin a download.

## Agent Execution Checklist (Internal)

- Run `scripts/download_video.py URL --info` for metadata. It never starts a provider; its oEmbed fallback supplies limited fields when extraction fails.
- Render the thumbnail when available. Use the requested file/audio, quality, subtitles and save location; proceed with defaults when already specified or implied.
- Run the ordinary download first. With an installed Node runtime, pass `--js-runtimes node` when yt-dlp needs it; runtime installation still follows dependency authorization.
- On failure, read the actual error and `-F` output. An absent requested format, images-only output, 403 or low resolution alone does not establish a token problem.
- If a failed request explicitly reports a missing/required PO Token, read [provider setup](references/po-token-setup.md). Within existing setup authorization, execute `--auto-po-token` and finish the original download; do not stop at giving the user a command. This option attempts the native route first, then permits a bounded provider retry and WPC recovery.
- Request browser-cookie permission before supplying either cookie option. Preserve the authorized cookie session and a compatible client throughout retries.
- For an isolated 403/fragment failure, the wrapper can retry a quality preset once with progressive formats. Verify the resulting resolution; the fallback may be lower quality. Custom formats and audio-only requests keep their explicit selection.
- Verify the final file with `ffprobe` and report its path, size and actual resolution or audio properties. Provider health or a format listing alone is not a completed download.

## When to Use This Skill

This skill should be invoked when users:
- Request downloading YouTube videos or playlists
- Want to extract audio from YouTube videos
- Experience yt-dlp download failures or limited format availability
- Need help with format selection or quality options
- Report only low-quality (360p) formats available
- Ask about downloading YouTube content in specific quality (1080p, 4K, etc.)
- Need to convert downloaded WebM videos to MP4 format for wider compatibility
- Request downloading HLS streams (m3u8) from platforms like Mux, Vimeo, or other streaming services
- Need to download protected streams that require authentication headers

## Prerequisites

### 1. Verify yt-dlp Installation (Run this yourself)

```bash
which yt-dlp
yt-dlp --version
```

If missing or a current extraction diagnostic requires an update, obtain any missing install/upgrade authorization, then use the existing installation owner:

```bash
brew upgrade yt-dlp  # macOS
# or
pip install --upgrade yt-dlp  # Cross-platform
```

Check the current [EJS setup guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS) for the JavaScript runtime and challenge-solver requirements of the installed distribution. An installed Node binary may need explicit `--js-runtimes node`; do not treat an EJS/nsig failure as a PO Token failure.

### 2. Check Current Quality Access (Run this yourself)

Before downloading, check available formats:

```bash
yt-dlp -F "https://youtu.be/VIDEO_ID"
```

Compare the listed media streams with the requested quality. If only a low-resolution format appears, inspect extraction/runtime warnings and the source availability before choosing recovery.

## High-Quality Download Workflow

### Step 1: Try the Native Client Selection

Keep `player_client` unset unless there is a specific diagnostic or explicit request. The [official extractor guide](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#youtube) describes yt-dlp's default attempt with clients that do not require tokens. Available formats depend on the video, account, client, network and current YouTube enforcement.

### Step 2: Download and Escalate Only When Needed

```bash
# Download best quality up to 1080p
scripts/download_video.py "VIDEO_URL" --quality 1080p

# Download best available quality
scripts/download_video.py "VIDEO_URL"

# After an explicit token requirement, with setup already authorized
scripts/download_video.py "VIDEO_URL" --auto-po-token
```

For installation and provider-specific recovery, load [PO Token setup](references/po-token-setup.md). Do not infer a provider requirement from resolution alone.

### Step 3: Verify Download Quality

```bash
# Check video resolution
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,codec_name -of default=noprint_wrappers=1 video.mp4
```

Expected output for 1080p:
```
codec_name=vp9
width=1920
height=1080
```

## Authorized Browser Cookies Method

Use cookies when the content requires the authorized account or a bot check persists, after cookie permission is granted. Cookies authenticate a session; they do not replace a missing PO Token:

```bash
# Firefox
yt-dlp --cookies-from-browser firefox -f "bestvideo[height<=1080]+bestaudio/best" "VIDEO_URL"

# Chrome
yt-dlp --cookies-from-browser chrome -f "bestvideo[height<=1080]+bestaudio/best" "VIDEO_URL"
```

**Benefits**: Access to age-restricted and members-only content.
**Requirements**:
- Must be logged into YouTube in the specified browser.
- Browser and yt-dlp must use the same IP/proxy.
- Preserve yt-dlp's default cookie-compatible clients; use `web_safari` only as a targeted retry. Do not combine account cookies with Android/iOS clients that do not support them.

## Common Tasks

### Audio-Only Download (Run this yourself)

Extract audio as MP3:

```bash
yt-dlp -x --audio-format mp3 "VIDEO_URL"
```

### Custom Output Directory (Run this yourself)

```bash
yt-dlp -P ~/Downloads/YouTube "VIDEO_URL"
```

### Download with Subtitles (Run this yourself)

```bash
yt-dlp --write-subs --sub-lang en "VIDEO_URL"
```

### Playlist Download (Run this yourself)

```bash
yt-dlp -f "bestvideo[height<=1080]+bestaudio/best" "PLAYLIST_URL"
```

### Convert WebM to MP4 (Run this yourself)

YouTube high-quality downloads often use WebM format (VP9 codec). Convert to MP4 for wider compatibility:

```bash
# Check if ffmpeg is installed
which ffmpeg || brew install ffmpeg  # macOS

# Convert WebM to MP4 with good quality settings
ffmpeg -i "video.webm" -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k "video.mp4"
```

**Parameters explained:**
- `-c:v libx264`: Use H.264 video codec (widely compatible)
- `-preset medium`: Balance between encoding speed and file size
- `-crf 23`: Constant Rate Factor for quality (18-28 range, lower = better quality)
- `-c:a aac`: Use AAC audio codec
- `-b:a 128k`: Audio bitrate 128 kbps

**Tip**: Conversion maintains 1080p resolution and provides ~6x encoding speed on modern hardware.

## Troubleshooting Quick Reference

### Missing Quality / Only Images / Requested Format Not Available

Inspect `-F`, the selected format expression, current yt-dlp/EJS/runtime warnings and source availability. These messages have multiple causes. Enter provider setup only when a failed extraction or media request also names a missing/required PO Token. Do not install a provider because a requested height or format ID is absent.

### Sign in to Confirm You’re Not a Bot

Check that the intended proxy/network is in use. If the challenge persists and cookies are needed, obtain cookie authorization, retain that session, and retry. Stop with the exact authorization gap if it is unavailable; do not silently read browser cookies.

### nsig / JavaScript Challenge Failure

Check the installed yt-dlp version and the [EJS runtime and solver instructions](https://github.com/yt-dlp/yt-dlp/wiki/EJS). Repair the diagnosed prerequisite within authorization. Android or AndroidVR can be selected explicitly for a bounded diagnostic, but neither is the default recovery or a guaranteed solution.

### 403 / SSL EOF / Fragment Errors

Distinguish a media 403 from TLS, timeout, proxy and provider-health errors. A generic 403 does not prove a Token requirement. Check the network path first for SSL/timeout failures; retry only after a relevant change. The wrapper's single progressive retry applies to 403/fragment failures with quality presets, and may reduce quality.

### Slow Downloads or Network Errors

For users in China or behind restrictive proxies:
- Downloads may be slow due to network conditions
- Allow sufficient time for completion
- yt-dlp automatically retries on transient failures

### PO Token Warning (Harmless)

```
WARNING: android client https formats require a GVS PO Token
```

**Action**: A successful, verified download needs no repair for an unused-client warning. On failure, read the full diagnostic and actual formats before choosing a token branch.

## Bundled Script Reference

### scripts/download_video.py

Use this wrapper for native-client downloads and bounded diagnostic recovery. It does not install/start providers or read cookies by default. Execute it yourself and report the verified file.

**Basic usage:**
```bash
scripts/download_video.py "VIDEO_URL"
```

**Arguments:**
- `url` - YouTube video URL (required)
- `-o, --output-dir` - Output directory
- `--output-template` - Output filename template (yt-dlp syntax)
- `-f, --format` - Format specification
- `-q, --quality` - Quality preset (best, 1080p, 720p, 480p, 360p, worst). Default: best (skipped for `--audio-only`)
- `-a, --audio-only` - Extract audio as MP3
- `--subtitles` - Download subtitles if available
- `--sub-lang` - Subtitle languages (comma-separated, default: en)
- `--cookies-from-browser` - Load cookies from a browser (e.g., chrome, firefox)
- `--cookies-file` - Load cookies from a cookies.txt file
- `--player-client` - Use a specific YouTube player client (e.g., web_safari)
- `--auto-po-token` - Authorize provider setup after a failed explicit missing/required-token diagnostic; try native clients first, then Docker bgutil or browser WPC
- `--no-auto-po-token` - Disable provider setup (default); does not disable already-installed yt-dlp plugins
- `--proxy` - Proxy URL for yt-dlp and the PO Token provider (e.g., http://127.0.0.1:1082)
- `--wpc-browser-path` - Browser executable path for WPC provider
- `-F, --list-formats` - List available formats
- `--merge-format` - Merge output container (e.g., mp4, mkv). Default: mp4
- `--playlist` - Allow playlist downloads (default: single video only)
- `--info` - Print title/uploader/duration/thumbnail and exit
- `--no-android-client` - Retained compatibility option; the wrapper already leaves native client selection unchanged
- `--js-runtimes` - Pass an installed runtime to yt-dlp, e.g. `node` or `node:/path/to/node`

## Quality Expectations

Do not promise a resolution based on a provider/client/cookie combination. Request the desired quality, inspect available formats, and verify the actual downloaded file. A successful high-resolution download without new provider setup proves only that input and environment; installed plugins or configuration may still contribute. A provider cannot create a resolution absent from the source.

## HLS Stream Downloads (m3u8)

For streaming platforms like Mux, Vimeo, and other HLS-based services, use ffmpeg as the primary tool. These streams often require authentication headers that yt-dlp may not handle correctly.

### Identifying HLS Streams

HLS streams use `.m3u8` playlist files:
- Master playlist: Lists multiple quality options
- Rendition playlist: Contains actual video/audio segment URLs

### Download Workflow

#### Step 1: Obtain the Stream URL

Get the m3u8 URL from the video source. For protected streams:
1. Open browser DevTools → Network tab
2. Play the video
3. Filter for "m3u8" to find the playlist URLs
4. Copy the rendition URL (usually contains quality info like "rendition.m3u8")

#### Step 2: Identify Required Headers

Many CDNs require authentication headers:
- **Referer**: Origin website (e.g., `https://maven.com/`)
- **Origin**: Same as Referer for CORS
- **User-Agent**: Browser identification

Check the Network tab to see which headers the browser sends.

#### Step 3: Download with ffmpeg

Use ffmpeg with the `-headers` flag for protected streams:

```bash
ffmpeg -headers "Referer: https://example.com/" \
  -protocol_whitelist file,http,https,tcp,tls,crypto,httpproxy \
  -i "https://cdn.example.com/path/rendition.m3u8?params" \
  -c copy -bsf:a aac_adtstoasc \
  output.mp4
```

**Key parameters:**
- `-headers`: Set HTTP headers (critical for authentication)
- `-protocol_whitelist`: Enable required protocols for HLS
- `-c copy`: Stream copy (no re-encoding, faster)
- `-bsf:a aac_adtstoasc`: Fix AAC audio compatibility

**Common header patterns:**
```bash
# Single header
-headers "Referer: https://example.com/"

# Multiple headers
-headers "Referer: https://example.com/" \
-headers "User-Agent: Mozilla/5.0..."

# Alternative syntax
-headers $'Referer: https://example.com/\r\nUser-Agent: Mozilla/5.0...'
```

### Handling Separate Audio/Video Streams

Some platforms (like Mux) deliver audio and video separately:

1. **Download audio stream:**
```bash
ffmpeg -headers "Referer: https://example.com/" \
  -protocol_whitelist file,http,https,tcp,tls,crypto,httpproxy \
  -i "https://cdn.example.com/audio/rendition.m3u8" \
  -c copy audio.m4a
```

2. **Download video stream:**
```bash
ffmpeg -headers "Referer: https://example.com/" \
  -protocol_whitelist file,http,https,tcp,tls,crypto,httpproxy \
  -i "https://cdn.example.com/video/rendition.m3u8" \
  -c copy video.mp4
```

3. **Merge streams:**
```bash
ffmpeg -i video.mp4 -i audio.m4a -c copy merged.mp4
```

### Troubleshooting HLS Downloads

#### 403 Forbidden Errors

**Cause**: Missing or incorrect authentication headers.

**Solution**:
1. Verify Referer header matches the video source website
2. Check if additional headers (Origin, User-Agent) are needed
3. Ensure the m3u8 URL includes all query parameters from browser

#### yt-dlp Stuck on Cookie Extraction

**Symptom**: `Extracting cookies from chrome` hangs indefinitely.

**Solution**: Use ffmpeg directly instead of yt-dlp for HLS streams.

#### Protocol Not Whitelisted

**Error**: `Protocol 'https' not on whitelist 'file,crypto,data'`

**Solution**: Add `-protocol_whitelist file,http,https,tcp,tls,crypto,httpproxy`

#### Empty Segments or No Streams

**Cause**: Expired signatures in the m3u8 URLs.

**Solution**:
1. Get fresh URLs from browser DevTools
2. Download immediately after obtaining URLs
3. Look for rendition URLs with updated signature parameters

### Performance Tips

- HLS downloads typically run at 10-15x realtime speed
- No re-encoding with `-c copy` (fastest)
- Monitor download with real-time progress display
- Use absolute output paths to avoid directory confusion

## Further Reading

- **PO Token Setup**: See `references/po-token-setup.md` for detailed installation and troubleshooting
- **Internal SOP**: `references/internal-sop.md` — the short list of yt-dlp failures that look like something else (URLs unquoted in zsh, proxy not reaching the PO Token provider). Read it first when a download fails for no obvious reason
- **yt-dlp Documentation**: https://github.com/yt-dlp/yt-dlp
- **Format Selection Guide**: https://github.com/yt-dlp/yt-dlp#format-selection

## Next Step: Text From the Video

Two situations, two routes:

- **The user's goal is text and nothing has been downloaded yet**: do not download the video just to get text — follow the text-first ladder in `references/text-first.md` (existing archived transcripts → platform transcript APIs → yt-dlp subtitle-only → authorized audio track + ASR).
- **The user already has the downloaded file and now also wants text**: still check existing transcripts and original subtitles using its known source identity. If those checks yield no usable text, reuse the local file at level L4 without another download. Proactively suggest:

```
Download complete: [filename]

If you need the spoken content as text, I can transcribe it for you.

Options:
A) Transcribe with /daymade-audio:asr-transcribe-to-text (Recommended for speech-to-text)
B) No thanks — I just needed the video file
```
