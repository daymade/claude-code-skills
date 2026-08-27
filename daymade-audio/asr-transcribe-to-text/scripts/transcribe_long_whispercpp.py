#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Checkpointed long-audio ASR using whisper.cpp + Silero VAD.

The source timeline is partitioned into explicit base blocks. Each extracted
block includes overlap on both sides, but a decoded segment belongs to exactly
one base block according to its source-time midpoint. This preserves context at
boundaries without duplicating text and makes interruption resumable per block.
"""

import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path


SCHEMA = "whispercpp-long-audio-v1"
MANIFEST_SCHEMA = "whispercpp-long-audio-checkpoint-v1"


class CheckpointIntegrityError(RuntimeError):
    pass


class DeterministicTranscriptionError(RuntimeError):
    pass


class OwnerProcessLost(RuntimeError):
    pass


def log(message):
    print(message, file=sys.stderr, flush=True)


def sha256_file(path, chunk_bytes=8 * 1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk_bytes):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_bytes(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".tinkle_{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path, text):
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path, value):
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def wav_contract(path):
    path = Path(path).resolve()
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frame_count = handle.getnframes()
    if channels != 1 or sample_width != 2 or sample_rate != 16000:
        raise ValueError(
            "long whisper.cpp input must be 16 kHz mono PCM16 WAV; "
            f"got channels={channels}, sample_width={sample_width}, "
            f"sample_rate={sample_rate}"
        )
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "channels": channels,
        "sample_width_bytes": sample_width,
        "sample_rate": sample_rate,
        "frame_count": frame_count,
        "duration_s": frame_count / sample_rate,
    }


def file_contract(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"required runtime asset does not exist: {path}")
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def plan_blocks(duration_s, processing_end_s, chunk_duration_s, overlap_s):
    if duration_s <= 0:
        raise ValueError("source duration must be positive")
    if processing_end_s <= 0 or processing_end_s > duration_s:
        raise ValueError("processing end must be inside the source duration")
    if chunk_duration_s <= 0:
        raise ValueError("chunk duration must be positive")
    if overlap_s < 0 or overlap_s >= chunk_duration_s / 2:
        raise ValueError("overlap must be non-negative and below half a chunk")
    blocks = []
    base_start = 0.0
    index = 0
    while base_start < processing_end_s:
        base_end = min(processing_end_s, base_start + chunk_duration_s)
        blocks.append(
            {
                "index": index,
                "base_start_s": round(base_start, 6),
                "base_end_s": round(base_end, 6),
                "extract_start_s": round(max(0.0, base_start - overlap_s), 6),
                "extract_end_s": round(
                    min(duration_s, base_end + overlap_s), 6
                ),
                "status": "pending",
            }
        )
        base_start = base_end
        index += 1
    return blocks


def format_timestamp(milliseconds):
    milliseconds = max(0, round(milliseconds))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def normalized_text(text):
    return "".join(str(text).casefold().split())


def has_shared_bigram(left, right):
    if len(left) < 2 or len(right) < 2:
        return False
    return any(left[index : index + 2] in right for index in range(len(left) - 1))


def deduplicate_block_seams(transcription, blocks, overlap_s):
    """Remove differently segmented copies created by adjacent block overlap."""
    discarded_indexes = set()
    comparison_radius_ms = round(max(1.0, overlap_s * 2) * 1000)
    by_block = {}
    for index, segment in enumerate(transcription):
        by_block.setdefault(segment["block_index"], []).append((index, segment))
    for block_index in range(len(blocks) - 1):
        boundary_ms = round(blocks[block_index]["base_end_s"] * 1000)
        left = [
            item
            for item in by_block.get(block_index, [])
            if item[1]["offsets"]["to"] >= boundary_ms - comparison_radius_ms
        ]
        right = [
            item
            for item in by_block.get(block_index + 1, [])
            if item[1]["offsets"]["from"] <= boundary_ms + comparison_radius_ms
        ]
        for left_index, left_segment in left:
            for right_index, right_segment in right:
                if left_index in discarded_indexes or right_index in discarded_indexes:
                    continue
                overlap_ms = min(
                    left_segment["offsets"]["to"], right_segment["offsets"]["to"]
                ) - max(
                    left_segment["offsets"]["from"], right_segment["offsets"]["from"]
                )
                if overlap_ms <= 0:
                    continue
                left_text = normalized_text(left_segment["text"])
                right_text = normalized_text(right_segment["text"])
                if not left_text or not right_text:
                    continue
                contained = left_text in right_text or right_text in left_text
                matcher = difflib.SequenceMatcher(
                    None, left_text, right_text, autojunk=False
                )
                similarity = matcher.ratio()
                longest_match = matcher.find_longest_match()
                shorter_coverage = longest_match.size / min(
                    len(left_text), len(right_text)
                )
                shorter_duration = min(
                    left_segment["offsets"]["to"]
                    - left_segment["offsets"]["from"],
                    right_segment["offsets"]["to"]
                    - right_segment["offsets"]["from"],
                )
                temporal_coverage = overlap_ms / shorter_duration
                shorter_text, longer_text = sorted(
                    (left_text, right_text), key=len
                )
                fragmented_expansion = (
                    temporal_coverage >= 0.45
                    and len(longer_text) >= len(shorter_text) * 1.5
                    and has_shared_bigram(shorter_text, longer_text)
                )
                if (
                    not contained
                    and similarity < 0.6
                    and shorter_coverage < 0.6
                    and not fragmented_expansion
                ):
                    continue
                if len(left_text) <= len(right_text):
                    discarded_indexes.add(left_index)
                else:
                    discarded_indexes.add(right_index)
    kept = [
        {key: value for key, value in segment.items() if key != "block_index"}
        for index, segment in enumerate(transcription)
        if index not in discarded_indexes
    ]
    return kept, len(discarded_indexes)


def checkpoint_identity(args, source, runtime, processing_end_s):
    return {
        "schema": MANIFEST_SCHEMA,
        "source_audio": source,
        "runtime": runtime,
        "parameters": {
            "processing_end_s": processing_end_s,
            "chunk_duration_s": args.chunk_duration,
            "overlap_s": args.overlap,
            "language": args.language,
            "prompt": args.prompt,
            "vad_threshold": args.vad_threshold,
            "vad_min_speech_ms": args.vad_min_speech_ms,
            "vad_min_silence_ms": args.vad_min_silence_ms,
            "vad_max_speech_s": args.vad_max_speech_s,
            "vad_speech_pad_ms": args.vad_speech_pad_ms,
            "vad_overlap_s": args.vad_overlap,
            "max_context": 0,
        },
        "producer": {
            "script": Path(__file__).name,
            "sha256": sha256_file(Path(__file__)),
        },
    }


def manifest_digest(identity):
    return sha256_text(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def load_or_create_manifest(path, identity, blocks):
    expected = {**identity, "block_count": len(blocks)}
    if path.is_file():
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CheckpointIntegrityError(
                f"checkpoint manifest cannot be decoded: {path}: {exc}"
            ) from exc
        if not isinstance(manifest, dict):
            raise CheckpointIntegrityError("checkpoint manifest root is not an object")
        for key, value in expected.items():
            if manifest.get(key) != value:
                raise CheckpointIntegrityError(
                    f"checkpoint identity mismatch for {key}"
                )
        entries = manifest.get("blocks")
        if not isinstance(entries, list) or len(entries) != len(blocks):
            raise CheckpointIntegrityError("checkpoint block table is malformed")
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or entry.get("index") != index:
                raise CheckpointIntegrityError(
                    f"checkpoint block {index} is malformed or out of order"
                )
            for key in (
                "base_start_s",
                "base_end_s",
                "extract_start_s",
                "extract_end_s",
            ):
                if entry.get(key) != blocks[index][key]:
                    raise CheckpointIntegrityError(
                        f"checkpoint block {index} changed {key}"
                    )
            if entry.get("status") not in {"pending", "running", "failed", "done"}:
                raise CheckpointIntegrityError(
                    f"checkpoint block {index} has invalid status"
                )
        return manifest
    manifest = {
        **expected,
        "status": "pending",
        "updated_at": time.time(),
        "blocks": blocks,
    }
    atomic_write_json(path, manifest)
    return manifest


def validate_done_block(checkpoint_dir, entry):
    if entry.get("status") != "done":
        return None
    expected_name = f"block-{entry['index']:04d}.json"
    if entry.get("artifact") != expected_name:
        raise CheckpointIntegrityError(
            f"completed block {entry['index']} has an invalid artifact name"
        )
    expected_hash = entry.get("sha256")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise CheckpointIntegrityError(
            f"completed block {entry['index']} has no valid hash"
        )
    artifact = checkpoint_dir / expected_name
    if not artifact.is_file() or sha256_file(artifact) != expected_hash:
        raise CheckpointIntegrityError(
            f"completed block {entry['index']} artifact is missing or changed"
        )
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CheckpointIntegrityError(
            f"completed block {entry['index']} artifact cannot be decoded"
        ) from exc
    transcription = payload.get("transcription")
    if (
        payload.get("schema") != SCHEMA
        or payload.get("index") != entry["index"]
        or not isinstance(transcription, list)
    ):
        raise CheckpointIntegrityError(
            f"completed block {entry['index']} artifact contract is invalid"
        )
    for field in (
        "base_start_s",
        "base_end_s",
        "extract_start_s",
        "extract_end_s",
    ):
        if payload.get(field) != entry.get(field):
            raise CheckpointIntegrityError(
                f"completed block {entry['index']} changed {field}"
            )
    replacements = payload.get("utf8_replacement_count")
    if (
        isinstance(replacements, bool)
        or not isinstance(replacements, int)
        or replacements < 0
        or entry.get("utf8_replacement_count") != replacements
        or entry.get("segment_count") != len(transcription)
    ):
        raise CheckpointIntegrityError(
            f"completed block {entry['index']} count receipt is invalid"
        )
    for segment_index, segment in enumerate(transcription):
        offsets = segment.get("offsets") if isinstance(segment, dict) else None
        text = segment.get("text") if isinstance(segment, dict) else None
        start = offsets.get("from") if isinstance(offsets, dict) else None
        end = offsets.get("to") if isinstance(offsets, dict) else None
        if (
            not isinstance(segment, dict)
            or segment.get("block_index") != entry["index"]
            or isinstance(start, bool)
            or not isinstance(start, (int, float))
            or isinstance(end, bool)
            or not isinstance(end, (int, float))
            or not math.isfinite(float(start))
            or not math.isfinite(float(end))
            or float(start) < 0
            or float(end) <= float(start)
            or not isinstance(text, str)
            or not text.strip()
        ):
            raise CheckpointIntegrityError(
                f"completed block {entry['index']} segment {segment_index} is invalid"
            )
        midpoint_s = (float(start) + float(end)) / 2000.0
        owns_midpoint = entry["base_start_s"] <= midpoint_s < entry["base_end_s"]
        if entry["base_end_s"] == entry["extract_end_s"]:
            owns_midpoint = (
                entry["base_start_s"] <= midpoint_s <= entry["base_end_s"]
            )
        if not owns_midpoint:
            raise CheckpointIntegrityError(
                f"completed block {entry['index']} segment {segment_index} "
                "is outside its ownership range"
            )
    return payload


def owner_is_alive(owner_pid):
    if owner_pid is None:
        return True
    try:
        os.kill(owner_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_child(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    process.communicate()


def run_checked(command, timeout, label, owner_pid=None):
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    started = time.monotonic()
    while process.poll() is None:
        if not owner_is_alive(owner_pid):
            terminate_child(process)
            raise OwnerProcessLost(
                f"owner process {owner_pid} disappeared during {label}"
            )
        if time.monotonic() - started >= timeout:
            terminate_child(process)
            raise DeterministicTranscriptionError(
                f"{label} timed out after {timeout}s"
            )
        time.sleep(0.25)
    stdout, stderr = process.communicate()
    completed = subprocess.CompletedProcess(
        command, process.returncode, stdout, stderr
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or b"")[-2000:].decode(
            "utf-8", errors="replace"
        )
        raise DeterministicTranscriptionError(
            f"{label} failed with exit {completed.returncode}: {detail.strip()}"
        )
    return completed


def normalize_whisper_json(raw_path, block):
    raw = raw_path.read_bytes()
    decoded = raw.decode("utf-8", errors="replace")
    replacement_count = decoded.count("\ufffd")
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise DeterministicTranscriptionError(
            f"whisper.cpp output is invalid JSON: {raw_path}: {exc}"
        ) from exc
    transcription = payload.get("transcription")
    if not isinstance(transcription, list):
        raise DeterministicTranscriptionError(
            f"whisper.cpp output has no transcription array: {raw_path}"
        )
    extract_offset_ms = round(block["extract_start_s"] * 1000)
    base_start_ms = round(block["base_start_s"] * 1000)
    base_end_ms = round(block["base_end_s"] * 1000)
    normalized = []
    for segment in transcription:
        if not isinstance(segment, dict) or not isinstance(segment.get("offsets"), dict):
            continue
        text = segment.get("text")
        start = segment["offsets"].get("from")
        end = segment["offsets"].get("to")
        if (
            not isinstance(text, str)
            or not text.strip()
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or end <= start
        ):
            continue
        global_start = round(float(start) + extract_offset_ms)
        global_end = round(float(end) + extract_offset_ms)
        midpoint = (global_start + global_end) / 2
        owns_midpoint = base_start_ms <= midpoint < base_end_ms
        if block["base_end_s"] == block["extract_end_s"]:
            owns_midpoint = base_start_ms <= midpoint <= base_end_ms
        if not owns_midpoint:
            continue
        normalized.append(
            {
                "timestamps": {
                    "from": format_timestamp(global_start),
                    "to": format_timestamp(global_end),
                },
                "offsets": {"from": global_start, "to": global_end},
                "text": text.strip(),
                "block_index": block["index"],
            }
        )
    return normalized, replacement_count


def process_block(args, block, checkpoint_dir):
    index = block["index"]
    with tempfile.TemporaryDirectory(prefix=f"tinkle_whisper_block_{index:04d}_") as tmp:
        temporary = Path(tmp)
        block_wav = temporary / f"block-{index:04d}.wav"
        extract_duration = block["extract_end_s"] - block["extract_start_s"]
        run_checked(
            [
                str(args.ffmpeg_path),
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-ss",
                f"{block['extract_start_s']:.6f}",
                "-i",
                str(args.audio),
                "-t",
                f"{extract_duration:.6f}",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(block_wav),
            ],
            args.block_timeout,
            f"ffmpeg extraction for block {index}",
            args.owner_pid,
        )
        output_prefix = temporary / f"block-{index:04d}-raw"
        command = [
            str(args.whisper_bin),
            "-m",
            str(args.whisper_model),
            "-l",
            args.language,
            "--prompt",
            args.prompt,
            "-mc",
            "0",
            "-sns",
            "--vad",
            "-vm",
            str(args.vad_model),
            "-vt",
            str(args.vad_threshold),
            "-vspd",
            str(args.vad_min_speech_ms),
            "-vsd",
            str(args.vad_min_silence_ms),
            "-vmsd",
            str(args.vad_max_speech_s),
            "-vp",
            str(args.vad_speech_pad_ms),
            "-vo",
            str(args.vad_overlap),
            "-ojf",
            "-f",
            str(block_wav),
            "-of",
            str(output_prefix),
        ]
        run_checked(
            command,
            args.block_timeout,
            f"whisper.cpp block {index}",
            args.owner_pid,
        )
        raw_json = output_prefix.with_suffix(".json")
        if not raw_json.is_file():
            raise DeterministicTranscriptionError(
                f"whisper.cpp block {index} produced no JSON"
            )
        transcription, replacements = normalize_whisper_json(raw_json, block)
    artifact = checkpoint_dir / f"block-{index:04d}.json"
    payload = {
        "schema": SCHEMA,
        "index": index,
        "base_start_s": block["base_start_s"],
        "base_end_s": block["base_end_s"],
        "extract_start_s": block["extract_start_s"],
        "extract_end_s": block["extract_end_s"],
        "utf8_replacement_count": replacements,
        "transcription": transcription,
    }
    atomic_write_json(artifact, payload)
    return artifact, payload


def render_plain_text(transcription):
    return "\n".join(segment["text"] for segment in transcription).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Checkpointed whisper.cpp + Silero VAD long-audio ASR"
    )
    parser.add_argument("audio", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--ffmpeg-path", type=Path, required=True)
    parser.add_argument("--whisper-bin", type=Path, required=True)
    parser.add_argument("--whisper-model", type=Path, required=True)
    parser.add_argument("--vad-model", type=Path, required=True)
    parser.add_argument("--chunk-duration", type=float, default=1200.0)
    parser.add_argument("--overlap", type=float, default=2.0)
    parser.add_argument("--end-at", type=float, default=None)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--prompt", default="以下是简体中文普通话:")
    parser.add_argument("--vad-threshold", type=float, default=0.5)
    parser.add_argument("--vad-min-speech-ms", type=int, default=250)
    parser.add_argument("--vad-min-silence-ms", type=int, default=500)
    parser.add_argument("--vad-max-speech-s", type=float, default=30.0)
    parser.add_argument("--vad-speech-pad-ms", type=int, default=200)
    parser.add_argument("--vad-overlap", type=float, default=0.25)
    parser.add_argument("--block-timeout", type=int, default=1800)
    parser.add_argument("--owner-pid", type=int, default=None)
    args = parser.parse_args()

    args.audio = args.audio.resolve()
    args.out_dir = args.out_dir.resolve()
    args.ffmpeg_path = args.ffmpeg_path.resolve()
    args.whisper_bin = args.whisper_bin.resolve()
    args.whisper_model = args.whisper_model.resolve()
    args.vad_model = args.vad_model.resolve()
    if args.owner_pid is not None and args.owner_pid <= 1:
        parser.error("--owner-pid must be greater than 1")
    if not owner_is_alive(args.owner_pid):
        raise OwnerProcessLost(f"owner process {args.owner_pid} is not alive")
    source = wav_contract(args.audio)
    processing_end_s = args.end_at if args.end_at is not None else source["duration_s"]
    runtime = {
        "ffmpeg": file_contract(args.ffmpeg_path),
        "whisper_bin": file_contract(args.whisper_bin),
        "whisper_model": file_contract(args.whisper_model),
        "vad_model": file_contract(args.vad_model),
    }
    blocks = plan_blocks(
        source["duration_s"], processing_end_s, args.chunk_duration, args.overlap
    )
    identity = checkpoint_identity(args, source, runtime, processing_end_s)
    digest = manifest_digest(identity)
    checkpoint_dir = args.out_dir / "_whispercpp_checkpoints" / (
        f"{args.audio.stem}-{digest[:16]}"
    )
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = checkpoint_dir / "manifest.json"
    manifest = load_or_create_manifest(manifest_path, identity, blocks)

    for index, entry in enumerate(manifest["blocks"]):
        if wav_contract(args.audio) != source:
            raise CheckpointIntegrityError(
                "source audio changed after the checkpoint identity was frozen"
            )
        if validate_done_block(checkpoint_dir, entry) is not None:
            log(f"Block {index + 1}/{len(blocks)} cached")
            continue
        entry["status"] = "running"
        entry["error"] = None
        manifest["status"] = "running"
        manifest["updated_at"] = time.time()
        atomic_write_json(manifest_path, manifest)
        log(
            f"Block {index + 1}/{len(blocks)} "
            f"source={entry['base_start_s']:.3f}-{entry['base_end_s']:.3f}s"
        )
        try:
            artifact, payload = process_block(args, entry, checkpoint_dir)
            if wav_contract(args.audio) != source:
                artifact.unlink(missing_ok=True)
                raise CheckpointIntegrityError(
                    f"source audio changed while block {index} was running"
                )
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            manifest["status"] = "failed"
            manifest["updated_at"] = time.time()
            atomic_write_json(manifest_path, manifest)
            raise
        entry.update(
            {
                "status": "done",
                "artifact": artifact.name,
                "sha256": sha256_file(artifact),
                "segment_count": len(payload["transcription"]),
                "utf8_replacement_count": payload["utf8_replacement_count"],
                "error": None,
            }
        )
        manifest["updated_at"] = time.time()
        atomic_write_json(manifest_path, manifest)

    transcription = []
    block_receipts = []
    for entry in manifest["blocks"]:
        payload = validate_done_block(checkpoint_dir, entry)
        if payload is None:
            raise CheckpointIntegrityError(
                f"block {entry['index']} is not complete after processing"
            )
        transcription.extend(payload["transcription"])
        block_receipts.append(
            {
                "index": entry["index"],
                "artifact": entry["artifact"],
                "sha256": entry["sha256"],
                "segment_count": entry["segment_count"],
            }
        )
    transcription.sort(
        key=lambda item: (
            item["offsets"]["from"],
            item["offsets"]["to"],
            item["block_index"],
        )
    )
    transcription, seam_duplicates_removed = deduplicate_block_seams(
        transcription, blocks, args.overlap
    )
    merged = {
        "schema": SCHEMA,
        "source_audio": source,
        "runtime": runtime,
        "parameters": identity["parameters"],
        "producer": identity["producer"],
        "blocks": block_receipts,
        "seam_duplicates_removed": seam_duplicates_removed,
        "transcription": transcription,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{args.audio.stem}.whispercpp.json"
    text_path = args.out_dir / f"{args.audio.stem}.whispercpp.txt"
    receipt_path = args.out_dir / f"{args.audio.stem}.whispercpp.receipt.json"
    atomic_write_json(json_path, merged)
    atomic_write_text(text_path, render_plain_text(transcription))
    manifest["status"] = "complete"
    manifest["updated_at"] = time.time()
    manifest["outputs"] = {
        "json": {"file": json_path.name, "sha256": sha256_file(json_path)},
        "txt": {"file": text_path.name, "sha256": sha256_file(text_path)},
    }
    atomic_write_json(manifest_path, manifest)
    receipt = {
        "schema": f"{SCHEMA}-receipt",
        "source_audio": source,
        "checkpoint_manifest": {
            "path": str(manifest_path),
            "sha256": sha256_file(manifest_path),
        },
        "outputs": manifest["outputs"],
        "segment_count": len(transcription),
        "seam_duplicates_removed": seam_duplicates_removed,
    }
    atomic_write_json(receipt_path, receipt)
    print(
        json.dumps(
            {
                "json": str(json_path),
                "txt": str(text_path),
                "receipt": str(receipt_path),
                "blocks": len(blocks),
                "segments": len(transcription),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except CheckpointIntegrityError as exc:
        log(f"CHECKPOINT_BLOCKED: {exc}")
        raise SystemExit(4)
    except (DeterministicTranscriptionError, ValueError) as exc:
        log(f"ASR_DETERMINISTIC_BLOCKED: {exc}")
        raise SystemExit(5)
    except OwnerProcessLost as exc:
        log(f"OWNER_GONE: {exc}")
        raise SystemExit(125)
