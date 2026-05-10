---
name: stepfun-tts
description: Generate Chinese / Japanese speech with StepFun's stepaudio-2.5-tts — Contextual TTS that replaces step-tts-2's `voice_label` with natural-language `instruction` (≤200 chars) plus inline `()` parentheses for句内 prosody. Use when the user wants emotional / prosody control over voice synthesis (whisper, pause, stress, mood pivot mid-sentence), batch-generates game / app voice lines, migrates from `step-tts-2` (the `voice_label → instruction` breaking change), or hits StepFun's stricter 2.5-era censorship (死/消失/political terms). Triggers on 阶跃 TTS, StepAudio 合成, 语音合成, 配音, 文本转语音, TTS 升级, 迁移 step-tts-2. For transcription with the sibling stepaudio-2.5-asr model, use the stepfun-asr skill instead.
---

# StepFun stepaudio-2.5-tts

Generate Chinese / Japanese speech with `stepaudio-2.5-tts` (released 2026-04, verified 2026-04-23). Contextual TTS — emotion and prosody go through natural-language description, not fixed labels.

> Companion: for transcription with `stepaudio-2.5-asr` (the sibling model), use the `stepfun-asr` skill — they share an API key but live on different endpoints with different body shapes.

**Why this skill exists** — StepAudio 2.5 has two non-obvious pitfalls that cost hours if you don't know them:

1. `stepaudio-2.5-tts` **rejects** `voice_label` (the step-tts-2 way). Emotion/prosody now goes through `instruction` (natural-language description, ≤200 chars) and inline `()` parentheses inside the text itself.
2. Censorship is stricter — anything containing 死 / 消失 / sensitive political terms returns `censorship_block`. Your rewrite options are in `references/migration_from_v2.md`.

## Config and auth

API key lives in `$STEPFUN_API_KEY` (preferred) or `${CLAUDE_PLUGIN_DATA}/config.json` (fallback for cross-session persistence). All bundled scripts try env first, then config.

First-time setup (one-liner):

```bash
mkdir -p "${CLAUDE_PLUGIN_DATA}" && cat > "${CLAUDE_PLUGIN_DATA}/config.json" <<EOF
{"api_key": "<paste key here>"}
EOF
```

If the user hasn't set a key, ask them to paste it (don't guess / don't use a placeholder). StepFun API keys are available at https://platform.stepfun.com/ → API Keys. **Use a Normal key, not a Plan key** (Plan keys are restricted to text models and silently fail on audio endpoints).

## Common tasks — decision tree

| User wants... | Script | Key detail |
|---|---|---|
| Synthesize 1–500 char Chinese with emotion | `scripts/tts_generate.py` | Use `instruction` for mood, `()` for inline prosody |
| Synthesize long text (500–1000 char) | `scripts/tts_generate.py` | 1000 char is the hard cap; split at semantic boundaries above that |
| Batch-generate game/app voice lines | `scripts/tts_generate.py --batch <jsonl>` | Handle `censorship_block` fallback individually |
| A/B compare two TTS models | `scripts/ab_compare.sh` | Compares duration/size across two directories |
| Migrate from `step-tts-2` | see `references/migration_from_v2.md` | `voice_label.emotion` → `instruction` rewrite + censorship list |

## Starting points

- **Synthesize a single line**: Run `python3 scripts/tts_generate.py --text "你好" --out /tmp/hello.mp3 --instruction "温暖的希望感"`. For fine-grained control read the "Contextual TTS" section below.
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
| `"voice_label is not supported for v2 models"` | Sent `voice_label` to `stepaudio-2.5-tts` | Remove `voice_label`; put the same intent into `instruction` as natural language |
| `"The content you provided or machine outputted is blocked." type: censorship_block` | Sensitive word (死 / 消失 / etc.) | Rewrite the phrase OR fall back to `step-tts-2` for that specific line (mixed-model is fine) |
| Silent audio truncation (input > 1000 chars) | Hard cap exceeded | Split at semantic boundaries; don't truncate mid-sentence |

More in `references/known_issues.md`.

## When to read references

- `references/api_reference.md` — exact request/response JSON for `/v1/audio/speech`, all fields, error responses. Read when writing raw HTTP calls instead of using the bundled scripts.
- `references/migration_from_v2.md` — complete playbook for moving a step-tts-2 project to stepaudio-2.5-tts. Has the emotion→instruction rewrite table, the A/B directory strategy, decision checkpoints, and the 2026-04 speed/quality trade-off data (`stepaudio-2.5-tts` is ~20% slower than step-tts-2; audible prosody improvement). Read before any migration work.
- `references/known_issues.md` — censorship patterns, TTS duration inflation, v2-family parameter naming gotcha, 1000-char hard cap. Read when debugging anomalous output or evaluating whether to adopt.

## Design invariants (don't break these)

1. **Non-destructive A/B output** — when regenerating a corpus with a new model, write to a parallel directory (`voice/zh_v25/`), never overwrite the production corpus. The migration playbook shows why.
2. **Per-line censorship handling** — if 2/29 lines get `censorship_block`, don't fail the batch. Log the skipped IDs, continue. Mixed-model fallback (step-tts-2 for the skipped 2) is normal.
3. **Don't duplicate voice_label logic in new code** — any new TTS code targeting stepaudio-2.5-tts should only use `instruction` + inline `()`. Do not write a branch that conditionally emits `voice_label`.

## Pricing (verified 2026-04-23, volatile)

- `stepaudio-2.5-tts` contextual synthesis: ~5.8 元 / 万字符
- Zero-shot voice cloning: ~9.9 元 / 音色

Re-verify at https://platform.stepfun.com/docs/zh/guides/pricing/details before quoting to stakeholders.
