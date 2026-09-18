# stepaudio-2.5-asr — Known Issues and Non-Obvious Behavior

> **版本框定**：本文件多数条目为 2.5 时代（2026-04）实测证据；2026-09 起新增的 v3/两代条目自带日期标注。当前默认模型是 `stepaudio-3-asr-max`（2026-09-16 起）；这些条目多数与模型版本无关（端点形状 / key 类型 / SSE 行为），但与 censorship、幻觉等模型行为相关的条目在 v3 上未经回归实测。

> **v3 能力缺口（2026-09-17 核对，时间戳一条已于 2026-09-18 撤回）**：~~`stepaudio-3-asr-max` 响应只有句段级 `start_time`/`end_time`，无逐词时间戳~~——**此断言错误**。实测 `stepaudio-3-asr-max` 与 `stepaudio-2.5-asr` 都逐词返回毫秒时间戳，见下方「逐词时间戳要显式开」。失误不在文档缺字段——`enable_timestamp` 一直写在官方**请求**字段表里，而只读了**响应**字段表（那里确实没有 word 级字段）。`hotwords` 参数虽在该 API 参考中对 v3 列出（无版本限定），但实测两个同音陷阱（「某人名」「某机构名」）带与不带结果逐字相同——按「接受但不生效」对待（此条未在 2026-09-18 复测）。


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

Verified 2026-09-17 on the official pages: `stepaudio-3-asr-max` is 2.8 元/小时 ([model page](https://stepfun.mintlify.app/zh/guides/models/stepaudio-3-asr)); `stepaudio-2.5-asr` is 0.15 元/小时 (~18.7× cheaper). Prices move — re-verify at https://platform.stepfun.com/docs/zh/guides/pricing/details before quoting to a stakeholder.

**Usage metering caveat (2026-09-17 measured, both generations):** the SSE `usage` object always reports `audio_tokens: 0` — billing is by audio duration and never appears on the token meter. Don't build cost observability on `usage`; track audio duration yourself.

## Empty transcript with no error

**Symptom:** SSE stream completes normally but `transcript.text.done.text` is empty string.

**Possible causes:**
1. Audio is silent / pure noise / corrupted
2. Audio language doesn't match the `language` parameter (e.g., sending English audio with `language: zh`)
3. Audio format mismatch (e.g., `format.type: mp3` but actual bytes are wav)
4. **Audio too short — sub-second clips silently return empty (2026-09-17 measured, BOTH generations)**: duration ladder on the same synthesized speech clip — 0.4s and 0.8s → empty `text` with all-zero usage; 1.5s and 3.0s → normal transcript. Identical on `stepaudio-3-asr-max` and `stepaudio-2.5-asr`. No error, no warning — check duration before treating empty as a failure.

The bundled script falls back to concatenating delta chunks if the `done` event has empty text — but if both are empty, the issue is upstream (the audio itself, not the API).

## Long-audio timeout behavior

The default `urllib`/`requests` timeout is too short for 17+ minute audio. The bundled script uses `timeout=1200` (20 minutes). If you write your own client, set the timeout to at least 2× expected wall clock time (RTF ~100× means 17 min audio takes ~10s wall clock, but TCP retries and network jitter can stretch this).

## 逐词时间戳要显式开，否则字段在、值恒为 0

**Symptom:** SSE 的每个 `transcript.text.delta` 都带 `start_time`/`end_time` 字段，看起来「已支持」，但值全是 0。

**Cause:** 请求体没发 `enable_timestamp: true`。服务端此时仍然返回这两个字段，只是不填值。
**只判字段存不存在会得出「支持」或「不支持」两种相反的错误结论**——必须比对数值。

**Fix:** 请求体加 `"enable_timestamp": true`。脚本已默认发送，无需开关——
参数不额外计费，没有关闭的理由。`scripts/check_params.py` 拿官方字段表对账，
防止下一个字段被同样漏掉。

同一段 30 秒英文音频，2026-09-18 实测：

| 模型 | `enable_timestamp` | 段数 | 非零时间戳 | 覆盖 |
|---|---|---|---|---|
| `stepaudio-3-asr-max` | 发 | 61 | 55/61 | 228→29920ms |
| `stepaudio-3-asr-max` | 不发 | 73 | 0/73 | 全 0 |
| `stepaudio-2.5-asr` | 发 | 59 | 57/59 | 388→29920ms |

发与不发的分词结果也不同（61 vs 73 段），纯文本输出不受影响。

**粒度**：一个 delta 一个词，单调不回退。但少量词与前一个词共用同一时刻
（v3 6/61，2.5 2/59）——服务端按块 flush，块内多个词共享块尾时刻。
用于定位「这句话在第几秒」足够；用于逐词强制对齐不够，那种精度仍需 whisper word timestamps。

**`stepaudio-2-asr-pro` 在该端点整体不可用**：官方请求字段表把它列为支持的 model，
但 2026-09-18 实测恒返回 `status=200: internal error`，与时间戳无关。

## 说话人识别在另一个端点，且必须公网 URL

**这个 SSE 端点没有说话人能力**，两个方向的证据：官方请求字段表无任何 speaker 字段；
14 个候选字段名（`enable_speaker_diarization` / `enable_diarization` / `enable_speaker` /
`speaker_diarization` / `diarization` / `enable_spk` / `enable_speaker_label` / `speaker_label` /
`enable_multi_speaker` / `speaker_info` / `enable_speaker_info` / `num_speakers` / `speaker_num` /
`max_speaker_num`）在双人音频上逐一实测，响应与基线零差异。

**判据先标定过再用**：这个端点对未知字段**静默接受**（`enable_zzz_definitely_not_a_field`
照样 200），所以「没报错」零信息量，只有响应变化算数；而只比字段名同样不行——
`enable_timestamp` 不改字段名只改值。最终判据＝字段名＋值形态＋时间戳非零数＋文本，
同请求两次跑出零差异（假阳性 0），且能抓到 `enable_timestamp`（召回有效）。

**有说话人能力的是异步文件端点**：

| | `/v1/audio/asr/sse`（本 skill） | `/v1/audio/asr/file/submit` + `/file/query` |
|---|---|---|
| 音频入参 | `audio.data`（base64） | `audio.url`，公网可访问、<100MB |
| 说话人 | 无 | `enable_speaker_info` → 每个 utterance 带 `speaker.id`（`spk_1`…），单任务上限 10 人；需同时 `show_utterances=true` |
| 分句/分词 | 无 | `show_utterances` |
| 双声道分轨 | 无 | `enable_channel_split`（需 `audio.channel=2`） |
| 模型 | `stepaudio-3-asr-max` | `stepaudio-2.5-asr` / `step-asr-1.1` |

**base64 走不通**，2026-09-18 实测三条路都失败，不要再试：
`audio.data` → `FAILED / audio_download / invalid audio url`；
`https://api.stepfun.com/v1/files/<id>/content`（先传到 StepFun files）→ `failed to download audio`（需鉴权）；
`stepfile://<id>` → `invalid audio url`。
用这个端点就必须先把音频放到一个公网可取的地址，这是对外动作，先问用户。
