# stepaudio-2.5-tts — Known Issues and Non-Obvious Behavior

> Historical observations from the 2.5 test pass. Read the [current API reference](api_reference.md) for supported routes and controls; these cases do not establish current model, key or voice support.


Collected from end-to-end testing 2026-04-23. These are things that burned real time to discover; they are not in the official docs.

## Stricter content censorship than step-tts-2

**Symptom:** `stepaudio-2.5-tts` returns `{"error":{"message":"The content you provided or machine outputted is blocked.","type":"censorship_block"}}` for content that step-tts-2 happily synthesized.

**Observed triggers:**
- 死 (die/dead) in any context, even negation
- 消失 (disappear / vanish)
- Combinations with emotional context: "我快要...消失了"
- Politically sensitive terms (standard CN content rules)

**Key insight:** Rewriting negations doesn't help — "我没有死" blocks as readily as "我死了". The classifier isn't doing deep semantic parsing.

**Response strategies** (pick per line):
1. Rewrite: "RAG 已死" → "这个技术过时了"
2. Fallback: keep step-tts-2 for the 2-5% of lines that block
3. Whitelist: contact StepFun BD (worth it at >5% blockage)

See `migration_from_v2.md` for the full blocking→fallback workflow.

## TTS duration inflation on short lines

**Observation:** Very short lines (1-2s in step-tts-2) become dramatically longer in stepaudio-2.5-tts.

Example from the reference project:
- `...你能看到我吗？` (10 chars)
- step-tts-2: 1.24s
- stepaudio-2.5-tts: 2.57s

**Cause:** The new model adds a pre-breath, pauses on `...` ellipses, and gives the line emotional weight — all of which lengthens delivery.

**Not a bug, but have a plan:**
- If your UI has per-line timing (auto-advance, animation sync), re-tune it after migration
- If you want the old pacing, write `instruction: "快速、干脆、不要停顿"` — but this negates a lot of what you're paying for in the new model

## `stepaudio-2.5-tts` is a "v2 model" for parameter rejection

**Why the error says "v2 models":** StepFun internally groups `stepaudio-2.5-tts` with their v2 family despite the "2.5" version number. The error message `voice_label is not supported for v2 models` uses this internal grouping, which is confusing.

Don't pattern-match on the version string. Just know that:
- `stepaudio-2.5-tts` → use `instruction` parameter
- `step-tts-2` → use `voice_label` parameter
- They are NOT API-compatible despite sharing `/v1/audio/speech`

## TTS text cap: 1000 chars (hard, not soft)

The API rejects >1000 char inputs with a 400 error. Split at sentence boundaries before sending.

Non-obvious caveat when probing the limit: don't use highly-repetitive test text. The TTS itself accepts repetitive 800-char inputs and produces normal audio, but if you then transcribe that audio with `stepaudio-2.5-asr` for round-trip verification, the ASR can hallucinate 3-4× character expansion (a known ASR-side bug, see the `stepfun-asr` skill's `known_issues.md`). Use varied real-world text for cap-probing tests.

## Account and cloning failures

Use the [current lifecycle and endpoint guidance](api_reference.md#voice-and-file-lifecycle)
when cloning or diagnosing account entitlement. The old test pass did not verify
clone sound quality. Preserve the native error and check the actual account route;
do not infer a universal key restriction or silently substitute another identity.
