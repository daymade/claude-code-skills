---
name: stepfun-tts
description: Generate Chinese / Japanese speech with StepFun's Contextual TTS — default `stepaudio-2.5-tts` (blind-judged better on neutral/emotive preset voices), `stepaudio-3-tts` for whisper & inline-prosody cases (where it won the same blind test). Replaces step-tts-2's `voice_label` with natural-language `instruction` (200 chars on 2.5, 500 on v3) plus inline `()` parentheses for句内 prosody. Use when the user wants emotional / prosody control over voice synthesis (whisper, pause, stress, mood pivot mid-sentence), batch-generates game / app voice lines, migrates from `step-tts-2` or `stepaudio-2.5-tts` (the `voice_label → instruction` breaking change), or needs cloned voices (复刻音色：克隆合成禁用 v3——克隆丢失，走 stepaudio-2.5-tts/step-tts-2). Triggers on 阶跃 TTS, StepAudio 合成, stepaudio-3-tts, stepaudio-2.5-tts, 语音合成, 配音, 文本转语音, TTS 升级, 迁移 step-tts-2. For transcription with the sibling stepaudio-3-asr-max model, use the stepfun-asr skill instead.
---

# StepFun Contextual TTS (default stepaudio-2.5-tts)

Generate Chinese / Japanese speech with StepFun's Contextual TTS — emotion and prosody go through natural-language description, not fixed labels. **Default model is `stepaudio-2.5-tts`** (what the bundled script uses): in a 2026-09-16 blind A/B on our own cases, 2.5 won the neutral / jiao / lively-girl pairs 3:2. **Pick `stepaudio-3-tts` when the line is whisper or heavy inline-`()` prosody** — v3 won exactly those two pairs; v3 also raises the `instruction` cap to 500 chars (2.5 is 200). ⚠️ **Never synthesize cloned voices with v3** — v3 speech 接受复刻音色 ID 不报错但静默回退默认女声——根因 = 阶跃复刻链路整体停在 2.5 家族（复刻创建 API 只收 2.5/step-tts-2/step-tts-mini，v3 不在列；v3 合成侧复刻未发布）。两代创建的克隆在 v3 上全丢：step-tts-2 克隆 SIM 0.272、2.5 创建的新克隆 SIM 0.195（锚 0.773），2.5 同 ID 0.743/0.678。

> Companion: for transcription with `stepaudio-3-asr-max` (the sibling model), use the `stepfun-asr` skill — they share an API key but live on different endpoints with different body shapes.

**Why this skill exists** — two non-obvious pitfalls that cost hours if you don't know them:

1. `stepaudio-3-tts` **rejects** `voice_label` (the step-tts-2 way) — verified on v3 2026-09-16: HTTP 400 `voice_label is not supported for this model`. Emotion/prosody goes through `instruction` (natural-language description, ≤500 chars on v3 — 200 was the 2.5 limit) and inline `()` parentheses inside the text itself.
2. Censorship behavior is model-version-specific — the 2.5-era trigger list (死 / 消失 / sensitive political terms → `censorship_block`) did **not** fire on v3 in a 2026-09-16 single-sample probe; treat censorship as present but re-verify per trigger before building rewrite maps. The 2.5-era options are in `references/migration_from_v2.md`.

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
| Migrate from `step-tts-2` / `stepaudio-2.5-tts` | see `references/migration_from_v2.md` | `voice_label.emotion` → `instruction` rewrite + 2.5-era censorship list |

## Starting points

- **Synthesize a single line**: Run `python3 scripts/tts_generate.py --text "你好" --out /tmp/hello.mp3 --instruction "温暖的希望感"`. For fine-grained control read the "Contextual TTS" section below.
- **From code**: this script is the endpoint's wrapper in `llm-registry` — `llmreg.wrapper_for("stepfun-tts").tts_generate.synthesize(api_key=…, text=…, model=…, extra={…})`. `extra` is merged into the request body as-is; with `{"timestamp": True, "return_url": True}` the server answers a JSON envelope (`{"data": {"url", "subtitles"}}`) that comes back under `json` instead of `audio_bytes` (verified 2026-09-19). Parameters are not billed — send what you need. Direct `/v1/audio/speech` calls elsewhere are blocked by the `llm-entry-guard` hook.
- **A full migration** from `step-tts-2` → Contextual TTS: read `references/migration_from_v2.md` end-to-end before touching code. It has the `INSTRUCTION_MAP`, the SKIP_CENSORED list pattern, and the output-directory-strategy for non-destructive A/B (written for 2.5; the migration mechanics are identical on v3).

## Contextual TTS — beyond emotion labels

The headline feature of `stepaudio-3-tts` is that you stop mapping emotions to fixed tags and start describing what you want in natural language. Two layers:

**Global context (`instruction` parameter)** — sets the overall tone for the entire utterance. ≤500 chars on v3 (2.5 was 200; a 300-char instruction verified accepted on v3 2026-09-16). Think of it like giving stage direction to a voice actor.

