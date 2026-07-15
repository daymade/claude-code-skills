# /// script
# requires-python = ">=3.10"
# dependencies = ["mlx-whisper"]
# ///
"""Word-level timestamps via mlx-whisper — the timing leg of the decoupled pipeline.

Qwen3-ASR emits plain text with no timing, so the decoupled speaker pipeline
borrows whisper's cross-attention word alignment as a TIMING LATTICE ONLY. The
transcript text comes from Qwen3-ASR (better Chinese WER); whisper words are
used purely to place chars on the timeline. See references/whisper_word_timestamps.md
and references/decoupled_speaker_alignment.md.

Apple Silicon only (mlx). Multiple inputs share ONE model load — pass the whole
batch in a single invocation.

Usage:
  uv run word_timestamps_whisper.py INPUT.wav [INPUT2.wav ...] --output-dir DIR \
    [--model mlx-community/whisper-large-v3-turbo] [--language zh] \
    [--initial-prompt "domain terms"] [--skip-existing]
"""
import argparse
import json
import sys
import time
from pathlib import Path


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def check_platform():
    import platform
    if sys.platform != "darwin" or platform.machine() not in ("arm64", "aarch64"):
        log("ERROR: mlx-whisper word timestamps require macOS on Apple Silicon (M1+).")
        log("The speaker pipeline's timing leg has no non-Apple backend yet — see SKILL.md.")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="mlx-whisper word-level timestamps -> JSON")
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--model", default="mlx-community/whisper-large-v3-turbo")
    ap.add_argument("--language", default="zh")
    ap.add_argument("--initial-prompt", default=None,
                    help="Domain terms to prime recognition (product names, jargon)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="Skip files whose <stem>.words.json already exists")
    args = ap.parse_args()

    check_platform()
    import mlx_whisper

    todo = []
    for wav in args.inputs:
        out = args.output_dir / f"{wav.stem}.words.json"
        if args.skip_existing and out.exists():
            log(f"SKIP (exists): {out.name}")
            continue
        todo.append((wav, out))
    if not todo:
        log("Nothing to do.")
        return

    log(f"Loading {args.model} (once for {len(todo)} files) ...")
    t0 = time.time()
    for wav, out in todo:
        log(f"Timing: {wav.name}")
        kwargs = {
            "path_or_hf_repo": args.model,
            "language": args.language,
            "word_timestamps": True,
        }
        if args.initial_prompt:
            kwargs["initial_prompt"] = args.initial_prompt
        result = mlx_whisper.transcribe(str(wav), **kwargs)

        words = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                if "start" in w and "end" in w:
                    words.append({"word": w["word"], "start": round(float(w["start"]), 3),
                                  "end": round(float(w["end"]), 3)})
        if not words:
            log(f"WARNING: no word timestamps for {wav.name} — skipping (alignment will fail for this file)")
            continue

        # Repetition-loop guard (music-only clips hallucinate looping words with
        # confident timestamps — see SKILL.md Batch Transcription). Don't abort:
        # the alignment step's anchored_ratio is the real trust signal; just warn.
        uniq = len({w["word"] for w in words}) / len(words)
        if uniq < 0.06 and len(words) > 20:
            log(f"WARNING: unique-word ratio {uniq:.3f} on {wav.name} — likely no-speech / "
                "music-only; timestamps (and downstream speaker labels) are probably junk")

        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"wav": str(wav), "model": args.model, "num_words": len(words), "words": words}
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(out)
        log(f"  {len(words)} words -> {out.name}")

    log(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
