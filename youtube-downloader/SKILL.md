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

### 1. Verify yt-dlp Installation

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

### 2. Check Current Quality Access

Before downloading, check available formats:

```bash
yt-dlp -F "https://youtu.be/VIDEO_ID"
```

**If only format 18 (360p) appears**: PO token provider setup needed for high-quality access.

## High-Quality Download Workflow

### Step 1: Install PO Token Provider (One-time Setup)

For 1080p/1440p/4K access, install a PO token provider plugin into yt-dlp's Python environment:

```bash
# Find yt-dlp's Python path
head -1 $(which yt-dlp)

# Install plugin (adjust path to match yt-dlp version)
/opt/homebrew/Cellar/yt-dlp/$(yt-dlp --version)/libexec/bin/python -m pip install bgutil-ytdlp-pot-provider
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
**Requirement**: Must be logged into YouTube in the specified browser.

## Common Tasks

### Audio-Only Download

Extract audio as MP3:

```bash
yt-dlp -x --audio-format mp3 "VIDEO_URL"
```

### Custom Output Directory

```bash
yt-dlp -P ~/Downloads/YouTube "VIDEO_URL"
```

### Download with Subtitles

```bash
yt-dlp --write-subs --sub-lang en "VIDEO_URL"
```

### Playlist Download

```bash
yt-dlp -f "bestvideo[height<=1080]+bestaudio/best" "PLAYLIST_URL"
```

### Convert WebM to MP4

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

### nsig Extraction Failed

**Symptoms**:
```
WARNING: [youtube] nsig extraction failed: Some formats may be missing
```

**Solution**:
1. Update yt-dlp to latest version
2. Install PO token provider
3. If still failing, use Android client: `yt-dlp --extractor-args "youtube:player_client=android" "VIDEO_URL"`

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

A convenience wrapper that applies Android client workaround by default:

**Basic usage:**
```bash
scripts/download_video.py "VIDEO_URL"
```

**Arguments:**
- `url` - YouTube video URL (required)
- `-o, --output-dir` - Output directory
- `-f, --format` - Format specification
- `-a, --audio-only` - Extract audio as MP3
- `-F, --list-formats` - List available formats
- `--no-android-client` - Disable Android client workaround

**Note**: This script uses Android client (360p only without PO tokens). For high quality, use yt-dlp directly with PO token provider.

## Quality Expectations

| Setup | 360p | 720p | 1080p | 1440p | 4K |
|-------|------|------|-------|-------|-----|
| No setup (default) | ✗ | ✗ | ✗ | ✗ | ✗ |
| Android client only | ✓ | ✗ | ✗ | ✗ | ✗ |
| **PO token provider** | ✓ | ✓ | ✓ | ✓ | ✓ |
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
