#!/usr/bin/env python3
"""Decoupled speaker alignment: attach speaker labels to a full-audio transcript.

This is the core of the decoupled (WhisperX-style) pipeline. Instead of cutting
audio by speaker and transcribing each slice (cascade — breaks ASR context), we
align three independent layers and never touch the ASR text:

  Layer 1  full-audio transcript (Qwen3-ASR)   — best text, no timing
  Layer 2  word-level timestamps (mlx-whisper) — timing lattice, text secondary
  Layer 3  diarization segments (pyannote)     — speaker x time, no text

Alignment:
  1. Normalize Layer 1 and Layer 2 to plain char streams (strip punctuation /
     whitespace / case), then find anchor blocks with difflib SequenceMatcher.
     Anchored chars inherit time directly from the whisper word they map to;
     chars between anchors get linearly interpolated times.
  2. Each timed char is assigned the speaker of the pyannote segment containing
     its midpoint; chars in inter-segment gaps inherit the nearest segment
     (<=1s) or the previous char's speaker.
  3. Turns are cut on speaker change or a > max_gap pause. Turn text is sliced
     from the ORIGINAL Layer-1 transcript (punctuation intact).

Pure stdlib module: import it from the orchestrator, or run standalone for
testing/debugging:

  uv run align_speakers.py \
    --text full.txt --words words.json --diarization diar.json \
    --out-dir OUT --stem NAME [--max-gap 2.0]

words.json format:      {"words": [{"word": str, "start": f, "end": f}, ...]}
diarization.json format: {"segments": [{"start": f, "end": f, "speaker": str}, ...]}
"""
import argparse
import bisect
import csv
import difflib
import json
import sys
from pathlib import Path

# Chars dropped when normalizing for alignment (CJK + ASCII punctuation, spaces).
_DROP = set(" \t\n\r，。！？；：、（）【】《》〈〉“”‘’\"'—…·~～.,!?;:'\"()[]{}<>-—_+*=/\\|@#$%^&`…‥•·、　")

MAX_GAP_DEFAULT = 2.0
# How far outside a diarization segment a char may sit and still inherit its
# speaker (pyannote boundaries routinely clip 100-500ms of speech).
SEG_EDGE_TOLERANCE = 1.0
# Below this anchored-char ratio the alignment is untrustworthy: the two
# transcripts diverged too much (wrong audio, heavy ASR failure on one side).
MIN_ANCHOR_RATIO = 0.5


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def normalize_stream(text):
    """Return (normalized_chars, raw_index_per_char)."""
    chars, raw_idx = [], []
    for i, ch in enumerate(text):
        if ch in _DROP:
            continue
        chars.append(ch.lower() if "A" <= ch <= "Z" else ch)
        raw_idx.append(i)
    return chars, raw_idx


def whisper_char_lattice(words):
    """Flatten whisper words to per-char (char, time), interpolating inside words."""
    chars, times = [], []
    for w in words:
        token = (w.get("word") or "").strip()
        if not token:
            continue
        start, end = float(w["start"]), float(w["end"])
        kept = [c for c in token if c not in _DROP]
        if not kept:
            continue
        n = len(kept)
        for j, c in enumerate(kept):
            # Linear interpolation across the word span, midpoint of each slot.
            t = start + (end - start) * (j + 0.5) / n
            chars.append(c.lower() if "A" <= c <= "Z" else c)
            times.append(round(t, 3))
    return chars, times


def anchor_align(qwen_chars, whisper_chars):
    """difflib matching blocks -> list of (qwen_pos, whisper_pos) anchor pairs."""
    matcher = difflib.SequenceMatcher(None, qwen_chars, whisper_chars, autojunk=False)
    anchors = []
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            anchors.append((block.a + k, block.b + k))
    return anchors


def assign_times(qwen_chars, whisper_times, anchors):
    """Every qwen char gets a time: direct at anchors, interpolated between them."""
    n = len(qwen_chars)
    times = [None] * n
    anchor_by_q = {}
    for q, w in anchors:
        anchor_by_q[q] = whisper_times[w]
    for q, t in anchor_by_q.items():
        times[q] = t
    if not anchor_by_q:
        return times, 0.0
    # Fill gaps by linear interpolation between surrounding anchors; clamp
    # edge regions to the nearest anchor time.
    sorted_q = sorted(anchor_by_q)
    first_q, last_q = sorted_q[0], sorted_q[-1]
    for i in range(first_q):
        times[i] = anchor_by_q[first_q]
    for i in range(last_q + 1, n):
        times[i] = anchor_by_q[last_q]
    for lo, hi in zip(sorted_q, sorted_q[1:]):
        t_lo, t_hi = anchor_by_q[lo], anchor_by_q[hi]
        span = hi - lo
        for i in range(lo + 1, hi):
            frac = (i - lo) / span
            times[i] = round(t_lo + (t_hi - t_lo) * frac, 3)
    anchored_ratio = len(anchor_by_q) / n if n else 0.0
    return times, round(anchored_ratio, 4)


def assign_speakers(times, segments):
    """Speaker per char: segment containing the time, else nearest within
    SEG_EDGE_TOLERANCE, else previous char's speaker."""
    if not segments:
        return ["SPEAKER_00"] * len(times)
    starts = [s["start"] for s in segments]
    speakers = []
    prev = segments[0]["speaker"]
    for t in times:
        if t is None:
            speakers.append(prev)
            continue
        idx = bisect.bisect_right(starts, t) - 1
        sp = None
        if idx >= 0:
            seg = segments[idx]
            if seg["start"] <= t <= seg["end"]:
                sp = seg["speaker"]
            elif t - seg["end"] <= SEG_EDGE_TOLERANCE:
                sp = seg["speaker"]
        if sp is None and idx + 1 < len(segments):
            nxt = segments[idx + 1]
            if nxt["start"] - t <= SEG_EDGE_TOLERANCE:
                sp = nxt["speaker"]
        if sp is None:
            sp = prev
        speakers.append(sp)
        prev = sp
    return speakers


