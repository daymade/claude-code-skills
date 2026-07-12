---
name: asr-transcribe-to-text
description: >-
  Transcribes audio and video to text using Qwen3-ASR, with input handling for local files, direct media URLs, and podcast/web pages. Supports local MLX inference on macOS Apple Silicon and remote OpenAI-compatible ASR endpoints. Use when the user wants to transcribe recordings, podcasts, lectures, interviews, meetings, screen recordings, or any audio/video file; also use for ASR, Qwen ASR, speech-to-text, 转录, 语音转文字, and 录音转文字 requests. Also covers word-level timestamps via mlx-whisper for subtitles and audio-visual alignment (字幕, 时间戳, 音画对齐). For multi-speaker recordings (meetings, interviews, panels, group discussions) it also does speaker diarization (who-said-what) and CAM++ voiceprint speaker identification — use it whenever the user needs speaker labels, a diarized transcript, to know who said what, 说话人分离, 说话人识别, or 谁在说话.
argument-hint: "[audio-or-video-file-path-or-url ...]"
---

# ASR Transcribe to Text

Transcribe audio/video to text using Qwen3-ASR. Two inference paths:

| Mode | When | Speed | Cost |
|------|------|-------|------|
| **Local MLX** | macOS Apple Silicon | 15-27x realtime | Free |
| **Remote API** | Any platform, or when local unavailable | Depends on GPU | API/self-hosted |

Configuration persists in `${CLAUDE_PLUGIN_DATA}/config.json`.

> **Need timestamps, not just text?** Qwen3-ASR outputs plain text only. For word-level timestamps (subtitles, aligning voiceover to video shots) use the mlx-whisper path instead — see `## Word-Level Timestamps` below.
>
> **Multiple speakers — need who-said-what?** Qwen3-ASR gives one flat block with no speaker labels. For meetings / interviews / podcasts, use the diarization + voiceprint path — see `## Speaker Diarization & Identification` below.

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
  A) https://asr.example.com/v1/audio/transcriptions (Self-hosted remote ASR)
  B) http://localhost:8002/v1/audio/transcriptions (Local ASR server)
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

## Step 1: Resolve Input

Accept local files, direct media URLs, or web/podcast episode pages.

- **Web or podcast page URL**: inspect the page for an existing transcript first. Use an official/platform transcript only when it is directly accessible to the user's account. If the transcript endpoint requires a login token and none is available, say that clearly and fall back to ASR from the audio URL.
- **Local file, direct media URL, or page URL fallback**: run the bundled resolver. It extracts media from common page metadata (`og:audio`, media tags, JSON-LD, RSS-style enclosure links), downloads URLs with atomic temp-file replacement, verifies remote `Content-Length` when present, computes SHA-256, and validates the result with `ffprobe`.

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_media_input.py \
  INPUT_FILE_OR_URL [INPUT_FILE_OR_URL2 ...] \
  --output-dir OUTPUT_DIR \
  --manifest OUTPUT_DIR/media_manifest.json
```

For suspicious or high-value downloads, add `--decode-check` to make `ffmpeg` decode the whole file before transcription:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/resolve_media_input.py \
  "https://www.xiaoyuzhoufm.com/episode/EPISODE_ID" \
  --output-dir OUTPUT_DIR \
  --manifest OUTPUT_DIR/media_manifest.json \
  --decode-check
```

Expected output:

```text
Downloaded ... bytes in ...s -> OUTPUT_DIR/episode-title.m4a
OUTPUT_DIR/episode-title.m4a
```

Use the printed local path as `INPUT_AUDIO` in later steps. If `${CLAUDE_PLUGIN_ROOT}` is empty, use the absolute path to this skill directory.

For third-party public podcasts or copyrighted media, save the transcript as a local file for the user's personal analysis. Do not paste a full long transcript into chat; provide a path, previews, summaries, or short excerpts instead.

## Step 2: Extract Audio (if input is video)

For video files (mp4, mov, mkv, avi, webm), extract as 16kHz mono WAV:

```bash
ffmpeg -i INPUT_VIDEO -vn -acodec pcm_s16le -ar 16000 -ac 1 OUTPUT.wav -y
```

