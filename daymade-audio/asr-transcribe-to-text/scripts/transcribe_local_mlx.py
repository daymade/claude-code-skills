# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mlx-audio==0.3.1",
#   "mlx-lm==0.30.5",
#   "transformers==5.0.0rc3",
# ]
# ///
"""
Local ASR transcription using mlx-audio + Qwen3-ASR on Apple Silicon.

Usage:
    uv run scripts/transcribe_local_mlx.py INPUT_AUDIO [INPUT_AUDIO2 ...] [--output-dir DIR]
    uv run scripts/transcribe_local_mlx.py --smoke-test

CRITICAL: max_tokens defaults to 200000. The upstream mlx-audio default (8192)
silently truncates audio longer than ~40 minutes. This was discovered empirically:
123 minutes of Chinese speech requires ~24,000 tokens. 8192 only covers the first
~40 minutes before the token budget is exhausted and remaining chunks are skipped.

Dependencies are pinned because newer mlx-audio/transformers combinations have
broken Qwen3-ASR model loading in practice.
"""

import argparse
import os
import platform
import sys
import time
from importlib.metadata import version


def check_platform():
    if sys.platform != "darwin" or platform.machine() not in ("arm64", "aarch64"):
        print("ERROR: Local MLX transcription requires macOS on Apple Silicon (M1+).", file=sys.stderr)
        print("Use the remote API mode instead.", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Transcribe audio/video using local MLX Qwen3-ASR")
    parser.add_argument("inputs", nargs="*", help="Audio/video file paths")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as input)")
    parser.add_argument("--model", default="mlx-community/Qwen3-ASR-1.7B-8bit",
                        help="HuggingFace model ID (default: mlx-community/Qwen3-ASR-1.7B-8bit)")
    parser.add_argument("--max-tokens", type=int, default=200000,
                        help="Max tokens for generation (default: 200000, covers multi-hour speech)")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Load the model and exit without transcribing audio")
    args = parser.parse_args()

    if not args.inputs and not args.smoke_test:
        parser.error("at least one input file is required unless --smoke-test is set")

    check_platform()

    from mlx_audio.stt.generate import load_model

    print("Dependency stack: "
          f"mlx-audio {version('mlx-audio')}, "
          f"mlx-lm {version('mlx-lm')}, "
          f"transformers {version('transformers')}",
          file=sys.stderr, flush=True)
    print(f"Loading model {args.model}...", file=sys.stderr, flush=True)
    t0 = time.time()
    model = load_model(args.model)
    load_time = time.time() - t0
    print(f"Model loaded in {load_time:.1f}s", file=sys.stderr, flush=True)

    if args.smoke_test:
        print("Smoke test OK: model loaded", file=sys.stderr, flush=True)
        return

    for audio_path in args.inputs:
        if not os.path.exists(audio_path):
            print(f"SKIP: {audio_path} not found", file=sys.stderr)
            continue

        name = os.path.splitext(os.path.basename(audio_path))[0]
        out_dir = args.output_dir or os.path.dirname(audio_path) or "."
        output_path = os.path.join(out_dir, f"{name}.txt")

        print(f"\nTranscribing: {os.path.basename(audio_path)}", file=sys.stderr, flush=True)
        t1 = time.time()

        result = model.generate(audio_path, max_tokens=args.max_tokens, verbose=True)

        elapsed = time.time() - t1
        text = result.text if hasattr(result, "text") else str(result)
        gen_tokens = result.generation_tokens if hasattr(result, "generation_tokens") else "N/A"

        tmp_path = f"{output_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, output_path)

        print(f"Done: {elapsed:.1f}s, {len(text)} chars, {gen_tokens} tokens → {output_path}",
              file=sys.stderr, flush=True)

    total = time.time() - t0
    print(f"\nAll done. Total: {total:.1f}s", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
