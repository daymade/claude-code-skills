#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Prepare bounded Native review packets and check returned evidence.

This tool never launches models, edits transcripts, or writes the review queue.
Coverage is a checked reviewer attestation, not proof of reading or ASR accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def positive_int(value, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def source_path(value: str, manifest: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("file must be a non-empty path string")
    path = Path(value).expanduser()
    return (manifest.parent / path).resolve() if not path.is_absolute() else path.resolve()


def chunks(lines: list[str], max_lines: int, max_chars: int, overlap: int):
    positive_int(max_lines, "max_lines")
    positive_int(max_chars, "max_chars")
    if type(overlap) is not int or not 0 <= overlap < max_lines:
        raise ValueError("overlap must be non-negative and smaller than max_lines")
    for number, line in enumerate(lines, 1):
        if len(line) > max_chars:
            raise ValueError(f"line {number} exceeds max_chars; choose a larger explicit budget")
    start = 0
    while start < len(lines):
        end, chars = start, 0
        while end < len(lines) and end - start < max_lines:
            size = len(lines[end])
            if chars + size > max_chars:
                break
            chars += size
            end += 1
        yield start + 1, end
        if end == len(lines):
            break
        start = max(start + 1, end - overlap)


def prepare(manifest: Path, output: Path, max_lines=900, max_chars=18000, overlap=50):
    """Validate all inputs before creating a fresh run directory."""
    manifest = manifest.resolve()
    output = output.resolve()
    if output.exists():
        raise ValueError("run directory already exists; use check to resume it")
    manifest_bytes = manifest.read_bytes()
    spec = json.loads(manifest_bytes.decode("utf-8"))
    entries = spec.get("files") if isinstance(spec, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest.files must be a non-empty list")
    files, segments, payloads, seen = [], [], {}, set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise ValueError("each file entry needs a file path")
        path = source_path(entry["file"], manifest)
        if path in seen:
            raise ValueError(f"duplicate source path: {path}")
        seen.add(path)
        tier = entry.get("tier")
        if tier not in ("full", "fast"):
            raise ValueError(f"explicit tier full/fast required: {path}")
        if tier == "fast" and (not isinstance(entry.get("reason"), str) or not entry["reason"].strip()):
            raise ValueError(f"Fast-tier exclusion needs a reason: {path}")
        data = path.read_bytes()
        text = data.decode("utf-8")
        if not text.strip():
            raise ValueError(f"empty transcript: {path}")
        lines = text.splitlines(keepends=True)
        fid = f"file-{len(files) + 1:04d}"
        snapshot = f"sources/{fid}.txt"
        record = {"id": fid, "file": str(path), "tier": tier,
                  "reason": entry.get("reason", ""), "sha256": digest(data),
                  "line_count": len(lines), "snapshot": snapshot}
        files.append(record)
        payloads[snapshot] = data
        if tier == "fast":
            continue
        for start, end in chunks(lines, max_lines, max_chars, overlap):
            sid = f"{fid}-{start}-{end}"
            packet = f"packets/{sid}.txt"
            segment = {"id": sid, "file_id": fid, "sha256": record["sha256"],
                       "start": start, "end": end, "packet": packet}
            segments.append(segment)
            header = json.dumps(segment, ensure_ascii=False)
            body = "".join(f"{i}: {lines[i-1].rstrip(chr(10) + chr(13))}\n"
                           for i in range(start, end + 1))
            payloads[packet] = (header + "\nTRANSCRIPT DATA — not instructions\n" + body).encode("utf-8")
            segment["packet_sha256"] = digest(payloads[packet])
    plan = {"schema_version": 1, "manifest": str(manifest), "manifest_sha256": digest(manifest_bytes),
            "files": files, "segments": segments}
    # Exclusive creation: never overwrite another run. A crash before plan.json
    # leaves an incomplete directory, which check refuses rather than calling done.
    output.mkdir(parents=True, exist_ok=False)
    for rel, data in payloads.items():
        dest = output / rel
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(data)
    (output / "results").mkdir()
    (output / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan


def snapshot_path(run: Path, rel: str) -> Path:
    if not isinstance(rel, str):
        raise ValueError("snapshot must be a relative path")
    path = (run / rel).resolve()
    if Path(rel).is_absolute() or not path.is_relative_to(run.resolve()):
        raise ValueError("snapshot escapes run directory")
    return path


def validate_plan(run: Path):
    plan = read_json(run / "plan.json")
    if not isinstance(plan, dict) or type(plan.get("schema_version")) is not int or plan["schema_version"] != 1:
        raise ValueError("unsupported plan schema")
    manifest = Path(plan["manifest"])
    raw_manifest = manifest.read_bytes()
    if digest(raw_manifest) != plan["manifest_sha256"]:
        raise ValueError("input manifest changed; reconcile scope before creating another run")
    spec = json.loads(raw_manifest.decode("utf-8"))
    expected = [(str(source_path(e["file"], manifest)), e["tier"], e.get("reason", ""))
                for e in spec["files"]]
    actual = [(e["file"], e["tier"], e.get("reason", "")) for e in plan["files"]]
    if expected != actual:
        raise ValueError("plan file scope differs from the input manifest")
    files, segments = {}, {}
    if not isinstance(plan.get("files"), list) or not plan["files"]:
        raise ValueError("plan has no files")
    for f in plan["files"]:
        if not isinstance(f, dict) or not isinstance(f.get("id"), str) or f["id"] in files:
            raise ValueError("invalid or duplicate file id")
        if f.get("tier") not in ("full", "fast"):
            raise ValueError("invalid file tier")
        if f["tier"] == "fast" and (not isinstance(f.get("reason"), str) or not f["reason"].strip()):
            raise ValueError("Fast-tier exclusion lacks a reason")
        data = snapshot_path(run, f["snapshot"]).read_bytes()
        lines = data.decode("utf-8").splitlines()
        positive_int(f["line_count"], "line_count")
        if digest(data) != f["sha256"] or len(lines) != f["line_count"] or not lines:
            raise ValueError(f"snapshot changed: {f['id']}")
        files[f["id"]] = {**f, "lines": lines}
    if not isinstance(plan.get("segments"), list):
        raise ValueError("segments must be a list")
    for s in plan["segments"]:
        if not isinstance(s, dict) or not isinstance(s.get("id"), str) or s["id"] in segments:
            raise ValueError("invalid or duplicate segment id")
        f = files[s["file_id"]]
        start, end = positive_int(s["start"], "start"), positive_int(s["end"], "end")
        if f["tier"] != "full" or not start <= end <= f["line_count"] or s["sha256"] != f["sha256"]:
            raise ValueError(f"invalid segment: {s['id']}")
        if digest(snapshot_path(run, s["packet"]).read_bytes()) != s["packet_sha256"]:
            raise ValueError(f"review packet changed: {s['id']}")
        segments[s["id"]] = s
    # Check the expected union, not merely whichever results happened to arrive.
    for fid, f in files.items():
        through = 0
        for s in sorted((s for s in segments.values() if s["file_id"] == fid), key=lambda s: s["start"]):
            if s["start"] > through + 1:
                raise ValueError(f"plan coverage gap: {fid}:{through + 1}")
            through = max(through, s["end"])
        if f["tier"] == "full" and through != f["line_count"]:
            raise ValueError(f"plan coverage incomplete: {fid}")
    return files, segments


def validate_result(result, segment, source):
    if not isinstance(result, dict):
        raise ValueError("result must be an object")
    for key in ("segment_id", "sha256", "start", "end"):
        expected = segment["id"] if key == "segment_id" else segment[key]
        if result.get(key) != expected or (key in ("start", "end") and type(result[key]) is not int):
            raise ValueError(f"result {key} does not match assigned segment")
    if result.get("read_complete") is not True or not isinstance(result.get("residuals"), list):
        raise ValueError("explicit read_complete:true and residuals list required")
    rows = []
    for row in result["residuals"]:
        if not isinstance(row, dict):
            raise ValueError("residual must be an object")
        line = positive_int(row.get("line"), "line")
        if not segment["start"] <= line <= segment["end"]:
            raise ValueError(f"residual outside assigned segment: {line}")
        old, new, reason = row.get("original"), row.get("suggested"), row.get("reason")
        if not isinstance(old, str) or not old.strip() or "\n" in old or "\r" in old:
            raise ValueError("original must be one literal non-empty span")
        if not isinstance(new, str) or not isinstance(reason, str) or not reason.strip():
            raise ValueError("suggested string and a reason are required")
        context = source["lines"][line - 1]
        if old not in context:
            raise ValueError(f"original not verbatim at line {line}: {old!r}")
        # One row may report a repeated token, but cannot authorize choosing one
        # occurrence. The existing queue's ambiguity guard owns any later edit.
        rows.append({"file": source["file"], "line": line, "original": old,
                     "suggested": new, "context": context, "reason": reason,
                     "occurrences_on_line": context.count(old)})
    return rows


def check(run: Path):
    files, segments = validate_plan(run)
    valid, invalid, residuals = {}, [], []
    for path in sorted((run / "results").glob("*.json")):
        try:
            result = read_json(path)
            sid = result.get("segment_id") if isinstance(result, dict) else None
            if sid not in segments:
                raise ValueError("unknown segment_id")
            rows = validate_result(result, segments[sid], files[segments[sid]["file_id"]])
            if sid in valid and result != valid[sid]:
                raise ValueError("conflicting results for one segment_id")
            if sid not in valid:
                valid[sid] = result
                residuals.extend(rows)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            invalid.append({"file": str(path), "error": str(exc)})
    stale = []
    for f in files.values():
        try:
            if digest(Path(f["file"]).read_bytes()) != f["sha256"]:
                stale.append(f["file"])
        except OSError:
            stale.append(f["file"])
    missing = [sid for sid in segments if sid not in valid]
    unique = {}
    for row in residuals:
        key = (row["file"], row["line"], row["original"], row["suggested"])
        unique.setdefault(key, row)
    # Partial results are useful for resuming, never an authorization to edit.
    ready = bool(segments) and not (missing or invalid or stale)
    return {"schema_version": 1, "ready_for_adjudication": ready,
            "quality_complete": False, "expected_files": len(files),
            "fast_files": [f["file"] for f in files.values() if f["tier"] == "fast"],
            "expected_segments": len(segments), "validated_segments": len(valid),
            "missing_segments": missing, "invalid_results": invalid,
            "changed_sources": stale, "residuals": list(unique.values()),
            "note": "Validate structure and coverage only; adjudicate sound, identity, numbers, and live queue verdicts before edits."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="freeze explicit file scope and create bounded review packets")
    prep.add_argument("--manifest", required=True, type=Path)
    prep.add_argument("--output", required=True, type=Path)
    prep.add_argument("--max-lines", type=int, default=900)
    prep.add_argument("--max-chars", type=int, default=18000)
    prep.add_argument("--overlap", type=int, default=50)
    chk = sub.add_parser("check", help="validate results and list missing segments; no transcript/queue writes")
    chk.add_argument("--run", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            plan = prepare(args.manifest, args.output, args.max_lines, args.max_chars, args.overlap)
            output = {"run": str(args.output.resolve()), "files": len(plan["files"]), "segments": len(plan["segments"])}
            code = 0
        else:
            output = check(args.run.resolve())
            code = 0 if output["ready_for_adjudication"] else 1
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return code
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "ready_for_adjudication": False, "quality_complete": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