Audio files (wav, mp3, m4a, flac, ogg) can be used directly. Get duration:
```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 INPUT_FILE
```

**Cleanup**: After transcription succeeds, delete extracted WAV files to save disk space.

## Step 3: Transcribe

### Path A: Local MLX (macOS Apple Silicon)

Use the bundled script — it handles dependency pins, model loading, chunking, and the critical `max_tokens` parameter. If `${CLAUDE_PLUGIN_ROOT}` is empty, use the absolute path to the `asr-transcribe-to-text` skill directory you just read.

Before a long first run, load the model once:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/transcribe_local_mlx.py --smoke-test
```

Expected output includes:
```text
Dependency stack: mlx-audio 0.3.1, mlx-lm 0.30.5, transformers 5.0.0rc3
Model loaded in ...
Smoke test OK: model loaded
```

Then transcribe:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/transcribe_local_mlx.py \
  INPUT_AUDIO [INPUT_AUDIO2 ...] \
  --output-dir OUTPUT_DIR
```

The script loads the model once and transcribes all files sequentially (no GPU contention). For details on performance, dependency pins, model compatibility, and the max_tokens truncation issue, see `references/local_mlx_guide.md`.

**Before batching many short files** (promo clips, montage cuts — anything that may contain music-only audio), read `## Batch Transcription (many short files)` below: one music-only clip can stall the whole batch for 10+ minutes.

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

## Step 4: Verify Output

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

## Step 5: Fallback — Overlap-Merge (Remote API Only)

If single remote request fails (timeout, OOM), fall back to chunked transcription:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/overlap_merge_transcribe.py \
  --config "${CLAUDE_PLUGIN_DATA}/config.json" \
  INPUT_AUDIO OUTPUT.txt
```

Splits into 18-minute chunks with 2-minute overlap, merges using punctuation-stripped fuzzy matching. See `references/overlap_merge_strategy.md` for algorithm details.

For local MLX mode, overlap-merge is unnecessary — the bundled script handles chunking internally with `max_tokens=200000`.

## Step 6: Recommend Transcript Correction

ASR output always contains recognition errors — homophones, garbled technical terms, broken sentences. After successful transcription, **proactively suggest** running the `transcript-fixer` skill on the output:

```
Transcription complete: [N] chars saved to [output_path].

ASR output typically contains recognition errors (homophones, garbled terms, broken sentences).
Would you like me to run /daymade-audio:transcript-fixer to clean up the text?

