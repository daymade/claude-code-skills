---
name: youtube-downloader
description: Download YouTube videos and HLS streams (m3u8) from platforms like Mux, Vimeo, etc. using yt-dlp and ffmpeg. Use this skill when users request downloading videos, extracting audio, handling protected streams with authentication headers, or troubleshooting download issues like nsig extraction failures, 403 errors, or cookie extraction problems.
---

# YouTube Downloader

## Overview

Enable reliable video and audio downloads from YouTube and HLS streaming platforms (Mux, Vimeo, etc.) using yt-dlp and ffmpeg. This skill provides workflows for:
- YouTube downloads (up to 4K) using PO token providers or browser cookies
- HLS stream downloads with authentication headers
- Handling protected content and troubleshooting common download failures

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
- If verification is required, automatically set up a local PO Token helper (no user actions). If Docker is missing or fails, do **not** attempt to install Docker—switch to the browser-based PO Token provider instead.

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
  - If blocked by a 403, automatically set up the verification helper and retry.

## Reliable Download SOP (Internal)

Follow this SOP to avoid common failures and confusion:

1. Quote URLs in shell commands (zsh treats `?` as a glob). Example: `'https://www.youtube.com/watch?v=VIDEO_ID'`.
2. Ensure proxy is active for both yt-dlp and PO Token providers (HTTP_PROXY/HTTPS_PROXY/ALL_PROXY).
3. If you see “Sign in to confirm you’re not a bot”, request permission and use browser cookies. Do not proceed without cookies.
4. Start a PO Token provider before downloading (fail fast if it cannot start).
   - Use Docker bgutil provider when available.
   - If Docker is missing or fails, switch to browser-based WPC provider.
5. If cookies are in use, prefer the `web_safari` player client. Otherwise prefer `mweb` for PO tokens.
6. Keep the browser window open while WPC is minting tokens. Ensure Chrome can reach YouTube through the same proxy.
7. If you get “Only images are available” or “Requested format is not available”, treat it as a PO Token failure and retry after fixing token provider/browser state.
8. If you get SSL EOF or fragment errors, treat it as a proxy/network issue. Retry with progressive formats and/or a better proxy.

## Agent Execution Checklist (Internal)

- Run `scripts/download_video.py URL --info` (add `--cookies-from-browser chrome` if permission granted) to fetch metadata and thumbnail.
- If yt-dlp metadata fails, rely on the script’s oEmbed fallback for title/uploader/thumbnail and note that duration may be unavailable.
- If a thumbnail URL is present, render it in the response with Markdown image syntax.
- Ask the user to choose video vs. audio-only and (optionally) a quality preset.
- Use a friendly default save location (Downloads folder) unless the user specifies a folder.
- For subtitles, run with `--subtitles` and the requested `--sub-lang`.
- After download, report file name, size, and resolution (if video) in plain language.
- If download fails with 403/fragment errors, retry once with non-m3u8 progressive formats.
- If “Sign in to confirm you’re not a bot” appears, request cookie access and retry with cookies + `web_safari`.
- If “Only images are available” appears, treat it as PO Token failure and retry after fixing provider/browser state.
- Start the PO Token provider before downloads (`--auto-po-token` default). Fail fast if it cannot start.
- If Docker-based provider fails (common in China), automatically fall back to the browser-based WPC provider (it may briefly open a browser window).
- If the WPC provider is used, keep the browser window open until download starts. If the browser fails to launch, set the Chrome path explicitly.
- If the PO Token provider times out, restart it once and retry.
- If a system proxy is configured, pass it into the provider container. If the proxy points to 127.0.0.1/localhost, rewrite it to `host.docker.internal` for Docker.

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

If not installed or outdated (< 2025.10.22):

```bash
brew upgrade yt-dlp  # macOS
# or
pip install --upgrade yt-dlp  # Cross-platform
```

**Critical**: Outdated yt-dlp versions cause nsig extraction failures and missing formats.

### 2. Check Current Quality Access (Run this yourself)

Before downloading, check available formats:

```bash
yt-dlp -F "https://youtu.be/VIDEO_ID"
```

**If only format 18 (360p) appears**: PO token provider setup needed for high-quality access.

## High-Quality Download Workflow

### Step 1: Install PO Token Provider (One-time Setup)

For 1080p/1440p/4K access, install a PO token provider plugin into yt-dlp's Python environment:

