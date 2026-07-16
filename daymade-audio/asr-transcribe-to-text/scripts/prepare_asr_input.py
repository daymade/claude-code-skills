#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""prepare_asr_input.py — merge multi-segment recordings and normalize audio for ASR.

Two jobs:
  A. Merge recorder dumps split into fixed-length segments (body mics, Sony/TX-style
     recorders) into one continuous file, so transcription keeps full-audio context.
  B. Normalize for ASR (16 kHz mono) and optionally apply a pitch-PRESERVED speedup
     (--speed) to shrink uploads billed by duration (Feishu Minutes and similar).

The script self-verifies instead of trusting ffmpeg exit code:
  - output duration must equal sum(inputs) / speed (tolerance 1.5 s)
  - every splice boundary gets a 10 s volume spot-check (dead air at a boundary
    means wrong segment order or a missing segment)
  - overall loudness is printed for comparison against the source

Usage:
  uv run prepare_asr_input.py SEG1.wav SEG2.wav -o merged.wav
  uv run prepare_asr_input.py SEG*.wav -o upload.m4a --speed 1.3
  python3 prepare_asr_input.py a.wav b.wav -o master.flac --order given

Output codec is chosen by extension: .wav (pcm_s16le) / .m4a (AAC 48k) /
.flac (lossless) / .mp3 (64k). Segments are sorted by the YYYYMMDD[_-]HHMMSS
timestamp embedded in their filenames when every file has one; otherwise the
given order is used (--order given forces the given order).
"""

import argparse
import json
import re
import subprocess
import sys

DURATION_TOLERANCE_S = 1.5
BOUNDARY_DEAD_AIR_DB = -50.0  # max_volume below this at a splice = suspicious

CODECS_BY_EXT = {
    ".wav": ["-c:a", "pcm_s16le"],
    ".m4a": ["-c:a", "aac", "-b:a", "48k"],
    ".flac": ["-c:a", "flac"],
    ".mp3": ["-c:a", "libmp3lame", "-b:a", "64k"],
}

TS_RE = re.compile(r"(\d{8})[_-]?(\d{6})")


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(path: str) -> dict:
    r = run([
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_name,sample_rate,channels:format=duration",
        "-of", "json", path,
    ])
    if r.returncode != 0:
        sys.exit(f"ffprobe failed on {path}:\n{r.stderr.strip()}")
    info = json.loads(r.stdout)
    stream = (info.get("streams") or [{}])[0]
    return {
        "codec": stream.get("codec_name", "?"),
        "rate": int(stream.get("sample_rate", 0)),
        "channels": stream.get("channels", 0),
        "duration": float(info.get("format", {}).get("duration", 0.0)),
    }


def duration_of(path: str) -> float:
    return probe(path)["duration"]


def sort_key_auto(path: str):
    m = TS_RE.search(path.rsplit("/", 1)[-1])
    return (m.group(1), m.group(2)) if m else None


def atempo_chain(factor: float) -> str:
    """Decompose into atempo stages of <=2x each (portable across ffmpeg versions)."""
    stages = []
    f = factor
    while f > 2.0:
        stages.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        stages.append("atempo=0.5")
        f /= 0.5
    stages.append(f"atempo={f:g}")
    return ",".join(stages)


def volumedetect(path: str, start: float | None = None, window: float | None = None) -> tuple[float, float]:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "info"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if window is not None:
        cmd += ["-t", f"{window:.3f}"]
    cmd += ["-i", path, "-af", "volumedetect", "-f", "null", "-"]
    r = run(cmd)
    mean = max_ = float("nan")
    for line in r.stderr.splitlines():
        if "mean_volume:" in line:
            mean = float(line.split("mean_volume:")[1].strip().rstrip(" dB"))
        if "max_volume:" in line:
            max_ = float(line.split("max_volume:")[1].strip().rstrip(" dB"))
    return mean, max_


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge + normalize audio for ASR, optional pitch-preserved speedup.")
    ap.add_argument("inputs", nargs="+", help="Input audio/video files (segments of one session)")
    ap.add_argument("-o", "--output", required=True, help="Output file; extension picks codec (.wav/.m4a/.flac/.mp3)")
    ap.add_argument("--speed", type=float, default=1.0, help="Pitch-preserved tempo factor, e.g. 1.3 (ASR-safe zone: <=1.5)")
    ap.add_argument("--order", choices=["auto", "given"], default="auto",
                    help="auto: sort by YYYYMMDD_HHMMSS in filenames when all have one; given: keep CLI order")
    args = ap.parse_args()

    ext = "." + args.output.rsplit(".", 1)[-1].lower() if "." in args.output else ""
    if ext not in CODECS_BY_EXT:
        sys.exit(f"Unknown output extension '{ext}'. Use one of: {', '.join(CODECS_BY_EXT)}")
    if args.speed <= 0:
        sys.exit("--speed must be > 0")
    if args.speed > 1.5:
        print(f"WARNING: --speed {args.speed} is above the ASR-safe zone (<=1.5x). Expect WER degradation.",
          file=sys.stderr)

    inputs = list(args.inputs)
    if args.order == "auto" and len(inputs) > 1:
        keys = [sort_key_auto(p) for p in inputs]
        if all(keys):
            inputs = [p for p, _ in sorted(zip(inputs, keys), key=lambda t: t[1])]
        else:
            print("NOTE: not all filenames carry a YYYYMMDD_HHMMSS timestamp; keeping given order.", file=sys.stderr)

    print("Merge order:")
    probes = []
    for i, p in enumerate(inputs):
        info = probe(p)
        probes.append(info)
        print(f"  {i + 1}. {p}  [{info['codec']} {info['rate']}Hz ch={info['channels']} {info['duration']:.2f}s]")

    ref = probes[0]
    for p, info in zip(inputs[1:], probes[1:]):
        if (info["rate"], info["channels"]) != (ref["rate"], ref["channels"]):
            print(f"WARNING: {p} has {info['rate']}Hz ch={info['channels']} "
                  f"(first segment: {ref['rate']}Hz ch={ref['channels']}) — it will be resampled, "
                  f"but confirm this is really the same session.", file=sys.stderr)

    total_in = sum(p["duration"] for p in probes)
    expected_out = total_in / args.speed
    print(f"Expected output duration: {expected_out:.2f}s ({total_in:.2f}s / {args.speed:g})")

    # Per-input normalize -> concat -> optional atempo. Normalizing BEFORE concat makes
    # the filter robust to mixed source params (concat itself refuses mismatched streams).
    per_input = [f"[{i}:a]aresample=16000,aformat=sample_fmts=s16:channel_layouts=mono[a{i}]"
                 for i in range(len(inputs))]
    concat_in = "".join(f"[a{i}]" for i in range(len(inputs)))
    graph = ";".join(per_input) + f";{concat_in}concat=n={len(inputs)}:v=0:a=1[c]"
    last = "c"
    if args.speed != 1.0:
        graph += f";[c]{atempo_chain(args.speed)}[s]"
        last = "s"

    cmd = (["ffmpeg", "-hide_banner", "-loglevel", "error"]
           + sum((["-i", p] for p in inputs), [])
           + ["-filter_complex", graph, "-map", f"[{last}]", "-ar", "16000", "-ac", "1"]
           + CODECS_BY_EXT[ext] + [args.output, "-y"])
    print("Running:", " ".join(cmd))
    r = run(cmd)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{r.stderr.strip()}")

    # --- verification (this is the part that matters; don't trust exit code alone) ---
    actual = duration_of(args.output)
    delta = actual - expected_out
    status = "OK" if abs(delta) <= DURATION_TOLERANCE_S else "FAIL"
    print(f"[{status}] duration: {actual:.2f}s vs expected {expected_out:.2f}s (delta {delta:+.2f}s)")
    if status == "FAIL":
        sys.exit("Duration mismatch — merged file does not account for every segment. Do not transcribe.")

    if len(inputs) > 1:
        cum = 0.0
        for i, info in enumerate(probes[:-1]):
            cum += info["duration"]
            b = cum / args.speed
            start = max(0.0, b - 5.0)
            _, maxv = volumedetect(args.output, start=start, window=10.0)
            flag = "OK" if maxv > BOUNDARY_DEAD_AIR_DB else "SUSPICIOUS"
            print(f"[{flag}] boundary {i + 1} @ {b:.1f}s: max_volume {maxv:.1f} dB"
                  + (" — dead air at splice, check segment order / missing segment" if flag == "SUSPICIOUS" else ""))

    mean, maxv = volumedetect(args.output)
    print(f"[info] overall: mean_volume {mean:.1f} dB, max_volume {maxv:.1f} dB")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
