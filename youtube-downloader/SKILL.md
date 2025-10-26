---
name: youtube-downloader
description: Download YouTube videos and audio using yt-dlp with robust error handling. Use this skill when users request downloading YouTube videos, extracting audio from YouTube, or need help with yt-dlp download issues like nsig extraction failures or network problems.
---

# YouTube Downloader

## Overview

Enable reliable YouTube video and audio downloads using yt-dlp with built-in workarounds for common issues like nsig extraction failures and network problems. Particularly useful for users behind proxies or in regions with YouTube access restrictions.

## When to Use This Skill

This skill should be invoked when users:
- Request downloading YouTube videos or playlists
- Want to extract audio from YouTube videos
- Experience yt-dlp download failures or nsig extraction errors
- Need help with format selection or quality options
- Ask about downloading from YouTube with specific requirements (resolution, format, etc.)

## Prerequisites

Verify yt-dlp is installed before proceeding:

```bash
which yt-dlp
```

If not installed, install via:

```bash
brew install yt-dlp  # macOS
# or
pip install yt-dlp  # Cross-platform
```

## Quick Start

### Basic Video Download

For simple video downloads, use the bundled `scripts/download_video.py`:

```bash
scripts/download_video.py "https://youtu.be/VIDEO_ID"
```

This automatically applies the Android client workaround to avoid nsig extraction issues.

### Audio-Only Download

To extract audio as MP3:

```bash
scripts/download_video.py "https://youtu.be/VIDEO_ID" --audio-only
```

### Custom Output Directory

Specify where to save downloads:

```bash
scripts/download_video.py "https://youtu.be/VIDEO_ID" -o ~/Downloads/YouTube
```

## Common Tasks

### 1. List Available Formats

Before downloading, check available video/audio formats:

```bash
scripts/download_video.py "https://youtu.be/VIDEO_ID" --list-formats
```

Or use yt-dlp directly:

```bash
yt-dlp -F "https://youtu.be/VIDEO_ID"
```

### 2. Download Specific Format

After identifying format codes from the list:

```bash
scripts/download_video.py "https://youtu.be/VIDEO_ID" -f "bestvideo+bestaudio"
```

Common format specifications:
- `bestvideo+bestaudio/best` - Best quality video and audio
- `bestvideo[height<=1080]+bestaudio` - Max 1080p video
- `bestaudio` - Audio only (best quality)
- `18` - Format code 18 (typically 360p MP4)

### 3. Download Playlist

Use yt-dlp directly for playlists:

```bash
yt-dlp --extractor-args "youtube:player_client=android" "PLAYLIST_URL"
```

### 4. Download with Subtitles

Include subtitles in the download:

```bash
yt-dlp --extractor-args "youtube:player_client=android" --write-subs --sub-lang en "VIDEO_URL"
```

## Troubleshooting

### nsig Extraction Failed

**Symptoms:**
```
WARNING: [youtube] nsig extraction failed: Some formats may be missing
ERROR: Requested format is not available
```

**Solution:**
Use the Android client workaround (automatically applied by `scripts/download_video.py`):

```bash
yt-dlp --extractor-args "youtube:player_client=android" "VIDEO_URL"
```

This is a YouTube-specific issue where the default web client fails to extract signature parameters. The Android client bypasses this restriction.

### GVS PO Token Warning

**Symptoms:**
```
WARNING: android client https formats require a GVS PO Token
```

**Impact:**
This warning can be ignored for most use cases. The download will still succeed using available formats. Only some high-quality formats may be skipped.

**Solution (if needed):**
For advanced users requiring all formats, see: https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide

### Network Issues in China or Behind Proxies

Downloads may experience intermittent connectivity. The script handles this automatically by retrying, but slower speeds are expected due to network conditions. Allow sufficient time for completion.

## Script Reference

### scripts/download_video.py

A Python wrapper around yt-dlp that applies best practices by default:
- Uses Android client workaround automatically
- Creates output directories if needed
- Provides clear success/failure feedback
- Supports common download scenarios

**Arguments:**
- `url` - YouTube video URL (required)
- `-o, --output-dir` - Output directory (default: current directory)
- `-f, --format` - Format specification
- `--no-android-client` - Disable Android client workaround
- `-a, --audio-only` - Download audio only (as MP3)
- `-F, --list-formats` - List available formats

**Example usage:**
```bash
# Basic download
scripts/download_video.py "https://youtu.be/VIDEO_ID"

# Audio only to specific directory
scripts/download_video.py "https://youtu.be/VIDEO_ID" -o ~/Music --audio-only

# Custom format
scripts/download_video.py "https://youtu.be/VIDEO_ID" -f "bestvideo[height<=720]+bestaudio"
```
