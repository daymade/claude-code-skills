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
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from importlib.metadata import version
from pathlib import Path


DEFAULT_CHUNK_DURATION_S = 1200.0
DEFAULT_MAX_TOKENS_PER_CHUNK = 8192
MAX_SAFE_TOKENS_PER_CHUNK = 16384
DEFAULT_MODEL_ID = "mlx-community/Qwen3-ASR-1.7B-8bit"
DEFAULT_MODEL_REVISION = "a8379a2e2f9e313c9292cdf1af4055ab56d50d55"
PINNED_DEPENDENCY_VERSIONS = {
    "mlx-audio": "0.3.1",
    "mlx-lm": "0.30.5",
    "transformers": "5.0.0rc3",
}
CHECKPOINT_SCHEMA_VERSION = 2
SPLITTER_CONTRACT_ID = "mlx_audio.qwen3_asr.split_audio_into_chunks-v1"
OWNER_POLL_SECONDS = 5.0
REPETITION_NGRAM_CHARS = 12
REPETITION_MIN_NORMALIZED_CHARS = 400
REPETITION_MIN_UNIQUE_RATIO = 0.20
QUALITY_POLICY_ID = "unique-12gram-v1"
IMMUTABLE_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class ChunkTokenLimitError(RuntimeError):
    """A chunk exhausted its bounded generation budget."""


class TranscriptQualityError(RuntimeError):
    """Generated text is bounded but still unusable ASR output."""


class CheckpointIntegrityError(RuntimeError):
    """Persisted checkpoint state is corrupt or belongs to another contract."""


def build_parser():
    parser = argparse.ArgumentParser(description="Transcribe audio/video using local MLX Qwen3-ASR")
    parser.add_argument("inputs", nargs="*", help="Audio/video file paths")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as input)")
    parser.add_argument("--model", default=DEFAULT_MODEL_ID,
                        help=f"HuggingFace model ID (default: {DEFAULT_MODEL_ID})")
    parser.add_argument(
        "--model-revision",
        default=None,
        help=("Immutable HuggingFace commit for --model. The built-in model "
              "uses its pinned tested revision; custom remote models must "
              "declare one explicitly."),
    )
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
    local_model = Path(args.model).expanduser().is_dir()
    if local_model:
        if args.model_revision is not None:
            parser.error(
                "local --model paths are content-addressed automatically; "
                "omit --model-revision"
            )
    else:
        if args.model_revision is None:
            if args.model != DEFAULT_MODEL_ID:
                parser.error("custom --model requires an immutable --model-revision")
            args.model_revision = DEFAULT_MODEL_REVISION
        if not IMMUTABLE_COMMIT_RE.fullmatch(args.model_revision):
            parser.error(
                "remote --model-revision must be a full 40-character lowercase "
                "commit SHA; branch/tag names such as main are mutable"
            )
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


def _is_audio_input_decode_error(error):
    """Return true only for source-container/audio-decoder failures.

    ``mlx_audio.stt.utils.load_audio`` uses miniaudio for most containers and
    its own ffmpeg wrapper for M4A/AAC. Runtime failures outside those decoder
    paths (GPU allocation, memory pressure, programming errors) must propagate
    unchanged instead of being disguised as container incompatibility.
    """
    error_type = type(error)
    if (
        error_type.__module__ == "miniaudio"
        and error_type.__name__ in {"DecodeError", "MiniaudioError"}
    ):
        return True

    message = str(error)
    if isinstance(error, ValueError) and message.startswith("Unsupported format:"):
        return True
    if isinstance(error, RuntimeError):
        return (
            "ffmpeg not found!" in message
            or message.startswith("ffprobe not found")
            or message.startswith("ffprobe failed:")
            or message == "No audio streams found in file"
            or message.startswith("ffmpeg decoding failed:")
        )
    return False


