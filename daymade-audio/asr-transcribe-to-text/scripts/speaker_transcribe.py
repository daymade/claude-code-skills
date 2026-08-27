#!/usr/bin/env python3
# /// script
# requires-python = "==3.13.*"
# dependencies = ["pyannote.audio==4.0.7", "torch==2.13.0", "torchaudio==2.11.0"]
# ///
"""Multi-speaker transcription, DECOUPLED (WhisperX-style): session ASR +
word-level timing + diarization, aligned after the fact. Audio is never cut at
speaker turns before ASR; the Qwen leg owns bounded low-energy long-audio chunks.

Three legs + one aligner:
  1. Qwen3-ASR MLX session transcript    (subprocess: transcribe_local_mlx.py)
  2. mlx-whisper word timestamps        (subprocess: word_timestamps_whisper.py)
  3. pyannote diarization               (in-process, MPS/CUDA; pipeline loaded
                                          ONCE for the whole batch, not per file)
  4. align_speakers.py attaches speakers to the Layer-1 text by mapping it
     onto the timed word lattice and the diarization segments.

Outputs per input (flat under OUTPUT_DIR — same contract downstream tools read):
  <stem>.diarization.json   raw pyannote segments
  <stem>.txt                [MM:SS - MM:SS] SPEAKER_xx + text
  <stem>.csv                file,start,end,duration,speaker,text
  <stem>.alignment.json     alignment provenance + anchored_ratio trust signal
  <stem>.receipt.json       atomic final contract: source + four artifact hashes
Intermediate legs are cached under OUTPUT_DIR/_align/ and reused only when a
sidecar proves the source-audio bytes, producer bytes, parameters, and cached
artifact bytes still match (pass --force to redo them).

Speaker labels are anonymous (SPEAKER_00...). Map them to real names with
voiceprint_id.py — references/voiceprint_speaker_id.md.

Prerequisite — HuggingFace token for pyannote (gated model). The script
implements the missing-token state machine itself (not just documented):
  - no token + first run            -> fail with setup steps (exit 3)
  - no token + config.diarization_declined -> warn (with setup steps) + fall
                                          back to plain text this run
  - token present                   -> proceed; diarize_all still fails exit 3
                                       authoritatively if the gated model can't load

Usage:
  uv run speaker_transcribe.py INPUT.wav [INPUT2.wav ...] OUTPUT_DIR [options]
  --no-diarization   plain-text fast path: Qwen3 full text only
  --text-file PATH   align ONE pre-made transcript (single input only)
  --force            redo intermediate legs even if present
  --timeout SEC      per-leg subprocess timeout (default 1800)
"""
import argparse
import csv
import io
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from transcribe_local_mlx import (
    DEFAULT_CHUNK_DURATION_S,
    DEFAULT_MAX_TOKENS_PER_CHUNK,
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    PINNED_DEPENDENCY_VERSIONS,
    QUALITY_POLICY_ID,
    _sha256_file,
    _sha256_text,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
)

PYANNOTE_SETUP_HINT = """
============================================================
pyannote could not load — speaker diarization needs a one-time setup:

  1. Accept the model terms (free account):
       https://hf.co/pyannote/speaker-diarization-3.1
       (also accept https://hf.co/pyannote/segmentation-3.0 if prompted)
  2. Log in from this machine:
       huggingface-cli login        (or: export HF_TOKEN=hf_...)

Then re-run — the token is detected automatically and speaker
diarization becomes permanent for every future run.
============================================================"""

DIARIZATION_DISABLED_BANNER = """⚠️  Speaker diarization is DISABLED for this run (config.diarization_declined is set).
    Output is plain text only — NO speaker labels.
    To enable speaker labels permanently:
      1. Accept terms: https://hf.co/pyannote/speaker-diarization-3.1
      2. huggingface-cli login   (or: export HF_TOKEN=hf_...)
      3. (optional) remove "diarization_declined" from config.json to stop this warning
    Once a token is present, diarization resumes automatically — no other action needed.
"""

# Substrings that indicate a pyannote/HF access problem (token/terms), vs a real
# bug. Broadened beyond the original few so an upstream wording change doesn't
# turn a legit "accept terms" prompt into a raw traceback.
PYANNOTE_ACCESS_KEYWORDS = (
    "token", "gated", "401", "403", "451", "unauthorized", "unauthorised",
    "forbidden", "accept", "license", "agreement", "login", "permission",
    "private repository", "user conditions", "credentials", "not authenticated",
)

