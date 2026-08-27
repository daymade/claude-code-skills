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
# requires-python = "==3.13.*"
# dependencies = ["pyannote.audio==4.0.7", "torch==2.13.0", "torchaudio==2.11.0"]
# ///
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

# pyannote 4 enables OTLP metrics during import unless this is already false.
# Local recordings must not emit duration/speaker metadata, and MPS failures
# must not silently spill into a many-hour CPU job.
os.environ["PYANNOTE_METRICS_ENABLED"] = "false"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"


PIPELINE_MODEL_ID = "pyannote/speaker-diarization-3.1"
PIPELINE_MODEL_REVISION = "84fd25912480287da0247647c3d2b4853cb3ee5d"


class PyannoteAccessError(RuntimeError):
    pass


def _torch_module():
    import torch

    return torch


def pick_device(device=None, torch_module=None):
    """Auto-pick cuda > mps > cpu; explicit requests are never rewritten."""
    if device:
        return device
    torch = torch_module or _torch_module()
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_pipeline(device=None):
    """Load the pyannote diarization pipeline ONCE (expensive) so a batch caller
    can reuse it across many files instead of reloading per file. Raises if the
    gated model can't be downloaded (missing HF token / terms not accepted) —
    callers catch and print the setup hint."""
    torch = _torch_module()
    from huggingface_hub.errors import (
        GatedRepoError,
        HfHubHTTPError,
        RepositoryNotFoundError,
    )
    from pyannote.audio import Pipeline

    device = pick_device(device, torch)
    print(f"Using device: {device}", file=sys.stderr, flush=True)
    try:
        pipeline = Pipeline.from_pretrained(
            PIPELINE_MODEL_ID,
            revision=PIPELINE_MODEL_REVISION,
        )
    except (GatedRepoError, RepositoryNotFoundError) as exc:
        raise PyannoteAccessError(
            "pyannote model access is not authorized"
        ) from exc
    except HfHubHTTPError as exc:
        response = getattr(exc, "response", None)
        if getattr(response, "status_code", None) in {401, 403}:
            raise PyannoteAccessError(
                "pyannote model access is not authorized"
            ) from exc
        raise
    if pipeline is None:
        raise PyannoteAccessError(
            "pyannote model is gated; accept its terms and authenticate"
        )
    pipeline.to(torch.device(device))
    return pipeline, device


def resolve_ffmpeg(ffmpeg_path=None):
    """Resolve one decoder executable and fail if it is unavailable."""
    configured = ffmpeg_path or os.environ.get("ASR_FFMPEG_PATH")
    if configured:
        candidate = Path(configured).expanduser()
        if not candidate.is_absolute():
            discovered = shutil.which(str(candidate))
            candidate = Path(discovered) if discovered else candidate
    else:
        discovered = shutil.which("ffmpeg")
        candidate = Path(discovered) if discovered else Path("ffmpeg")
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise RuntimeError(
            "ffmpeg is required for controlled pyannote audio decoding; "
            "pass --ffmpeg-path or set ASR_FFMPEG_PATH"
        )
    return candidate


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def source_contract(path):
    path = Path(path).resolve()
    state = path.stat()
    return {
        "path": str(path),
        "size": state.st_size,
        "sha256": _sha256_file(path),
    }


def producer_contract():
    script = Path(__file__).resolve()
    lock = script.with_suffix(f"{script.suffix}.lock")
    if not lock.is_file():
        raise RuntimeError(f"diarization dependency lock is missing: {lock}")
    return {
        "script": script.name,
        "sha256": _sha256_file(script),
        "lock": lock.name,
        "lock_sha256": _sha256_file(lock),
    }


def model_contract():
    return {
        "id": PIPELINE_MODEL_ID,
        "revision": PIPELINE_MODEL_REVISION,
    }


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


def start_owner_watchdog(owner_pid, interval_seconds=1.0):
    if owner_pid is None:
        return None
    if owner_pid <= 1 or not owner_is_alive(owner_pid):
        raise SystemExit(125)
    stop = threading.Event()

    def watch():
        while not stop.wait(interval_seconds):
            if not owner_is_alive(owner_pid):
                os._exit(125)

    threading.Thread(
        target=watch,
        name=f"pyannote-owner-watch-{owner_pid}",
        daemon=True,
    ).start()
    return stop


