---
name: audio-router
description: >-
  Routes StepFun ASR/语音识别, StepFun TTS/配音, transcript/妙记→会议纪要 and
  merge/review minutes; waveform/波形, cutpoint/吞字风险 and tail/尾衰 diagnostics
  use daudio. Reads the selected owner; generic ASR and correction stay direct.
---

# Daymade audio router

Choose the route by the requested result. Locate **this loaded**
`audio-router/SKILL.md` in the active catalog or invocation, follow symlinks
to its canonical path, and verify its parent is `audio-router`. Its parent's
parent is the audio suite root. For a bundled specialist, resolve its relative path against
the router directory and verify it is a direct sibling `SKILL.md` under that
root. Do not anchor resolution to the task's working directory or a remembered
cache path. `${CLAUDE_PLUGIN_ROOT}` may exist in Claude Code but is absent in
Codex; stop if the active Router path is ambiguous.

For the three specialist rows below, read the selected child `SKILL.md`
**in full** before acting. Continue a
truncated read and load that child's task-required references. The children
and their scripts remain installed; only their automatic catalog entries are
hidden. Claude users can still invoke their original
`/daymade-audio:<child>` commands manually.

| Requested result | Read this exact file |
|---|---|
| Transcribe with StepFun `stepaudio-3-asr-max`, obtain its independent speaker timeline, migrate older StepFun ASR, or diagnose the misleading “model not supported” endpoint error | `../stepfun-asr/SKILL.md` |
| Synthesize Chinese/Japanese speech or voiceover with StepFun, including prosody, emotions, or a compatible cloned voice | `../stepfun-tts/SKILL.md` |
| Turn an existing meeting transcript or 妙记 text, with optional participant notes, into 会议纪要; merge multiple minute drafts, review existing minutes against supplied sources, or reconcile speaker labels from verified evidence | `../meeting-minutes-taker/SKILL.md` |

For waveform/波形 analysis, speech cutpoints/吞字风险, or tail energy/尾衰,
read [Acoustic diagnostics](references/acoustic-diagnostics.md) in full before
acting. Resolve this reference inside the canonical router directory; the
direct-sibling check above applies to the three specialist rows. Use the
diagnostic route's runtime checks and recovery path before executing daudio.

Do not select StepFun merely because a user says “transcribe this audio.”
General audio/video transcription, speaker diarization, audio preprocessing,
and subtitles retain the direct `asr-transcribe-to-text` entry. Correcting
recognition mistakes in existing text retains the direct `transcript-fixer`
entry. If the user has a raw meeting recording and needs it filed into its
project, use `meeting-ingest` when installed; this table begins after a
transcript exists. Company-specific voice profiles may have their own TTS
owner; do not substitute StepFun solely from the word “voiceover.”

If a task spans stages, read the owner of each stage before acting. Selecting
a StepFun child does not authorize a paid call or uploading audio. A request
for meeting minutes does not authorize guessing an anonymous speaker's real
identity; use only the evidence the child and project permit.
