"""Optional user-configured process dispatch; no inference or SDK dependency.

DAYMADE_AUDIO_CONFIG selects the user JSON profile; otherwise use
$XDG_CONFIG_HOME/daymade-audio/config.json (default ~/.config). A configured
external_dispatch must contain protocol=1 and a literal argv array. The command
receives --request PATH, inherits stdio and owns request cleanup after execution.
Missing/malformed configured dispatch fails closed; an absent binding preserves
standalone producer use. Each independently installable audio Skill ships the
same protocol module.
Inputs declare exactly one of path/uri/text; outputs name exact files. A producer
may explicitly declare raw stdout capture; transport bytes are not voice/name or
transcript-quality confirmation. Describing artifacts must not run inference.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path


BYPASS = "DAYMADE_AUDIO_DISPATCH_BYPASS"
NONCE = "DAYMADE_AUDIO_DISPATCH_NONCE"


class DispatchError(RuntimeError):
    pass


def _binding():
    explicit = os.environ.get("DAYMADE_AUDIO_CONFIG")
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = Path(explicit).expanduser() if explicit is not None else root / "daymade-audio/config.json"
    if not path.is_file():
        if explicit is not None:
            raise DispatchError("DAYMADE_AUDIO_CONFIG must name a readable JSON profile")
        return None
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise DispatchError("audio dispatch profile is unreadable or invalid JSON") from error
    if not isinstance(profile, dict):
        raise DispatchError("audio dispatch profile must be an object")
    if "external_dispatch" not in profile:
        return None
    binding = profile["external_dispatch"]
    if (not isinstance(binding, dict) or type(binding.get("protocol")) is not int
            or binding["protocol"] != 1 or not isinstance(binding.get("argv"), list)
            or not binding["argv"] or any(not isinstance(part, str) or not part or "\0" in part
                                         for part in binding["argv"])):
        raise DispatchError("external_dispatch requires protocol=1 and a nonempty literal argv array")
    return binding


def _consume_bypass(producer_id, script):
    token, nonce = os.environ.get(BYPASS), os.environ.get(NONCE)
    if token is None and nonce is None:
        return False
    try:
        value = json.loads(token) if token else None
    except ValueError as error:
        raise DispatchError("invalid single-use producer bypass") from error
    if (not isinstance(value, dict) or set(value) != {"producer_id", "script", "nonce"}
            or value["producer_id"] != producer_id or value["script"] != script
            or not isinstance(nonce, str) or not nonce or value["nonce"] != nonce):
        raise DispatchError("producer bypass does not match this producer, script and nonce")
    del os.environ[BYPASS]
    del os.environ[NONCE]
    return True


def _artifact(path, kind, role):
    return {"path": str(Path(path).expanduser().resolve()), "kind": kind, "role": role}


def describe(producer_id, args):
    """Describe declared source/possible output files, never scan directories.

    Output existence is decided after the producer runs. Optional reports can
    legitimately be absent; a stale file's presence alone does not prove this
    invocation produced it. The orchestrator must reconcile source/result state.
    """
    inputs, outputs = [], []
    if producer_id in {"asr.speaker", "asr.mlx"}:
        for source in args.inputs:
            source = Path(source)
            inputs.append(_artifact(source, "recording", "source_audio"))
            target = (Path(args.out_dir) if producer_id == "asr.speaker"
                      else Path(args.output_dir) if args.output_dir else source.parent)
            outputs.append(_artifact(target / f"{source.stem}.txt", "transcript", "plain_text"))
            if producer_id == "asr.speaker" and not args.no_diarization:
                for suffix, kind, role in ((".csv", "transcript", "speaker_turns"),
                                           (".diarization.json", "alignment", "diarization"),
                                           (".alignment.json", "alignment", "word_alignment"),
                                           (".receipt.json", "context", "producer_receipt")):
                    outputs.append(_artifact(target / f"{source.stem}{suffix}", kind, role))
        if getattr(args, "text_file", None):
            inputs.append(_artifact(args.text_file, "transcript", "existing_transcript"))
    elif producer_id == "asr.long":
        inputs.append(_artifact(args.audio, "recording", "source_audio"))
        inputs.append(_artifact(args.gpu_runtime_manifest, "context", "gpu_runtime_manifest"))
        for suffix, kind, role in ((".whispercpp.txt", "transcript", "plain_text"),
                                   (".whispercpp.json", "transcript", "timed_segments"),
                                   (".whispercpp.receipt.json", "context", "producer_receipt")):
            outputs.append(_artifact(Path(args.out_dir) / f"{Path(args.audio).stem}{suffix}", kind, role))
    elif producer_id == "asr.remote":
        inputs.append(_artifact(args.source, "recording", "source_audio"))
        outputs.append(_artifact(args.output, "transcript", "plain_text"))
        outputs.append(_artifact(str(args.output) + ".asr.json", "context", "producer_receipt"))
    elif producer_id == "asr.diarize":
        inputs.append(_artifact(args.wav_path, "recording", "source_audio"))
        outputs.append(_artifact(args.output_json, "alignment", "diarization"))
    elif producer_id in {"voiceprint.match", "voiceprint.enroll"}:
        inputs.append(_artifact(args.audio, "recording", "source_audio"))
        inputs.append(_artifact(args.refs, "voiceprint", "reference_vectors"))
        if producer_id == "voiceprint.enroll":
            outputs.append(_artifact(args.refs, "voiceprint", "raw_enrollment_vectors"))
        else:
            inputs.append(_artifact(args.diar, "alignment", "diarization"))
            if args.csv:
                inputs.append(_artifact(args.csv, "transcript", "existing_speaker_turns"))
                csv = Path(args.csv)
                for suffix, kind, role in ((".csv", "transcript", "speaker_turns"),
                                           (".txt", "transcript", "speaker_text"),
                                           (".diarization.json", "alignment", "diarization"),
                                           (".alignment.json", "alignment", "word_alignment"),
                                           (".receipt.json", "context", "producer_receipt")):
                    outputs.append(_artifact(csv.with_suffix(suffix), kind, role))
    elif producer_id == "asr.stepfun_sse":
        inputs.append(_artifact(args.audio, "recording", "source_audio"))
    elif producer_id == "asr.stepfun_file":
        inputs.append({"uri": args.url, "kind": "recording", "role": "source_audio"})
    elif producer_id == "transcript.correct":
        # Reuse the producer's user-owned output-root selection, not a second
        # workspace default. Importing config does not run correction/model code.
        from utils.config import get_config, intermediate_directory
        source = Path(args.input)
        config = get_config()
        inputs.extend([_artifact(source, "transcript", "source_transcript"),
                       _artifact(config.database.path, "dictionary", "correction_dictionary")])
        roster = os.environ.get("TRANSCRIPT_FIXER_PEOPLE_ROSTER") or config.paths.people_roster_path
        if roster:
            inputs.append(_artifact(roster, "context", "people_roster"))
        for domain in (args.domain or "").split(","):
            if domain.strip():
                inputs.append(_artifact(Path(config.paths.config_dir) / "contexts" / f"{domain.strip()}.md",
                                        "context", "domain_context"))
        target = Path(args.output) if args.output else (intermediate_directory(source) or source.parent)
        explicit_file = bool(args.output and not target.is_dir()
                             and target.suffix.lower() in {".md", ".markdown", ".txt"})
        out_dir = target.parent if explicit_file else target
        review_dir = Path(args.sidecar_dir) if args.sidecar_dir else out_dir
        # Auto-finalization can update the input itself; its pre-run bytes must
        # be retained by the orchestrator before it invokes this producer.
        outputs.append(_artifact(source, "transcript", "possibly_finalized_input"))
        outputs.append(_artifact(target if explicit_file else out_dir / f"{source.stem}_stage1.md",
                                 "transcript", "stage1"))
        for suffix in ("_stage2.md", "_dryrun.md"):
            outputs.append(_artifact(out_dir / f"{source.stem}{suffix}", "transcript", suffix[1:-3]))
        for suffix in ("_changes.md", "_needs_review.md"):
            outputs.append(_artifact(review_dir / f"{source.stem}{suffix}", "context", suffix[1:-3]))
        for suffix in ("_对比报告.md", "_unified.diff", "_对比.html", "_行内对比.txt"):
            outputs.append(_artifact(out_dir / f"{source.stem}{suffix}", "context", "comparison_report"))
    else:
        raise DispatchError("unsupported audio producer")
    return inputs, outputs


def dispatch_cli(producer_id, script, args, *, artifacts=None, stdout=None):
    """Replace this process with the configured dispatcher, or run standalone.

    Only a precisely matching bypass is consumed, once, by the original engine.
    Its child producers must independently enter their own configured dispatch.
    """
    try:
        script = str(Path(script).resolve())
        if _consume_bypass(producer_id, script):
            return
        binding = _binding()
        if binding is None:
            return
        inputs, outputs = artifacts() if artifacts is not None else describe(producer_id, args)
        request = {"protocol": 1, "producer_id": producer_id,
                   "executable": sys.executable, "script": script,
                   "argv": sys.argv[1:], "cwd": os.getcwd(), "nonce": uuid.uuid4().hex,
                   "inputs": inputs, "outputs": outputs}
        if stdout is not None:
            request["stdout"] = stdout
        fd, path = tempfile.mkstemp(prefix="daymade-audio-dispatch-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(request, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            command = [*binding["argv"], "--request", path]
            os.execvpe(command[0], command, os.environ.copy())
        except OSError as error:
            Path(path).unlink(missing_ok=True)
            raise DispatchError("configured audio dispatcher could not execute; producer was not run") from error
    except DispatchError as error:
        print(f"Audio dispatch failed: {error}", file=sys.stderr)
        raise SystemExit(78) from error
