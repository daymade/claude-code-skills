# Speaker Diarization (Multi-Speaker Transcription)

The default long-recording pipeline produces speaker-labeled transcripts by
**decoupling**: whisper.cpp + Silero VAD text/timing, pyannote speech/speaker
segments, then late fusion. `speaker_transcribe.py` remains the short/medium
Qwen3-ASR + mlx-whisper alternative. Architecture, alignment algorithm, and trust signals:
**`references/decoupled_speaker_alignment.md`** — read that first. This file
carries the production pitfalls (architecture-independent) and the legacy
cascade notes.

```
16kHz mono PCM16 WAV
  1. Source-time base blocks (+2s overlap) -> checkpoint units
  2. whisper.cpp + Silero VAD              -> speech-only text + time
  3. pyannote diarization                   -> segments {start,end,speaker}
  4. late fusion                            -> [start-end] SPEAKER_xx + text
```

## Short/medium alternative: bundled Qwen pipeline

`scripts/speaker_transcribe.py` runs all four steps in one command:

```bash
uv run scripts/speaker_transcribe.py INPUT.wav OUTPUT_DIR --device mps
```

It writes `<stem>.txt` (readable), `<stem>.csv`
(`file,start,end,duration,speaker,text` — the tabular form review UIs and the
voiceprint step consume), `<stem>.diarization.json`, and
`<stem>.alignment.json` (provenance + `anchored_ratio` trust signal), and
`<stem>.receipt.json` (atomic final bundle contract; required for automated completion).
Intermediate legs are cached under `OUTPUT_DIR/_align/`; `--force` redoes them.

## The pieces (if you need to customize)

1. **16k mono WAV** — pyannote, whisper, and Qwen3-ASR all want 16 kHz:
   `ffmpeg -i in.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 in.wav`
2. **Session text** — `transcribe_local_mlx.py` (or any ASR; pass the text
   via `--text-file` to skip this leg).
3. **Word timing** — `word_timestamps_whisper.py in.wav --output-dir DIR`
   (mlx, Apple Silicon).
4. **Diarize** — `diarize_speakers.py in.wav diar.json --device mps`
   (needs an HF token; see the script header).
5. **Align** — `align_speakers.py --text T --words W --diarization D
   --out-dir OUT --stem NAME` (standalone for debugging/custom chains).

## Long-audio facts verified on real production audio

- A 4h39m37.75s body-mic WAV disproved fixed Qwen generation windows: 20,
  10, and 5 minute variants each hit the 8192-token ceiling on different source
  regions. Short canaries had passed; they did not establish long-form safety.
- whisper.cpp without VAD also hallucinated repeated text over silence. With
  Silero VAD v6.2.0, the same source exposed 12,609.78 seconds of speech and
  excluded roughly 1h09m28s of silence/noise before ASR. Two known failure
  windows then transcribed without the previous loops.
- `-mc 0` (no stored prior-window text context) stopped cross-window repetition
  propagation. Compression/logprob/no-speech fallbacks remain enabled.
- Outer blocks are cut by FFmpeg on the **original source timeline**. Do not use
  whisper.cpp `--offset-t` to checkpoint a VAD-compressed full file: with VAD
  enabled, its offset applies after speech compaction and no longer names the
  original source time.
- Each block owns decoded segments by source-time midpoint. Adjacent blocks may
  still segment the same boundary phrase differently, so seam-only temporal +
  text similarity de-duplication is required and independently tested.
- A recorder file can outlive the business session. Persist an explicit
  evidence-backed `--end-at` boundary instead of forcing post-meeting ambient
  audio into the meeting transcript.

Official references: [whisper.cpp VAD](https://github.com/ggml-org/whisper.cpp),
[faster-whisper VAD/long-form options](https://github.com/SYSTRAN/faster-whisper),
[WhisperX late-fusion architecture](https://github.com/m-bain/whisperX), and
[NeMo long-audio buffered inference](https://docs.nvidia.com/nemo/speech/nightly/asr/inference.html).

## Key facts & pitfalls (from production)

- **All on accelerated paths; no silent CPU fallback.** whisper.cpp uses Metal
  on Apple Silicon; pyannote uses explicit MPS. Runtime failures propagate
  instead of turning a minutes-long job into an unattended many-hour CPU run.
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
near-field speaker beats session-level ASR. Everything else uses the decoupled
default.

## Alternative engines (context, not a benchmark)

The short/medium path pairs pyannote (diarization) + mlx-whisper (timing) +
Qwen3-ASR (text). The long path pairs whisper.cpp/Silero with pyannote. Other
stacks exist (FunASR Paraformer bundles diarization + transcription; NeMo
Sortformer is an end-to-end diarizer; cloud ASR services do the whole chain
server-side). They have not been benchmarked head-to-head here — see
`decoupled_speaker_alignment.md` § Alternatives for the landscape.
