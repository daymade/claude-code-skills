# Overlap-Merge Strategy: Why and How

> **First check whether your server already solves this — several do, and better.**
> vLLM's speech-to-text endpoint splits long audio itself, at the **quietest point inside
> a ~100 ms window** with 1 s of overlap (`SpeechToTextConfig.min_energy_split_window_size`
> / `overlap_chunk_second`). That sidesteps the problem described below rather than
> repairing it: it doesn't cut mid-sentence in the first place, so there is no truncated
> tail to stitch back together. Against such an endpoint, splitting client-side makes the
> result *worse*, and the right fix for a rejected long file is raising the server's limits
> — see SKILL.md, Path B.
>
> **This document applies when the endpoint won't take the whole file and can't be made
> to**: it has a fixed context window or hard duration limit, it OOMs at the same input
> length every time, or you have no permission to reconfigure it. That is a real and common
> situation — the technique below is sound, it just isn't the first thing to reach for.

## The Problem with Naive Chunking

When ASR transcribes audio in chunks, each chunk's last sentence gets **forcibly truncated**. The model closes the sentence at the chunk boundary even if the speaker is mid-sentence.

**Real example from testing (5-minute chunks):**

| Version | Text at boundary |
|---------|-----------------|
| 5min chunk ending | "...靠的就。" (truncated) |
| Continuous 10min | "...靠的就是其中一次战略会。" (complete) |
| Next 5min chunk start | "如果不这么啃，这个业务..." (picks up but gap exists) |

Concatenating these chunks produces: "靠的就。如果不这么啃..." — losing "是其中一次战略会" entirely.

## Why Exact String Matching Fails

The same 2-minute audio segment transcribed in two different contexts (end of chunk A vs start of chunk B) produces **different punctuation**:

- Chunk A: "可能三年AI的进化"
- Chunk B: "可能。三年AI的进化"

The words are identical, but punctuation differs because the model's sentence boundary decisions depend on surrounding context. Exact string matching finds zero overlap.

## The Solution: Punctuation-Stripped Fuzzy Matching

1. Strip all punctuation from both the tail of chunk A and the head of chunk B
2. Find the longest common substring in the stripped versions
3. Use chunk B's version at the merge point (because chunk A's ending is truncated while chunk B has the complete sentence)

## Optimal Parameters (Empirically Determined)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Chunk duration | 18 min (1080s) | Safe margin under 20min paper benchmark; 4090 24GB handles much more |
| Overlap duration | 2 min (120s) | ~800 chars overlap region; enough for reliable fuzzy matching |
| Min match length | 15 chars | Filters false positives while catching real overlaps |
| Search window | 600 chars | Covers the overlap region with margin |

## When to Use This Fallback

Only use overlap-merge when the single full-length request fails. Reasons it might fail:
- Audio longer than ~2 hours (untested territory, may OOM on 24GB VRAM)
- GPU memory pressure from other processes
- Network timeout (curl max-time exceeded)

For audio under 1 hour, always try single request first — it's faster, simpler, and produces the best quality.

## Empirical Comparison (55-minute AI course recording)

| Strategy | Segments | Boundaries | Total chars | Quality |
|----------|----------|------------|-------------|---------|
| 12x5min direct concat | 12 | 11 cuts | 23,060 | 11 truncated sentences |
| 4x18min overlap merge | 4 | 3 merges | 22,781 | Zero truncation |
| 1x55min single request | 1 | 0 | 22,889 | Perfect (best) |