PROCESS_HEARTBEAT_SECONDS = 60.0
PROCESS_TERM_GRACE_SECONDS = 5.0
OWNER_POLL_SECONDS = 5.0
CACHE_PROVENANCE_SCHEMA = 2
FINAL_RECEIPT_SCHEMA = "speaker-bundle-receipt-v1"
FINAL_ARTIFACT_SUFFIXES = {
    "txt": ".txt",
    "csv": ".csv",
    "diarization": ".diarization.json",
    "alignment": ".alignment.json",
}
_SOURCE_IDENTITY_CACHE = {}

# Map the orchestrator's --language to a whisper language code. The whisper leg
# is a TIMING lattice, but it still must decode in the right language or its
# word tokenization is garbage and the difflib anchor ratio collapses.
_WHISPER_LANG_MAP = {
    "chinese": "zh", "zh": "zh", "cn": "zh", "mandarin": "zh",
    "english": "en", "en": "en",
    "japanese": "ja", "ja": "ja",
    "korean": "ko", "ko": "ko",
    "french": "fr", "fr": "fr",
    "german": "de", "de": "de",
    "spanish": "es", "es": "es",
}


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def _source_audio_identity(path):
    source = Path(path).resolve()
    state = source.stat()
    cache_key = (
        str(source),
        state.st_dev,
        state.st_ino,
        state.st_size,
        state.st_mtime_ns,
        state.st_ctime_ns,
    )
    identity = _SOURCE_IDENTITY_CACHE.get(cache_key)
    if identity is None:
        identity = {
            "path": str(source),
            "size": state.st_size,
            "sha256": _sha256_file(source),
        }
        _SOURCE_IDENTITY_CACHE[cache_key] = identity
    return dict(identity)


def _artifact_provenance_path(artifact):
    artifact = Path(artifact)
    return artifact.with_name(f"{artifact.name}.provenance.json")


def _cache_contract(wav, producer_script, parameters):
    producer = HERE / producer_script
    return {
        "schema_version": CACHE_PROVENANCE_SCHEMA,
        "source_audio": _source_audio_identity(wav),
        "producer": {
            "script": producer.name,
            "sha256": _sha256_file(producer),
        },
        "parameters": dict(parameters),
    }


def _artifact_cache_valid(wav, artifact, producer_script, parameters):
    artifact = Path(artifact)
    provenance_path = _artifact_provenance_path(artifact)
    if not artifact.is_file() or not provenance_path.is_file():
        return False
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    expected = _cache_contract(wav, producer_script, parameters)
    if any(provenance.get(key) != value for key, value in expected.items()):
        return False
    return provenance.get("artifact_sha256") == _sha256_file(artifact)


def _write_artifact_provenance(artifact, frozen_contract):
    artifact = Path(artifact)
    provenance = {
        **frozen_contract,
        "artifact_sha256": _sha256_file(artifact),
    }
    atomic_write_json(_artifact_provenance_path(artifact), provenance)


def _cache_contract_still_matches(
    wav, producer_script, parameters, frozen_contract
):
    return _cache_contract(wav, producer_script, parameters) == frozen_contract


def _artifact_provenance_matches_source(wav, artifact):
    artifact = Path(artifact)
    provenance_path = _artifact_provenance_path(artifact)
    if not artifact.is_file() or not provenance_path.is_file():
        return False
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return (
        provenance.get("source_audio") == _source_audio_identity(wav)
        and provenance.get("artifact_sha256") == _sha256_file(artifact)
    )


