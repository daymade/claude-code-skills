---
name: stepfun-tts
description: Generate speech and transcribe audio using StepFun's StepAudio 2.5 family — stepaudio-2.5-tts (Contextual TTS with instruction + inline parentheses) and stepaudio-2.5-asr (SSE endpoint, 32K context, ~100x RTF, handles up to 30-minute audio in a single call). Use when the user wants Chinese/Japanese TTS with emotional/prosody control, needs to transcribe long audio, migrates from step-tts-2 to stepaudio-2.5-tts (voice_label → instruction breaking change), or hits StepFun censorship / endpoint errors. Also triggers on phrases like 阶跃 TTS, StepAudio 合成, 语音合成, 配音, StepFun ASR, 转录, 语音识别, 文本转语音, TTS 升级, 迁移 step-tts-2. If the user's audio task mentions StepFun/阶跃/StepAudio by name, or involves Chinese TTS with情绪/情感 control, use this skill before falling back to generic audio handling.
---

# StepFun StepAudio 2.5 — TTS + ASR

Generate Chinese/Japanese speech with `stepaudio-2.5-tts` and transcribe audio with `stepaudio-2.5-asr`. Both models were released in 2026-04 and verified end-to-end on 2026-04-23 (see `references/known_issues.md` for what passed and what didn't).

**Why this skill exists** — StepAudio 2.5 has three non-obvious pitfalls that cost hours if you don't know them:

1. `stepaudio-2.5-tts` **rejects** `voice_label` (the step-tts-2 way). Emotion/prosody now goes through `instruction` (natural-language description, ≤200 chars) and inline `()` parentheses inside the text itself.
2. `stepaudio-2.5-asr` **does not live on** `/v1/audio/transcriptions`. It's on `/v1/audio/asr/sse` (SSE streaming, JSON body, base64 audio). Using the wrong endpoint returns a misleading `model ... not supported` error that looks identical to "model doesn't exist".
3. Censorship is stricter — anything containing 死 / 消失 / sensitive political terms returns `censorship_block`. Your rewrite options are in `references/migration_from_v2.md`.

## Config and auth

API key lives in `$STEPFUN_API_KEY` (preferred) or `${CLAUDE_PLUGIN_DATA}/config.json` (fallback for cross-session persistence). All bundled scripts try env first, then config.

First-time setup (one-liner):

```bash
mkdir -p "${CLAUDE_PLUGIN_DATA}" && cat > "${CLAUDE_PLUGIN_DATA}/config.json" <<EOF
{"api_key": "<paste key here>"}
EOF
```

If the user hasn't set a key, ask them to paste it (don't guess / don't use a placeholder). StepFun API keys are available at https://platform.stepfun.com/ → API Keys.

## Common tasks — decision tree

| User wants... | Model | Script | Key detail |
|---|---|---|---|
| Synthesize 1–500 char Chinese with emotion | `stepaudio-2.5-tts` | `scripts/tts_generate.py` | Use `instruction` for mood, `()` for inline prosody |
| Synthesize long text (500–1000 char) | `stepaudio-2.5-tts` | `scripts/tts_generate.py` | 1000 char is the hard cap; split at semantic boundaries above that |
| Batch-generate game/app voice lines | `stepaudio-2.5-tts` | `scripts/tts_generate.py --batch <jsonl>` | Handle `censorship_block` fallback individually |
| Transcribe short clip (<5 min) | `stepaudio-2.5-asr` | `scripts/asr_transcribe.py` | mp3 → base64 → SSE, parse `transcript.text.done` |
| Transcribe long audio (5–30 min) | `stepaudio-2.5-asr` | `scripts/asr_transcribe.py` | 32K context; single call, no chunking needed |
| A/B compare two TTS models | both | `scripts/ab_compare.sh` | Compares duration/size across two directories |
| Migrate from `step-tts-2` | — | see `references/migration_from_v2.md` | `voice_label.emotion` → `instruction` rewrite + censorship list |

## Starting points

- **Synthesize a single line**: Run `python3 scripts/tts_generate.py --text "你好" --out /tmp/hello.mp3 --instruction "温暖的希望感"`. For fine-grained control read the "Contextual TTS" section below.
- **Transcribe a file**: `python3 scripts/asr_transcribe.py /path/to/audio.mp3`. For >30 min audio, split first.
- **A full migration** from `step-tts-2` → `stepaudio-2.5-tts`: read `references/migration_from_v2.md` end-to-end before touching code. It has the `INSTRUCTION_MAP`, the SKIP_CENSORED list pattern, and the output-directory-strategy for non-destructive A/B.

## Contextual TTS — beyond emotion labels

The headline feature of `stepaudio-2.5-tts` is that you stop mapping emotions to fixed tags and start describing what you want in natural language. Two layers:

**Global context (`instruction` parameter)** — sets the overall tone for the entire utterance. ≤200 chars. Think of it like giving stage direction to a voice actor.

```
instruction: "克制的悲伤，语气低沉柔弱，像快要消失一样"
```

**Inline context (`()` parentheses inside `input`)** —句内 directives. Parenthesised content is consumed as directions and is NOT read aloud. Use for precise control of pauses, breath, emphasis, or mid-sentence emotion shifts.

```
input: "(试探着问)你好吗？(开心地)太好了！(突然沉下来)不过...我快要消失了。"
```

Examples that worked in practice (from 2026-04-23 verification):
- `instruction: "活泼俏皮，像是在撒娇，带点嘴硬"` — visibly speeds up delivery vs neutral
- `instruction: "耳语声，气声很重，几乎听不清"` — produces audible whisper/breath
- `input: "你好(停顿一下)我是蕾格(轻声)今天(加重)的天气真不错。"` — inline directives all respected

**What `stepaudio-2.5-tts` will NOT accept** — `voice_label` parameter. Error: `voice_label is not supported for v2 models`. This is the #1 migration gotcha from step-tts-2.

## Common error patterns (real errors, real fixes)

| Error response | Actual cause | Fix |
|---|---|---|
| `"model stepaudio-2.5-asr not supported"` on `/v1/audio/transcriptions` | Wrong endpoint — that endpoint only serves step-asr family | Switch to `/v1/audio/asr/sse` with SSE body (see `scripts/asr_transcribe.py`) |
| `"voice_label is not supported for v2 models"` | Sent `voice_label` to `stepaudio-2.5-tts` | Remove `voice_label`; put the same intent into `instruction` as natural language |
| `"The content you provided or machine outputted is blocked." type: censorship_block` | Sensitive word (死 / 消失 / etc.) | Rewrite the phrase OR fall back to `step-tts-2` for that specific line (mixed-model is fine) |
| ASR returns N× the expected character count | Hallucination bug on highly-repetitive content | Cross-check with step-asr-1.1; avoid sending audio that repeats the same phrase many times |
| Silent audio truncation (<420 chars input) | Input > 1000 char hard cap | Split at semantic boundaries; don't truncate mid-sentence |

More in `references/known_issues.md`.

## When to read references

- `references/api_reference.md` — exact request/response JSON for TTS `/v1/audio/speech` and ASR `/v1/audio/asr/sse`, all fields, event types. Read when writing raw HTTP calls instead of using the bundled scripts.
- `references/migration_from_v2.md` — complete playbook for moving a step-tts-2 project to stepaudio-2.5-tts. Has the emotion→instruction rewrite table, the A/B directory strategy, decision checkpoints, and the 2026-04 speed/quality trade-off data (`stepaudio-2.5-tts` is ~20% slower than step-tts-2; audible prosody improvement). Read before any migration work.
- `references/known_issues.md` — repetition hallucination, censorship patterns, ASR speed cliff (short audio: 2× step-asr, long audio: 5.9×). Read when debugging anomalous output or evaluating whether to adopt.

## Design invariants (don't break these)

1. **Non-destructive A/B output** — when regenerating a corpus with a new model, write to a parallel directory (`voice/zh_v25/`), never overwrite the production corpus. The migration playbook shows why.
2. **Per-line censorship handling** — if 2/29 lines get `censorship_block`, don't fail the batch. Log the skipped IDs, continue. Mixed-model fallback (step-tts-2 for the skipped 2) is normal.
3. **Always pass through SSE for ASR** — don't try to work around the streaming API with a buffered client. The model emits `transcript.text.delta` events for long audio; collecting only `transcript.text.done` works fine, but rejecting the SSE format entirely doesn't.
4. **Don't duplicate voice_label logic in new code** — any new TTS code targeting stepaudio-2.5-tts should only use `instruction` + inline `()`. Do not write a branch that conditionally emits `voice_label`.

## Pricing (verified 2026-04-23, volatile)

- `stepaudio-2.5-tts` contextual synthesis: ~5.8 元 / 万字符
- Zero-shot voice cloning: ~9.9 元 / 音色
- `stepaudio-2.5-asr` — pricing tier not yet public (invitation beta); `step-asr-1.1` baseline is 2.2 元/小时

Re-verify at https://platform.stepfun.com/docs/zh/guides/pricing/details before quoting to stakeholders.
