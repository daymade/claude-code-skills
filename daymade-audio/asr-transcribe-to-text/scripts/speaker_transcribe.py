#!/usr/bin/env python3
"""Multi-speaker transcription: WAV -> speaker-labeled transcript + CSV.

Chains the full pipeline so you don't reassemble it each time:
  diarize (pyannote @ MPS) -> merge same-speaker turns -> transcribe each turn
  (Qwen3-ASR MLX, bundled transcribe_local_mlx.py) -> stitch labels + text.

Full explanation and pitfalls: references/speaker_diarization.md.

Speaker labels are anonymous (SPEAKER_00, SPEAKER_01, ...). To map them to real
names, or unify a speaker across files, run voiceprint identification afterward
on the CSV -> references/voiceprint_speaker_id.md.

Prerequisite: HuggingFace token for pyannote (see diarize_speakers.py header).

Usage:
  uv run speaker_transcribe.py INPUT.wav OUTPUT_DIR [--device mps] [--max-gap 2.0]

Outputs (under OUTPUT_DIR):
  <stem>.diarization.json   raw pyannote segments
  <stem>.txt                [MM:SS - MM:SS] SPEAKER_xx\n text
  <stem>.csv                file,start,end,duration,speaker,text  (for review UIs)
"""
# /// script
# dependencies = ["pyannote.audio", "torch", "torchaudio"]
# ///
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import torch
from pyannote.audio import Pipeline

HERE = Path(__file__).resolve().parent
MLX_SCRIPT = HERE / "transcribe_local_mlx.py"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def pick_device(device):
    if device:
        return device
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def diarize(wav, device):
    """pyannote 3.1 segments. CPU is a per-file fallback only, never primary."""
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
    pipeline.to(torch.device(device))
    try:
        result = pipeline(str(wav))
    except RuntimeError as e:
        if device != "cpu":
            log(f"{device} failed ({e}); retrying on cpu")
            pipeline.to(torch.device("cpu"))
            result = pipeline(str(wav))
        else:
            raise
    diar = result.exclusive_speaker_diarization
    segs = [{"start": round(s.start, 3), "end": round(s.end, 3), "speaker": lbl}
            for s, _, lbl in diar.itertracks(yield_label=True)]
    segs.sort(key=lambda x: x["start"])
    return segs


def merge_turns(segments, max_gap=2.0):
    """Merge adjacent same-speaker segments with a gap <= max_gap seconds.

    Diarization emits many short fragments; without this you get hundreds of
    sub-second lines, each a separate transcription call. Merging makes readable
    turns and cuts model calls.
    """
    if not segments:
        return []
    turns = []
    cur = dict(segments[0])
    for s in segments[1:]:
        if s["speaker"] == cur["speaker"] and s["start"] - cur["end"] <= max_gap:
            cur["end"] = s["end"]
        else:
            turns.append(cur)
            cur = dict(s)
    turns.append(cur)
    for t in turns:
        t["duration"] = round(t["end"] - t["start"], 3)
    return turns


def slice_and_transcribe(wav, turns, seg_dir, language="Chinese", timeout=600):
    """Cut each turn's audio and transcribe the slices in one batched MLX call."""
    seg_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, t in enumerate(turns):
        p = seg_dir / f"{i:04d}_{int(t['start']*1000)}_{int(t['end']*1000)}_{t['speaker']}.wav"
        if not p.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav), "-vn", "-acodec", "pcm_s16le",
                 "-ar", "16000", "-ac", "1", "-ss", f"{t['start']:.3f}",
                 "-to", f"{t['end']:.3f}", str(p)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        paths.append(p)
    if paths:
        log(f"Transcribing {len(paths)} turns (Qwen3-ASR MLX)...")
        # Model loads once for the whole batch — cheap per turn.
        subprocess.run(["uv", "run", str(MLX_SCRIPT), "--output-dir", str(seg_dir),
                        "--language", language] + [str(p) for p in paths],
                       check=True, timeout=timeout)
    texts = []
    for t, p in zip(turns, paths):
        tp = p.with_suffix(".txt")
        texts.append((t, tp.read_text(encoding="utf-8").strip() if tp.exists() else ""))
    return texts


def fmt(sec):
    m, s = int(sec // 60), int(sec % 60)
    return f"{m:02d}:{s:02d}.{int((sec % 1) * 1000):03d}"


def write_outputs(turn_texts, stem, wav_name, out_dir):
    txt = out_dir / f"{stem}.txt"
    csv_path = out_dir / f"{stem}.csv"
    lines = [f"# File: {wav_name}", f"# Turns: {len(turn_texts)}", ""]
    for t, text in turn_texts:
        lines += [f"[{fmt(t['start'])} - {fmt(t['end'])}] {t['speaker']}", text, ""]
    txt.write_text("\n".join(lines), encoding="utf-8")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "start", "end", "duration", "speaker", "text"])
        for t, text in turn_texts:
            w.writerow([wav_name, t["start"], t["end"], t["duration"], t["speaker"], text])
    log(f"Wrote {txt} and {csv_path}")


def main():
    ap = argparse.ArgumentParser(description="Multi-speaker transcription pipeline")
    ap.add_argument("wav", type=Path, help="16kHz mono WAV")
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--device", default=None, help="mps / cuda / cpu (default: auto)")
    ap.add_argument("--max-gap", type=float, default=2.0, help="merge same-speaker gap (s)")
    ap.add_argument("--language", default="Chinese")
    args = ap.parse_args()

    device = pick_device(args.device)
    log(f"Device: {device}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.wav.stem

    segments = diarize(args.wav, device)
    (args.out_dir / f"{stem}.diarization.json").write_text(
        json.dumps({"num_speakers": len({s['speaker'] for s in segments}),
                    "segments": segments}, ensure_ascii=False, indent=2), encoding="utf-8")
    turns = merge_turns(segments, args.max_gap)
    log(f"{len(segments)} segments -> {len(turns)} turns, "
        f"{len({s['speaker'] for s in segments})} speakers")

    turn_texts = slice_and_transcribe(
        args.wav, turns, args.out_dir / f"{stem}.turns", language=args.language)
    write_outputs(turn_texts, stem, args.wav.name, args.out_dir)


if __name__ == "__main__":
    main()
