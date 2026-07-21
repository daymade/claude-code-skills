---
name: asr-transcribe-to-text
description: >-
  Transcribe audio/video to speaker-labeled text — who-said-what by default, plain-text opt-out; MLX-local on Apple Silicon or remote; local files, media URLs. Use for transcribing recordings/podcasts/lectures/meetings, ASR, speech-to-text, 转录, 语音转文字, 录音转文字, speaker diarization/说话人分离/识别/谁在说话, timestamps 字幕/时间戳/音画对齐, CAM++ voiceprint ID. This skill ALSO owns audio PREPROCESSING for ASR as a first-class trigger, even without transcription: convert any audio/video into an ASR-ready file (转换成适合 ASR 的格式, 转格式, convert/prepare audio for ASR, 音频预处理), downsample to 16kHz mono 16-bit (降采样, 重采样, 单声道, 归一化), merge multi-segment recorder dumps (多段合并/拼接, DJI TX01/TX02), transcode to small M4A + pitch-preserved speedup to cut metered-ASR billed minutes (转 M4A, 压缩上传, 加速, 1.3x, 飞书妙记/Feishu Minutes). Trigger even when it looks like a trivial one-line ffmpeg — the skill owns sample-rate/bit-depth/channel, merge-order, speed-vs-WER, format choices + a blessed prepare_asr_input.py.
argument-hint: "[audio-or-video-file-path-or-url ...]"
---

# ASR Transcribe to Text

Transcribe audio/video to **speaker-labeled** text. Default pipeline (decoupled,
WhisperX-style): Qwen3-ASR transcribes the full audio with context intact,
mlx-whisper supplies a word-level timing lattice, pyannote supplies speaker
segments, and an aligner merges the three — the audio is never cut before ASR,
so transcription quality stays at full-audio fidelity.

| Mode | When | Speed | Cost |
|------|------|-------|------|
| **Local MLX** | macOS Apple Silicon | 15-27x realtime | Free |
| **Remote API** | Any platform, or when local unavailable | Depends on GPU | API/self-hosted |

Configuration persists in `${CLAUDE_PLUGIN_DATA}/config.json`.

> **Speaker labels are the default.** Every run produces `[start-end] SPEAKER_xx: text`
> + CSV. Plain-text-only output is the opt-out (`--no-diarization`) for monologues,
> podcasts, or when you just want a summary — see Step 3.
>
> **One-time setup for diarization:** pyannote is a gated HuggingFace model — it
> needs a token once (`## Speaker Diarization & Identification` below). First run
> without it FAILS with setup steps; after setup, full capability is permanent
> and auto-detected.

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
    # 'diarization_declined': True  # set only after the user explicitly declines
    #   the pyannote setup in Step 3 — every run then warns + goes plain-text
    #   until an HF token appears (auto-detected)
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
uv run ${CLAUDE_SKILL_DIR}/scripts/resolve_media_input.py \
  INPUT_FILE_OR_URL [INPUT_FILE_OR_URL2 ...] \
  --output-dir OUTPUT_DIR \
  --manifest OUTPUT_DIR/media_manifest.json
```

For suspicious or high-value downloads, add `--decode-check` to make `ffmpeg` decode the whole file before transcription:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/resolve_media_input.py \
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

Use the printed local path as `INPUT_AUDIO` in later steps. If your runtime shows the literal `${CLAUDE_SKILL_DIR}` instead of a substituted path, resolve the skill directory per the Troubleshooting entry at the bottom of this document.

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

## Preprocess: Merge Segments & Shrink Metered Uploads (optional)

Run this BEFORE transcription when either applies:

- **The recording is a multi-segment dump** — body mics and field recorders split
  sessions into fixed-length files (e.g. `TX02_MIC024_....wav`, `TX02_MIC025_....wav`;
  `TX01/TX02` = DJI MIC MINI 2S internal recording — device roster and the
  recorder→Feishu-Minutes paths: the meeting-ingest skill's `meeting-ingest/references/architecture.md` §①-L0).
  Merge them and transcribe the merged file: full-audio context is the quality basis
  of the decoupled pipeline (Step 3), so transcribing segments separately throws away
  exactly what the architecture buys.
- **The audio goes to a metered ASR** (Feishu Minutes, any per-minute quota) — a
  pitch-PRESERVED speedup cuts billed duration directly, and modern ASR does not care:
  1.3x was user-verified on Feishu Minutes (2026-07-16) with no perceptible recognition
  difference, and public Whisper benchmarks show no sharp WER drop until 2.0x
  (≤1.5x = safe zone, ~3% WER increase at 1.5x; >2x unusable).

Use the bundled script — it merges, normalizes to 16 kHz mono, optionally speeds up,
and verifies its own output instead of trusting the ffmpeg exit code:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/prepare_asr_input.py SEG1.wav SEG2.wav -o merged.wav   # merge only
uv run ${CLAUDE_SKILL_DIR}/scripts/prepare_asr_input.py SEG*.wav -o upload.m4a --speed 1.3  # merge + quota-saving speedup
```

