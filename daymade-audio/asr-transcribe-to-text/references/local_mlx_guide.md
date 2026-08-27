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
| Model revision | Script-pinned immutable HuggingFace commit | Remote revisions must be full commit SHAs; branch/tag names are rejected. Custom local model directories are content-addressed from their files instead of trusting a caller label |
| chunk_duration | `1200` seconds | The pinned Qwen3 implementation already splits long audio near low-energy boundaries at about 20 minutes |
| max_tokens | `8192` **per chunk** | About twice the observed 20-minute Chinese requirement; bounds KV-cache growth and repetition loops |
| Audio format | WAV 16kHz mono PCM | Best compatibility with ASR models |

The built-in immutable revision resolves its exact local Hugging Face snapshot
before attempting the network. A warmed machine therefore remains a genuinely
local ASR path even when the proxy or Hugging Face metadata endpoint is down;
first-time model acquisition still uses the same pinned remote revision.

## Performance Benchmarks (M5 Pro 48GB, April 2026)

| Audio Length | Inference Time | Speed | Chars | Tokens |
|-------------|---------------|-------|-------|--------|
| 1 min | 3.7s | 16x realtime | 295 | ~180 |
| 5 min | 11.1s | 27x realtime | 1,633 | ~980 |
| 15 min | 50.5s | 17.8x realtime | 5,074 | ~3,045 |
| 123 min | 502s (8m22s) | 14.7x realtime | 40,347 | 24,337 |
| 96 min | 409s (6m48s) | 14.1x realtime | 30,018 | 18,214 |

Model load: ~4s (cached), ~130s (first download).

## Critical: `max_tokens` is per chunk, not per recording

The pinned `mlx-audio 0.3.1` Qwen3-ASR implementation calls
`_generate_single_chunk(..., max_tokens=max_tokens)` inside its chunk loop. The
same limit is therefore available to **every** roughly 20-minute chunk. Passing
`200000` does not give a five-hour recording one shared 200K budget; it permits
each chunk to grow toward 200K tokens.

This distinction is the resource boundary. A verified failure on 2026-08-27
used `200000` on a 4h39m recording: one MLX worker remained inside GPU
generation for more than nine hours, reached a 33.4 GB physical footprint
(44.0 GB peak), and produced no final transcript because the caller only wrote
after the whole recording returned.

The bundled script now keeps `8192` as the default per-chunk budget and rejects
values above `16384` unless `--allow-high-token-budget` is stated explicitly.
If a chunk reaches the ceiling, the script fails that chunk instead of shipping
a possibly repeated or truncated transcript. Do not double the limit blindly:
first inspect whether that chunk contains unusually dense speech or a
music/silence repetition loop.

## Chunk checkpoints and recovery

The bundled script reproduces the pinned upstream low-energy chunking before
calling the model, then commits each chunk atomically under
`<output-dir>/_mlx_checkpoints/`. The model still loads once; only the generation
cache resets between chunks. Input identity includes the full source-audio
SHA-256 in addition to path and metadata, so a same-size replacement with a
restored mtime cannot reuse another recording's checkpoint. Identity also binds
the transcriber script bytes, splitter contract, pinned dependency versions,
sample rate, quality policy, generation parameters, and immutable model
revision. Any producer/model/contract change selects a new checkpoint namespace;
the older successful chunks remain on disk but are not mislabeled as output from
the new producer. On a retry with the same complete contract, completed chunk
hashes are verified and skipped.

Resource bounds are not treated as transcript quality. Before committing a
chunk and again before publishing the joined transcript, the script measures
the ratio of unique 12-character alphanumeric windows. Text of at least 400
normalized characters below `0.20` is rejected as a repetition loop even if
generation stopped below the token ceiling. The quality-policy version is part
of checkpoint identity, preventing unchecked older parts from being resumed.

The speaker orchestrator has a separate outer cache for Qwen text, Whisper
words, and pyannote segments. Each artifact has a provenance sidecar containing
the source-audio SHA-256, producer-script SHA-256, semantic parameters, and
artifact SHA-256. Source and producer identities are frozen before each leg;
if either changes before publication, the result is rejected instead of being
signed with the later bytes. Schema-v1 sidecars are invalidated so a prior
post-run signature cannot survive this repair. Missing or mismatched provenance
reruns that leg; an existing file alone is not completion. Completed checkpoint
entry `i` must name exactly `chunk-{i:04d}.txt`, not merely any chunk-shaped
filename. After all four final artifacts are written, the
speaker orchestrator atomically commits `<stem>.receipt.json`; it binds source
bytes, final TXT/CSV/diarization/alignment hashes, all producer-script hashes,
semantic parameters, and the pinned model/dependency contract. Downstream
automation must validate that receipt rather than treating alignment existence
as completion.

Expected long-run progress looks like:

```text
Chunk 1/14 starting at 0.0s (max_tokens=8192)
Chunk 1/14 committed: 6310 chars, 3812 tokens
Chunk 2/14 starting at 1198.4s (max_tokens=8192)
```

A missing/corrupt completed part fails fast. A crash while one chunk is running
leaves earlier parts intact and reruns only the incomplete chunk. The final
`.txt` is still an atomic all-chunks projection, so downstream readers never
mistake a partial recording for a complete transcript.

Managed callers pass `--owner-pid`; the MLX worker exits with its checkpoints
intact if that supervisor disappears. `speaker_transcribe.py` separately runs
each uv child in a process group, prints a heartbeat, and terminates the whole
group on timeout or parent termination. These two protections cover both the
normal timeout path and the orphan-worker path.

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
