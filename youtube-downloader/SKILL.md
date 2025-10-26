---
name: youtube-downloader
description: Download YouTube videos and audio using yt-dlp with robust error handling. Use this skill when users request downloading YouTube videos, extracting audio from YouTube, or need help with yt-dlp download issues like nsig extraction failures or network problems.
---

# YouTube Downloader

## Overview

Enable reliable YouTube video and audio downloads using yt-dlp with built-in workarounds for common issues like nsig extraction failures and network problems. This skill provides workflows for obtaining high-quality downloads (up to 4K) using PO token providers or browser cookies.

## When to Use This Skill

This skill should be invoked when users:
- Request downloading YouTube videos or playlists
- Want to extract audio from YouTube videos
- Experience yt-dlp download failures or limited format availability
- Need help with format selection or quality options
- Report only low-quality (360p) formats available
- Ask about downloading YouTube content in specific quality (1080p, 4K, etc.)
- Need to convert downloaded WebM videos to MP4 format for wider compatibility

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

## Further Reading

- **PO Token Setup**: See `references/po-token-setup.md` for detailed installation and troubleshooting
- **yt-dlp Documentation**: https://github.com/yt-dlp/yt-dlp
- **Format Selection Guide**: https://github.com/yt-dlp/yt-dlp#format-selection
