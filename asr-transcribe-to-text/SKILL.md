---
name: asr-transcribe-to-text
description: Transcribes audio and video files to text using Qwen3-ASR. Supports two modes — local MLX inference on macOS Apple Silicon (no API key, 15-27x realtime) and remote API via vLLM/OpenAI-compatible endpoints. Auto-detects platform and recommends the best path. Triggers when the user wants to transcribe recordings, convert audio/video to text, do speech-to-text, or mentions ASR, Qwen ASR, 转录, 语音转文字, 录音转文字. Also triggers for meeting recordings, lectures, interviews, podcasts, screen recordings, or any audio/video file the user wants converted to text.
argument-hint: [audio-or-video-file-path ...]
---

# ASR Transcribe to Text

Transcribe audio/video files to text using Qwen3-ASR. Two inference paths:

| Mode | When | Speed | Cost |
|------|------|-------|------|
| **Local MLX** | macOS Apple Silicon | 15-27x realtime | Free |
| **Remote API** | Any platform, or when local unavailable | Depends on GPU | API/self-hosted |

Configuration persists in `${CLAUDE_PLUGIN_DATA}/config.json`.

## Step 0: Detect Platform and Load Config

```bash
cat "${CLAUDE_PLUGIN_DATA}/config.json" 2>/dev/null
```

**If config exists**, read values and proceed to Step 1.

**If config does not exist**, auto-detect platform first:

```bash
python3 -c "
import sys, platform
is_mac_arm = sys.platform == 'darwin' and platform.machine() in ('arm64', 'aarch64')
print(f'Platform: {sys.platform} {platform.machine()}')
print(f'Apple Silicon: {is_mac_arm}')
if is_mac_arm:
    print('RECOMMEND: local-mlx')
else:
    print('RECOMMEND: remote-api')
"
```

Then use **AskUserQuestion** with platform-aware defaults:

For **macOS Apple Silicon** (recommended: local):
```
ASR setup — your Mac has Apple Silicon, so local transcription is recommended.

Q1: Transcription mode?
  A) Local MLX — runs on your Mac's GPU, no API key needed, 15-27x realtime (Recommended)
  B) Remote API — send audio to a server (vLLM, Tailscale workstation, etc.)

Q2: Does your network have an HTTP proxy that might intercept traffic?
  A) Yes — bypass proxy for ASR traffic (Recommended if using Shadowrocket/Clash)
  B) No — direct connection
```

For **other platforms** (recommended: remote):
```
ASR setup — local MLX requires macOS Apple Silicon. Using remote API mode.

Q1: ASR Endpoint URL?
  A) http://workstation-4090-wsl:8002/v1/audio/transcriptions (Qwen3-ASR vLLM via Tailscale)
  B) http://localhost:8002/v1/audio/transcriptions (Local server)
  C) Custom URL

Q2: Proxy bypass needed?
  A) Yes (Recommended for Shadowrocket/Clash/corporate proxy)
  B) No
```

Save config:
```bash
mkdir -p "${CLAUDE_PLUGIN_DATA}"
python3 -c "
import json
config = {
    'mode': 'MODE',           # 'local-mlx' or 'remote-api'
    'model': 'MODEL_ID',      # local: 'mlx-community/Qwen3-ASR-1.7B-8bit', remote: 'Qwen/Qwen3-ASR-1.7B'
    'max_tokens': 200000,     # local only, critical for long audio
    'endpoint': 'URL',        # remote only
    'noproxy': True,
    'max_timeout': 900        # remote only
}
with open('${CLAUDE_PLUGIN_DATA}/config.json', 'w') as f:
    json.dump(config, f, indent=2)
print('Config saved.')
"
```

## Step 1: Extract Audio (if input is video)

For video files (mp4, mov, mkv, avi, webm), extract as 16kHz mono WAV:

```bash
ffmpeg -i INPUT_VIDEO -vn -acodec pcm_s16le -ar 16000 -ac 1 OUTPUT.wav -y
```

Audio files (wav, mp3, m4a, flac, ogg) can be used directly. Get duration:
```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 INPUT_FILE
```

**Cleanup**: After transcription succeeds, delete extracted WAV files to save disk space.

## Step 2: Transcribe

### Path A: Local MLX (macOS Apple Silicon)

