#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Fuse whisper.cpp timed segments with pyannote speech/speaker intervals.

The adapter deliberately trusts neither decoder alone: whisper.cpp owns text
and coarse timing; pyannote owns speech presence and speaker identity. Segments
that do not overlap any pyannote speech interval are excluded as ungrounded.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
import wave
from pathlib import Path


PIPELINE_ID = "whispercpp-pyannote-late-fusion-v1"
FINAL_RECEIPT_SCHEMA = "speaker-bundle-receipt-v1"
CSV_FIELDS = ("file", "start", "end", "duration", "speaker", "text")


class OwnerProcessLost(RuntimeError):
    pass


def sha256_file(path, chunk_bytes=8 * 1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk_bytes):
            digest.update(block)
    return digest.hexdigest()


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


def atomic_write_json(path, payload):
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def read_json(path):
    path = Path(path).resolve()
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            raw = handle.read()
            after = os.fstat(handle.fileno())
        if any(
            getattr(before, field) != getattr(after, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns")
        ):
            raise ValueError(f"JSON input changed while being read: {path}")
        decoded = raw.decode("utf-8", errors="replace")
        value = json.loads(decoded)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    identity = {
        "path": str(path),
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    return value, decoded.count("\ufffd"), identity


def source_identity(path):
    path = Path(path).resolve()
    state = path.stat()
    return {
        "path": str(path),
        "size": state.st_size,
        "sha256": sha256_file(path),
    }


def require_owner_alive(owner_pid):
    if owner_pid is None:
        return
    if owner_pid <= 1:
        raise OwnerProcessLost("owner PID must be greater than 1")
    try:
        os.kill(owner_pid, 0)
    except ProcessLookupError as exc:
        raise OwnerProcessLost(f"owner process {owner_pid} is not alive") from exc
    except PermissionError:
        pass


def wav_duration(path):
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        if rate <= 0:
            raise ValueError(f"invalid WAV sample rate: {path}")
        return handle.getnframes() / rate


def overlap_seconds(start_a, end_a, start_b, end_b):
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def normalize_repeat_key(text):
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", normalized).strip()


def timed_segments(whisper_payload):
    raw = whisper_payload.get("transcription")
    if not isinstance(raw, list):
        raise ValueError("whisper.cpp JSON has no transcription array")
    result = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"whisper segment {index} is not an object")
        offsets = item.get("offsets")
        text = item.get("text")
        if not isinstance(offsets, dict) or not isinstance(text, str):
            raise ValueError(f"whisper segment {index} lacks offsets/text")
        start_ms = offsets.get("from")
        end_ms = offsets.get("to")
        if (
            isinstance(start_ms, bool)
            or not isinstance(start_ms, (int, float))
            or isinstance(end_ms, bool)
            or not isinstance(end_ms, (int, float))
            or not math.isfinite(float(start_ms))
            or not math.isfinite(float(end_ms))
        ):
            raise ValueError(f"whisper segment {index} has invalid offsets")
        start = float(start_ms) / 1000.0
        end = float(end_ms) / 1000.0
        text = text.strip()
        if end <= start or not text:
            raise ValueError(f"whisper segment {index} has empty text or duration")
        result.append({"index": index, "start": start, "end": end, "text": text})
    return result


def diarization_segments(diarization_payload):
    raw = diarization_payload.get("segments")
    if not isinstance(raw, list):
        raise ValueError("diarization JSON has no segments array")
    result = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"diarization segment {index} is not an object")
        try:
            start = float(item["start"])
            end = float(item["end"])
            speaker = str(item["speaker"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid diarization segment {index}") from exc
        if (
            isinstance(item.get("start"), bool)
            or isinstance(item.get("end"), bool)
            or not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0
            or end <= start
            or not speaker.strip()
        ):
            raise ValueError(f"invalid diarization segment {index}")
        result.append({"start": start, "end": end, "speaker": speaker})
    if result != sorted(
        result, key=lambda item: (item["start"], item["end"], item["speaker"])
    ):
        raise ValueError("diarization segments are not sorted")
    speakers = {item["speaker"] for item in result}
    if diarization_payload.get("num_segments") != len(result):
        raise ValueError("diarization num_segments does not match segments")
    if diarization_payload.get("num_speakers") != len(speakers):
        raise ValueError("diarization num_speakers does not match segments")
    return result


def validate_whisper_receipt(whisper_path, whisper_payload, whisper_contract):
    whisper_path = Path(whisper_path).resolve()
    suffix = ".whispercpp.json"
    if not whisper_path.name.endswith(suffix):
        raise ValueError("whisper JSON name does not follow the runner contract")
    stem = whisper_path.name[: -len(suffix)]
    receipt_path = whisper_path.with_name(f"{stem}.whispercpp.receipt.json")
    if not receipt_path.is_file():
        raise ValueError(f"whisper receipt is missing: {receipt_path}")
    receipt, _replacements, receipt_contract = read_json(receipt_path)
    if receipt.get("schema") != "whispercpp-long-audio-v1-receipt":
        raise ValueError("whisper receipt schema is invalid")
    if receipt.get("source_audio") != whisper_payload.get("source_audio"):
        raise ValueError("whisper receipt source does not match JSON")
    outputs = receipt.get("outputs")
    json_output = outputs.get("json") if isinstance(outputs, dict) else None
    if not isinstance(json_output, dict) or json_output != {
        "file": whisper_path.name,
        "sha256": whisper_contract["sha256"],
    }:
        raise ValueError("whisper receipt does not bind the JSON bytes")
    manifest_receipt = receipt.get("checkpoint_manifest")
    if not isinstance(manifest_receipt, dict):
        raise ValueError("whisper checkpoint receipt is missing")
    manifest_path_value = manifest_receipt.get("path")
    if not isinstance(manifest_path_value, str):
        raise ValueError("whisper checkpoint path is missing")
    manifest_path = Path(manifest_path_value).resolve()
    if not manifest_path.is_file():
        raise ValueError(f"whisper checkpoint manifest is missing: {manifest_path}")
    manifest, _manifest_replacements, manifest_contract = read_json(manifest_path)
    if manifest_receipt.get("sha256") != manifest_contract["sha256"]:
        raise ValueError("whisper checkpoint hash does not match")
    if (
        manifest.get("schema") != "whispercpp-long-audio-checkpoint-v1"
        or manifest.get("status") != "complete"
    ):
        raise ValueError("whisper checkpoint is not complete")
    for field in ("source_audio", "runtime", "parameters", "producer"):
        if manifest.get(field) != whisper_payload.get(field):
            raise ValueError(f"whisper checkpoint {field} does not match JSON")
    if manifest.get("outputs") != outputs:
        raise ValueError("whisper checkpoint outputs do not match receipt")
    return {
        "receipt": receipt_contract,
        "checkpoint_manifest": manifest_contract,
    }


def ground_segments(whisper_segments, diar_segments, min_overlap):
    grounded = []
    discarded_no_speech = []
    diar_index = 0
    for segment in whisper_segments:
        while (
            diar_index < len(diar_segments)
            and diar_segments[diar_index]["end"] <= segment["start"]
        ):
            diar_index += 1
        overlaps = {}
        cursor = diar_index
        while cursor < len(diar_segments):
            diar = diar_segments[cursor]
            if diar["start"] >= segment["end"]:
                break
            overlap = overlap_seconds(
                segment["start"], segment["end"], diar["start"], diar["end"]
            )
            if overlap > 0:
                overlaps[diar["speaker"]] = overlaps.get(diar["speaker"], 0.0) + overlap
            cursor += 1
        if not overlaps or max(overlaps.values()) < min_overlap:
            discarded_no_speech.append(segment)
            continue
        speaker, speaker_overlap = min(
            overlaps.items(), key=lambda item: (-item[1], item[0])
        )
        grounded.append(
            {
                **segment,
                "speaker": speaker,
                "speaker_overlap_s": round(speaker_overlap, 3),
                "speech_overlap_s": round(sum(overlaps.values()), 3),
            }
        )
    return grounded, discarded_no_speech


def collapse_repeat_runs(segments, max_gap=0.25, minimum_run=3):
    kept = []
    discarded = []
    index = 0
    while index < len(segments):
        run = [segments[index]]
        key = normalize_repeat_key(segments[index]["text"])
        cursor = index + 1
        while cursor < len(segments):
            previous = run[-1]
            candidate = segments[cursor]
            if (
                normalize_repeat_key(candidate["text"]) != key
                or candidate["start"] - previous["end"] > max_gap
            ):
                break
            run.append(candidate)
            cursor += 1
        if len(run) >= minimum_run:
            survivor = dict(run[0])
            survivor["collapsed_repeat_count"] = len(run)
            kept.append(survivor)
            discarded.extend(run[1:])
        else:
            kept.extend(run)
        index = cursor
    return kept, discarded


def merge_turns(segments, max_gap):
    turns = []
    for segment in segments:
        if (
            turns
            and turns[-1]["speaker"] == segment["speaker"]
            and segment["start"] - turns[-1]["end"] <= max_gap
        ):
            turns[-1]["end"] = max(turns[-1]["end"], segment["end"])
            turns[-1]["text"] = f"{turns[-1]['text']} {segment['text']}".strip()
            turns[-1]["source_segment_count"] += 1
            turns[-1]["speech_overlap_s"] = round(
                turns[-1]["speech_overlap_s"] + segment["speech_overlap_s"], 3
            )
            continue
        turns.append(
            {
                "start": segment["start"],
                "end": segment["end"],
                "speaker": segment["speaker"],
                "text": segment["text"],
                "source_segment_count": 1,
                "speech_overlap_s": segment["speech_overlap_s"],
            }
        )
    return turns


def format_timestamp(seconds):
    milliseconds = round(seconds * 1000)
    minutes, remainder = divmod(milliseconds, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def render_txt(source_name, turns):
    lines = [f"# File: {source_name}", f"# Turns: {len(turns)}", ""]
    for turn in turns:
        lines.extend(
            [
                f"[{format_timestamp(turn['start'])} - {format_timestamp(turn['end'])}] "
                f"{turn['speaker']}",
                turn["text"],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_csv(source_name, turns):
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=CSV_FIELDS,
    )
    writer.writeheader()
    for turn in turns:
        writer.writerow(
            {
                "file": source_name,
                "start": round(turn["start"], 3),
                "end": round(turn["end"], 3),
                "duration": round(turn["end"] - turn["start"], 3),
                "speaker": turn["speaker"],
                "text": turn["text"],
            }
        )
    return buffer.getvalue()


def csv_turn_contract_sha256(turns, source_name):
    rows = [
        {
            "file": source_name,
            "start": str(round(turn["start"], 3)),
            "end": str(round(turn["end"], 3)),
            "duration": str(round(turn["end"] - turn["start"], 3)),
            "speaker": turn["speaker"],
            "text": turn["text"],
        }
        for turn in turns
    ]
    contract = [
        {field: row.get(field) for field in CSV_FIELDS}
        for row in rows
    ]
    return hashlib.sha256(
        json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Late-fuse whisper.cpp text with pyannote speech/speakers"
    )
    parser.add_argument("whisper_json", type=Path)
    parser.add_argument("diarization_json", type=Path)
    parser.add_argument("source_audio", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--stem", default=None)
    parser.add_argument("--min-speech-overlap", type=float, default=0.05)
    parser.add_argument("--max-gap", type=float, default=2.0)
    parser.add_argument(
        "--end-at",
        type=float,
        default=None,
        help="explicit source-time boundary; later audio remains outside the transcript",
    )
    parser.add_argument("--owner-pid", type=int, default=None)
    args = parser.parse_args()

    if args.min_speech_overlap <= 0:
        parser.error("--min-speech-overlap must be positive")
    if args.max_gap < 0:
        parser.error("--max-gap cannot be negative")
    if args.end_at is not None and args.end_at <= 0:
        parser.error("--end-at must be positive")
    for path in (args.whisper_json, args.diarization_json, args.source_audio):
        if not path.is_file():
            parser.error(f"input does not exist: {path}")
    require_owner_alive(args.owner_pid)

    (
        whisper_payload,
        whisper_utf8_replacements,
        whisper_input_contract,
    ) = read_json(args.whisper_json)
    (
        diarization_payload,
        diarization_utf8_replacements,
        diarization_input_contract,
    ) = read_json(
        args.diarization_json
    )
    whisper_receipts = validate_whisper_receipt(
        args.whisper_json, whisper_payload, whisper_input_contract
    )
    script_path = Path(__file__).resolve()
    runner_path = script_path.with_name("transcribe_long_whispercpp.py")
    diarizer_path = script_path.with_name("diarize_speakers.py")
    diarizer_lock_path = diarizer_path.with_suffix(
        f"{diarizer_path.suffix}.lock"
    )
    for producer_path in (runner_path, diarizer_path, diarizer_lock_path):
        if not producer_path.is_file():
            raise ValueError(f"pipeline producer is missing: {producer_path}")
    frozen_producers = {
        "transcribe_long_whispercpp.py": source_identity(runner_path),
        "fuse_whispercpp_diarization.py": source_identity(script_path),
        "diarize_speakers.py": source_identity(diarizer_path),
        "diarize_speakers.py.lock": source_identity(diarizer_lock_path),
    }
    whisper_segments = timed_segments(whisper_payload)
    diar_segments = diarization_segments(diarization_payload)
    current_source = source_identity(args.source_audio)
    recorded_source = whisper_payload.get("source_audio")
    if not isinstance(recorded_source, dict) or any(
        recorded_source.get(field) != current_source[field]
        for field in ("path", "size", "sha256")
    ):
        raise ValueError("whisper.cpp source identity does not match source audio")
    recorded_whisper_producer = whisper_payload.get("producer")
    if (
        not isinstance(recorded_whisper_producer, dict)
        or recorded_whisper_producer.get("script") != runner_path.name
        or recorded_whisper_producer.get("sha256")
        != frozen_producers[runner_path.name]["sha256"]
    ):
        raise ValueError("whisper.cpp producer does not match current runner")
    recorded_diarization_source = diarization_payload.get("source_audio")
    if not isinstance(recorded_diarization_source, dict) or any(
        recorded_diarization_source.get(field) != current_source[field]
        for field in ("path", "size", "sha256")
    ):
        raise ValueError("diarization source identity does not match source audio")
    expected_diarization_producer = {
        "script": diarizer_path.name,
        "sha256": frozen_producers[diarizer_path.name]["sha256"],
        "lock": diarizer_lock_path.name,
        "lock_sha256": frozen_producers[diarizer_lock_path.name]["sha256"],
    }
    if diarization_payload.get("producer") != expected_diarization_producer:
        raise ValueError("diarization producer does not match current pipeline")
    diarization_model_contract = diarization_payload.get("model_contract")
    if not isinstance(diarization_model_contract, dict):
        raise ValueError("diarization model contract is missing")
    diarization_decoder_contract = diarization_payload.get("decoder")
    if not isinstance(diarization_decoder_contract, dict):
        raise ValueError("diarization decoder contract is missing")

    asr_parameters = whisper_payload.get("parameters")
    if not isinstance(asr_parameters, dict):
        raise ValueError("whisper.cpp parameters contract is missing")
    asr_processing_end = asr_parameters.get("processing_end_s")
    if (
        isinstance(asr_processing_end, bool)
        or not isinstance(asr_processing_end, (int, float))
        or not math.isfinite(float(asr_processing_end))
        or float(asr_processing_end) <= 0
    ):
        raise ValueError("whisper.cpp processing boundary is invalid")
    processing_end = float(asr_processing_end)
    if args.end_at is not None and abs(args.end_at - processing_end) > 0.001:
        raise ValueError("fusion boundary does not match whisper.cpp boundary")
    duration = wav_duration(args.source_audio)
    if processing_end > duration + 0.001:
        raise ValueError("processing boundary exceeds source duration")

    raw_whisper_segment_count = len(whisper_segments)
    discarded_after_boundary = []
    bounded_whisper_segments = []
    for segment in whisper_segments:
        if segment["start"] >= processing_end:
            discarded_after_boundary.append(segment)
            continue
        bounded = dict(segment)
        bounded["end"] = min(bounded["end"], processing_end)
        if bounded["end"] > bounded["start"]:
            bounded_whisper_segments.append(bounded)
    whisper_segments = bounded_whisper_segments
    diar_segments = [
        {**segment, "end": min(segment["end"], processing_end)}
        for segment in diar_segments
        if segment["start"] < processing_end
    ]
    canonical_diarization = {
        **diarization_payload,
        "num_segments": len(diar_segments),
        "num_speakers": len({segment["speaker"] for segment in diar_segments}),
        "segments": [
            {
                **segment,
                "duration": round(segment["end"] - segment["start"], 3),
            }
            for segment in diar_segments
        ],
    }
    grounded, discarded_no_speech = ground_segments(
        whisper_segments, diar_segments, args.min_speech_overlap
    )
    deduplicated, discarded_repeats = collapse_repeat_runs(grounded)
    turns = merge_turns(deduplicated, args.max_gap)
    if not turns:
        raise RuntimeError("fusion produced no speech-grounded turns")
    require_owner_alive(args.owner_pid)

    stem = args.stem or args.source_audio.stem
    args.out_dir.mkdir(parents=True, exist_ok=True)
    txt_path = args.out_dir / f"{stem}.txt"
    csv_path = args.out_dir / f"{stem}.csv"
    canonical_diarization_path = args.out_dir / f"{stem}.diarization.json"
    alignment_path = args.out_dir / f"{stem}.alignment.json"
    receipt_path = args.out_dir / f"{stem}.receipt.json"

    atomic_write_json(canonical_diarization_path, canonical_diarization)
    atomic_write_text(txt_path, render_txt(args.source_audio.name, turns))
    atomic_write_text(csv_path, render_csv(args.source_audio.name, turns))
    alignment = {
        "schema": PIPELINE_ID,
        "source_audio": current_source,
        "inputs": {
            "whisper_json": {
                **whisper_input_contract,
                "utf8_replacement_count": whisper_utf8_replacements,
            },
            "whisper_receipt": whisper_receipts["receipt"],
            "whisper_checkpoint_manifest": whisper_receipts[
                "checkpoint_manifest"
            ],
            "diarization_json": {
                **diarization_input_contract,
                "utf8_replacement_count": diarization_utf8_replacements,
            },
        },
        "parameters": {
            "min_speech_overlap_s": args.min_speech_overlap,
            "max_turn_gap_s": args.max_gap,
            "repeat_run_minimum": 3,
            "processing_end_s": processing_end,
        },
        "source_duration_s": round(duration, 6),
        "raw_whisper_segments": raw_whisper_segment_count,
        "segments_within_processing_range": len(whisper_segments),
        "discarded_after_processing_boundary": len(discarded_after_boundary),
        "speech_grounded_segments": len(grounded),
        "discarded_no_speech_segments": len(discarded_no_speech),
        "discarded_adjacent_repeat_segments": len(discarded_repeats),
        "num_turns": len(turns),
        "num_speakers": len({turn["speaker"] for turn in turns}),
        "last_grounded_end_s": round(max(turn["end"] for turn in turns), 3),
        "report": {
            "trustworthy": True,
            "anchored_ratio": 1.0,
            "anchored_ratio_semantics": "same-decoder text and timing",
            "num_turns": len(turns),
            "speakers": sorted({turn["speaker"] for turn in turns}),
        },
        "turn_contract": {
            "schema": "speaker-csv-v1",
            "sha256": csv_turn_contract_sha256(turns, args.source_audio.name),
        },
        "component_sha256": {
            "txt": sha256_file(txt_path),
            "csv": sha256_file(csv_path),
            "diarization": sha256_file(canonical_diarization_path),
        },
        "label_mapping": {},
        "turns": turns,
    }
    atomic_write_json(alignment_path, alignment)
    if source_identity(args.source_audio) != current_source:
        raise RuntimeError("source audio changed while fusion was running")
    for frozen_input in (
        whisper_input_contract,
        diarization_input_contract,
        whisper_receipts["receipt"],
        whisper_receipts["checkpoint_manifest"],
    ):
        if source_identity(Path(frozen_input["path"])) != frozen_input:
            raise RuntimeError(
                f"pipeline input changed during fusion: {frozen_input['path']}"
            )
    for name, frozen in frozen_producers.items():
        if source_identity(Path(frozen["path"])) != frozen:
            raise RuntimeError(f"pipeline producer changed during fusion: {name}")
    require_owner_alive(args.owner_pid)
    pipeline_contract = {
        name: contract["sha256"]
        for name, contract in frozen_producers.items()
    }
    parameters_contract = {
        "asr": whisper_payload.get("parameters"),
        "fusion": alignment["parameters"],
    }
    model_contract = {
        "whisper": whisper_payload.get("runtime"),
        "diarization": diarization_model_contract,
        "diarization_decoder": diarization_decoder_contract,
    }
    receipt = {
        "schema": FINAL_RECEIPT_SCHEMA,
        "source_audio": alignment["source_audio"],
        "producer": {
            "script": script_path.name,
            "sha256": frozen_producers[script_path.name]["sha256"],
        },
        "inputs": alignment["inputs"],
        "artifacts": {
            "txt": {
                "file": txt_path.name,
                "size": txt_path.stat().st_size,
                "sha256": sha256_file(txt_path),
            },
            "csv": {
                "file": csv_path.name,
                "size": csv_path.stat().st_size,
                "sha256": sha256_file(csv_path),
            },
            "diarization": {
                "file": canonical_diarization_path.name,
                "size": canonical_diarization_path.stat().st_size,
                "sha256": sha256_file(canonical_diarization_path),
            },
            "alignment": {
                "file": alignment_path.name,
                "size": alignment_path.stat().st_size,
                "sha256": sha256_file(alignment_path),
            },
        },
        "pipeline": pipeline_contract,
        "parameters": parameters_contract,
        "model_contract": model_contract,
    }
    atomic_write_json(receipt_path, receipt)
    print(
        json.dumps(
            {
                "txt": str(txt_path),
                "csv": str(csv_path),
                "alignment": str(alignment_path),
                "receipt": str(receipt_path),
                "raw_segments": len(whisper_segments),
                "discarded_after_boundary": len(discarded_after_boundary),
                "grounded_segments": len(grounded),
                "discarded_no_speech": len(discarded_no_speech),
                "discarded_repeats": len(discarded_repeats),
                "turns": len(turns),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except OwnerProcessLost as exc:
        print(f"OWNER_GONE: {exc}", file=sys.stderr)
        raise SystemExit(125)
