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

Long audio is transcribed as independently committed 20-minute chunks. The pinned
mlx-audio Qwen3-ASR implementation applies ``max_tokens`` to EACH chunk, not to the
whole recording. Keeping that limit bounded prevents one bad/silent chunk from
growing a multi-hour KV cache; committing every chunk makes interruption resumable.

Dependencies are pinned because newer mlx-audio/transformers combinations have
broken Qwen3-ASR model loading in practice.
"""

import argparse
import hashlib
import json
import numbers
import os
import platform
import sys
import threading
import time
from importlib.metadata import version
from pathlib import Path


DEFAULT_CHUNK_DURATION_S = 1200.0
DEFAULT_MAX_TOKENS_PER_CHUNK = 8192
MAX_SAFE_TOKENS_PER_CHUNK = 16384
OWNER_POLL_SECONDS = 5.0


class ChunkTokenLimitError(RuntimeError):
    """A chunk exhausted its bounded generation budget."""


def build_parser():
    parser = argparse.ArgumentParser(description="Transcribe audio/video using local MLX Qwen3-ASR")
    parser.add_argument("inputs", nargs="*", help="Audio/video file paths")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as input)")
    parser.add_argument("--model", default="mlx-community/Qwen3-ASR-1.7B-8bit",
                        help="HuggingFace model ID (default: mlx-community/Qwen3-ASR-1.7B-8bit)")
    parser.add_argument("--language", default="Chinese",
                        help="Language for transcription output (default: Chinese)")
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS_PER_CHUNK,
        help=("Maximum generation tokens PER audio chunk "
              f"(default {DEFAULT_MAX_TOKENS_PER_CHUNK}; safe ceiling "
              f"{MAX_SAFE_TOKENS_PER_CHUNK})"),
    )
    parser.add_argument(
        "--chunk-duration",
        type=float,
        default=DEFAULT_CHUNK_DURATION_S,
        help="Maximum chunk duration in seconds (default 1200 = 20 minutes)",
    )
    parser.add_argument(
        "--allow-high-token-budget",
        action="store_true",
        help="Explicitly allow --max-tokens above the safe per-chunk ceiling",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Checkpoint root (default: <output-dir>/_mlx_checkpoints)",
    )
    parser.add_argument(
        "--owner-pid",
        type=int,
        default=None,
        help="Exit if this supervising process disappears (used by managed pipelines)",
    )
    parser.add_argument("--smoke-test", action="store_true",
                        help="Load the model and exit without transcribing audio")
    return parser


def validate_args(parser, args):
    if not args.inputs and not args.smoke_test:
        parser.error("at least one input file is required unless --smoke-test is set")
    if args.max_tokens <= 0:
        parser.error("--max-tokens must be positive")
    if args.chunk_duration <= 0:
        parser.error("--chunk-duration must be positive")
    if args.max_tokens > MAX_SAFE_TOKENS_PER_CHUNK and not args.allow_high_token_budget:
        parser.error(
            f"--max-tokens={args.max_tokens} exceeds the safe PER-CHUNK ceiling "
            f"{MAX_SAFE_TOKENS_PER_CHUNK}; use --allow-high-token-budget only after "
            "measuring unified-memory impact"
        )
    if args.owner_pid is not None and (args.owner_pid <= 1 or args.owner_pid == os.getpid()):
        parser.error("--owner-pid must identify a different live supervising process")


def _owner_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_owner_watchdog(owner_pid, poll_seconds=OWNER_POLL_SECONDS):
    """Bind a managed ASR worker to its supervisor without affecting direct CLI use."""
    if owner_pid is None:
        return None
    if not _owner_alive(owner_pid):
        raise RuntimeError(f"ASR owner process is not alive: pid={owner_pid}")

    def watch():
        while True:
            time.sleep(poll_seconds)
            if _owner_alive(owner_pid):
                continue
            message = (
                f"ASR owner pid={owner_pid} disappeared; aborting orphan worker "
                "with resumable checkpoints intact.\n"
            )
            try:
                os.write(2, message.encode("utf-8", "replace"))
            finally:
                os._exit(125)

    thread = threading.Thread(target=watch, name="asr-owner-watchdog", daemon=True)
    thread.start()
    return thread


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def atomic_write_text(path, text):
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path, value):
    atomic_write_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path, chunk_bytes=8 * 1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk_bytes):
            digest.update(block)
    return digest.hexdigest()


def _checkpoint_identity(audio_path, model_name, language, chunk_duration, max_tokens):
    source = Path(audio_path).resolve()
    state = source.stat()
    identity = {
        "source": str(source),
        "source_size": state.st_size,
        "source_mtime_ns": state.st_mtime_ns,
        "source_sha256": _sha256_file(source),
        "model": model_name,
        "language": language,
        "chunk_duration_s": chunk_duration,
        "max_tokens_per_chunk": max_tokens,
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return identity, digest


def _load_or_create_manifest(path, identity, chunk_count):
    expected = {
        "schema_version": 1,
        **identity,
        "chunk_count": chunk_count,
    }
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise RuntimeError(
                    f"checkpoint identity mismatch for {key}: "
                    f"expected {value!r}, got {manifest.get(key)!r}"
                )
        chunks = manifest.get("chunks")
        if not isinstance(chunks, list) or len(chunks) != chunk_count:
            raise RuntimeError("checkpoint chunk table is missing or malformed")
        return manifest
    manifest = {
        **expected,
        "status": "pending",
        "current_chunk": None,
        "updated_at": time.time(),
        "chunks": [{"index": index, "status": "pending"} for index in range(chunk_count)],
    }
    atomic_write_json(path, manifest)
    return manifest


def _validated_completed_part(checkpoint_dir, entry):
    if entry.get("status") != "done":
        return None
    part_name = entry.get("part")
    expected_hash = entry.get("sha256")
    if not part_name or not expected_hash:
        raise RuntimeError(f"completed checkpoint entry is incomplete: {entry}")
    part = checkpoint_dir / part_name
    if not part.is_file():
        raise RuntimeError(f"completed checkpoint part is missing: {part}")
    text = part.read_text(encoding="utf-8")
    if _sha256_text(text) != expected_hash:
        raise RuntimeError(f"completed checkpoint part hash mismatch: {part}")
    return text


def transcribe_chunks(
    model,
    chunks,
    output_path,
    checkpoint_dir,
    identity,
    max_tokens,
    language,
    chunk_duration,
    clear_cache=None,
):
    """Transcribe and atomically commit each upstream-equivalent audio chunk."""
    output_path = Path(output_path)
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = checkpoint_dir / "manifest.json"
    manifest = _load_or_create_manifest(manifest_path, identity, len(chunks))
    texts = []

    for index, (chunk_audio, offset_seconds) in enumerate(chunks):
        entry = manifest["chunks"][index]
        completed = _validated_completed_part(checkpoint_dir, entry)
        if completed is not None:
            texts.append(completed)
            print(
                f"Chunk {index + 1}/{len(chunks)} resumed from checkpoint "
                f"({entry.get('chars', len(completed))} chars)",
                file=sys.stderr,
                flush=True,
            )
            continue

        manifest["status"] = "running"
        manifest["current_chunk"] = index
        manifest["updated_at"] = time.time()
        entry.update({"status": "running", "offset_s": float(offset_seconds)})
        atomic_write_json(manifest_path, manifest)
        print(
            f"Chunk {index + 1}/{len(chunks)} starting at {float(offset_seconds):.1f}s "
            f"(max_tokens={max_tokens})",
            file=sys.stderr,
            flush=True,
        )

        started = time.monotonic()
        try:
            # The upstream splitter may move a boundary by up to five seconds
            # to land on low energy. Give the already-isolated chunk a small
            # margin so model.generate does not split it a second time.
            result = model.generate(
                chunk_audio,
                max_tokens=max_tokens,
                language=language,
                chunk_duration=chunk_duration + 10.0,
                verbose=True,
            )
            text = result.text if hasattr(result, "text") else str(result)
            generation_tokens = getattr(result, "generation_tokens", None)
            if (
                isinstance(generation_tokens, numbers.Integral)
                and generation_tokens >= max_tokens
            ):
                raise ChunkTokenLimitError(
                    f"chunk {index + 1}/{len(chunks)} reached the per-chunk token ceiling "
                    f"({generation_tokens}/{max_tokens}); refusing a possibly repeated or "
                    "truncated transcript"
                )
            part_name = f"chunk-{index:04d}.txt"
            atomic_write_text(checkpoint_dir / part_name, text)
            entry.update(
                {
                    "status": "done",
                    "part": part_name,
                    "chars": len(text),
                    "generation_tokens": generation_tokens,
                    "sha256": _sha256_text(text),
                    "elapsed_s": round(time.monotonic() - started, 3),
                }
            )
            manifest["updated_at"] = time.time()
            atomic_write_json(manifest_path, manifest)
            texts.append(text)
            print(
                f"Chunk {index + 1}/{len(chunks)} committed: "
                f"{len(text)} chars, {generation_tokens} tokens",
                file=sys.stderr,
                flush=True,
            )
        except BaseException as exc:
            entry.update({"status": "failed", "error": str(exc)[:500]})
            manifest.update(
                {
                    "status": "failed",
                    "current_chunk": index,
                    "error": str(exc)[:500],
                    "updated_at": time.time(),
                }
            )
            atomic_write_json(manifest_path, manifest)
            raise
        finally:
            if clear_cache is not None:
                clear_cache()

    final_text = " ".join(text.strip() for text in texts if text.strip())
    atomic_write_text(output_path, final_text)
    manifest.update(
        {
            "status": "complete",
            "current_chunk": None,
            "output": str(output_path),
            "output_sha256": _sha256_text(final_text),
            "updated_at": time.time(),
        }
    )
    manifest.pop("error", None)
    atomic_write_json(manifest_path, manifest)
    return final_text, manifest


def check_platform():
    if sys.platform != "darwin" or platform.machine() not in ("arm64", "aarch64"):
        print("ERROR: Local MLX transcription requires macOS on Apple Silicon (M1+).", file=sys.stderr)
        print("Use the remote API mode instead.", file=sys.stderr)
        sys.exit(1)


def main():
    parser = build_parser()
    args = parser.parse_args()
    validate_args(parser, args)

    check_platform()
    start_owner_watchdog(args.owner_pid)

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
        os.makedirs(out_dir, exist_ok=True)
        output_path = os.path.join(out_dir, f"{name}.txt")

        print(f"\nTranscribing: {os.path.basename(audio_path)}", file=sys.stderr, flush=True)
        t1 = time.time()

        from mlx_audio.stt.models.qwen3_asr.qwen3_asr import split_audio_into_chunks
        from mlx_audio.stt.utils import load_audio
        import mlx.core as mx
        import numpy as np

        sample_rate = int(getattr(model, "sample_rate", 16000))
        waveform = np.array(load_audio(audio_path, sr=sample_rate))
        chunks = split_audio_into_chunks(
            waveform,
            sr=sample_rate,
            chunk_duration=args.chunk_duration,
        )
        identity, digest = _checkpoint_identity(
            audio_path,
            args.model,
            args.language,
            args.chunk_duration,
            args.max_tokens,
        )
        checkpoint_root = Path(args.checkpoint_dir) if args.checkpoint_dir else Path(out_dir) / "_mlx_checkpoints"
        checkpoint_dir = checkpoint_root / f"{name}-{digest[:16]}"
        text, manifest = transcribe_chunks(
            model,
            chunks,
            output_path,
            checkpoint_dir,
            identity,
            args.max_tokens,
            args.language,
            args.chunk_duration,
            clear_cache=mx.clear_cache,
        )

        elapsed = time.time() - t1
        total_tokens = sum(
            entry.get("generation_tokens") or 0 for entry in manifest["chunks"]
        )
        print(f"Done: {elapsed:.1f}s, {len(text)} chars, {total_tokens} tokens → {output_path}",
              file=sys.stderr, flush=True)

    total = time.time() - t0
    print(f"\nAll done. Total: {total:.1f}s", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
