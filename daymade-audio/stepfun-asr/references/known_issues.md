# stepaudio-2.5-asr — Known Issues and Non-Obvious Behavior

Collected from end-to-end testing 2026-04-23. These are things that burned real time to discover; they are not in the official docs.

## Wrong endpoint gives a misleading error (the #1 trap)

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

## ASR speed scales non-linearly — short audio is a trap

**Observation:** The headline "5.9× faster than step-asr" from the marketing is true for long audio but misleading for short clips.

| Audio length | stepaudio-2.5-asr | step-asr-1.1 | Speedup |
|---|---|---|---|
| 5-15s clips | ~500ms | ~900ms | **2.0×** |
| 115s audio | 1.36s | 7.16s | **5.3×** |
| 1046s (17.4 min) | 10.4s | (would need chunking) | **~101× RTF** |

**Why:** The LLM + MTP-5 fusion overhead is amortized over longer contexts. Short requests pay the model-spin-up cost.

**Practical implication:** If your workload is many short (<10s) clips, the speedup over `step-asr-1.1` is modest — 2× not 5×. If your workload is long audio (>2 min), the difference is dramatic and you should migrate.

## "Plan key" vs "Normal key" — silent auth failure

StepFun sells a cheap "Plan" subscription for text models (step_plan endpoint). **Plan keys cannot call audio endpoints.** This silently manifests as 4xx errors that don't mention auth at all.

If you hit auth-shaped failures and your account has a Plan subscription, verify you're using a Normal key (different value, obtained separately in the StepFun console under the same "API Keys" page).

## Censorship can fire on the ASR side too

**Observed once (rare):** An ASR request on a user-uploaded recording of political content returned:

```
data: {"type":"error","message":"content blocked ..."}
```

Handle the `error` event type in the SSE stream — don't assume only `delta` and `done` events fire. If your code only handles `transcript.text.delta` and `transcript.text.done`, a blocked-content event is silently dropped and the request appears to return empty text with no error surfaced to the caller.

The bundled `scripts/asr_transcribe.py` handles this correctly — see `_consume_sse()` for the pattern.

## Pricing opacity

As of 2026-04-23, `stepaudio-2.5-asr` is in invitation beta. No public per-minute rate. `step-asr-1.1` baseline is 2.2 元/小时. The invitation PDF mentions "成本直降 80%" implying roughly 0.4 元/小时, but this is not yet on the pricing page. Do not quote a price to a stakeholder without re-verifying at https://platform.stepfun.com/docs/zh/guides/pricing/details.

## Empty transcript with no error

**Symptom:** SSE stream completes normally but `transcript.text.done.text` is empty string.

**Possible causes:**
1. Audio is silent / pure noise / corrupted
2. Audio language doesn't match the `language` parameter (e.g., sending English audio with `language: zh`)
3. Audio format mismatch (e.g., `format.type: mp3` but actual bytes are wav)

The bundled script falls back to concatenating delta chunks if the `done` event has empty text — but if both are empty, the issue is upstream (the audio itself, not the API).

## Long-audio timeout behavior

The default `urllib`/`requests` timeout is too short for 17+ minute audio. The bundled script uses `timeout=1200` (20 minutes). If you write your own client, set the timeout to at least 2× expected wall clock time (RTF ~100× means 17 min audio takes ~10s wall clock, but TCP retries and network jitter can stretch this).
