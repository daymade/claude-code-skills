# Speaker Diarization (Multi-Speaker Transcription)

The default pipeline produces speaker-labeled transcripts by **decoupling**:
full-audio Qwen3-ASR text + whisper word timing + pyannote segments, aligned
after the fact. Architecture, alignment algorithm, and trust signals:
**`references/decoupled_speaker_alignment.md`** — read that first. This file
carries the production pitfalls (architecture-independent) and the legacy
cascade notes.

```
16kHz mono WAV
  1. Qwen3-ASR full audio       -> text (context intact)
  2. mlx-whisper word timestamps -> time lattice
  3. pyannote 3.1 diarization    -> segments {start, end, speaker}
  4. align                       -> [start-end] SPEAKER_xx: text
```

## Fastest path: the bundled pipeline

`scripts/speaker_transcribe.py` runs all four steps in one command:

```bash
uv run scripts/speaker_transcribe.py INPUT.wav OUTPUT_DIR --device mps
```

It writes `<stem>.txt` (readable), `<stem>.csv`
(`file,start,end,duration,speaker,text` — the tabular form review UIs and the
voiceprint step consume), `<stem>.diarization.json`, and
`<stem>.alignment.json` (provenance + `anchored_ratio` trust signal).
Intermediate legs are cached under `OUTPUT_DIR/_align/`; `--force` redoes them.

## The pieces (if you need to customize)

1. **16k mono WAV** — pyannote, whisper, and Qwen3-ASR all want 16 kHz:
   `ffmpeg -i in.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 in.wav`
2. **Full-audio text** — `transcribe_local_mlx.py` (or any ASR; pass the text
   via `--text-file` to skip this leg).
3. **Word timing** — `word_timestamps_whisper.py in.wav --output-dir DIR`
   (mlx, Apple Silicon).
4. **Diarize** — `diarize_speakers.py in.wav diar.json --device mps`
   (needs an HF token; see the script header).
5. **Align** — `align_speakers.py --text T --words W --diarization D
   --out-dir OUT --stem NAME` (standalone for debugging/custom chains).

## Key facts & pitfalls (from production)

- **All on GPU; CPU forbidden as the primary path.** pyannote 3.1 @ MPS runs
  ~16× realtime on Apple Silicon; Qwen3-ASR @ MLX is 15–27×. The scripts only
  drop to CPU if a specific MPS op is unimplemented for one file — never by
  default.
- **HF token required** — pyannote models are gated. Accept the terms at
  `hf.co/pyannote/speaker-diarization-3.1` and `huggingface-cli login` once.
  The Step 3 state machine in SKILL.md handles the no-token case: fail the
  first time with setup steps, warn-and-continue plain-text afterward.
- **`anchored_ratio` is the trust signal.** ≥ 0.8 normal; < 0.5 means the
  Qwen3 text and whisper lattice diverged heavily — verify labels against the
  audio before trusting them.
- **Silence is already gone.** pyannote's internal VAD emits only speech
  segments, so a 30-min recording may total ~8 min of speech — the segments
  won't cover the whole timeline, and that's correct, not a bug.
- **One person can split into 2+ `SPEAKER_xx`** (over-segmentation),
  especially in noisy or far-field audio. Expected — voiceprint identity
  (below) collapses the fragments back to one person.
- **Diarization quality is scene-dependent.** Balanced round-table audio
  diarizes cleanly; a body-worn / lapel mic where one near-field speaker
  dominates and others are far-field is harder. Verify against the transcript
  content before trusting labels.

## Output: speaker labels are anonymous

`SPEAKER_00 / SPEAKER_01` are arbitrary and **per-file** — SPEAKER_00 in file A
is not the same person as SPEAKER_00 in file B. To map them to **real names**,
or to **unify a speaker across files**, you need a voiceprint reference set →
**`references/voiceprint_speaker_id.md`**.

## Legacy: the cascade variant

`scripts/speaker_transcribe_cascade.py` is the old cut-then-transcribe path
(diarize → slice audio per turn → ASR each slice → stitch). It breaks ASR
context at every cut and measurably lowers text quality; on monologue it can
also manufacture a second fake speaker. Kept for one narrow case: extremely
noisy / heavy-overlap audio where per-slice isolation of a dominant
near-field speaker beats full-audio ASR. Everything else uses the decoupled
default.

## Alternative engines (context, not a benchmark)

This path pairs pyannote (diarization) + whisper (timing) + Qwen3-ASR (text)
because the skill already ships the Qwen3-ASR MLX path and it's strong on
Chinese. Other stacks exist (FunASR Paraformer bundles diarization +
transcription; NeMo Sortformer is an end-to-end diarizer; cloud ASR services
do the whole chain server-side). They haven't been benchmarked head-to-head
here — see `decoupled_speaker_alignment.md` § Alternatives for the landscape.