Expected output:

```text
Merge order:
  1. SEG1.wav  [pcm_s24le 48000Hz ch=1 1800.14s]
  2. SEG2.wav  [pcm_s24le 48000Hz ch=1 1800.15s]
[OK] duration: 4946.19s vs expected 4946.18s (delta +0.00s)
[OK] boundary 1 @ 1384.7s: max_volume -15.5 dB
[info] overall: mean_volume -38.3 dB, max_volume 0.0 dB
Wrote upload.m4a
```

- Segments sort by the `YYYYMMDD_HHMMSS` timestamp embedded in their filenames when
  every file has one (recorder dumps do); otherwise the given order is kept with a note —
  eyeball the printed merge order before transcribing.
- Self-verification: output duration must equal Σsegments ÷ speed (±1.5 s, hard FAIL
  otherwise); each splice gets a 10 s volume spot-check (dead air at a boundary = wrong
  order or a missing segment); overall loudness prints for comparison with the source.
- Speedup must be `atempo`-style pitch-preserved stretch — never sample-rate trickery,
  which shifts pitch and breaks both ASR accuracy and diarization voiceprints.
- **Pick the output format by destination** — codec follows the file extension:

  | Destination | Format | Why |
  |---|---|---|
  | Local MLX pipeline (Path A) | `.wav` or `.m4a` | Both feed the pipeline directly (m4a verified 2026-07-18: a 3-min slice transcribed cleanly). M4A is ~5x smaller — 324 MB WAV → 63 MB M4A on a 2h49m merge, duration identical to the second |
  | Metered upload (Feishu Minutes, per-minute quota) | `.m4a` + `--speed 1.3` | AAC 48k is speech-transparent for ASR, ~30% smaller than mp3 at equal speech quality; speedup cuts billed duration ~23% |
  | Lossless archive | `.flac` | ~50% of WAV, bit-perfect |
  | Only when the target rejects the above | `.mp3` | Compatibility fallback |
- Keep the originals until the transcript passes Step 4 verification.

## Step 3: Transcribe (speaker labels by default)

### Path A: Local MLX (macOS Apple Silicon) — default

Run the decoupled speaker pipeline — it handles dependency pins, model loading,
and the critical `max_tokens` parameter internally.

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/speaker_transcribe.py \
  INPUT_AUDIO [INPUT_AUDIO2 ...] OUTPUT_DIR
```

Expected output (per file):

```text
Device: mps
+ uv run .../transcribe_local_mlx.py ...        (leg 1: full-audio text)
+ uv run .../word_timestamps_whisper.py ...     (leg 2: timing lattice)
... diarization ...                             (leg 3: pyannote segments)
STEM: 42 turns, speakers=['SPEAKER_00', 'SPEAKER_01'], anchored_ratio=0.93
Wrote STEM.txt, STEM.csv, STEM.alignment.json
```

Outputs per input: `<stem>.txt` (`[MM:SS - MM:SS] SPEAKER_xx` + text),
`<stem>.csv` (`file,start,end,duration,speaker,text` — feeds review UIs and
voiceprint ID), `<stem>.diarization.json`, `<stem>.alignment.json` (provenance
+ `anchored_ratio` trust signal; < 0.5 prints a loud warning — verify labels
against the audio before trusting them). Intermediate legs are cached in
`OUTPUT_DIR/_align/` so re-runs are cheap (`--force` redoes them).

Before a long first run, smoke-test the Qwen3 leg once:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/transcribe_local_mlx.py --smoke-test
```

