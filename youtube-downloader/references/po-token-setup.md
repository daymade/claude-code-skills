# PO Token Setup Guide

## What are PO Tokens?

Proof of Origin (PO) Tokens are cryptographic attestations required by YouTube for certain clients and request types. Without them, requests for affected format URLs may return HTTP Error 403 or result in restricted format access.

## When to Enter This Branch

Start with yt-dlp's default clients. Use this guide when the failed extraction or media request explicitly identifies a missing/required PO Token, or the user explicitly requests provider setup. A 403, unavailable format, images-only result or requested 1080p/4K quality alone is insufficient.

Check the current [extractor guidance](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#youtube), [Token enforcement by client/request type](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide#current-po-token-enforcement) and [EJS setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS). Treat JavaScript challenge/runtime failures separately from token failures. Do not assume a provider grants every source quality.

## Operational SOP (Internal)

Follow [the download SOP](internal-sop.md) for diagnosis, authorization and file acceptance. Within an already-authorized setup branch, run the preparation and resume the original download yourself. Otherwise obtain only the missing installation/service permission. Cookie extraction requires its own authorization.

For a failed explicit token requirement, the wrapper's `--auto-po-token` option permits provider setup and a token-assisted retry after its native attempt. `--info` and `-F` never start the helper. Direct provider setup below remains available for an explicit setup request.

Use `mweb` with web tokens for a targeted non-cookie retry; preserve compatible cookie clients (the wrapper uses `web_safari`) when authorized cookies are present. Web tokens are not Android/iOS tokens. Keep a WPC browser window open while it mints tokens. Preserve shared providers on health failure rather than deleting/restarting them automatically.

### Authorized Provider Setup

After setup is authorized, reuse a healthy installed provider. If a new Docker provider is needed and Docker is already available:

1. Install the plugin into yt-dlp's Python environment (one-time):
```bash
<YTDLP_PYTHON> -m pip install bgutil-ytdlp-pot-provider
```
In China, prefer a local PyPI mirror:
```bash
<YTDLP_PYTHON> -m pip install bgutil-ytdlp-pot-provider -i https://pypi.tuna.tsinghua.edu.cn/simple
```

2. Start the provider (Docker):
```bash
docker run -d --name bgutil-pot-provider -p 4416:4416 --init brainicism/bgutil-ytdlp-pot-provider
```

3. Retry yt-dlp downloads using a web client (e.g., `mweb`) so PO tokens apply.

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
<YTDLP_PYTHON> -m pip install bgutil-ytdlp-pot-provider

# For pip-installed yt-dlp
python3 -m pip install bgutil-ytdlp-pot-provider --user
```

**Step 3: Verify Installation**

```bash
yt-dlp -F "https://youtu.be/VIDEO_ID"
```

Inspect verbose yt-dlp output for the selected provider and successful token acquisition. Then download the requested format and verify the file. Format availability alone does not prove which provider supplied it.

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

### 3. yt-dlp-getpot-wpc (Browser-based, no Docker)

- **Installation**: `pip install yt-dlp-getpot-wpc`
- **Requires**: yt-dlp 2025.09.26 or above
- **Method**: Uses a browser window to mint tokens
- **Best for**: Environments without Docker or restricted networks

In China, prefer a local PyPI mirror:
```bash
pip install yt-dlp-getpot-wpc -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 4. yt-dlp-get-pot-rustypipe

- **Installation**: `pip install yt-dlp-get-pot-rustypipe`
- **Method**: Uses rustypipe-botguard
- **Supports**: All web-based YouTube clients
- **Best for**: Advanced users, specific client requirements

## Verification Workflow

### Check Available Formats

```bash
yt-dlp -F "https://youtu.be/VIDEO_ID"
```

Compare the actual format list with the requested media. Format IDs and maximum resolution vary by source and client. Do not infer provider status from a fixed ID list or resolution table.

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

**Symptom**: The chosen provider reports a token-generation or connection error

**Solution**:
1. Verify yt-dlp version: `yt-dlp --version` (need 2025.05.22+)
2. Check plugin installation: `pip list | grep bgutil`
3. Ensure plugin installed in correct Python environment
4. Read the provider error and repair its diagnosed dependency or connection within authorization. Do not reinstall or restart a shared service on a resolution-only symptom.

### Warning Messages

```
WARNING: [youtube] [pot:bgutil:http] Error reaching GET http://127.0.0.1:4416/ping
```

**Impact**: The named HTTP provider did not answer. Other clients/providers may still complete the download; this message alone does not establish the final result.

**Action**: No action needed if download succeeds with high-quality formats.

## Alternative: Browser Cookies Method

When an account or persistent bot check requires an authenticated session, obtain cookie permission before using:

```bash
# Firefox
yt-dlp --cookies-from-browser firefox "VIDEO_URL"

# Chrome
yt-dlp --cookies-from-browser chrome "VIDEO_URL"
```

**Benefits**:
- Access age-restricted content
- Access members-only content
- Availability according to that account's actual access; no quality guarantee

**Requirements**:
- Must be logged into YouTube in the browser
- Browser and yt-dlp must use same IP address

## Quality and Recovery Boundaries

Verify the downloaded file rather than promising quality by setup type. Cookies do not replace a missing Token; a provider does not fix missing EJS components, network timeouts or absent source formats. Stop escalating once the requested file is verified. Keep a failed provider setup visible and resume from that missing prerequisite after it is repaired.

## References

- [yt-dlp PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)
- [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
- [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp)