def build_turns(qwen_raw, raw_idx, times, speakers, max_gap):
    """Cut turns on speaker change or a pause > max_gap; slice text from the
    original transcript so punctuation survives."""
    turns = []
    n = len(raw_idx)
    if n == 0:
        return turns
    cur_speaker = speakers[0]
    start_i = 0
    for i in range(1, n):
        gap = (times[i] or 0) - (times[i - 1] or 0)
        if speakers[i] != cur_speaker or gap > max_gap:
            turns.append((start_i, i, cur_speaker))
            start_i = i
            cur_speaker = speakers[i]
    turns.append((start_i, n, cur_speaker))
    out = []
    for lo, hi, sp in turns:
        raw_lo, raw_hi = raw_idx[lo], raw_idx[hi - 1] + 1
        # Trailing punctuation (。！？ etc.) sits between this turn's last kept
        # char and the next turn's first — it belongs to the sentence it ends,
        # so absorb it here instead of dropping it at the boundary.
        while raw_hi < len(qwen_raw) and qwen_raw[raw_hi] in _DROP:
            raw_hi += 1
        text = qwen_raw[raw_lo:raw_hi].strip()
        if not text:
            continue
        out.append({
            "start": times[lo],
            "end": times[hi - 1],
            "duration": round((times[hi - 1] or 0) - (times[lo] or 0), 3),
            "speaker": sp,
            "text": text,
        })
    return out


def align(qwen_text, whisper_words, diar_segments, max_gap=MAX_GAP_DEFAULT):
    """Full alignment. Returns (turns, report)."""
    qwen_chars, raw_idx = normalize_stream(qwen_text)
    w_chars, w_times = whisper_char_lattice(whisper_words)
    if not qwen_chars:
        raise ValueError("transcript normalizes to empty — cannot align")
    if not w_chars:
        raise ValueError("whisper word lattice is empty — cannot align")
    anchors = anchor_align(qwen_chars, w_chars)
    times, ratio = assign_times(qwen_chars, w_times, anchors)
    speakers = assign_speakers(times, diar_segments)
    turns = build_turns(qwen_text, raw_idx, times, speakers, max_gap)
    report = {
        "qwen_chars": len(qwen_chars),
        "whisper_chars": len(w_chars),
        "anchored_ratio": ratio,
        "trustworthy": ratio >= MIN_ANCHOR_RATIO,
        "num_turns": len(turns),
        "speakers": sorted({t["speaker"] for t in turns}),
    }
    return turns, report


def fmt(sec):
    sec = sec or 0
    m, s = int(sec // 60), int(sec % 60)
    return f"{m:02d}:{s:02d}.{int((sec % 1) * 1000):03d}"


def write_outputs(turns, report, wav_name, out_dir, stem):
    out_dir = Path(out_dir)
    txt = out_dir / f"{stem}.txt"
    csv_path = out_dir / f"{stem}.csv"
    lines = [f"# File: {wav_name}", f"# Turns: {len(turns)}", ""]
    for t in turns:
        lines += [f"[{fmt(t['start'])} - {fmt(t['end'])}] {t['speaker']}", t["text"], ""]
    txt.write_text("\n".join(lines), encoding="utf-8")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "start", "end", "duration", "speaker", "text"])
        for t in turns:
            w.writerow([wav_name, t["start"], t["end"], t["duration"], t["speaker"], t["text"]])
    (out_dir / f"{stem}.alignment.json").write_text(
        json.dumps({"wav": wav_name, "report": report,
                    "note": "turn text comes from the full-audio ASR transcript; "
                            "times/speakers aligned from whisper word lattice + pyannote"},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    log(f"Wrote {txt.name}, {csv_path.name}, {stem}.alignment.json")


def main():
    ap = argparse.ArgumentParser(description="Align full transcript + word lattice + diarization")
    ap.add_argument("--text", type=Path, required=True, help="full-audio transcript (plain text)")
    ap.add_argument("--words", type=Path, required=True, help='JSON {"words":[{word,start,end}]}')
    ap.add_argument("--diarization", type=Path, required=True, help='JSON {"segments":[{start,end,speaker}]}')
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--stem", required=True)
    ap.add_argument("--wav-name", default=None)
    ap.add_argument("--max-gap", type=float, default=MAX_GAP_DEFAULT)
    args = ap.parse_args()

    qwen_text = args.text.read_text(encoding="utf-8")
    words = json.loads(args.words.read_text(encoding="utf-8"))["words"]
    segments = json.loads(args.diarization.read_text(encoding="utf-8"))["segments"]
    turns, report = align(qwen_text, words, segments, args.max_gap)
    log(f"Alignment: {report}")
    if not report["trustworthy"]:
        log(f"WARNING: anchored_ratio {report['anchored_ratio']} < {MIN_ANCHOR_RATIO} — "
            "the two transcripts diverge heavily; speaker labels may be unreliable")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_outputs(turns, report, args.wav_name or args.stem, args.out_dir, args.stem)


if __name__ == "__main__":
    main()