Expected output includes `Dependency stack: mlx-audio 0.3.1, mlx-lm 0.30.5,
transformers 5.0.0rc3` and `Smoke test OK`. For performance details and the
max_tokens truncation issue, see `references/local_mlx_guide.md`.

**How it works (and why):** full-audio Qwen3-ASR text + mlx-whisper word
timestamps + pyannote speaker segments, aligned after the fact — the audio is
never cut before transcription, so ASR keeps full context. Architecture,
alignment algorithm, and failure modes: `references/decoupled_speaker_alignment.md`.

**First run: pyannote needs a one-time HuggingFace token.** If the script exits
with the setup hint (exit code 3), STOP and use **AskUserQuestion**:

```
Speaker diarization needs a one-time setup (gated model, free):
  1. Accept terms at https://hf.co/pyannote/speaker-diarization-3.1
  2. Run `huggingface-cli login` (or set HF_TOKEN)

Options:
A) Set it up now — I'll wait, then rerun with full speaker labels (Recommended)
B) Continue without speakers this time — plain text only
```

- **A** → after the user confirms login, rerun the same command. The token is
  auto-detected every run; full capability is permanent from then on.
- **B** → persist the choice (`diarization_declined: true` in config.json) and
  rerun the SAME command. The script detects the flag, prints a one-line warning
  with the two setup steps, and auto-falls back to plain text for that run —
  no need to pass `--no-diarization` (the fallback is automatic now, enforced in
  the script not just the doc). The same warn-and-continue happens on every
  later run while the token is still missing. When a token later appears,
  diarization resumes automatically (the flag is ignored once a token is
  present) — mention this so the user knows setup is all that's needed.

**Plain-text fast path** (monologue, podcast, "just summarize it"):

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/speaker_transcribe.py \
  INPUT_AUDIO OUTPUT_DIR --no-diarization
```

**Remote/pre-made ASR text** (e.g. from Path B, or another ASR service): skip
the Qwen3 leg and align that text instead. `--text-file` pairs ONE transcript
with ONE input wav — passing multiple inputs is rejected (one transcript can't
be aligned to several files):

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/speaker_transcribe.py \
  INPUT_AUDIO OUTPUT_DIR --text-file TRANSCRIPT.txt
```

**Non-Apple-Silicon machines:** the whisper timing leg is MLX-only. Without it
there is no timing lattice to align speakers onto — run with `--no-diarization`
and tell the user speaker mode currently requires Apple Silicon (cloud ASR with
built-in diarization, e.g. Feishu Minutes, is the no-local-GPU alternative).

**Before batching many short files** (promo clips, montage cuts — anything that
may contain music-only audio), read `## Batch Transcription (many short files)`
below: one music-only clip can stall the whole batch for 10+ minutes.

### Path B: Remote API

The remote endpoint returns plain text only — speakers are added locally by
aligning that text (leg 1) with the local timing + diarization legs. So Path B
= fetch text remotely, then run Path A's pipeline with `--text-file`.

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

Then attach speakers locally (Apple Silicon + pyannote token required):

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/speaker_transcribe.py \
  INPUT_AUDIO OUTPUT_DIR --text-file OUTPUT.txt
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
5. **Speaker path**: check the alignment report — `anchored_ratio` should be ≥ 0.5 (the script warns when lower), the speaker count should be plausible for the recording (a two-person interview showing 5 speakers, or a monologue split into 2+, means diarization over-segmented — see `references/speaker_diarization.md` for when to distrust labels)

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
python3 ${CLAUDE_SKILL_DIR}/scripts/overlap_merge_transcribe.py \
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

mlx-whisper's word timing is now the **timing leg of the default speaker pipeline** (leg 2 — `scripts/word_timestamps_whisper.py` runs it automatically). This section is for using word timestamps STANDALONE: subtitle generation, aligning narration to shot boundaries, per-clip captioning.

Qwen3-ASR is an LLM-decoder ASR: it emits plain text with no alignment information, on both local and remote paths. When the task needs to know *when* each word is spoken, use `mlx-whisper` with `word_timestamps=True`. Whisper's cross-attention word alignment is the de-facto local solution for this class of task.