```bash
# Find yt-dlp's Python path (interpreter used by yt-dlp)
head -1 $(which yt-dlp)

# Install plugin using the interpreter from the line above
<YTDLP_PYTHON> -m pip install bgutil-ytdlp-pot-provider
```

**Verification**: Run `yt-dlp -F "VIDEO_URL"` again. Look for formats 137 (1080p), 271 (1440p), or 313 (4K).

See `references/po-token-setup.md` for detailed setup instructions and troubleshooting.

### Step 2: Download with Best Quality

Once PO token provider is installed:

```bash
# Download best quality up to 1080p
yt-dlp -f "bestvideo[height<=1080]+bestaudio/best" "VIDEO_URL"

# Download best available quality (4K if available)
yt-dlp -f "bestvideo+bestaudio/best" "VIDEO_URL"
```

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

## Alternative: Browser Cookies Method

If PO token provider setup is problematic, use browser cookies:

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
- Do not use Android client with cookies (Android client does not support cookies).

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

### Only 360p Available (Format 18)

**Cause**: Missing PO token provider or outdated yt-dlp.

**Solution**:
1. Update yt-dlp: `brew upgrade yt-dlp`
2. Install PO token provider (see Step 1 above)
3. Or use browser cookies method

### Sign in to Confirm You’re Not a Bot

**Cause**: YouTube requires authentication to proceed.

**Solution**:
1. Request permission and use browser cookies (`--cookies-from-browser chrome`).
2. Ensure the browser and yt-dlp use the same IP/proxy.
3. Retry with `web_safari` client if needed.

### Only Images Available / Requested Format Not Available

**Cause**: PO tokens not applied or provider/browser verification failed.

**Solution**:
1. Verify PO Token provider is running before download.
2. Keep the browser window open if using WPC.
3. If cookies are in use, prefer `web_safari` client and retry.

### nsig Extraction Failed

**Symptoms**:
```
WARNING: [youtube] nsig extraction failed: Some formats may be missing
```

**Solution**:
1. Update yt-dlp to latest version
2. Install PO token provider
3. If still failing and PO tokens are disabled, use Android client: `yt-dlp --extractor-args "youtube:player_client=android" "VIDEO_URL"`

### SSL EOF / Fragment Errors

**Cause**: Proxy or network instability.

**Solution**:
1. Retry with progressive formats (non-m3u8).
2. Switch to a more stable proxy/node.
3. Avoid closing the PO token browser window during download.

### Slow Downloads or Network Errors

For users in China or behind restrictive proxies:
- Downloads may be slow due to network conditions
- Allow sufficient time for completion
- yt-dlp automatically retries on transient failures

### PO Token Warning (Harmless)

```
WARNING: android client https formats require a GVS PO Token
```

**Action**: Ignore if download succeeds. This indicates Android client has limited format access without PO tokens.

## Bundled Script Reference

### scripts/download_video.py

Use this convenience wrapper to auto-start a PO Token provider by default for high-quality downloads. Use it yourself and report results to the user without asking them to run commands.

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
- `--auto-po-token` - Auto-start PO Token provider (default; uses Docker if available, otherwise switches to browser-based provider)
- `--no-auto-po-token` - Disable auto PO Token setup
- `--proxy` - Proxy URL for yt-dlp and the PO Token provider (e.g., http://127.0.0.1:1082)
- `--wpc-browser-path` - Browser executable path for WPC provider
- `-F, --list-formats` - List available formats
- `--merge-format` - Merge output container (e.g., mp4, mkv). Default: mp4
- `--playlist` - Allow playlist downloads (default: single video only)
- `--info` - Print title/uploader/duration/thumbnail and exit
- `--no-android-client` - Disable Android client fallback

**Note**: Use the Android client only when PO tokens are disabled. Keep PO tokens enabled for high quality.

## Quality Expectations

| Setup | 360p | 720p | 1080p | 1440p | 4K |
|-------|------|------|-------|-------|-----|
| **Auto PO token (default)** | ✓ | ✓ | ✓ | ✓ | ✓ |
| Android client only | ✓ | ✗ | ✗ | ✗ | ✗ |
| PO token provider (manual) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Browser cookies | ✓ | ✓ | ✓ | ✓ | ✓ |

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
- **yt-dlp Documentation**: https://github.com/yt-dlp/yt-dlp
- **Format Selection Guide**: https://github.com/yt-dlp/yt-dlp#format-selection
