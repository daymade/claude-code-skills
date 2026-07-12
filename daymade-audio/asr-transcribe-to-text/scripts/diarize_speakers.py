#!/usr/bin/env python3
"""Speaker diarization: split a WAV into per-speaker segments (who spoke when).

Runs pyannote speaker-diarization-3.1 on Apple GPU (MPS) / CUDA. This is the
first half of multi-speaker transcription: diarize here, then transcribe each
turn's audio slice with transcribe_local_mlx.py and stitch the speaker labels
back on. Full pipeline: references/speaker_diarization.md.

Output JSON has per-segment {start, end, duration, speaker}. Speaker labels are
ANONYMOUS (SPEAKER_00, SPEAKER_01, ...) and arbitrary per file — the same real
person is often even split across two labels. To map labels to real names, or
to unify them across files, you need a voiceprint reference set — see
references/voiceprint_speaker_id.md.

Prerequisite — HuggingFace token (pyannote models are gated):
  1. Accept the terms at hf.co/pyannote/speaker-diarization-3.1
  2. `huggingface-cli login` once (or set HF_TOKEN)

Usage:
  uv run diarize_speakers.py INPUT.wav OUTPUT.json [--device mps]
"""
# /// script
# dependencies = ["pyannote.audio", "torch", "torchaudio"]
# ///
import argparse
import json
import sys
from pathlib import Path

import torch
from pyannote.audio import Pipeline


def diarize(wav_path, output_json, device=None):
    wav_path, output_json = Path(wav_path), Path(output_json)

    # Prefer GPU/NPU. pyannote on CPU is far slower, so auto-pick cuda > mps >
    # cpu and treat CPU only as a per-file fallback when a specific MPS op is
    # unimplemented (the except branch below) — never as the primary path.
    if device is None:
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
    print(f"Using device: {device}", file=sys.stderr, flush=True)

    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
    pipeline.to(torch.device(device))

    print(f"Diarizing {wav_path}...", file=sys.stderr, flush=True)
    try:
        result = pipeline(wav_path)
    except RuntimeError as e:
        # A specific MPS op may be unimplemented for some audio; fall back to
        # CPU for THIS file rather than crash. If already on CPU, it's a real error.
        if device != "cpu":
            print(f"{device} failed ({e}); retrying on cpu", file=sys.stderr, flush=True)
            pipeline.to(torch.device("cpu"))
            result = pipeline(wav_path)
        else:
            raise

    diarization = result.exclusive_speaker_diarization
    segments = [
        {
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "duration": round(seg.end - seg.start, 3),
            "speaker": label,
        }
        for seg, _, label in diarization.itertracks(yield_label=True)
    ]
    segments.sort(key=lambda s: s["start"])

    output = {
        "wav_path": str(wav_path),
        "device": device,
        "num_segments": len(segments),
        "num_speakers": len(set(s["speaker"] for s in segments)),
        "segments": segments,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(segments)} segments, {output['num_speakers']} speakers -> {output_json}",
          file=sys.stderr, flush=True)


def main():
    ap = argparse.ArgumentParser(description="Speaker diarization -> per-segment JSON")
    ap.add_argument("wav_path", type=Path, help="16kHz mono WAV")
    ap.add_argument("output_json", type=Path)
    ap.add_argument("--device", default=None, help="mps / cuda / cpu (default: auto)")
    args = ap.parse_args()
    diarize(args.wav_path, args.output_json, args.device)


if __name__ == "__main__":
    main()