def load_audio_with_ffmpeg_fallback(
    audio_path,
    sample_rate,
    loader,
    *,
    ffmpeg_path=None,
    run_command=None,
):
    """Decode with MLX first, then normalize unsupported containers via ffmpeg.

    The checkpoint and output identities remain bound to ``audio_path``. The
    normalized WAV is a short-lived decoder input only.
    """
    try:
        return loader(str(audio_path), sr=sample_rate)
    except Exception as direct_error:
        if not _is_audio_input_decode_error(direct_error):
            raise
        executable = ffmpeg_path
        if executable is None:
            executable = shutil.which("ffmpeg")
        if not executable:
            raise RuntimeError(
                f"MLX could not decode {audio_path!s}, and ffmpeg is unavailable "
                "for temporary PCM normalization"
            ) from direct_error

        command_runner = run_command or subprocess.run
        with tempfile.TemporaryDirectory(prefix="tinkle_mlx_audio_") as temp_dir:
            normalized = Path(temp_dir) / "tinkle_normalized.wav"
            command = [
                str(executable),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(audio_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-c:a",
                "pcm_s16le",
                str(normalized),
            ]
            try:
                result = command_runner(
                    command,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as ffmpeg_error:
                raise RuntimeError(
                    f"MLX could not decode {audio_path!s}; ffmpeg could not start: "
                    f"{ffmpeg_error}"
                ) from ffmpeg_error
            if result.returncode != 0 or not normalized.is_file():
                detail = (result.stderr or result.stdout or "no ffmpeg output").strip()
                raise RuntimeError(
                    f"MLX could not decode {audio_path!s}; ffmpeg normalization "
                    f"failed with exit {result.returncode}: {detail[-500:]}"
                ) from direct_error

            print(
                f"MLX decoder could not read {Path(audio_path).name}; "
                "using a temporary ffmpeg-normalized PCM WAV",
                file=sys.stderr,
                flush=True,
            )
            try:
                return loader(str(normalized), sr=sample_rate)
            except Exception as normalized_error:
                if not _is_audio_input_decode_error(normalized_error):
                    raise
                raise RuntimeError(
                    f"MLX could not decode ffmpeg-normalized audio for {audio_path!s}: "
                    f"{normalized_error}"
                ) from normalized_error


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


def _unique_character_ngram_ratio(text, ngram_chars=REPETITION_NGRAM_CHARS):
    """Language-agnostic repetition signal for Chinese and whitespace text."""
    normalized = "".join(character.casefold() for character in text if character.isalnum())
    if len(normalized) < REPETITION_MIN_NORMALIZED_CHARS:
        return None
    window_count = len(normalized) - ngram_chars + 1
    unique_count = len(
        {normalized[index:index + ngram_chars] for index in range(window_count)}
    )
    return unique_count / window_count


def _assert_transcript_quality(text, scope):
    ratio = _unique_character_ngram_ratio(text)
    if ratio is not None and ratio < REPETITION_MIN_UNIQUE_RATIO:
        raise TranscriptQualityError(
            f"{scope} failed repetition-loop quality gate "
            f"(unique_{REPETITION_NGRAM_CHARS}gram_ratio={ratio:.4f} "
            f"< {REPETITION_MIN_UNIQUE_RATIO:.4f}); refusing unusable ASR text"
        )
    return ratio


def _runtime_dependency_versions():
    actual = {name: version(name) for name in PINNED_DEPENDENCY_VERSIONS}
    mismatches = {
        name: {"expected": expected, "actual": actual[name]}
        for name, expected in PINNED_DEPENDENCY_VERSIONS.items()
        if actual[name] != expected
    }
    if mismatches:
        raise RuntimeError(
            "runtime dependency contract mismatch: "
            + json.dumps(mismatches, sort_keys=True)
        )
    return actual


def _sha256_model_tree(model_path):
    """Content-address a local model directory, including symlink targets."""
    root = Path(model_path).expanduser().resolve()
    records = []
    for candidate in sorted(root.rglob("*"), key=lambda path: path.as_posix()):
        if candidate.is_symlink():
            target = candidate.resolve(strict=True)
            if not target.is_file():
                raise ValueError(f"local model symlink is not a file: {candidate}")
        elif candidate.is_file():
            target = candidate
        else:
            continue
        records.append(
            (
                candidate.relative_to(root).as_posix(),
                target.stat().st_size,
                _sha256_file(target),
            )
        )
    if not records:
        raise ValueError(f"local model directory contains no files: {root}")
    return hashlib.sha256(
        json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _resolve_model_source(model_name, model_revision):
    """Resolve remote refs to a commit snapshot or hash local model bytes."""
    model_path = Path(model_name).expanduser()
    if model_path.is_dir():
        content_digest = _sha256_model_tree(model_path)
        return (
            str(model_path.resolve()),
            "local-content-addressed",
            f"local-sha256:{content_digest}",
        )
    from huggingface_hub import snapshot_download

    snapshot = Path(
        snapshot_download(repo_id=model_name, revision=model_revision)
    ).resolve()
    resolved_revision = snapshot.name.lower()
    if not IMMUTABLE_COMMIT_RE.fullmatch(resolved_revision):
        raise RuntimeError(
            f"HuggingFace did not resolve {model_name}@{model_revision} "
            f"to an immutable commit snapshot: {snapshot}"
        )
    return str(snapshot), "resolved-pinned", resolved_revision


def _checkpoint_identity(
    audio_path,
    model_name,
    model_revision,
    language,
    chunk_duration,
    max_tokens,
    sample_rate,
    dependency_versions,
    producer_sha256=None,
):
    source = Path(audio_path).resolve()
    state = source.stat()
    if not model_revision:
        raise ValueError("checkpoint identity requires an immutable model revision")
    producer_sha256 = producer_sha256 or _sha256_file(Path(__file__))
    identity = {
        "source": str(source),
        "source_size": state.st_size,
        "source_mtime_ns": state.st_mtime_ns,
        "source_sha256": _sha256_file(source),
        "model": model_name,
        "model_revision": model_revision,
        "language": language,
        "chunk_duration_s": chunk_duration,
        "max_tokens_per_chunk": max_tokens,
        "sample_rate": sample_rate,
        "quality_policy": QUALITY_POLICY_ID,
        "producer": {
            "script": Path(__file__).name,
            "sha256": producer_sha256,
        },
        "splitter_contract": SPLITTER_CONTRACT_ID,
        "dependencies": dict(sorted(dependency_versions.items())),
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return identity, digest


def _load_or_create_manifest(path, identity, chunk_count):
    expected = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        **identity,
        "chunk_count": chunk_count,
    }
    if path.exists():
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CheckpointIntegrityError(
                f"checkpoint manifest cannot be decoded: {path}: {exc}"
            ) from exc
        if not isinstance(manifest, dict):
            raise CheckpointIntegrityError(
                "checkpoint manifest root must be an object"
            )
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise CheckpointIntegrityError(
                    f"checkpoint identity mismatch for {key}: "
                    f"expected {value!r}, got {manifest.get(key)!r}"
                )
        chunks = manifest.get("chunks")
        if not isinstance(chunks, list) or len(chunks) != chunk_count:
            raise CheckpointIntegrityError(
                "checkpoint chunk table is missing or malformed"
            )
        allowed_statuses = {"pending", "running", "failed", "done"}
        for index, entry in enumerate(chunks):
            if (
                not isinstance(entry, dict)
                or type(entry.get("index")) is not int
                or entry.get("index") != index
                or entry.get("status") not in allowed_statuses
            ):
                raise CheckpointIntegrityError(
                    "checkpoint chunk entries are missing, malformed, or out of order"
                )
            if entry.get("status") == "done":
                part_name = entry.get("part")
                part_hash = entry.get("sha256")
                expected_part_name = f"chunk-{index:04d}.txt"
                if (
                    not isinstance(part_name, str)
                    or Path(part_name).name != part_name
                    or part_name != expected_part_name
                    or not isinstance(part_hash, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", part_hash)
                ):
                    raise CheckpointIntegrityError(
                        f"completed checkpoint entry {index} has unsafe or malformed identity"
                    )
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


def _validated_completed_part(checkpoint_dir, entry, expected_index):
    if not isinstance(entry, dict):
        raise CheckpointIntegrityError("checkpoint chunk entry is not an object")
    if entry.get("status") != "done":
        return None
    if type(entry.get("index")) is not int or entry.get("index") != expected_index:
        raise CheckpointIntegrityError(
            f"completed checkpoint entry index mismatch: expected "
            f"{expected_index}, got {entry.get('index')!r}"
        )
    part_name = entry.get("part")
    expected_hash = entry.get("sha256")
    expected_part_name = f"chunk-{expected_index:04d}.txt"
    if (
        not isinstance(part_name, str)
        or Path(part_name).name != part_name
        or part_name != expected_part_name
        or not isinstance(expected_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
    ):
        raise CheckpointIntegrityError(
            f"completed checkpoint entry is incomplete: {entry}"
        )
    part = checkpoint_dir / part_name
    if not part.is_file():
        raise CheckpointIntegrityError(
            f"completed checkpoint part is missing: {part}"
        )
    try:
        text = part.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CheckpointIntegrityError(
            f"completed checkpoint part cannot be read: {part}: {exc}"
        ) from exc
    if _sha256_text(text) != expected_hash:
        raise CheckpointIntegrityError(
            f"completed checkpoint part hash mismatch: {part}"
        )
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
        completed = _validated_completed_part(checkpoint_dir, entry, index)
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
            quality_ratio = _assert_transcript_quality(
                text, f"chunk {index + 1}/{len(chunks)}"
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
            if quality_ratio is not None:
                entry["unique_12gram_ratio"] = round(quality_ratio, 6)
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
    try:
        final_quality_ratio = _assert_transcript_quality(final_text, "complete transcript")
    except TranscriptQualityError as exc:
        manifest.update(
            {
                "status": "failed",
                "current_chunk": None,
                "error": str(exc)[:500],
                "updated_at": time.time(),
            }
        )
        atomic_write_json(manifest_path, manifest)
        raise
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
    if final_quality_ratio is not None:
        manifest["output_unique_12gram_ratio"] = round(final_quality_ratio, 6)
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
    running_producer_sha256 = _sha256_file(Path(__file__))

    from mlx_audio.stt.utils import load_model

    dependency_versions = _runtime_dependency_versions()
    print("Dependency stack: "
          f"mlx-audio {dependency_versions['mlx-audio']}, "
          f"mlx-lm {dependency_versions['mlx-lm']}, "
          f"transformers {dependency_versions['transformers']}",
          file=sys.stderr, flush=True)
    model_source, model_source_kind, resolved_model_revision = _resolve_model_source(
        args.model, args.model_revision
    )
    args.model_revision = resolved_model_revision
    print(
        f"Loading model {args.model}@{args.model_revision} "
        f"({model_source_kind})...",
        file=sys.stderr,
        flush=True,
    )
    t0 = time.time()
    model = load_model(model_source)
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
        waveform = np.array(
            load_audio_with_ffmpeg_fallback(audio_path, sample_rate, load_audio)
        )
        chunks = split_audio_into_chunks(
            waveform,
            sr=sample_rate,
            chunk_duration=args.chunk_duration,
        )
        identity, digest = _checkpoint_identity(
            audio_path,
            args.model,
            args.model_revision,
            args.language,
            args.chunk_duration,
            args.max_tokens,
            sample_rate,
            dependency_versions,
            producer_sha256=running_producer_sha256,
        )
        checkpoint_root = Path(args.checkpoint_dir) if args.checkpoint_dir else Path(out_dir) / "_mlx_checkpoints"
        checkpoint_dir = checkpoint_root / f"{name}-{digest[:16]}"
        try:
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
        except CheckpointIntegrityError as exc:
            print(f"CHECKPOINT_BLOCKED: {exc}", file=sys.stderr, flush=True)
            raise SystemExit(4) from exc
        except (ChunkTokenLimitError, TranscriptQualityError) as exc:
            print(
                f"ASR_DETERMINISTIC_BLOCKED: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            raise SystemExit(5) from exc

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