Options:
A) Yes — run daymade-audio:transcript-fixer on the output now (Recommended)
B) No — the raw transcription is good enough for my needs
C) Later — I'll run it myself when ready
```

If the user chooses A, invoke the `transcript-fixer` skill with the output file path. The two skills form a natural pipeline: **transcribe → correct → review**.

## Reconfigure

```bash
rm "${CLAUDE_PLUGIN_DATA}/config.json"
```

Then re-run Step 0.

## Batch Transcription (many short files)

Passing many files to one `transcribe_local_mlx.py` invocation is efficient (model loads once) — **but only when every file contains actual speech.** If the batch may include music-only / BGM-only clips (short promo videos, montage clips with subtitles instead of voiceover), do NOT batch them in one process:

- On music/rhythm-only audio the model can fall into a **repetition loop hallucination** (e.g. endless "One, two, three, one, two, three...") that burns toward `max_tokens=200000` — one such file can stall for 10+ minutes and starve the whole batch.
- **Drive batch jobs one-file-per-process with a per-file timeout** (e.g. `timeout 240` / `perl -e 'alarm 240; exec @ARGV'` around each invocation, skip on timeout, second pass for failures). A stuck file then costs 4 minutes, not the batch.
- For a stuck file, retry with `--max-tokens 3000`: real speech in a short clip fits comfortably; a looping file gets truncated output you can classify.
- **Detect "no speech" instead of shipping garbage**: if the transcript's unique-word ratio is extremely low (e.g. `len(set(words))/len(words) < 0.06` on a 40+ char output), the clip almost certainly has no voiceover — label it as such rather than delivering the loop text. (Downstream OCR of on-screen captions is the actual fix for subtitle-only videos.)

## Word-Level Timestamps (subtitles, audio-visual alignment)

Qwen3-ASR is an LLM-decoder ASR: it emits plain text with no alignment information, on both local and remote paths. When the task needs to know *when* each word is spoken — subtitle generation, aligning narration to shot boundaries, per-clip captioning — use `mlx-whisper` with `word_timestamps=True` instead. Whisper's cross-attention word alignment is the de-facto local solution for this class of task.

Key facts (full recipe in `references/whisper_word_timestamps.md`):

- Model: `mlx-community/whisper-large-v3-turbo` (~1.6GB). Its Chinese WER is higher than Qwen3-ASR for pure transcription, but for alignment tasks Qwen3-ASR is not an option at all; prime domain terms via `initial_prompt`.
- **Segment granularity trap**: on short videos (15–40s) whisper often returns the whole clip as one segment — always work from the word list and assign words to time windows by midpoint.
- Pairs with ffmpeg scene detection (`select='gt(scene,0.3)'`) for the visual side; avoid PySceneDetect on non-ASCII paths.

## Speaker Diarization & Identification (who said what)

Qwen3-ASR returns one flat block of text with no speaker labels — useless for a
meeting / interview / podcast / any multi-person recording where you need **who said
what**. Two bundled paths, both GPU (pyannote @ MPS + CAM++), both needing a
HuggingFace token for pyannote:

- **Diarization + per-speaker transcription** — `scripts/speaker_transcribe.py`
  runs pyannote (who spoke when) + Qwen3-ASR (what was said) in one command and
  writes a speaker-labeled transcript + CSV. Full recipe, the merge-turns step, and
  production pitfalls: `references/speaker_diarization.md`. (Need just the segments?
  `scripts/diarize_speakers.py` does diarization alone.)
- **Voiceprint identification** — diarization labels are anonymous (`SPEAKER_00`…)
  and per-file. To map them to real names, unify a speaker across files, or collapse
  diarization's over-segmentation, use CAM++ voiceprints via `scripts/voiceprint_id.py`.
  Recipe **and the critical acoustic-domain caveat** — a voiceprint built from one
  mic type matches the same person on a different mic far less well:
  `references/voiceprint_speaker_id.md`.

## Troubleshooting

### Local MLX fails while loading the model

If model loading fails with an error like:

```text
AttributeError: 'str' object has no attribute '__module__'
```

the agent is probably using an unpinned or stale copy of the local MLX script. The known-good stack is:

```text
mlx-audio 0.3.1
mlx-lm 0.30.5
transformers 5.0.0rc3
```

Run the bundled `--smoke-test` command and confirm the dependency stack line matches. Do not start a long transcription until the smoke test succeeds.

### `${CLAUDE_PLUGIN_ROOT}` is empty

Some runtimes do not set skill environment variables. Use the absolute path to the skill directory that contains this `SKILL.md`, then run `scripts/transcribe_local_mlx.py` from there.

## Bundled Resources

**Scripts:**
- `resolve_media_input.py` — Resolve local paths, direct media URLs, and podcast/web pages into validated local media files
- `transcribe_local_mlx.py` — Local MLX transcription (macOS ARM64, PEP 723 deps)
- `overlap_merge_transcribe.py` — Chunked transcription with overlap merge (remote API fallback)
- `diarize_speakers.py` — Speaker diarization (pyannote 3.1 @ MPS) → per-segment JSON
- `speaker_transcribe.py` — Multi-speaker pipeline: diarize → merge turns → per-turn Qwen3-ASR → speaker-labeled transcript + CSV
- `voiceprint_id.py` — CAM++ voiceprint enroll/match: map anonymous SPEAKER_xx to real names

**References:**
- `local_mlx_guide.md` — Performance benchmarks, max_tokens truncation, model compatibility
- `overlap_merge_strategy.md` — Why naive chunking fails, fuzzy merge algorithm
- `whisper_word_timestamps.md` — Word-level timestamps via mlx-whisper: alignment recipe, segment-granularity trap, scene-detection pairing
- `speaker_diarization.md` — Multi-speaker transcription: pyannote + per-turn Qwen3, merge-turns step, production pitfalls
- `voiceprint_speaker_id.md` — CAM++ speaker ID: enroll/match, threshold+margin gates, the acoustic-domain caveat, bootstrap