Key facts (full recipe in `references/whisper_word_timestamps.md`):

- Model: `mlx-community/whisper-large-v3-turbo` (~1.6GB). Its Chinese WER is higher than Qwen3-ASR for pure transcription, but for alignment tasks Qwen3-ASR is not an option at all; prime domain terms via `initial_prompt`.
- **Segment granularity trap**: on short videos (15–40s) whisper often returns the whole clip as one segment — always work from the word list and assign words to time windows by midpoint.
- Pairs with ffmpeg scene detection (`select='gt(scene,0.3)'`) for the visual side; avoid PySceneDetect on non-ASCII paths.

## Speaker Diarization & Identification (who said what)

Speaker labels are the DEFAULT output of Step 3 (decoupled architecture:
full-audio Qwen3-ASR text + whisper timing lattice + pyannote segments,
aligned — never cut-then-transcribe). This section covers the pieces.

- **The pipeline** — `scripts/speaker_transcribe.py` runs all three legs +
  alignment in one command and writes the speaker-labeled transcript + CSV.
  Architecture, alignment algorithm, trust signals (`anchored_ratio`), and
  failure modes: `references/decoupled_speaker_alignment.md`. Production
  pitfalls (over-segmentation, mic-domain effects, when to distrust labels):
  `references/speaker_diarization.md`.
- **Diarization alone** — `scripts/diarize_speakers.py` emits just the
  `speaker × time` segments (no transcription).
- **Legacy cascade** — `scripts/speaker_transcribe_cascade.py` is the old
  cut-then-transcribe variant (diarize → slice audio per turn → ASR each
  slice). It breaks ASR context at every cut and lowers text quality; kept
  only for extremely noisy / heavy-overlap audio where per-slice isolation of
  a dominant near-field speaker beats full-audio ASR. Everything else uses
  the decoupled default.
- **Voiceprint identification** — diarization labels are anonymous
  (`SPEAKER_00`…) and per-file. To map them to real names, unify a speaker
  across files, or collapse diarization's over-segmentation, use CAM++
  voiceprints via `scripts/voiceprint_id.py`. Recipe **and the critical
  acoustic-domain caveat** — a voiceprint built from one mic type matches the
  same person on a different mic far less well:
  `references/voiceprint_speaker_id.md`.

**One-time pyannote setup** (gated model): accept terms at
`hf.co/pyannote/speaker-diarization-3.1`, then `huggingface-cli login` once
(or set `HF_TOKEN`). Auto-detected on every run afterward.

## Transcript Audit & Review (HTML)

After diarization you get a CSV per file (`file,start,end,duration,speaker,text`). The bundled audit HTML generator turns those CSVs into a single, reader-first review page with audio playback, per-turn flags/notes, speaker aliasing, and export.

Generate it from a speaker-transcribe output directory:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/generate_audit_html.py \
  OUTPUT_DIR \
  --output OUTPUT_DIR/audit/index.html \
  --audio-dir /path/to/original/audio