def _csv_turn_contract_sha256(csv_path):
    fields = ("file", "start", "end", "duration", "speaker", "text")
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        rows = [
            {field: row.get(field) for field in fields}
            for row in csv.DictReader(handle)
        ]
    return _sha256_text(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _stamp_alignment_source(wav, out_dir, stem, expected_source):
    alignment_path = Path(out_dir) / f"{stem}.alignment.json"
    current_source = _source_audio_identity(wav)
    if current_source != expected_source:
        raise RuntimeError(f"source audio changed while aligning: {wav}")
    payload = json.loads(alignment_path.read_text(encoding="utf-8"))
    payload["source_audio"] = current_source
    payload["pipeline"] = {
        "speaker_transcribe_sha256": _sha256_file(Path(__file__)),
        "align_speakers_sha256": _sha256_file(HERE / "align_speakers.py"),
    }
    payload["turn_contract"] = {
        "schema": "speaker-csv-v1",
        "sha256": _csv_turn_contract_sha256(
            Path(out_dir) / f"{stem}.csv"
        ),
    }
    payload["component_sha256"] = {
        "txt": _sha256_file(Path(out_dir) / f"{stem}.txt"),
        "csv": _sha256_file(Path(out_dir) / f"{stem}.csv"),
        "diarization": _sha256_file(
            Path(out_dir) / f"{stem}.diarization.json"
        ),
    }
    payload["label_mapping"] = {}
    atomic_write_json(alignment_path, payload)


def _final_receipt_path(out_dir, stem):
    return Path(out_dir) / f"{stem}.receipt.json"


def _pipeline_contract():
    scripts = (
        "speaker_transcribe.py",
        "transcribe_local_mlx.py",
        "word_timestamps_whisper.py",
        "diarize_speakers.py",
        "align_speakers.py",
    )
    return {
        name: _sha256_file(HERE / name)
        for name in scripts
    }


def _external_text_identity(text_file):
    if text_file is None:
        return None
    path = Path(text_file).resolve()
    state = path.stat()
    return {
        "path": str(path),
        "size": state.st_size,
        "sha256": _sha256_file(path),
    }


def _write_final_receipt(
    wav, out_dir, stem, parameters, pipeline_contract=None
):
    """Atomically commit the complete bundle after every final artifact exists."""
    artifacts = {}
    for name, suffix in FINAL_ARTIFACT_SUFFIXES.items():
        path = Path(out_dir) / f"{stem}{suffix}"
        if not path.is_file():
            raise RuntimeError(f"cannot write final receipt; missing {path}")
        artifacts[name] = {
            "file": path.name,
            "size": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
    payload = {
        "schema": FINAL_RECEIPT_SCHEMA,
        "source_audio": _source_audio_identity(wav),
        "artifacts": artifacts,
        "pipeline": pipeline_contract or _pipeline_contract(),
        "parameters": parameters,
        "model_contract": {
            "id": DEFAULT_MODEL_ID,
            "revision": DEFAULT_MODEL_REVISION,
            "chunk_duration_s": DEFAULT_CHUNK_DURATION_S,
            "max_tokens_per_chunk": DEFAULT_MAX_TOKENS_PER_CHUNK,
            "quality_policy": QUALITY_POLICY_ID,
            "dependencies": dict(sorted(PINNED_DEPENDENCY_VERSIONS.items())),
        },
    }
    atomic_write_json(_final_receipt_path(out_dir, stem), payload)


def _final_artifact_paths(out_dir, stem):
    return {
        name: Path(out_dir) / f"{stem}{suffix}"
        for name, suffix in FINAL_ARTIFACT_SUFFIXES.items()
    }


def _artifact_receipt(path):
    return {
        "file": path.name,
        "size": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def apply_speaker_mapping_transaction(out_dir, stem, mapping, source):
    """Relabel TXT/CSV and commit alignment+receipt last, with rollback."""
    if not mapping:
        return
    if not isinstance(mapping, dict) or any(
        not isinstance(old, str)
        or not old
        or not isinstance(new, str)
        or not new
        for old, new in mapping.items()
    ):
        raise ValueError("speaker mapping must contain non-empty string pairs")

    paths = _final_artifact_paths(out_dir, stem)
    receipt_path = _final_receipt_path(out_dir, stem)
    mutable_paths = {**paths, "receipt": receipt_path}
    missing = [name for name, path in mutable_paths.items() if not path.is_file()]
    if missing:
        raise RuntimeError(
            f"receipt-aware speaker relabel requires complete bundle; missing {missing}"
        )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != FINAL_RECEIPT_SCHEMA:
        raise RuntimeError("speaker bundle receipt schema is invalid")
    recorded_artifacts = receipt.get("artifacts")
    if not isinstance(recorded_artifacts, dict) or any(
        recorded_artifacts.get(name) != _artifact_receipt(path)
        for name, path in paths.items()
    ):
        raise RuntimeError("speaker bundle bytes do not match the final receipt")

    snapshots = {
        name: path.read_bytes() for name, path in mutable_paths.items()
    }
    try:
        transcript = paths["txt"].read_text(encoding="utf-8")
        transcript_label = re.compile(
            r"(?m)^(?P<prefix>\[\d+:\d{2}\.\d{3} - "
            r"\d+:\d{2}\.\d{3}\] )(?P<speaker>.+)$"
        )
        txt_speakers = {
            match.group("speaker")
            for match in transcript_label.finditer(transcript)
        }
        with paths["csv"].open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or "speaker" not in reader.fieldnames:
                raise ValueError("speaker CSV is missing the speaker column")
            fieldnames = list(reader.fieldnames)
            rows = list(reader)
        csv_speakers = {row["speaker"] for row in rows}

        alignment = json.loads(paths["alignment"].read_text(encoding="utf-8"))
        recorded_mapping = alignment.get("label_mapping")
        if not isinstance(recorded_mapping, dict):
            recorded_mapping = {}
        diarization = json.loads(
            paths["diarization"].read_text(encoding="utf-8")
        )
        canonical_speakers = {
            segment.get("speaker")
            for segment in diarization.get("segments", [])
            if isinstance(segment, dict)
            and isinstance(segment.get("speaker"), str)
        }

        effective_mapping = {}
        for old, new in mapping.items():
            if old not in canonical_speakers:
                raise ValueError(
                    f"speaker mapping source {old!r} is not a canonical "
                    "diarization label"
                )
            committed = recorded_mapping.get(old)
            if committed is not None:
                if committed != new:
                    raise ValueError(
                        f"speaker label {old!r} is already mapped to "
                        f"{committed!r}; refusing conflicting remap to {new!r}"
                    )
                continue
            if old == new:
                continue
            in_txt = old in txt_speakers
            in_csv = old in csv_speakers
            if in_txt != in_csv:
                raise ValueError(
                    f"speaker label {old!r} is not consistent across TXT and CSV"
                )
            if in_txt:
                effective_mapping[old] = new
                continue
            raise ValueError(
                f"speaker label {old!r} is absent from the current bundle"
            )
        if not effective_mapping:
            return

        transcript = transcript_label.sub(
            lambda match: (
                match.group("prefix")
                + effective_mapping.get(
                    match.group("speaker"), match.group("speaker")
                )
            ),
            transcript,
        )
        for row in rows:
            row["speaker"] = effective_mapping.get(
                row["speaker"], row["speaker"]
            )

        updated_mapping = {**recorded_mapping, **effective_mapping}

        atomic_write_text(paths["txt"], transcript)
        csv_buffer = io.StringIO(newline="")
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        atomic_write_text(paths["csv"], csv_buffer.getvalue())

        alignment["label_mapping"] = updated_mapping
        alignment["turn_contract"] = {
            "schema": "speaker-csv-v1",
            "sha256": _csv_turn_contract_sha256(paths["csv"]),
        }
        alignment["component_sha256"] = {
            name: _sha256_file(paths[name])
            for name in ("txt", "csv", "diarization")
        }
        sources = alignment.get("label_mapping_sources")
        if not isinstance(sources, list):
            sources = []
        sources.append(source)
        alignment["label_mapping_sources"] = sources[-8:]
        atomic_write_json(paths["alignment"], alignment)

        receipt["artifacts"] = {
            name: _artifact_receipt(path) for name, path in paths.items()
        }
        atomic_write_json(receipt_path, receipt)
    except BaseException:
        restore_errors = []
        for name, payload in snapshots.items():
            try:
                atomic_write_bytes(mutable_paths[name], payload)
            except Exception as exc:
                restore_errors.append(f"{name}:{exc}")
        if restore_errors:
            raise RuntimeError(
                "speaker relabel failed and rollback was incomplete: "
                + "; ".join(restore_errors)
            )
        raise


class ParentTermination(SystemExit):
    """The pipeline supervisor received a termination signal."""


def _owner_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_owner_watchdog(owner_pid, poll_seconds=OWNER_POLL_SECONDS):
    """Terminate this orchestrator if its managed caller disappears."""
    if owner_pid is None:
        return None
    if owner_pid <= 1 or owner_pid == os.getpid() or not _owner_alive(owner_pid):
        raise RuntimeError(f"invalid or dead speaker pipeline owner: pid={owner_pid}")

    def watch():
        while True:
            time.sleep(poll_seconds)
            if _owner_alive(owner_pid):
                continue
            log(f"Owner pid={owner_pid} disappeared; terminating speaker pipeline")
            os.kill(os.getpid(), signal.SIGTERM)
            return

    thread = threading.Thread(target=watch, name="speaker-owner-watchdog", daemon=True)
    thread.start()
    return thread


def _process_group_exists(process_group_id):
    """Return whether any process still belongs to a managed process group."""
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(process, grace_seconds=PROCESS_TERM_GRACE_SECONDS):
    """Terminate a full uv/Python process tree, even if its leader exits first."""
    process_group_id = process.pid
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        if process.poll() is None:
            process.terminate()

    deadline = time.monotonic() + grace_seconds
    while _process_group_exists(process_group_id) and time.monotonic() < deadline:
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    if _process_group_exists(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            if process.poll() is None:
                process.kill()

    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=grace_seconds)


def run(cmd, timeout=None):
    log("+ " + " ".join(str(c) for c in cmd))
    process = subprocess.Popen(cmd, start_new_session=True)
    started = time.monotonic()
    next_heartbeat = started + PROCESS_HEARTBEAT_SECONDS
    previous_handlers = {}

    def interrupted(signum, _frame):
        raise ParentTermination(128 + signum)

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        previous_handlers[signum] = signal.signal(signum, interrupted)
    try:
        while True:
            elapsed = time.monotonic() - started
            if timeout is not None and elapsed >= timeout:
                raise subprocess.TimeoutExpired(cmd, timeout)
            wait_slice = 1.0
            if timeout is not None:
                wait_slice = max(0.001, min(wait_slice, timeout - elapsed))
            try:
                returncode = process.wait(timeout=wait_slice)
                break
            except subprocess.TimeoutExpired:
                now = time.monotonic()
                if now >= next_heartbeat:
                    log(
                        f"Still running pid={process.pid}, elapsed={int(now - started)}s: "
                        + " ".join(str(c) for c in cmd[:4])
                    )
                    next_heartbeat = now + PROCESS_HEARTBEAT_SECONDS
        # A wrapper that exits while descendants remain is not success. Clear the
        # original group before returning so inherited pipes cannot hold callers open.
        _terminate_process_group(process)
        if returncode != 0:
            # Preserve the child pipeline's machine-readable failure class for
            # the DJI supervisor.  Human stderr wording is not an API.
            if returncode in {2, 3, 4, 5}:
                raise SystemExit(returncode)
            raise subprocess.CalledProcessError(returncode, cmd)
    except BaseException:
        _terminate_process_group(process)
        raise
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def _whisper_lang(language):
    """Forward the real language to the whisper leg (was: only 'zh' when the
    orchestrator language started with 'chin', silently forcing zh otherwise)."""
    l = (language or "").strip().lower()
    if l in _WHISPER_LANG_MAP:
        return _WHISPER_LANG_MAP[l]
    if not l:
        return "zh"
    return l  # pass through; whisper rejects unsupported codes clearly rather than silently forcing zh


def _is_pyannote_access_error(e):
    return any(k in str(e).lower() for k in PYANNOTE_ACCESS_KEYWORDS)


def _hint_import_error(e):
    log(f"ERROR importing pyannote stack: {e}")
    log(PYANNOTE_SETUP_HINT)
    log("NOTE: if you ran this with plain `python` instead of `uv run`, that is "
        "likely the cause — pyannote/torch are only installed inside the uv env.")
    sys.exit(3)


def _config_path():
    """config.json path (CLAUDE_PLUGIN_DATA when run via the skill). None when
    not under the agent runtime — then we can't persist 'declined' and fall
    back to first-time-fail."""
    pd = os.environ.get("CLAUDE_PLUGIN_DATA")
    return Path(pd) / "config.json" if pd else None


def _read_config():
    p = _config_path()
    if not p or not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _hf_token_present():
    """Cheap pre-check for a HuggingFace token. The authoritative check is
    still load_pipeline() — a token without accepted terms fails there. This
    just decides warn-vs-fail without the expensive model download."""
    if os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"):
        return True
    tok = Path.home() / ".cache" / "huggingface" / "token"
    try:
        return tok.exists() and bool(tok.read_text(encoding="utf-8").strip())
    except Exception:
        return False


def plain_text_path(args, timeout):
    """Plain-text fast path: session-wide Qwen3 text, no speakers."""
    if args.text_file:
        for wav in args.inputs:
            out = args.out_dir / f"{wav.stem}.txt"
            out.write_text(Path(args.text_file).read_text(encoding="utf-8"), encoding="utf-8")
            log(f"Wrote {out} (from --text-file)")
        return
    cmd = ["uv", "run", str(HERE / "transcribe_local_mlx.py"),
           "--output-dir", str(args.out_dir), "--language", args.language,
           "--owner-pid", str(os.getpid())]
    cmd += [str(w) for w in args.inputs]
    run(cmd, timeout=timeout)


def diarize_all(wavs, out_dir, device, force, ffmpeg_path=None):
    """Leg 3: pyannote pipeline loaded ONCE, run per file (cached — not a
    per-wav reload, which the old loop did and which cost 10-30s/file)."""
    try:
        from diarize_speakers import (
            ffmpeg_contract,
            load_pipeline,
            run_pipeline,
            write_diarization_json,
        )
    except Exception as e:
        _hint_import_error(e)
    decoder = ffmpeg_contract(ffmpeg_path)
    cache_parameters = {"device": device, "decoder": decoder}
    pending = [
        (w, out_dir / f"{w.stem}.diarization.json")
        for w in wavs
        if force
        or not _artifact_cache_valid(
            w,
            out_dir / f"{w.stem}.diarization.json",
            "diarize_speakers.py",
            cache_parameters,
        )
    ]
    if not pending:
        log("Leg 3 (diarization): all cached")
        return decoder
    frozen_contracts = {
        w: _cache_contract(w, "diarize_speakers.py", cache_parameters)
        for w, _diar_json in pending
    }
    try:
        pipeline, dev = load_pipeline(device)
    except Exception as e:
        if _is_pyannote_access_error(e):
            log(f"pyannote access error: {e}")
            log(PYANNOTE_SETUP_HINT)
            sys.exit(3)
        raise
    failed = []
    for wav, diar_json in pending:
        try:
            segments = run_pipeline(
                pipeline, wav, dev, ffmpeg_path=decoder["path"]
            )
        except Exception as e:
            if _is_pyannote_access_error(e):
                log(f"pyannote access error on {wav.name}: {e}")
                log(PYANNOTE_SETUP_HINT)
                sys.exit(3)
            log(f"WARNING: diarization failed for {wav.name} ({e}); skipping")
            failed.append(wav.name)
            continue
        frozen_contract = frozen_contracts[wav]
        if not _cache_contract_still_matches(
            wav, "diarize_speakers.py", cache_parameters, frozen_contract
        ):
            log(
                f"WARNING: source or diarization producer changed while "
                f"processing {wav.name}; refusing provenance"
            )
            failed.append(wav.name)
            continue
        write_diarization_json(
            segments,
            wav,
            dev,
            diar_json,
            decoder_contract=decoder,
        )
        _write_artifact_provenance(diar_json, frozen_contract)
    if failed:
        raise RuntimeError(f"diarization produced no fresh artifact for: {failed}")
    return decoder


def _run_batched_leg(wavs, work_root, script, staging_name, staging_suffix,
                     dest_for, extra_args, force, timeout, cache_label, missing_label,
                     cache_parameters):
    """Shared staging+move ceremony for legs 1 and 2: run `script` once on all
    uncached inputs (it writes flat <stem><staging_suffix> into a staging dir),
    then move each output to dest_for(stem). One model load per leg, not per file."""
    todo = [
        w
        for w in wavs
        if force
        or not _artifact_cache_valid(
            w, dest_for(w.stem), script, cache_parameters
        )
    ]
    if not todo:
        log(f"{cache_label}: all cached")
        return
    staging_root = work_root / staging_name
    staging = staging_root / f".tinkle_run_{uuid.uuid4().hex}"
    frozen_contracts = {
        w: _cache_contract(w, script, cache_parameters) for w in todo
    }
    cmd = ["uv", "run", str(HERE / script), "--output-dir", str(staging)] + extra_args + [str(w) for w in todo]
    run(cmd, timeout=timeout)
    staged_outputs = {
        w: staging / f"{w.stem}{staging_suffix}" for w in todo
    }
    missing_outputs = [
        w.name for w, staged in staged_outputs.items() if not staged.exists()
    ]
    if missing_outputs:
        for name in missing_outputs:
            log(
                f"WARNING: {missing_label} {name} — alignment will fail for "
                "this file"
            )
        raise RuntimeError(
            f"{script} exited 0 but produced no fresh artifact for: "
            f"{missing_outputs}"
        )
    changed_contracts = [
        w.name
        for w in todo
        if not _cache_contract_still_matches(
            w, script, cache_parameters, frozen_contracts[w]
        )
    ]
    if changed_contracts:
        raise RuntimeError(
            f"{script} source or producer changed while processing: "
            f"{changed_contracts}; refusing stale provenance"
        )
    for w in todo:
        staged = staged_outputs[w]
        dest = dest_for(w.stem)
        dest.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(dest)
        _write_artifact_provenance(dest, frozen_contracts[w])


def leg_text(wavs, work_root, language, force, timeout):
    """Leg 1: session-wide Qwen3 transcript (one model load for the batch)."""
    # transcribe_local_mlx.py writes flat <stem>.txt into --output-dir; stage then
    # move to work_root/<stem>/<stem>.qwen.txt (different name — the .qwen. prefix).
    _run_batched_leg(
        wavs, work_root, "transcribe_local_mlx.py", "_qwen", ".txt",
        dest_for=lambda stem: work_root / stem / f"{stem}.qwen.txt",
        extra_args=[
            "--language", language,
            "--owner-pid", str(os.getpid()),
            "--checkpoint-dir", str(work_root / "_qwen" / "_mlx_checkpoints"),
        ],
        force=force, timeout=timeout,
        cache_label="Leg 1 (Qwen3 full text)", missing_label="no Qwen3 transcript for",
        cache_parameters={"language": language})


def leg_words(wavs, work_root, language, initial_prompt, force, timeout):
    """Leg 2: whisper word lattice, one model load for the whole batch."""
    extra = ["--language", _whisper_lang(language)]  # ALWAYS forward the real language (fixes silent-zh-on-English)
    if initial_prompt:
        extra += ["--initial-prompt", initial_prompt]
    _run_batched_leg(
        wavs, work_root, "word_timestamps_whisper.py", "_words", ".words.json",
        dest_for=lambda stem: work_root / stem / f"{stem}.words.json",
        extra_args=extra, force=force, timeout=timeout,
        cache_label="Leg 2 (whisper word lattice)", missing_label="no word lattice for",
        cache_parameters={
            "language": _whisper_lang(language),
            "initial_prompt": initial_prompt,
        })


def leg_align(
    wavs,
    out_dir,
    work_root,
    max_gap,
    text_file=None,
    receipt_parameters=None,
    receipt_pipeline=None,
):
    """Leg 4: attach speakers to full text, write the output contract.
    Per-file resilient — one bad file is recorded as failed, not a batch crash;
    an untrustworthy alignment is NOT written (would ship fake timestamps)."""
    from align_speakers import align, write_outputs, MIN_ANCHOR_RATIO

    failed = []
    for wav in wavs:
        stem = wav.stem
        diar_json = out_dir / f"{stem}.diarization.json"
        wpath = work_root / stem / f"{stem}.words.json"
        tpath = Path(text_file) if text_file else work_root / stem / f"{stem}.qwen.txt"
        missing = [p for p in (diar_json, wpath, tpath) if not p.exists()]
        if missing:
            log(f"ERROR {stem}: missing {[str(p) for p in missing]} — cannot align")
            failed.append(stem)
            continue
        parameters = receipt_parameters or {}
        provenance_inputs = [
            (
                diar_json,
                "diarization",
                "diarize_speakers.py",
                {
                    "device": parameters.get("device"),
                    "decoder": parameters.get("decoder"),
                },
            ),
            (
                wpath,
                "word lattice",
                "word_timestamps_whisper.py",
                {
                    "language": _whisper_lang(parameters.get("language")),
                    "initial_prompt": parameters.get("initial_prompt"),
                },
            ),
        ]
        if text_file is None:
            provenance_inputs.append(
                (
                    tpath,
                    "Qwen transcript",
                    "transcribe_local_mlx.py",
                    {"language": parameters.get("language")},
                )
            )
        stale = [
            label
            for path, label, producer, cache_parameters in provenance_inputs
            if not _artifact_cache_valid(
                wav, path, producer, cache_parameters
            )
        ]
        if stale:
            log(f"ERROR {stem}: stale/unproven {stale} — cannot align")
            failed.append(stem)
            continue
        source_identity = _source_audio_identity(wav)
        try:
            qwen_text = tpath.read_text(encoding="utf-8")
            words = json.loads(wpath.read_text(encoding="utf-8"))["words"]
            segments = json.loads(diar_json.read_text(encoding="utf-8"))["segments"]
            turns, report = align(qwen_text, words, segments, max_gap)
        except Exception as e:
            log(f"ERROR {stem}: alignment failed ({e}) — skipped")
            failed.append(stem)
            continue
        log(f"{stem}: {report['num_turns']} turns, speakers={report['speakers']}, "
            f"anchored_ratio={report['anchored_ratio']}")
        if not report["trustworthy"]:
            log(f"SKIP {stem}: anchored_ratio {report['anchored_ratio']} < {MIN_ANCHOR_RATIO} — "
                "transcripts diverge too heavily; NOT writing speaker-labeled output "
                "(it would be garbage). Re-check audio/text pairing or ASR quality.")
            failed.append(stem)
            continue
        write_outputs(turns, report, wav.name, out_dir, stem)
        _stamp_alignment_source(wav, out_dir, stem, source_identity)
        _write_final_receipt(
            wav,
            out_dir,
            stem,
            receipt_parameters or {},
            receipt_pipeline,
        )
    if failed:
        log(f"FAILED/skipped files: {failed}")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Decoupled multi-speaker transcription")
    ap.add_argument("inputs", nargs="+", type=Path, help="16kHz mono WAV(s)")
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--device", default=None, help="mps / cuda / cpu (default: auto)")
    ap.add_argument(
        "--ffmpeg-path",
        default=None,
        help="explicit FFmpeg executable (or set ASR_FFMPEG_PATH)",
    )
    ap.add_argument("--max-gap", type=float, default=2.0, help="turn split gap (s)")
    ap.add_argument("--language", default="Chinese")
    ap.add_argument("--initial-prompt", default=None,
                    help="Domain terms to prime whisper timing recognition")
    ap.add_argument("--no-diarization", action="store_true",
                    help="plain-text fast path: Qwen3 full text only, no speakers")
    ap.add_argument("--text-file", default=None,
                    help="skip leg 1; align ONE pre-made transcript (single input only)")
    ap.add_argument("--force", action="store_true", help="redo cached intermediate legs")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="per-leg subprocess timeout in seconds (default 1800)")
    ap.add_argument("--owner-pid", type=int, default=None,
                    help="terminate if this managed caller disappears")
    args = ap.parse_args()

    start_owner_watchdog(args.owner_pid)

    # The flat output contract (<stem>.txt/.csv/.diarization.json) keys on stem
    # alone, so duplicate stems can't be disambiguated — refuse rather than
    # silently overwrite one file's output with another's.
    stems = [w.stem for w in args.inputs]
    if len(set(stems)) != len(stems):
        dups = sorted({s for s in stems if stems.count(s) > 1})
        log(f"ERROR: duplicate file stems {dups} — outputs collide on <stem>. "
            "Rename the files to unique names before batching.")
        sys.exit(2)
    # --text-file is one transcript for one wav; with multiple inputs every wav
    # would be aligned against the same text (silent garbage).
    if args.text_file and len(args.inputs) > 1:
        log("ERROR: --text-file aligns ONE pre-made transcript to ONE wav; "
            "pass a single input with it (not a batch).")
        sys.exit(2)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.no_diarization:
        plain_text_path(args, args.timeout)
        log("Done (plain-text fast path, no speaker labels).")
        return

    # pyannote-missing state machine (implemented; see module docstring).
    if not _hf_token_present():
        if _read_config().get("diarization_declined"):
            log(DIARIZATION_DISABLED_BANNER)
            plain_text_path(args, args.timeout)
            log("Done (plain text — diarization disabled; see warning above).")
            return
        log(PYANNOTE_SETUP_HINT)
        sys.exit(3)

    work_root = args.out_dir / "_align"
    work_root.mkdir(parents=True, exist_ok=True)
    # Freeze producer bytes before any long-running leg. If files change while
    # this process runs, downstream current-contract validation rejects the old
    # process instead of attributing its outputs to the new on-disk code.
    receipt_pipeline = _pipeline_contract()

    decoder = diarize_all(
        args.inputs,
        args.out_dir,
        args.device,
        args.force,
        args.ffmpeg_path,
    )
    if args.text_file:
        log("Leg 1 skipped (--text-file)")
    else:
        leg_text(args.inputs, work_root, args.language, args.force, args.timeout)
    leg_words(args.inputs, work_root, args.language, args.initial_prompt, args.force, args.timeout)
    receipt_parameters = {
        "language": args.language,
        "initial_prompt": args.initial_prompt,
        "device": args.device,
        "decoder": decoder,
        "max_gap": args.max_gap,
        "text_file": _external_text_identity(args.text_file),
    }
    leg_align(
        args.inputs,
        args.out_dir,
        work_root,
        args.max_gap,
        args.text_file,
        receipt_parameters,
        receipt_pipeline,
    )
    log("Done.")


if __name__ == "__main__":
    main()
