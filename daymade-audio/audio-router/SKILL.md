---
name: audio-router
description: >-
  Routes audio: StepFun ASR/语音识别, StepFun TTS/配音, transcript/妙记→会议纪要,
  merge/review minutes. Reads one bundled specialist; generic ASR and correction
  stay direct.
---

# Daymade audio router

Choose a bundled specialist by the requested result. Locate **this loaded**
`audio-router/SKILL.md` in the active catalog or invocation, follow symlinks
to its canonical path, and verify its parent is `audio-router`. Its parent's
parent is the audio suite root. Resolve the selected relative path against
the router directory and verify it is a direct sibling `SKILL.md` under that
root. Do not anchor resolution to the task's working directory or a remembered
cache path. `${CLAUDE_PLUGIN_ROOT}` may exist in Claude Code but is absent in
Codex; stop if the active Router path is ambiguous.

Read the selected child `SKILL.md` **in full** before acting. Continue a
truncated read and load that child's task-required references. The children
and their scripts remain installed; only their automatic catalog entries are
hidden. Claude users can still invoke their original
`/daymade-audio:<child>` commands manually.

| Requested result | Read this exact file |
|---|---|
| Transcribe with StepFun `stepaudio-3-asr-max`, obtain its independent speaker timeline, migrate older StepFun ASR, or diagnose the misleading “model not supported” endpoint error | `../stepfun-asr/SKILL.md` |
| Synthesize Chinese/Japanese speech or voiceover with StepFun, including prosody, emotions, or a compatible cloned voice | `../stepfun-tts/SKILL.md` |
| Turn an existing meeting transcript or 妙记 text into 会议纪要; merge multiple minute drafts, review existing minutes against the transcript, or reconcile speaker labels from verified evidence | `../meeting-minutes-taker/SKILL.md` |

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
