---
name: asr-transcribe-to-text
description: Transcribe audio and video files to text using a remote ASR service (Qwen3-ASR or OpenAI-compatible endpoint). Extracts audio from video, sends to configurable ASR endpoint, outputs clean text. Use when the user wants to transcribe recordings, convert audio/video to text, do speech-to-text, or mentions ASR, Qwen ASR, 转录, 语音转文字, 录音转文字, or has a meeting recording, lecture, interview, or screen recording to transcribe.
argument-hint: [audio-or-video-file-path]
---

# ASR Transcribe to Text

Transcribe audio/video files to text using a configurable ASR endpoint (default: Qwen3-ASR-1.7B via vLLM). Configuration persists across sessions in `${CLAUDE_PLUGIN_DATA}/config.json`.

## Step 0: Load or Initialize Configuration

```bash
cat "${CLAUDE_PLUGIN_DATA}/config.json" 2>/dev/null
```

**If config exists**, read the values and proceed to Step 1.

**If config does not exist** (first run), use **AskUserQuestion**:

```
First-time setup for ASR transcription.
I need to know where your ASR service is running so I can send audio to it.

RECOMMENDATION: Use the defaults below if you have Qwen3-ASR on a 4090 via Tailscale.

Q1: ASR Endpoint URL?
  A) http://workstation-4090-wsl:8002/v1/audio/transcriptions (Default — Qwen3-ASR vLLM via Tailscale)
  B) http://localhost:8002/v1/audio/transcriptions (Local machine)
  C) Let me enter a custom URL

Q2: Does your network have an HTTP proxy that might intercept LAN/Tailscale traffic?
  A) Yes — add --noproxy to bypass it (Recommended if you use Shadowrocket/Clash/corporate proxy)
  B) No — direct connection is fine
```

Save the config:
```bash
mkdir -p "${CLAUDE_PLUGIN_DATA}"
python3 -c "
import json
config = {
    'endpoint': 'USER_PROVIDED_ENDPOINT',
    'model': 'USER_PROVIDED_MODEL_OR_DEFAULT',
    'noproxy': True,  # or False based on user answer
    'max_timeout': 900
}
with open('${CLAUDE_PLUGIN_DATA}/config.json', 'w') as f:
    json.dump(config, f, indent=2)
print('Config saved.')
"
```

## Step 1: Validate Input and Check Service Health