Use the bundled script — it handles model loading, chunking, and the critical `max_tokens` parameter:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/transcribe_local_mlx.py \
  INPUT_AUDIO [INPUT_AUDIO2 ...] \
  --output-dir OUTPUT_DIR
```

The script loads the model once and transcribes all files sequentially (no GPU contention). For details on performance, model compatibility, and the max_tokens truncation issue, see `references/local_mlx_guide.md`.

**Critical**: The upstream `mlx-audio` default `max_tokens=8192` silently truncates audio longer than ~40 minutes. The bundled script defaults to `200000`. If calling `model.generate()` directly, always pass `max_tokens=200000`.

### Path B: Remote API

**Health check first** (skip if already verified this session):
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
    print(f'HEALTH CHECK FAILED: {base}/models', file=sys.stderr)
    sys.exit(1)
print(f'Service healthy: {base}')
"
```

Read config and send via curl:

```bash
python3 -c "
import json, subprocess, sys, os, tempfile
with open('${CLAUDE_PLUGIN_DATA}/config.json') as f:
    cfg = json.load(f)
noproxy = ['--noproxy', '*'] if cfg.get('noproxy', True) else []
timeout = str(cfg.get('max_timeout', 900))
audio_file = 'AUDIO_FILE_PATH'
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
print(f'Transcribed: {len(text)} chars', file=sys.stderr)
print(text)
os.unlink(output_json)
" > OUTPUT.txt
```

**If remote health check fails**, diagnose in order:
1. Network: `ping -c 1 HOST` or `tailscale status | grep HOST`
2. Service: `tailscale ssh USER@HOST "curl -s localhost:PORT/v1/models"`
3. Proxy: retry with `--noproxy '*'` toggled

## Step 3: Verify Output

After transcription, check for truncation — the most common failure mode:

1. Confirm output is not empty
2. Check character count is plausible (~400 chars/min for Chinese, ~200 words/min for English)
3. Check the **ending** — does it trail off mid-sentence? If so, `max_tokens` was exhausted
4. Show user the first and last ~200 characters as preview

If truncated or wrong, use **AskUserQuestion**:
```
Transcription may be truncated:
- Expected: ~[N] chars for [M] minutes of audio
- Got: [actual] chars ([pct]% of expected)
- Last line: "[last 100 chars...]"

Options:
A) Retry with higher max_tokens (current: [N], try: [N*2])
B) Switch mode — try [local/remote] instead
C) Save as-is — the output looks complete to me
D) Abort
```

## Step 4: Fallback — Overlap-Merge (Remote API Only)

If single remote request fails (timeout, OOM), fall back to chunked transcription:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/overlap_merge_transcribe.py \
  --config "${CLAUDE_PLUGIN_DATA}/config.json" \
  INPUT_AUDIO OUTPUT.txt
```

Splits into 18-minute chunks with 2-minute overlap, merges using punctuation-stripped fuzzy matching. See `references/overlap_merge_strategy.md` for algorithm details.

For local MLX mode, overlap-merge is unnecessary — the bundled script handles chunking internally with `max_tokens=200000`.

## Step 5: Recommend Transcript Correction

ASR output always contains recognition errors — homophones, garbled technical terms, broken sentences. After successful transcription, **proactively suggest** running the `transcript-fixer` skill on the output:

```
Transcription complete: [N] chars saved to [output_path].

ASR output typically contains recognition errors (homophones, garbled terms, broken sentences).
Would you like me to run /transcript-fixer to clean up the text?

Options:
A) Yes — run transcript-fixer on the output now (Recommended)
B) No — the raw transcription is good enough for my needs
C) Later — I'll run it myself when ready
```

If the user chooses A, invoke the `transcript-fixer` skill with the output file path. The two skills form a natural pipeline: **transcribe → correct → review**.

## Reconfigure

```bash
rm "${CLAUDE_PLUGIN_DATA}/config.json"
```

Then re-run Step 0.

## Bundled Resources

**Scripts:**
- `transcribe_local_mlx.py` — Local MLX transcription (macOS ARM64, PEP 723 deps)
- `overlap_merge_transcribe.py` — Chunked transcription with overlap merge (remote API fallback)

**References:**
- `local_mlx_guide.md` — Performance benchmarks, max_tokens truncation, model compatibility
- `overlap_merge_strategy.md` — Why naive chunking fails, fuzzy merge algorithm
