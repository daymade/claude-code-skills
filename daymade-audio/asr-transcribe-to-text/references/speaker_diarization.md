# Speaker Diarization (Multi-Speaker Transcription)

Qwen3-ASR (and the default transcribe path) returns one flat block of text — fine
for a single speaker, useless for a meeting / interview / podcast where you need
to know **who said what**. This is the path for multi-speaker recordings.

## The two halves

Diarization answers *"who spoke when"* (pyannote); ASR answers *"what was said"*
(Qwen3-ASR). Neither does the other's job — run both and stitch:

```
16kHz mono WAV
  1. diarize (pyannote 3.1 @ MPS)          -> segments {start, end, speaker}
  2. merge same-speaker segments <= 2s apart -> turns
  3. slice each turn's audio + transcribe per slice (Qwen3-ASR MLX)
  4. stitch                                 -> [start-end] SPEAKER_xx: text
```

## Fastest path: the bundled pipeline

`scripts/speaker_transcribe.py` runs all four steps in one command:

```bash
uv run scripts/speaker_transcribe.py INPUT.wav OUTPUT_DIR --device mps
```

It writes `<stem>.txt` (readable) and `<stem>.csv` (`file,start,end,duration,speaker,text`
— the tabular form review UIs and the voiceprint step consume). Use this unless you
need to customize a step, in which case assemble it from the pieces below.

## The pieces (if you need to customize)

1. **16k mono WAV** — both pyannote and Qwen3-ASR want 16 kHz:
   `ffmpeg -i in.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 in.wav`
2. **Diarize** — `uv run scripts/diarize_speakers.py in.wav diar.json --device mps`
   (needs a HF token; see the script header).
3. **Merge turns** — same speaker, gap ≤ 2s (`merge_turns()` in speaker_transcribe.py).
4. **Slice + transcribe** — cut each turn (`ffmpeg -ss START -to END`) and batch the
   slices through `transcribe_local_mlx.py` (model loads once).
5. **Stitch** — speaker + text into transcript / CSV.

## Key facts & pitfalls (from production)

- **All on GPU; CPU forbidden as the primary path.** pyannote 3.1 @ MPS runs ~16×
  realtime on Apple Silicon; Qwen3-ASR @ MLX is 15–27×. The scripts only drop to
  CPU if a specific MPS op is unimplemented for one file — never by default.
- **HF token required** — pyannote models are gated. Accept the terms at
  `hf.co/pyannote/speaker-diarization-3.1` and `huggingface-cli login` once.
- **Merge < 2s is not cosmetic.** Without it you get hundreds of sub-second
  fragments, each its own transcription call and its own unreadable line.
- **Transcribe per-turn, not whole-file** — that's the only way each text block
  carries a speaker. The model still loads once; only inference repeats.
- **Silence is already gone.** pyannote's internal VAD emits only speech segments,
  so a 30-min recording may total ~8 min of speech — the segments won't cover the
  whole timeline, and that's correct, not a bug.
- **One person can split into 2+ `SPEAKER_xx`** (over-segmentation), especially in
  noisy or far-field audio. Expected — voiceprint identity (below) collapses the
  fragments back to one person.
- **Diarization quality is scene-dependent.** Balanced round-table audio diarizes
  cleanly; a body-worn / lapel mic where one near-field speaker dominates and others
  are far-field is harder. Verify against the transcript content before trusting labels.

## Output: speaker labels are anonymous

`SPEAKER_00 / SPEAKER_01` are arbitrary and **per-file** — SPEAKER_00 in file A is
not the same person as SPEAKER_00 in file B. To map them to **real names**, or to
**unify a speaker across files**, you need a voiceprint reference set →
**`references/voiceprint_speaker_id.md`**.

## Alternative engines (context, not a benchmark)

This path pairs pyannote (diarization) with Qwen3-ASR (transcription) because the
skill already ships the Qwen3-ASR MLX path and it's strong on Chinese. Other stacks
exist (e.g. FunASR Paraformer bundles diarization + transcription; NeMo has its own
diarizer). They haven't been benchmarked head-to-head here — pyannote + Qwen3 is
what's *verified working* in this skill, not a claim that it's optimal for your audio.
