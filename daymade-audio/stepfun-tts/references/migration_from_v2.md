# Migrating from step-tts-2 to stepaudio-2.5-tts

Complete playbook for moving a production `step-tts-2` voice corpus to `stepaudio-2.5-tts`. Based on a real end-to-end migration done 2026-04-23 on a ~30-line Chinese voice-acting project. Read this before changing any production code.

## What "migration" actually means here

The API endpoint is the same (`/v1/audio/speech`), but the **emotional control model is completely different**:

| Aspect | step-tts-2 | stepaudio-2.5-tts |
|---|---|---|
| Emotion mechanism | `voice_label.emotion = "悲伤"` etc. (discrete tags) | `instruction = "克制的悲伤，语气低沉"` (natural language) |
| Multi-language | `voice_label.language = "日语"` etc. | `instruction` or Zero-shot clone |
| Inline prosody | N/A | `()` parentheses in the input text |
| Max text | 1000 chars | 1000 chars (same) |
| Censorship | Moderate | Stricter (2/29 lines blocked in the reference project) |
| Typical duration for same text | baseline | +20% (more pauses, more breathy) |
| Subjective quality | Clearly synthetic | Still audibly synthetic, but with prosody variance that "sounds like someone reading" more often |

You are not just swapping a model ID. You need to rewrite every `voice_label.emotion` call and handle a new class of error (`censorship_block`).

## The rewrite — emotion tags → instruction sentences

The step-tts-2 style usually looked like:

```typescript
const EMOTION_MAP = {
  sad: '悲伤',
  hopeful: '高兴',
  relieved: '高兴',
  smile: '非常高兴',
};

body.voice_label = { emotion: EMOTION_MAP[expression] };
```

The stepaudio-2.5-tts equivalent:

```typescript
const INSTRUCTION_MAP = {
  sad: '克制的悲伤，语气低沉柔弱，像快要消失一样',
  hopeful: '温暖的希望感，语气鼓励，带着期待',
  relieved: '如释重负，语气柔和放松',
  smile: '明朗开心，语气上扬，带着微笑',
};

body.instruction = INSTRUCTION_MAP[expression];
// DELETE body.voice_label entirely — sending it triggers an error
```

### How to write a good `instruction`

Writing instruction sentences is a craft. They should describe **what the performance feels like**, not just "happy" or "sad". Good instructions use:

- A core emotion word (悲伤, 希望, 开心)
- A qualifier that bounds intensity (克制的, 温暖的, 如释重负)
- A specific vocal behavior (语气低沉柔弱, 带着微笑, 像快要消失一样)

Bad: `"悲伤"` — same semantic content as the old emotion tag; wastes the instruction parameter
Good: `"克制的悲伤，语气低沉柔弱，像快要消失一样"` — three distinct signals the model can combine

Keep under 200 chars. In practice 30-50 chars is plenty.

### Inline `()` directives — new capability

Beyond the global `instruction`, stepaudio-2.5-tts parses parentheses inside the `input` itself. Directives in parentheses are **not read aloud** — they control delivery.

Use when a single line has multiple emotional beats:

```
input: "(试探着问)你好吗？(开心地)太好了！(突然沉下来)不过...我快要消失了。"
```

Also useful for micro-control:
- `(停顿一下)` between clauses that shouldn't run together
- `(轻声)` for intimate moments
- `(加重)` on the key word of a sentence

This is genuinely new vs step-tts-2 and worth using on your most dramatic lines.

## Handling censorship_block

stepaudio-2.5-tts rejects more content than step-tts-2. Observed triggers from the reference project:

| Trigger phrase | Example line that failed |
|---|---|
| "死" in any context | "他们都在说'RAG 已死'... 我快要...消失了。" |
| "没有死" | "但我没有死，对吧？" (negation doesn't help) |
| "消失" / "透明" | Combined with "死" is especially reliable at triggering |

The error:

```json
{"error":{"message":"The content you provided or machine outputted is blocked.","type":"censorship_block"}}
```

Three response strategies (pick per line, not globally):

1. **Rewrite** — "RAG 已死" → "这个技术过时了" keeps the narrative, passes censorship
2. **Mixed-model fallback** — keep step-tts-2 for the 2-3 blocked lines, use stepaudio-2.5-tts for the rest. The voice difference is audible but tolerable for 2 lines out of 30
3. **Request whitelist** — contact StepFun BD for your account; only worth it if you have >5% blockage rate

The batch script (`scripts/tts_generate.py --batch`) logs censored IDs separately so you can handle them individually rather than aborting.

## A/B directory strategy — don't overwrite production

Non-destructive layout. Output the new model's files to a parallel directory, not on top of the existing corpus:

```
public/data/voice/
├── zh/         ← step-tts-2 production (untouched)
└── zh_v25/     ← stepaudio-2.5-tts candidate (A/B)
```

In the runtime voice loader, add a fallback for lines that are not in `zh_v25/` (censored ones):

```typescript
const getVoicePath = (nodeId: string, lang: string) => {
  // 2 lines censored on v25 — keep step-tts-2 for those
  const censored = new Set(['encounter_3', 'chapter_3_final_hope']);
  const useV25 = lang === 'zh' && !censored.has(nodeId);
  const dir = useV25 ? 'zh_v25' : lang;
  return `/data/voice/${dir}/${nodeId}.mp3`;
};
```

Benefits:
- Instant rollback: delete the `zh_v25/` directory
- Run the game/app with old voices while evaluating the new ones
- Human A/B: toggle the flag per-session to compare

### Don't hard-code the censored list across multiple files

If you put `['encounter_3', 'chapter_3_final_hope']` in the runtime loader, the generation script, AND the docs, you'll have three places to update when the list changes. Treat the generation script's `SKIP_CENSORED` set as the SSOT; the loader can import or mirror it but shouldn't independently enumerate the same IDs.

## The time-cost you're buying

Across 26 lines of the reference project, stepaudio-2.5-tts produced **~20% longer total duration** than step-tts-2 for the same text. Per-line:

| Line type | step-tts-2 | stepaudio-2.5-tts | Δ |
|---|---|---|---|
| Very short (1-2s) | 1.24s | 2.57s | **+107%** |
| Short (3-5s) | 3.00s | 3.94s | +31% |
| Medium (8-12s) | 9.64s | 8.54s | -11% (mixed) |
| Long (12-15s) | 12.48s | 9.82s | -21% |

Short lines grow a lot because the new model adds breath and pause before starting. Long lines often shrink because English loanwords are handled faster.

**Implications for UI timing:**
- Auto-advance timers need re-tuning; anything that assumed 6-8 chars/sec is now 5.5 chars/sec
- Short lines feel markedly slower — the "...你能看到我吗？" intake of breath is noticeable
- Overall dialogue pacing in a visual novel becomes 20% slower

This is the main trade-off users report: **the new model is more "alive" but the app feels slower**. Whether that's acceptable is a product decision, not a technical one.

## Decision checkpoints — before you commit

Use these to keep the migration from becoming a one-way door.

### Before the first full regeneration

- [ ] Confirm the A/B directory layout matches the loader's fallback logic (production directory untouched)
- [ ] Write the `INSTRUCTION_MAP` — don't just mechanically translate emotion tags, actually describe the performance
- [ ] Have 3-5 sample lines ready for listening test BEFORE regenerating the whole corpus (spend 5 min on quality, save 20 min of regeneration if it sounds wrong)

### After the first full regeneration

- [ ] Listen to every censored line manually. Decide rewrite vs fallback vs whitelist
- [ ] Check `ab_compare.sh` output: is the total duration change within acceptable bounds?
- [ ] Play 5 random new lines in-context (the actual game/app) — don't trust the raw mp3 listen-through

### Before switching production

- [ ] Run a real user-playthrough session end-to-end on the new voices
- [ ] Check every line with `...` punctuation for how the new model handles the ellipsis (sometimes too slow, sometimes too abrupt)
- [ ] Re-tune any auto-advance, skip, or per-line timing parameters
- [ ] Write a rollback script: `rm -rf zh_v25/` + revert loader change. If it's more than one commit, you've leaked complexity into the codebase

### After production rollout

- [ ] Monitor user sentiment on pacing for 1-2 weeks before pronouncing success
- [ ] Keep the step-tts-2 generation script in version control for at least one release cycle

## What NOT to do

- **Don't regenerate blindly.** Listen to samples first. A/B of 30 lines takes ~10 min; regenerate-without-listening is how you ship something that "technically works" but sounds worse.
- **Don't mix `voice_label` and `instruction` in the same request.** stepaudio-2.5-tts rejects `voice_label` entirely, but people occasionally leave it in to "be safe" — it's not safe, it's an error.
- **Don't try to pass emotion tags through `instruction`.** `instruction: "悲伤"` works but wastes the parameter. Write a full sentence.
- **Don't delete the step-tts-2 generation script** until you've shipped the new model to production and had it stable for a full release cycle. You will want the rollback path.
- **Don't assume Japanese migrates the same way.** The reference project didn't test Japanese voices under stepaudio-2.5-tts. Run a separate mini-A/B for Japanese before committing.

## Batch migration with the bundled script

The skill's `scripts/tts_generate.py --batch` is built for this workflow. Feed it a JSONL file:

```jsonl
{"id": "encounter_1", "text": "...你能看到我吗？", "instruction": "克制的悲伤，语气低沉柔弱"}
{"id": "encounter_2", "text": "太好了... 最近能看到我的人，越来越少了。", "instruction": "克制的悲伤，语气低沉柔弱"}
```

Run:

```bash
python3 scripts/tts_generate.py --batch lines.jsonl --out-dir ./voice/zh_v25
```

The script handles censorship_block per-line, reports the skipped IDs at the end, and keeps going. You get a clean list of "what to fall back on step-tts-2 for" without having to retry the whole batch.
