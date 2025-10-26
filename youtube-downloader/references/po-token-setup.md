# PO Token Setup Guide

## What are PO Tokens?

Proof of Origin (PO) Tokens are cryptographic attestations required by YouTube for certain clients and request types. Without them, requests for affected format URLs may return HTTP Error 403 or result in restricted format access.

## Why PO Tokens Matter

As of late 2024/early 2025, YouTube increasingly requires PO tokens for high-quality video formats (1080p, 1440p, 4K). Without PO token support:

- **Android client**: Only 360p available (format 18)
- **Web client**: nsig extraction failures, missing formats
- **iOS client**: Similar restrictions

With PO token provider: **Full access** to all quality levels including 4K.

## Recommended Solution: PO Token Provider Plugin

### Installation

Install a PO token provider plugin to handle token generation automatically. The plugin must be installed into yt-dlp's own Python environment.

**Step 1: Locate yt-dlp's Python**

```bash
head -1 $(which yt-dlp)
# Output example: #!/opt/homebrew/Cellar/yt-dlp/2025.10.22/libexec/bin/python
```

**Step 2: Install Plugin**

```bash
# For Homebrew-installed yt-dlp (macOS)
/opt/homebrew/Cellar/yt-dlp/$(yt-dlp --version)/libexec/bin/python -m pip install bgutil-ytdlp-pot-provider

# For pip-installed yt-dlp
python3 -m pip install bgutil-ytdlp-pot-provider --user
```

**Step 3: Verify Installation**

```bash
yt-dlp -F "https://youtu.be/VIDEO_ID"
```

Look for high-quality formats (137, 248, 271, 313) in the output. If present, the plugin is working.

## Available PO Token Provider Plugins

### 1. bgutil-ytdlp-pot-provider (Recommended)

- **Installation**: `pip install bgutil-ytdlp-pot-provider`
- **Requires**: yt-dlp 2025.05.22 or above
- **Automatic**: Works transparently once installed
- **Best for**: General use, most reliable

### 2. yt-dlp-get-pot

- **Installation**: `pip install yt-dlp-get-pot`
- **Requires**: yt-dlp 2025.01.15 or above
- **Method**: Launches browser to mint tokens
- **Best for**: Users comfortable with browser automation

### 3. yt-dlp-get-pot-rustypipe

- **Installation**: `pip install yt-dlp-get-pot-rustypipe`
- **Method**: Uses rustypipe-botguard
- **Supports**: All web-based YouTube clients
- **Best for**: Advanced users, specific client requirements

## Verification Workflow

### Check Available Formats

```bash
yt-dlp -F "https://youtu.be/VIDEO_ID"
```

**Without PO token provider:**
```
ID  EXT   RESOLUTION
18  mp4   640x360     # Only low quality
```

**With PO token provider:**
```
ID  EXT   RESOLUTION
137 mp4   1920x1080   # 1080p available
248 webm  1920x1080
271 webm  2560x1440   # 1440p available
313 webm  3840x2160   # 4K available
```

### Download Best Quality

```bash
# 1080p max
yt-dlp -f "bestvideo[height<=1080]+bestaudio/best" "VIDEO_URL"

# Best available (4K if available)
yt-dlp -f "bestvideo+bestaudio/best" "VIDEO_URL"
```

### Verify Downloaded Quality

```bash
# Check resolution
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of default=noprint_wrappers=1 video.mp4
```

## Troubleshooting

### Plugin Not Working

**Symptom**: Still only seeing format 18 after plugin installation

**Solution**:
1. Verify yt-dlp version: `yt-dlp --version` (need 2025.05.22+)
2. Check plugin installation: `pip list | grep bgutil`
3. Ensure plugin installed in correct Python environment
4. Try reinstalling: `pip uninstall bgutil-ytdlp-pot-provider && pip install bgutil-ytdlp-pot-provider`

### Warning Messages

```
WARNING: [youtube] [pot:bgutil:http] Error reaching GET http://127.0.0.1:4416/ping
```

**Impact**: This warning is usually harmless if formats are available. The plugin uses HTTP as fallback.

**Action**: No action needed if download succeeds with high-quality formats.

## Alternative: Browser Cookies Method

If PO token providers don't work, use browser cookies for authentication:

```bash
# Firefox
yt-dlp --cookies-from-browser firefox "VIDEO_URL"

# Chrome
yt-dlp --cookies-from-browser chrome "VIDEO_URL"
```

**Benefits**:
- Access age-restricted content
- Access members-only content
- Better quality selection

**Requirements**:
- Must be logged into YouTube in the browser
- Browser and yt-dlp must use same IP address

## Quality Comparison

| Method | 360p | 720p | 1080p | 1440p | 4K |
|--------|------|------|-------|-------|-----|
| Default (no workaround) | ✗ | ✗ | ✗ | ✗ | ✗ |
| Android client only | ✓ | ✗ | ✗ | ✗ | ✗ |
| PO token provider | ✓ | ✓ | ✓ | ✓ | ✓ |
| Browser cookies | ✓ | ✓ | ✓ | ✓ | ✓ |

## References

- [yt-dlp PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)
- [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
- [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp)
