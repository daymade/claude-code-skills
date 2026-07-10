# Local MLX Transcription Guide

## Platform Requirements

- macOS on Apple Silicon (M1/M2/M3/M4/M5+)
- Python 3.10+
- `uv` package manager
- ~3GB disk for model weights (first download)

## Verified Dependency Stack

The bundled `scripts/transcribe_local_mlx.py` pins the local MLX stack because newer resolver output has broken Qwen3-ASR model loading in practice.

| Package | Version | Why |
|---------|---------|-----|
| `mlx-audio` | `0.3.1` | Known-good Qwen3-ASR loader |
| `mlx-lm` | `0.30.5` | Compatible transitive loader stack |
| `transformers` | `5.0.0rc3` | Avoids tokenizer registration failure seen with newer 5.x builds |

Run this before a long transcription:

```bash
uv run scripts/transcribe_local_mlx.py --smoke-test
```

Expected output includes:

```text
Dependency stack: mlx-audio 0.3.1, mlx-lm 0.30.5, transformers 5.0.0rc3
Model loaded in ...
Smoke test OK: model loaded
```

If the dependency stack differs, the agent is probably running an installed/stale copy or bypassing the bundled script.

## Recommended Configuration

| Setting | Value | Why |
|---------|-------|-----|
| Model | `mlx-community/Qwen3-ASR-1.7B-8bit` | 8-bit quantized, fast inference, good quality |
| max_tokens | `200000` | Default 8192 silently truncates audio >40min |
| Audio format | WAV 16kHz mono PCM | Best compatibility with ASR models |

## Performance Benchmarks (M5 Pro 48GB, April 2026)

| Audio Length | Inference Time | Speed | Chars | Tokens |
|-------------|---------------|-------|-------|--------|
| 1 min | 3.7s | 16x realtime | 295 | ~180 |
| 5 min | 11.1s | 27x realtime | 1,633 | ~980 |
| 15 min | 50.5s | 17.8x realtime | 5,074 | ~3,045 |
| 123 min | 502s (8m22s) | 14.7x realtime | 40,347 | 24,337 |
| 96 min | 409s (6m48s) | 14.1x realtime | 30,018 | 18,214 |

Model load: ~4s (cached), ~130s (first download).

## Critical: max_tokens Truncation

The `model.generate()` method in mlx-audio has `max_tokens=8192` as default. This is a **global budget shared across all audio chunks**, not per-chunk. When exhausted, remaining chunks are silently skipped.

For 123 minutes of Chinese speech:
- Required: ~24,000 tokens
- Default budget: 8,192 tokens
- Result: only first ~40 minutes transcribed, rest silently dropped

Always pass `max_tokens=200000` for any audio longer than 20 minutes.

## Model Weight Compatibility

Two MLX packages exist for Qwen3-ASR. Their weight formats are **incompatible**:

| Package | Use with | Weight Format |
|---------|----------|--------------|
| `mlx-audio` (Blaizzy) | `mlx-community/Qwen3-ASR-1.7B-8bit` | mlx-audio quantization (audio_tower quantized) |
| `mlx-qwen3-asr` (moona3k) | `Qwen/Qwen3-ASR-1.7B` | Own loader (audio_tower NOT quantized) |

Crossing these produces "Missing 297 parameters" error. This skill uses `mlx-audio`.

## Known Failure: Unpinned Newer Dependencies

Failure signature:

```text
AttributeError: 'str' object has no attribute '__module__'
```

Observed root cause: resolving `mlx-audio>=0.3.1` installed `mlx-audio 0.4.4`, `mlx-lm 0.31.3`, and `transformers 5.13.0`; model loading failed before transcription began. The fix is to run the bundled script with its pinned PEP 723 dependencies and confirm `--smoke-test` passes.

## Alternatives Not Recommended

| Approach | Issue |
|----------|-------|
| PyTorch MPS (qwen-asr package) | 97.77% time in GPU↔CPU sync, RTF 5.5-24.5x |
| whisper.cpp large-v3-turbo | High Chinese error rate **for pure transcription** — but when the task needs word-level timestamps (subtitles, audio-visual alignment), whisper is the only local option and Qwen3-ASR cannot do it at all; see `whisper_word_timestamps.md` |
| Official qwen-asr on macOS | Designed for CUDA only |
