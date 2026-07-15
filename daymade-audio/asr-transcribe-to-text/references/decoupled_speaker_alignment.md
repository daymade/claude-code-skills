# Decoupled Speaker Alignment (the default architecture)

The default speaker pipeline never cuts audio before transcription. Three
independent layers are produced and merged afterward:

```
16kHz mono WAV
 ├─ leg 1  Qwen3-ASR full-audio transcript   → best text, no timing
 ├─ leg 2  mlx-whisper word timestamps       → timing lattice (text secondary)
 ├─ leg 3  pyannote diarization              → speaker × time segments
 └─ leg 4  align_speakers.py                 → speaker-labeled transcript
```

## Why decouple (vs the legacy cascade)

The cascade variant (`speaker_transcribe_cascade.py`) diarizes first, cuts the
audio per turn, and transcribes each slice independently. That has three
structural costs:

1. **Lower ASR accuracy.** ASR disambiguates with context — homophones,
   sentence boundaries, trailing particles. Cutting at diarization boundaries
   destroys cross-turn context; short slices are worst.
2. **Spurious speakers on monologue.** A single-speaker recording fed to
   pyannote can come back as `SPEAKER_00`/`SPEAKER_01`, slicing one person
   into two "people" and misleading every downstream consumer.
3. **Two failure modes welded together.** A bad slice boundary and an ASR
   error are indistinguishable in the output and can't be re-run separately.

Decoupling keeps each layer at full strength: Qwen3-ASR sees the whole file
(context intact, best Chinese WER in this skill), whisper only lends its
cross-attention word timing (its Chinese text quality is irrelevant — the
words are a time lattice, not a transcript), pyannote only answers
who-spoke-when.

## The alignment algorithm (`scripts/align_speakers.py`, stdlib only)

1. **Normalize** the Qwen3 transcript and the whisper word stream to plain
   char streams (drop punctuation/whitespace/case; keep an index map back to
   the raw transcript so punctuation can be restored later). Whisper words
   become a per-char time lattice by linear interpolation inside each word.
2. **Anchor**: `difflib.SequenceMatcher` matching blocks between the two char
   streams. Anchored Qwen3 chars inherit the whisper time directly; chars
   between anchors get linearly interpolated times.
3. **Speaker per char**: the pyannote segment containing the char's time;
   chars in inter-segment gaps inherit the nearest segment within 1s
   (pyannote clips boundaries) or the previous char's speaker.
4. **Cut turns** on speaker change or a pause > `--max-gap` (default 2s).
   Turn text is sliced from the ORIGINAL Qwen3 transcript, so punctuation
   survives; trailing sentence punctuation at turn boundaries is absorbed
   into the turn it ends.

## Trust signals

- **`anchored_ratio`** (in `<stem>.alignment.json` + stderr): fraction of
  Qwen3 chars that matched the whisper lattice directly. ≥ 0.8 is normal for
  same-audio transcripts. **< 0.5 means the two transcripts diverged
  heavily** (wrong audio, one ASR failed, heavy music/noise) — the script
  prints a loud warning; verify speaker labels against the audio before
  trusting them.
- **Speaker count sanity**: a two-person interview returning 5 speakers, or a
  monologue returning 2+, means diarization over-segmented (see
  `speaker_diarization.md` § pitfalls). Voiceprint ID collapses fragments.
- **Missing legs**: if whisper returns no words (music-only clip), alignment
  fails for that file loudly rather than emitting unlabeled text silently.

## Failure modes & handling

| Symptom | Cause | Handling |
|---|---|---|
| exit 3 + setup hint | pyannote gated model, no HF token | SKILL.md Step 3 state machine: fail first time, AskUserQuestion, warn-and-continue afterward |
| `anchored_ratio` < 0.5 warning | transcripts diverge | verify labels manually; often a whisper language mismatch or music-only audio |
| one person split into SPEAKER_00/01 | diarization over-segmentation (noisy/far-field) | expected; run `voiceprint_id.py` to collapse |
| music-only clip, looping whisper words | whisper hallucination with confident timestamps | unique-word-ratio warning in leg 2; anchored_ratio will also be low |

## Alternatives & context (July 2026)

- **Cloud ASR with built-in diarization** (Feishu Minutes, iFlytek,
  AssemblyAI, Deepgram): same decoupled idea, run for you, zero setup —
  the pragmatic choice when local setup isn't worth it or the machine
  isn't Apple Silicon.
- **NVIDIA NeMo Sortformer**: end-to-end diarizer, stronger on hard
  multi-speaker audio; heavier to deploy locally than pyannote.
- **End-to-end joint ASR+diarization models** (SpeakerLM et al.): one model
  emits text + speaker, no cascade at all — promising, not yet in local
  production toolchains.

The bundled pyannote + whisper-timing + Qwen3-text trio is what's *verified
working* in this skill, not a claim that it's optimal for every audio.