def ffmpeg_contract(ffmpeg_path=None, run_command=subprocess.run):
    """Return the exact decoder identity stored with derived artifacts."""
    executable = resolve_ffmpeg(ffmpeg_path)
    completed = run_command(
        [str(executable), "-version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "")[-500:].strip()
        raise RuntimeError(
            f"ffmpeg identity probe failed: exit={completed.returncode}: {detail}"
        )
    version_lines = (completed.stdout or completed.stderr or "").splitlines()
    if not version_lines:
        raise RuntimeError("ffmpeg identity probe returned no version")
    return {
        "path": str(executable),
        "version": version_lines[0],
        "sha256": _sha256_file(executable),
    }


def load_audio_from_ffmpeg(
    audio_path,
    *,
    ffmpeg_path=None,
    torch_module=None,
    run_command=subprocess.run,
):
    """Decode through an explicit FFmpeg process and return pyannote waveform input.

    pyannote 4 otherwise delegates path decoding to TorchCodec and whatever
    FFmpeg shared libraries happen to be visible. Pre-decoding to finite 16 kHz
    mono float32 keeps the model input stable across machines and environments.
    """
    audio_path = Path(audio_path).resolve()
    executable = resolve_ffmpeg(ffmpeg_path)
    with tempfile.TemporaryDirectory(prefix="tinkle_pyannote_decode_") as tmp:
        pcm_path = Path(tmp) / "audio.f32"
        completed = run_command(
            [
                str(executable),
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(audio_path),
                "-f",
                "f32le",
                "-acodec",
                "pcm_f32le",
                "-ac",
                "1",
                "-ar",
                "16000",
                str(pcm_path),
            ],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or b"")[-500:]
            if isinstance(detail, bytes):
                detail = detail.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"ffmpeg could not decode {audio_path.name}: "
                f"exit={completed.returncode}: {detail.strip()}"
            )
        pcm = pcm_path.read_bytes() if pcm_path.is_file() else b""
    if not pcm or len(pcm) % 4 != 0:
        raise RuntimeError(
            f"ffmpeg returned empty or malformed float32 PCM for {audio_path.name}"
        )
    torch = torch_module or _torch_module()
    waveform = torch.frombuffer(bytearray(pcm), dtype=torch.float32).clone()
    if waveform.numel() == 0 or not bool(torch.isfinite(waveform).all()):
        raise RuntimeError(
            f"decoded audio contains no finite samples: {audio_path.name}"
        )
    return {"waveform": waveform.unsqueeze(0), "sample_rate": 16000}


def run_pipeline(pipeline, wav_path, device, ffmpeg_path=None):
    """Run one file through controlled decode and the already-loaded pipeline."""
    wav_path = Path(wav_path)
    print(f"Diarizing {wav_path}...", file=sys.stderr, flush=True)
    audio_input = load_audio_from_ffmpeg(wav_path, ffmpeg_path=ffmpeg_path)
    result = pipeline(audio_input)
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
    return segments


def write_diarization_json(
    segments,
    wav_path,
    device,
    output_json,
    decoder_contract=None,
    source_audio=None,
    producer=None,
    model=None,
):
    output = {
        "wav_path": str(wav_path),
        "device": device,
        "num_segments": len(segments),
        "num_speakers": len(set(s["speaker"] for s in segments)),
        "segments": segments,
    }
    if decoder_contract is not None:
        output["decoder"] = dict(decoder_contract)
    if source_audio is not None:
        output["source_audio"] = dict(source_audio)
    if producer is not None:
        output["producer"] = dict(producer)
    if model is not None:
        output["model_contract"] = dict(model)
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".tinkle_{output_json.name}.",
        suffix=".tmp",
        dir=output_json.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_json)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Saved {len(segments)} segments, {output['num_speakers']} speakers -> {output_json}",
          file=sys.stderr, flush=True)


def diarize(wav_path, output_json, device=None, ffmpeg_path=None, owner_pid=None):
    """CLI entry: load pipeline, run one file, write JSON.

    Batch callers (e.g. speaker_transcribe.py) should call load_pipeline() once
    and run_pipeline() per file instead, to avoid reloading the pipeline."""
    wav_path, output_json = Path(wav_path).resolve(), Path(output_json)
    watchdog = start_owner_watchdog(owner_pid)
    try:
        frozen_source = source_contract(wav_path)
        frozen_producer = producer_contract()
        frozen_model = model_contract()
        decoder = ffmpeg_contract(ffmpeg_path)
        pipeline, device = load_pipeline(device)
        segments = run_pipeline(
            pipeline, wav_path, device, ffmpeg_path=decoder["path"]
        )
        if source_contract(wav_path) != frozen_source:
            raise RuntimeError("source audio changed while diarization was running")
        if producer_contract() != frozen_producer:
            raise RuntimeError("diarization producer changed while processing audio")
        write_diarization_json(
            segments,
            wav_path,
            device,
            output_json,
            decoder_contract=decoder,
            source_audio=frozen_source,
            producer=frozen_producer,
            model=frozen_model,
        )
    finally:
        if watchdog is not None:
            watchdog.set()


def main():
    ap = argparse.ArgumentParser(description="Speaker diarization -> per-segment JSON")
    ap.add_argument("wav_path", type=Path, help="16kHz mono WAV")
    ap.add_argument("output_json", type=Path)
    ap.add_argument("--device", default=None, help="mps / cuda / cpu (default: auto)")
    ap.add_argument(
        "--ffmpeg-path",
        default=None,
        help="explicit FFmpeg executable (or set ASR_FFMPEG_PATH)",
    )
    ap.add_argument("--owner-pid", type=int, default=None)
    args = ap.parse_args()
    try:
        diarize(
            args.wav_path,
            args.output_json,
            args.device,
            args.ffmpeg_path,
            args.owner_pid,
        )
    except PyannoteAccessError as exc:
        print(f"PYANNOTE_ACCESS_BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(3)


if __name__ == "__main__":
    main()
