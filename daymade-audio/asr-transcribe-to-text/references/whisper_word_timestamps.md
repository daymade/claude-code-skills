# Word-Level Timestamps with mlx-whisper

Qwen3-ASR (both paths in SKILL.md) decodes plain text with **no timing information**. When the task needs to know *when* each word is spoken — subtitle generation, aligning voiceover lines to video shots, per-clip captioning — switch to a whisper-family model: whisper exposes cross-attention-based word alignment, and `mlx-whisper` runs it natively on Apple Silicon.

## Recipe

```python
# /// script
# dependencies = ["mlx-whisper"]
# ///
import mlx_whisper

result = mlx_whisper.transcribe(
    "audio_16k_mono.wav",                                  # same 16kHz mono WAV prep as SKILL.md Step 2
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
    language="zh",
    word_timestamps=True,
    initial_prompt="<domain terms: product names, technical vocabulary>",
)
words = [w for seg in result["segments"] for w in seg.get("words", [])]
# each w: {"word": str, "start": float, "end": float}
```

- Model weights: `mlx-community/whisper-large-v3-turbo` (~1.6GB, downloads on first run; a local directory path also works as `path_or_hf_repo`).
- `initial_prompt` is whisper's domain-priming channel — list the proper nouns and technical vocabulary likely to appear. It measurably reduces homophone errors on domain-heavy speech.

## Why large-v3-turbo here, despite the "Not Recommended" note

`local_mlx_guide.md` lists whisper large-v3-turbo as not recommended — that verdict is about **pure transcription quality** (Qwen3-ASR has lower Chinese WER, still true). But for timestamp/alignment tasks Qwen3-ASR is not an option at all, so the comparison flips:

- turbo's distilled decoder (4 layers vs 32) keeps it fast on MPS;
- with `initial_prompt` priming, Chinese output on short narrated videos was sufficient in practice to pair words with visuals;
- if transcript fidelity also matters downstream, run Qwen3-ASR separately for the text and whisper only for the timing.

## The segment-vs-word granularity trap (short videos)

On short-form videos (15–40s, hard cuts every 1.5–2.5s), whisper often returns the **whole clip as one segment** — segment-level timestamps are useless for per-shot work. Observed on real batches:

- Always set `word_timestamps=True` and work from the flattened word list, not `segments`.
- Assign each word to a time window by its **midpoint**: `start <= (w["start"] + w["end"]) / 2 < end`. Join the words per window to get that window's line. Midpoint assignment avoids double-counting words that straddle a cut.

## Pairing with scene detection (audio-visual alignment)

The visual side of alignment — shot boundaries — pairs well with ffmpeg's scene filter:

```bash
ffmpeg -i in.mp4 -vf "select='gt(scene,0.3)',showinfo" -f null -
# parse `pts_time:` from stderr; threshold 0.3 is stable for hard cuts in montage-style videos
```

Then extract one representative frame per shot at its midpoint (`ffmpeg -ss <mid> -frames:v 1`).

Why not PySceneDetect: its OpenCV backend raises `VideoOpenFailure` on non-ASCII (e.g. CJK) file paths on macOS, and symlinking to an ASCII path did not resolve it in practice. The ffmpeg filter is immune to path encoding.

## Music-only clips

The repetition-loop hallucination described in SKILL.md `## Batch Transcription` applies to whisper too: a BGM-only clip yields junk words with confident timestamps. The unique-word-ratio check and per-file timeout patterns from that section carry over unchanged.
