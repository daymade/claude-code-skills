#!/usr/bin/env python3
"""Measure an explicit existing ASR command and check source-grounded text.

No model selection, installation, scheduler, service mutation or shell command
parsing. Store per-run observations; compare them on demand, not in a ledger.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import unicodedata

from transcribe_remote import atomic_write, sha256


def normalize(text):
    return "".join(char for char in unicodedata.normalize("NFKC", text).casefold()
                   if not char.isspace() and not unicodedata.category(char).startswith("P"))


def edit_distance(left, right):
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def quality(text, expected=None, anchors=(), max_cer=None):
    if max_cer is not None and (not math.isfinite(max_cer) or max_cer < 0):
        raise ValueError("maximum CER must be a finite nonnegative number")
    actual = normalize(text)
    missing = [part for part in anchors if normalize(part) not in actual]
    reference = normalize(expected) if expected is not None else None
    if reference == "":
        raise ValueError("reference contains no speech text")
    if reference is not None and len(reference) > 10000:
        raise ValueError("use a bounded original-speech reference (at most 10000 normalized characters)")
    cer = edit_distance(reference, actual) / len(reference) if reference else None
    if missing or (cer is not None and max_cer is not None and cer > max_cer):
        verdict = "failed"
    elif reference is not None and max_cer is not None:
        verdict = "passed_text_check"
    else:
        verdict = "unverified"
    return {"cer": cer, "missing_anchors": missing, "verdict": verdict,
            "max_cer": max_cer, "speaker_accuracy": "unverified"}


def run(args):
    source, text_path = args.source.resolve(), args.text.resolve()
    output = args.output.resolve()
    inputs = [source, args.argv.resolve()] + [path.resolve() for path in
              (args.reference, args.anchors, args.identity) if path is not None]
    if output in inputs or output == text_path or text_path in inputs:
        raise ValueError("observation and transcript must not overwrite input evidence")
    if output.exists():
        raise ValueError("use a fresh observation path to preserve prior evidence")
    if text_path.exists():
        raise ValueError("use a fresh text path; a pre-existing file could mask failure")
    expected = args.reference.read_text(encoding="utf-8") if args.reference else None
    anchors = json.loads(args.anchors.read_text(encoding="utf-8")) if args.anchors else []
    if not isinstance(anchors, list) or not all(isinstance(s, str) and normalize(s) for s in anchors):
        raise ValueError("anchors must be a JSON list of nonempty speech fragments")
    quality("", expected, anchors, args.max_cer)  # validate before costly inference
    reference_hash = sha256(args.reference) if args.reference else None
    anchors_hash = sha256(args.anchors) if args.anchors else None
    command = json.loads(args.argv.read_text(encoding="utf-8"))
    if not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part for part in command):
        raise ValueError("argv must be a nonempty JSON list of nonempty strings")
    command = [part.replace("{source}", str(source)).replace("{text}", str(text_path))
               for part in command]
    before = sha256(source)
    started = time.monotonic()
    # Inherit stdout/stderr so existing progress, checkpoints and device signals
    # remain visible. The caller's ASR runner owns its interruption/cleanup.
    process = subprocess.run(command, stdin=subprocess.DEVNULL, check=False)
    elapsed = time.monotonic() - started
    if sha256(source) != before:
        raise RuntimeError("source changed during measurement")
    if process.returncode or not text_path.is_file():
        raise RuntimeError(f"ASR command failed or text missing (exit {process.returncode})")
    text = text_path.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError("ASR text is empty")
    if ((args.reference and sha256(args.reference) != reference_hash)
            or (args.anchors and sha256(args.anchors) != anchors_hash)):
        raise RuntimeError("quality reference changed during measurement")
    observation = {"schema": 1, "source_path": str(source), "source_sha256": before,
                   "text_path": str(text_path), "text_sha256": sha256(text_path), "wall_seconds": elapsed,
                   "state": args.state, "route": args.route,
                   "identity_path": str(args.identity.resolve()) if args.identity else None,
                   "identity_sha256": sha256(args.identity) if args.identity else None,
                   "observer_sha256": sha256(__file__),
                   "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                   "reference_path": str(args.reference.resolve()) if args.reference else None,
                   "anchors_path": str(args.anchors.resolve()) if args.anchors else None,
                   "reference_sha256": reference_hash,
                   "anchors_sha256": anchors_hash,
                   "max_cer": args.max_cer}
    atomic_write(args.output, json.dumps(observation, indent=2, ensure_ascii=False) + "\n")
    return {**observation, "quality": quality(text, expected, anchors, args.max_cer)}


def checked_artifact(item, name, optional=False):
    path, digest = item.get(name + "_path"), item.get(name + "_sha256")
    if optional and path is None and digest is None:
        return None
    if not isinstance(path, str) or not isinstance(digest, str) or sha256(path) != digest:
        raise ValueError(f"missing or changed {name} artifact")
    return Path(path)


def compare(observations):
    if len(observations) < 2:
        raise ValueError("compare requires at least two observations")
    for field in ("source_sha256", "reference_sha256", "anchors_sha256"):
        if len({item.get(field) for item in observations}) != 1:
            raise ValueError(f"cannot compare different {field}")
    evaluated = []
    for item in observations:
        checked_artifact(item, "source")
        text = checked_artifact(item, "text").read_text(encoding="utf-8")
        reference = checked_artifact(item, "reference", optional=True)
        anchors = checked_artifact(item, "anchors", optional=True)
        identity = checked_artifact(item, "identity", optional=True)
        evaluated.append({**item, "quality": quality(text,
            reference.read_text(encoding="utf-8") if reference else None,
            json.loads(anchors.read_text(encoding="utf-8")) if anchors else [], item.get("max_cer")),
            "runtime_evidence": json.loads(identity.read_text(encoding="utf-8")) if identity else None})
    if any(item["quality"]["verdict"] != "passed_text_check" for item in evaluated):
        return {"verdict": "quality_not_established", "selected_route": None}
    if len({item.get("max_cer") for item in evaluated}) != 1:
        raise ValueError("cannot compare different quality thresholds")
    # Device/model evidence remains inspectable. Do not turn a caller's route
    # label into a verified GPU or whole-pipeline performance claim.
    fastest = min(evaluated, key=lambda item: item["wall_seconds"])
    return {"verdict": "measured_text_legs_only", "selected_route": fastest["route"],
            "whole_pipeline_winner": None,
            "observations": [{"route": item["route"], "state": item["state"],
                              "wall_seconds": item["wall_seconds"],
                              "quality": item["quality"],
                              "runtime_evidence": item.get("runtime_evidence")}
                             for item in evaluated]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    runner = modes.add_parser("run")
    runner.add_argument("--source", type=Path, required=True)
    runner.add_argument("--text", type=Path, required=True)
    runner.add_argument("--argv", type=Path, required=True)
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument("--route", required=True)
    runner.add_argument("--state", choices=("cold", "warm", "resume", "unknown"), default="unknown")
    runner.add_argument("--identity", type=Path)
    runner.add_argument("--reference", type=Path)
    runner.add_argument("--anchors", type=Path)
    runner.add_argument("--max-cer", type=float)
    comparison = modes.add_parser("compare")
    comparison.add_argument("observations", type=Path, nargs="+")
    args = parser.parse_args()
    if getattr(args, "max_cer", None) is not None and args.max_cer < 0:
        parser.error("max-cer cannot be negative")
    try:
        result = run(args) if args.mode == "run" else compare(
            [json.loads(path.read_text(encoding="utf-8")) for path in args.observations])
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Measurement failed: {error}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