Read config and health-check in a single command (shell variables don't persist across Bash calls):

```bash
python3 -c "
import json, subprocess, sys
with open('${CLAUDE_PLUGIN_DATA}/config.json') as f:
    cfg = json.load(f)
base = cfg['endpoint'].rsplit('/audio/', 1)[0]
noproxy = ['--noproxy', '*'] if cfg.get('noproxy', True) else []
result = subprocess.run(
    ['curl', '-s', '--max-time', '10'] + noproxy + [f'{base}/models'],
    capture_output=True, text=True
)
if result.returncode != 0 or not result.stdout.strip():
    print(f'HEALTH CHECK FAILED', file=sys.stderr)
    print(f'Endpoint: {base}/models', file=sys.stderr)
    print(f'stdout: {result.stdout[:200]}', file=sys.stderr)
    print(f'stderr: {result.stderr[:200]}', file=sys.stderr)
    sys.exit(1)
else:
    print(f'Service healthy: {base}')
    print(f'Model: {cfg[\"model\"]}')
"
```

**If health check fails**, use **AskUserQuestion**:

```
ASR service at [endpoint] is not responding.

Options:
A) Diagnose — check network, Tailscale, and service status step by step
B) Reconfigure — the endpoint URL might be wrong, let me re-enter it
C) Try anyway — send the transcription request and see what happens
D) Abort — I'll fix the service manually and come back later
```

For option A, diagnose in order:
1. Network: `ping -c 1 HOST` or `tailscale status | grep HOST`
2. Service: `tailscale ssh USER@HOST "curl -s localhost:PORT/v1/models"`
3. Proxy: retry with `--noproxy '*'` toggled

## Step 2: Extract Audio (if input is video)

For video files (mp4, mov, mkv, avi, webm), extract audio as 16kHz mono MP3:

```bash
ffmpeg -i INPUT_VIDEO -vn -acodec libmp3lame -q:a 4 -ar 16000 -ac 1 OUTPUT.mp3 -y
```

For audio files (mp3, wav, m4a, flac, ogg), use directly — no conversion needed.

Get duration for progress estimation:
```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 INPUT_FILE
```

## Step 3: Transcribe — Single Request First

**Always try full-length single request first.** Chunking causes sentence truncation at every split boundary — the model forces the last sentence to close and loses words. Single request = zero truncation + fastest speed.

The Qwen3-ASR paper's "20-minute limit" is a training benchmark, not an inference hard limit. Empirically verified: 55 minutes transcribed in a single 76-second request on 4090 24GB.

```bash
python3 -c "
import json, subprocess, sys, os, tempfile
with open('${CLAUDE_PLUGIN_DATA}/config.json') as f:
    cfg = json.load(f)
noproxy = ['--noproxy', '*'] if cfg.get('noproxy', True) else []
timeout = str(cfg.get('max_timeout', 900))
audio_file = 'AUDIO_FILE_PATH'  # replace with actual path
output_json = tempfile.mktemp(suffix='.json', prefix='asr_')

result = subprocess.run(
    ['curl', '-s', '--max-time', timeout] + noproxy + [
        cfg['endpoint'],
        '-F', f'file=@{audio_file}',
        '-F', f'model={cfg[\"model\"]}',
        '-o', output_json
    ], capture_output=True, text=True
)

with open(output_json) as f:
    data = json.load(f)
if 'text' not in data:
    print(f'ERROR: {json.dumps(data)[:300]}', file=sys.stderr)
    sys.exit(1)
text = data['text']
duration = data.get('usage', {}).get('seconds', 0)
print(f'Transcribed: {len(text)} chars, {duration}s audio', file=sys.stderr)
print(text)
os.unlink(output_json)
" > OUTPUT.txt
```

**Performance reference**: ~400 characters per minute for Chinese speech; rates vary by language. Qwen3-ASR supports 52 languages including Chinese dialects, English, Japanese, Korean, and more.

## Step 4: Verify and Confirm Output

After transcription, verify quality:
1. Confirm the response contains a `text` field (not an error message)
2. Check character count is plausible for the audio duration (~400 chars/min for Chinese)
3. Show the user the first ~200 characters as a preview

If the output looks wrong (empty, garbled, or error), use **AskUserQuestion**:

```
Transcription may have an issue:
- Expected: ~[N] chars for [M] minutes of audio
- Got: [actual chars] chars
- Preview: "[first 100 chars...]"

Options:
A) Save as-is — the output looks fine to me
B) Retry with fallback — split into chunks and merge (handles long audio / OOM)
C) Reconfigure — try a different model or endpoint
D) Abort — something is wrong with the service
```

If output is good, save as `.txt` alongside the original file or to user-specified location.

## Step 5: Fallback — Overlap-Merge for Very Long Audio

If single request fails (timeout, OOM, HTTP error), fall back to chunked transcription with overlap merging:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/overlap_merge_transcribe.py \
  --config "${CLAUDE_PLUGIN_DATA}/config.json" \
  INPUT_AUDIO OUTPUT.txt
```

This splits into 18-minute chunks with 2-minute overlap, then merges using punctuation-stripped fuzzy matching. See [references/overlap_merge_strategy.md](references/overlap_merge_strategy.md) for the algorithm details.

## Reconfigure

To change the ASR endpoint, model, or proxy settings:

```bash
rm "${CLAUDE_PLUGIN_DATA}/config.json"
```

Then re-run Step 0 to collect new values via AskUserQuestion.