```

Defaults assume a flat layout under `PROJECT_DIR`: `PROJECT_DIR/*.csv` transcripts, `PROJECT_DIR/*.diarization.json`, and the original audio files placed next to the outputs. `speaker_transcribe.py` itself writes the CSV, TXT, and diarization files flat under its `OUTPUT_DIR`. If your project uses a different structure, override any of those paths:

```bash
uv run ${CLAUDE_SKILL_DIR}/scripts/generate_audit_html.py \
  /path/to/project \
  --output /path/to/project/audit/index.html \
  --csv-dir /path/to/project/csv \
  --txt-dir /path/to/project/txt \
  --diarization-dir /path/to/project/diarization \
  --audio-dir /path/to/project/audio \
  --original-dir /path/to/project/original \
  --manifest /path/to/project/manifest.json \
  --title "Project Audit" \
  --subtitle "Speaker-labeled transcript review" \
  --storage-key "project-audit" \
  --known-speaker "Speaker A" \
  --known-speaker "Speaker B"
```

**Key CLI options:**

| Option | Meaning |
|--------|---------|
| `project_dir` | Base project directory (required) |
| `--output` | Where to write `index.html` |
| `--csv-dir` | Directory containing `*.csv` transcript files |
| `--txt-dir` | Directory containing `*.txt` plain-text transcripts (optional) |
| `--diarization-dir` | Directory containing `*.diarization.json` files |
| `--audio-dir` | Directory containing playback audio files |
| `--original-dir` | Directory containing original source media (optional) |
| `--manifest` | JSON manifest mapping file IDs to metadata (optional) |
| `--title` / `--subtitle` | Page title and subtitle |
| `--storage-key` | `localStorage` namespace for state persistence |
| `--known-speaker` | Repeatable; `"Name"` auto-assigns a color, `"Name=#hex"` sets one explicitly |
| `--material-final` / `--material-rough` | Repeatable material classification labels used for filtering |

The output is a single self-contained HTML file with no external dependencies. Open it in a browser to review, flag, and annotate turns; the export button produces a report of all flagged rows with reasons and notes.

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

### `${CLAUDE_SKILL_DIR}` is not substituted

Script paths in this skill use `${CLAUDE_SKILL_DIR}` — the skill's own directory, which Claude Code substitutes when the skill loads. If a command reaches you with the literal `${CLAUDE_SKILL_DIR}` (some runtimes don't substitute), resolve the skill directory in this order:

1. The skill-load envelope: `Base directory for this skill: <path>` → `<path>` is the skill directory.
2. No envelope → find candidates and pick the one this session's available-skills list points to (installed copies can lag a source checkout):
   `find ~/.claude ~/.claude-profiles ~/.codex ~/workspace -maxdepth 7 -type d -name asr-transcribe-to-text 2>/dev/null | head -5`

Substitute the resolved absolute path for `${CLAUDE_SKILL_DIR}` everywhere in this document.

## Bundled Resources

**Scripts:**
- `resolve_media_input.py` — Resolve local paths, direct media URLs, and podcast/web pages into validated local media files
- `prepare_asr_input.py` — Merge multi-segment recordings + normalize for ASR (16 kHz mono), optional pitch-preserved speedup for metered uploads; self-verifies duration math and splice boundaries
- `transcribe_local_mlx.py` — Local MLX transcription (macOS ARM64, PEP 723 deps)
- `speaker_transcribe.py` — **DEFAULT pipeline**: decoupled multi-speaker transcription (full-audio Qwen3-ASR + whisper word timing + pyannote diarization, aligned) → speaker-labeled transcript + CSV; `--no-diarization` plain-text fast path; `--text-file` for remote/pre-made ASR text
- `align_speakers.py` — Decoupled alignment core (stdlib): maps full transcript onto whisper word lattice + pyannote segments; usable standalone for debugging
- `word_timestamps_whisper.py` — mlx-whisper word-level timestamps → JSON timing lattice (Apple Silicon)
- `speaker_transcribe_cascade.py` — LEGACY cut-then-transcribe variant (extremely noisy / heavy-overlap audio only)
- `diarize_speakers.py` — Speaker diarization alone (pyannote 3.1 @ MPS) → per-segment JSON
- `voiceprint_id.py` — CAM++ voiceprint enroll/match: map anonymous SPEAKER_xx to real names
- `overlap_merge_transcribe.py` — Chunked transcription with overlap merge (remote API fallback)
- `generate_audit_html.py` — Build a self-contained HTML audit/review page from speaker-transcribe CSV outputs

**References:**
- `decoupled_speaker_alignment.md` — The default architecture: why decouple, alignment algorithm, trust signals, failure modes
- `speaker_diarization.md` — Production pitfalls: over-segmentation, mic-domain effects, when to distrust labels; legacy cascade notes
- `voiceprint_speaker_id.md` — CAM++ speaker ID: enroll/match, threshold+margin gates, the acoustic-domain caveat, bootstrap
- `local_mlx_guide.md` — Performance benchmarks, max_tokens truncation, model compatibility
- `whisper_word_timestamps.md` — mlx-whisper word timing: the timing leg of the default pipeline; standalone subtitle/AV-alignment recipe
- `overlap_merge_strategy.md` — Why naive chunking fails, fuzzy merge algorithm
