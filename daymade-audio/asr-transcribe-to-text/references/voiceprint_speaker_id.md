# Voiceprint Speaker Identification

Diarization (`references/speaker_diarization.md`) gives you anonymous `SPEAKER_00 /
SPEAKER_01` labels — arbitrary and per-file. Collect **name candidates** and
investigate cross-file matches using CAM++ voiceprints via
`scripts/voiceprint_id.py` (funasr auto-downloads the model from ModelScope).

## How it works

CAM++ turns a speech clip into a 192-dim L2-normalized embedding. A person's
**centroid** is the mean of several clip embeddings. To identify a speaker, take
the cosine similarity of their centroid to each enrolled centroid. The native
candidate gates remain:

- `cosine >= threshold` (default 0.45), AND
- `best - second_best >= margin` (default 0.05)

Neither gate is a calibrated probability or identity confirmation. All labels
remain unchanged, even at cosine 1.0 or when a legacy bank claims “confirmed”.
Missing calibration, independently bound enrollment or a verified source-bound
identity decision must not become a certain name from context or self-introduction.

## Enroll (build the reference set)

Give each person clean spans (in seconds) where they speak alone:

```bash
uv run scripts/voiceprint_id.py enroll --refs refs.json --name Alice \
    --audio alice.wav --spans "0-30,45-62"
```

Repeat per person into the same `refs.json`. More and longer clean spans → a
sturdier centroid.

## Match (retain candidates without changing speaker labels)

```bash
uv run scripts/voiceprint_id.py match --refs refs.json --audio rec.wav \
    --diar rec.diarization.json --csv rec.csv
```

For each speaker, match embeds the longest turns and retains all ranked native
labels, cosine scores, the old threshold/margin result, selected spans and refusal
reasons. JSON stdout contains an empty `mapping`, `labels_changed=false`, candidates
and the path of a new private `*.voiceprint-candidates.<invocation>.json` artifact.
The artifact binds original audio/diarization and optional CSV/receipt SHA256s,
plus the exact pinned bank reference or local bank fingerprint. It does not copy
biometric vectors. Original bank bytes, existing human/source names, anonymous
labels and receipt-backed TXT/CSV/alignment/receipt files remain untouched.

When the existing audio profile declares `api.endpoint`, match calls daudio's
`/v1/identity/evaluate` once per usable speaker for diagnostic reasons, with no
calibration policy fabricated. An unconfigured/unavailable evaluator is recorded
without retrying inference or discarding candidates. Even an evaluator response
claiming “confirmed” is not independently verified decision readback and cannot
enable relabeling. With no profile, local JSON matching still runs as candidates.

Explicit human/source mappings continue to use the existing receipt-aware
`apply_speaker_mapping_transaction`: TXT, CSV, alignment and final receipt commit
together with rollback, idempotent replay and rejection of conflicting canonical
labels. Voiceprint match does not call that writer. This entry does not yet have
a verified identity-decision consumption path for automatic certain-name output.

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
   score highest against their own out-of-domain centroid). Retain this as a
   candidate for review, not a confirmed cross-record identity.
2. **Rebuild in-domain** — after independently checking the selected person's
   enrollment, take the reviewed segments and `enroll`
   a fresh centroid from THIS recording's audio. Re-match with it; the same person
   may score ~0.9+ on those same samples. This circular score is not independent
   validation and cannot authorize confirming a name in later recordings.

## Other pitfalls

- **Over-segmentation collapses for free.** If diarization split one person into
  `SPEAKER_01` + `SPEAKER_05`, both may nominate the same centroid. Inspect the
  candidate evidence before merging turns; matching does not rewrite either label.
- **Don't force unknowns onto a name.** A recording will contain people not in your
  reference set (a one-off guest). The margin gate leaves them `SPEAKER_xx`; label
  those by hand rather than lowering the threshold until they snap onto a wrong name.
- **Enrollment can run on CPU** (a one-time embed of a few spans) without pain; it's
  bulk identification you want on GPU. On Apple Silicon funasr uses `--device mps`;
  a Swift CoreML/ANE path exists in some stacks but isn't required here.