```
instruction: "克制的悲伤，语气低沉柔弱，像快要消失一样"
```

**Inline context (`()` parentheses inside `input`)** —句内 directives. Parenthesised content is consumed as directions and is NOT read aloud. Use for precise control of pauses, breath, emphasis, or mid-sentence emotion shifts.

```
input: "(试探着问)你好吗？(开心地)太好了！(突然沉下来)不过...我快要消失了。"
```

Examples that worked in practice (verified 2026-04-23 on 2.5; all five re-verified on v3 2026-09-16, including these instruction and inline-prosody cases):
- `instruction: "活泼俏皮，像是在撒娇，带点嘴硬"` — visibly speeds up delivery vs neutral
- `instruction: "耳语声，气声很重，几乎听不清"` — produces audible whisper/breath
- `input: "你好(停顿一下)我是蕾格(轻声)今天(加重)的天气真不错。"` — inline directives all respected

**What `stepaudio-3-tts` will NOT accept** — `voice_label` parameter. Error on v3: `voice_label is not supported for this model` (2.5 said `...for v2 models`). This is the #1 migration gotcha from step-tts-2.

## Common error patterns (real errors, real fixes)

| Error response | Actual cause | Fix |
|---|---|---|
| `"voice_label is not supported for this model"` (v3) / `"...for v2 models"` (2.5) | Sent `voice_label` to a Contextual TTS model | Remove `voice_label`; put the same intent into `instruction` as natural language |
| `"The content you provided or machine outputted is blocked." type: censorship_block` | Sensitive word (2.5-era: 死 / 消失 / etc.; v3 triggers unverified) | Rewrite the phrase OR fall back to `step-tts-2` for that specific line (mixed-model is fine) |
| Silent audio truncation (input > 1000 chars) | Hard cap exceeded | Split at semantic boundaries; don't truncate mid-sentence |

More in `references/known_issues.md`.

## When to read references

- `references/api_reference.md` — exact request/response JSON for `/v1/audio/speech`, all fields, error responses. Read when writing raw HTTP calls instead of using the bundled scripts.
- `references/migration_from_v2.md` — complete playbook for moving a step-tts-2 project to Contextual TTS. Has the emotion→instruction rewrite table, the A/B directory strategy, decision checkpoints, and the 2026-04 speed/quality trade-off data (written against 2.5). Read before any migration work.
- `references/known_issues.md` — censorship patterns, TTS duration inflation, v2-family parameter naming gotcha, 1000-char hard cap. 2.5-era verification; re-verify on v3 before relying on a specific entry. Read when debugging anomalous output or evaluating whether to adopt.

## Design invariants (don't break these)

1. **Non-destructive A/B output** — when regenerating a corpus with a new model, write to a parallel directory (`voice/zh_v3/`), never overwrite the production corpus. The migration playbook shows why.
2. **Per-line censorship handling** — if 2/29 lines get `censorship_block`, don't fail the batch. Log the skipped IDs, continue. Mixed-model fallback (step-tts-2 for the skipped 2) is normal.
3. **Don't duplicate voice_label logic in new code** — any new TTS code targeting stepaudio-3-tts should only use `instruction` + inline `()`. Do not write a branch that conditionally emits `voice_label`.

## v3-specific facts (verified 2026-09-16)

- Official voices: 60+ via `GET /v1/audio/system_voices?model=stepaudio-3-tts` — the 2.5 list is fully inherited, plus new voices (e.g. English-named `Lisa`/`Alfie`, 上海话 `shanghaifemale`/`shanghaimale`).
- **Cloned (复刻) voices: do NOT use `stepaudio-3-tts`** — root cause nailed 2026-09-16: StepFun's whole cloning stack is still 2.5-family. The creation API (`POST /v1/audio/voices`) only accepts `stepaudio-2.5-tts` / `step-tts-2` / `step-tts-mini`, and v3 `/v1/audio/speech` silently falls back to a default female voice for ANY cloned ID — SIM 0.272 (step-tts-2 clone) and 0.195 (fresh 2.5-created clone) vs the 0.773 anchor; the same IDs on 2.5 score 0.743/0.678. Synthesize clones with `stepaudio-2.5-tts` (best SIM) or `step-tts-2`.
- **No WebSocket streaming for v3** (as of 2026-09-16): `wss://api.stepfun.com/v1/realtime/audio?model=stepaudio-3-tts` is rejected at handshake (404), while 2.5 still streams there. Need char-level subtitle timestamps on v3? Use REST `timestamp:true + return_url:true` (subtitles arrive in the response JSON `data.subtitles[]`, char-level ms, accumulated absolute axis) — bare `stream_format:"audio"` cannot carry subtitles (server 400).

## Pricing (verified 2026-09-16, volatile)

- `stepaudio-3-tts` synthesis: 2.5 元 / 万字符 (official model page, 2026-09-16 — cheaper than the 2.5-era ~5.8)
- Zero-shot voice cloning: 9.9 元 / 音色

Re-verify at https://platform.stepfun.com/docs/zh/guides/pricing/details before quoting to stakeholders.
