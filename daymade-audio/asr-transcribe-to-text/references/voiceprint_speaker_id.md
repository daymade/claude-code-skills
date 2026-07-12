# Voiceprint Speaker Identification

Diarization (`references/speaker_diarization.md`) gives you anonymous `SPEAKER_00 /
SPEAKER_01` labels — arbitrary and per-file. This is how you map them to **real
names**, and unify the same person **across files**, using CAM++ voiceprints via
`scripts/voiceprint_id.py` (funasr auto-downloads the model from ModelScope).

## How it works

CAM++ turns a speech clip into a 192-dim L2-normalized embedding. A person's
**centroid** is the mean of several clip embeddings. To identify a speaker, take
the cosine similarity of their centroid to each enrolled centroid and accept a name
only when it clears BOTH gates:

- `cosine >= threshold` (default 0.45), AND
- `best - second_best >= margin` (default 0.05)

The margin gate is what keeps an unknown person **anonymous** instead of being
forced onto the nearest enrolled name. Tune both against your own audio.

## Enroll (build the reference set)

Give each person clean spans (in seconds) where they speak alone:

```bash
uv run scripts/voiceprint_id.py enroll --refs refs.json --name Alice \
    --audio alice.wav --spans "0-30,45-62"
```

Repeat per person into the same `refs.json`. More and longer clean spans → a
sturdier centroid.

## Match (name the speakers in a recording)

```bash
uv run scripts/voiceprint_id.py match --refs refs.json --audio rec.wav \
    --diar rec.diarization.json --csv rec.csv
```

For each `SPEAKER_xx` it embeds the longest turns, matches to `refs.json`, prints
the mapping, and (with `--csv`) rewrites the CSV's speaker column. Unmatched
speakers keep their `SPEAKER_xx` label for a human to resolve.

## ⚠ The acoustic-domain caveat (the biggest real-world trap)

**A voiceprint is far less portable across recording environments than you'd expect.**
CAM++ similarity for the SAME person drops sharply when recording conditions change —
near-field vs far-field, lapel vs room mic vs phone vs video.

Measured in one project: same person, **same** recording domain scored ~0.77 median
cosine; the **same** person across **different** domains scored ~0.48 — barely above
the 0.45 threshold, with almost no margin. Different people in the same domain sit
well below that. So the failure mode isn't "can't tell people apart" — it's "same
person, wrong environment, similarity collapses."

Consequences:

- **Enroll from the SAME kind of audio you'll identify.** A centroid built from
  room-mic recordings is unreliable on lapel-mic recordings of the same person.
- If your only reference is from a different domain, use it to *bootstrap* only
  (below), then rebuild the centroid from in-domain samples.
- When a name comes back weak (similarity just over threshold, tiny margin), suspect
  a domain mismatch before suspecting the person is wrong.

## Bootstrap when you have no in-domain reference yet

Chicken-and-egg: to build an in-domain centroid you must first know which
`SPEAKER_xx` is that person — but that's exactly what you're trying to determine.
Resolve it in two passes:

1. **Coarse pass** — match with whatever cross-domain reference you have. Even at
   ~0.48 the *relative* ranking is usually right (a person's own segments still
   score highest against their own out-of-domain centroid), which is enough to tag
   which `SPEAKER_xx` is them.
2. **Rebuild in-domain** — take the segments just tagged as that person and `enroll`
   a fresh centroid from THIS recording's audio. Re-match with it; the same person
   now scores ~0.9+ (they're literally their own in-domain samples), and subsequent
   recordings in this domain identify cleanly.

## Other pitfalls

- **Over-segmentation collapses for free.** If diarization split one person into
  `SPEAKER_01` + `SPEAKER_05`, both match the same centroid → both get the same
  name. Voiceprint ID is how you undo diarization's over-segmentation.
- **Don't force unknowns onto a name.** A recording will contain people not in your
  reference set (a one-off guest). The margin gate leaves them `SPEAKER_xx`; label
  those by hand rather than lowering the threshold until they snap onto a wrong name.
- **Enrollment can run on CPU** (a one-time embed of a few spans) without pain; it's
  bulk identification you want on GPU. On Apple Silicon funasr uses `--device mps`;
  a Swift CoreML/ANE path exists in some stacks but isn't required here.
