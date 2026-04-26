# StepAudio 2.5 — Known Issues and Non-Obvious Behavior

Collected from end-to-end testing 2026-04-23. These are things that burned real time to discover; they are not in the official docs.

## ASR repetition hallucination (real, bounded)

**Symptom:** Transcribe a TTS-generated audio of highly-repetitive Chinese text (e.g., the same 60-char sentence repeated 10 times) and `stepaudio-2.5-asr` returns 3-4× the expected character count, with the same sentence restated many extra times in the output.

**This is a genuine model hallucination**, not a transport bug. Verified by:

1. MD5 diff — `run1` vs `run2` of the same TTS input produce different audio files (not file corruption)
2. Determinism — re-running ASR on the same audio gives the same 4× output every time (not transient noise)
3. Cross-validation — `step-asr` and `step-asr-1.1` on the exact same audio return the correct character count (~800 chars for 800 input), so the audio itself is fine
4. ffprobe confirms audio duration is normal (~219s for 800 chars at typical speed)

**Conclusion:** The LLM-based ASR sees a repetitive pattern in the audio and "continues predicting" repetitions that aren't there.

**When it triggers:**
- Audio duration > 90s AND
- Content is highly repetitive (same phrase appearing 5+ times)

**Doesn't trigger on real-world content:**
- Podcasts, interviews, varied dialogue, stories — all fine
- Even 17.4-minute audio from 90 different TTS segments: returns correct 6332 chars, RTF 101×

**Workaround for edge cases:**
- If your domain has genuinely repetitive content (e.g., IVR transcripts, repeated sloganeering), cross-validate with `step-asr-1.1` on random samples
- For most workflows: just use it; the hallucination mode is exotic

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

## ASR speed scales non-linearly — short audio is a trap

**Observation:** The headline "5.9× faster than step-asr" from the marketing is true for long audio but misleading for short clips.

| Audio length | stepaudio-2.5-asr | step-asr-1.1 | Speedup |
|---|---|---|---|
| 5-15s clips | ~500ms | ~900ms | **2.0×** |
| 115s audio | 1.36s | 7.16s | **5.3×** |
| 1046s (17.4 min) | 10.4s | (would need chunking) | **~101× RTF** |

**Why:** The LLM + MTP-5 fusion overhead is amortized over longer contexts. Short requests pay the model-spin-up cost.

**Practical implication:** If your workload is many short (<10s) clips, the speedup over `step-asr-1.1` is modest — 2× not 5×. If your workload is long audio (>2 min), the difference is dramatic and you should migrate.

## Wrong ASR endpoint gives a misleading error

**Symptom:** Calling `/v1/audio/transcriptions` with `model=stepaudio-2.5-asr`:

```json
{"error":{"message":"model stepaudio-2.5-asr not supported","type":"request_params_invalid"}}
```

This response is **identical in structure** to sending a genuinely nonexistent model name. It takes real debugging to realize the model exists but on a different endpoint.

**Diagnostic sequence that wastes the least time:**

1. Try `step-asr` on the same endpoint — if it works, endpoint access is fine
2. Check the `/v1/audio/asr/sse` endpoint (the actual stepaudio-2.5-asr home)
3. If both fail, THEN ask BD about whitelist

Don't assume "permission denied" on the first error.

## TTS duration inflation on short lines

**Observation:** Very short lines (1-2s in step-tts-2) become dramatically longer in stepaudio-2.5-tts.

Example from the reference project:
- `...你能看到我吗？` (10 chars)
- step-tts-2: 1.24s
- stepaudio-2.5-tts: 2.57s (**+107%**)

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

## ASR "Plan key" vs "Normal key"

StepFun sells a cheap "Plan" subscription for text models (step_plan endpoint). **Plan keys cannot call audio endpoints.** This silently manifests as 4xx errors that don't mention auth at all.

If you hit auth-shaped failures and your account has a Plan subscription, verify you're using a Normal key (different value, obtained separately in the StepFun console under the same "API Keys" page).

## Censorship can fire on the ASR side too

**Observed once (rare):** An ASR request on a user-uploaded recording of political content returned:

```
data: {"type":"error","message":"content blocked ..."}
```

Handle the `error` event type in the SSE stream — don't assume only `delta` and `done` events fire.

## Pricing opacity for stepaudio-2.5-asr

As of 2026-04-23, `stepaudio-2.5-asr` is in invitation beta. No public per-minute rate. `step-asr-1.1` baseline is 2.2 元/小时. The invitation PDF mentions "成本直降 80%" implying roughly 0.4 元/小时, but this is not yet on the pricing page. Do not quote a price to a stakeholder without re-verifying at https://platform.stepfun.com/docs/zh/guides/pricing/details.

## TTS text cap: 1000 chars (hard, not soft)

The API rejects >1000 char inputs with a 400 error. Split at sentence boundaries before sending. Non-obvious: when testing "what's the real limit?", avoid highly-repetitive test text — it can appear to succeed at 800 chars but produce strange audio (see the 2026-04 test where 800-char repetitive inputs played back normal audio but the ASR hallucinated 4× replay).

## Voice cloning — not tested in this skill

Zero-shot voice cloning (`9.9 元/音色`) is advertised as a headline feature but was not verified in this skill's test pass. If you need voice cloning, check the StepFun docs at https://platform.stepfun.com/docs/zh/api-reference/audio/create-voice and validate on your own data — don't assume the quality claims without a listen test.
