#!/usr/bin/env python3
"""Import a speaker_transcribe CSV and one audio file into a review project.

Python 3.10+, standard library only. Requires ffprobe and ffmpeg on PATH.
Names are unverified candidates; importing never confirms a human identity.
"""

from __future__ import annotations

import argparse
import array
from collections import Counter
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


CSV_FIELDS = ("file", "start", "end", "duration", "speaker", "text")
SAMPLE_RATE = 16000
MIN_WINDOW_SAMPLES = SAMPLE_RATE // 10
MAX_PEAKS = 100000
END_TOLERANCE = 0.1


class PrepareError(ValueError):
    """A source or output cannot safely be used for this import."""


def _absolute_path(value, label, *, must_exist=False):
    path = Path(value)
    if not path.is_absolute():
        raise PrepareError(f"{label} must be an absolute path")
    try:
        resolved = path.resolve(strict=must_exist)
        if must_exist and not resolved.is_file():
            raise OSError("Not a file")
    except (OSError, RuntimeError) as exc:
        raise PrepareError(f"{label} must refer to a readable file") from exc
    return resolved


def _number(value, field, line):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PrepareError(f"CSV row {line}: {field} must be a finite number") from exc
    if not math.isfinite(number):
        raise PrepareError(f"CSV row {line}: {field} must be a finite number")
    return number


def _read_csv(path):
    try:
        raw = path.read_bytes()
        stream = io.StringIO(raw.decode("utf-8-sig"), newline="")
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames
        if not headers or len(set(headers)) != len(headers) or any(not h for h in headers):
            raise PrepareError("CSV needs a nonempty header with unique column names")
        if set(CSV_FIELDS) - set(headers):
            raise PrepareError("CSV needs columns: " + ",".join(CSV_FIELDS))
        rows = []
        for row in reader:
            line = reader.line_num
            if None in row or any(row.get(field) is None for field in CSV_FIELDS):
                raise PrepareError(f"CSV row {line}: missing or extra field values")
            if not row["file"].strip():
                raise PrepareError(f"CSV row {line}: file must identify one audio source")
            start = _number(row["start"], "start", line)
            end = _number(row["end"], "end", line)
            duration = _number(row["duration"], "duration", line)
            if not 0 <= start < end:
                raise PrepareError(f"CSV row {line}: require 0 <= start < end")
            if duration <= 0:
                raise PrepareError(f"CSV row {line}: duration must be positive")
            rows.append({"raw": {field: row[field] for field in CSV_FIELDS},
                         "start": start, "end": end, "line": line})
    except PrepareError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PrepareError("CSV must be a readable, valid UTF-8 CSV file") from exc
    if not rows:
        raise PrepareError("CSV contains no transcript rows")
    if len({row["raw"]["file"].strip() for row in rows}) != 1:
        raise PrepareError("CSV contains multiple file values; one --audio cannot safely bind multiple sources")
    return raw, rows


def _required_tool(name):
    executable = shutil.which(name)
    if executable is None:
        raise PrepareError(f"{name} is required on PATH; install it before importing")
    return executable


def _probe_duration(audio, executable):
    try:
        result = subprocess.run(
            [executable, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_type,duration:format=duration",
             "-of", "json", str(audio)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PrepareError("ffprobe could not inspect the audio") from exc
    if result.returncode:
        raise PrepareError("ffprobe could not read an audio stream from the input")
    try:
        metadata = json.loads(result.stdout)
        streams = metadata.get("streams", [])
        if not streams or streams[0].get("codec_type") != "audio":
            raise ValueError("No audio stream")
        candidates = (streams[0].get("duration"), metadata.get("format", {}).get("duration"))
        for candidate in candidates:
            try:
                duration = float(candidate)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(duration) and duration > 0:
                return duration
    except (ValueError, TypeError, AttributeError):
        pass
    raise PrepareError("ffprobe did not report a finite, positive audio duration")


class _PeakCollector:
    """Accumulate equal-width PCM peaks without retaining the decoded recording."""

    def __init__(self, window_samples, max_points=MAX_PEAKS):
        self.window_samples = window_samples
        self.max_points = max_points
        self.peaks = []
        self.pending_count = 0
        self.pending_peak = 0
        self.sample_count = 0

    def feed(self, samples):
        self.sample_count += len(samples)
        offset = 0
        while offset < len(samples):
            count = min(self.window_samples - self.pending_count, len(samples) - offset)
            block = samples[offset:offset + count]
            self.pending_peak = max(self.pending_peak, max(block), -min(block))
            self.pending_count += count
            offset += count
            if self.pending_count == self.window_samples:
                self.peaks.append(self.pending_peak)
                self.pending_count = 0
                self.pending_peak = 0
                if len(self.peaks) > self.max_points:
                    # A container may understate its duration. Rebin already-read
                    # peaks too, retaining the unmatched window as pending audio.
                    previous = self.peaks
                    self.peaks = [max(previous[i:i + 2])
                                  for i in range(0, len(previous) - 1, 2)]
                    if len(previous) % 2:
                        self.pending_count = self.window_samples
                        self.pending_peak = previous[-1]
                    self.window_samples *= 2

    def finish(self):
        peaks = self.peaks + ([self.pending_peak] if self.pending_count else [])
        if len(peaks) > self.max_points:
            peaks = [max(peaks[i:i + 2]) for i in range(0, len(peaks), 2)]
        return [round(peak / 32768, 6) for peak in peaks]


def _waveform(audio, duration, executable):
    window = max(MIN_WINDOW_SAMPLES, math.ceil(duration * SAMPLE_RATE / MAX_PEAKS))
    collector = _PeakCollector(window)
    try:
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                [executable, "-v", "error", "-nostdin", "-i", str(audio),
                 "-map", "0:a:0", "-vn", "-sn", "-dn", "-ac", "1",
                 "-ar", str(SAMPLE_RATE), "-af", "asetpts=N/SR/TB",
                 "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"],
                stdout=subprocess.PIPE, stderr=errors,
            )
            try:
                remainder = b""
                with process.stdout:
                    while chunk := process.stdout.read(64 * 1024):
                        chunk = remainder + chunk
                        usable = len(chunk) - len(chunk) % 2
                        samples = array.array("h")
                        samples.frombytes(chunk[:usable])
                        if sys.byteorder != "little":
                            samples.byteswap()
                        if samples:
                            collector.feed(samples)
                        remainder = chunk[usable:]
                returncode = process.wait()
            except BaseException:
                # This process belongs to this import; never touch other jobs.
                if process.poll() is None:
                    process.terminate()
                process.wait()
                raise
    except OSError as exc:
        raise PrepareError("ffmpeg could not start audio decoding") from exc
    if returncode or remainder or not collector.sample_count:
        raise PrepareError("ffmpeg could not decode a complete, nonempty audio stream")
    return collector.finish()


def _sha256_file(path):
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise PrepareError("Audio must be a readable file") from exc
    return digest.digest()


def _anonymous_label(label):
    normalized = label.strip().casefold()
    return (
        normalized in {"", "unknown", "unk", "未知", "未知说话人", "未定", "未定说话人", "待核", "待确认"}
        or re.fullmatch(r"speaker(?:[\s_-]+[a-z0-9]+|\d+)?", normalized) is not None
        or re.fullmatch(r"说话人[\s_-]*[0-9a-z一二三四五六七八九十]*", normalized) is not None
    )


def build_project(csv_path, audio_path, *, title="录音校勘", people=None, project_id=None):
    """Read sources and produce an unconfirmed project; never write review state."""
    csv_path = _absolute_path(csv_path, "--csv", must_exist=True)
    audio_path = _absolute_path(audio_path, "--audio", must_exist=True)
    csv_bytes, rows = _read_csv(csv_path)
    if not isinstance(title, str) or not title.strip():
        raise PrepareError("--title must be nonempty")
    if project_id is not None and (
        not isinstance(project_id, str) or not project_id.strip()
        or len(project_id) > 128 or any(ord(c) < 32 for c in project_id)
    ):
        raise PrepareError("--project-id must contain 1–128 characters without control characters")
    names = people if people is not None else [row["raw"]["speaker"] for row in rows
                                              if not _anonymous_label(row["raw"]["speaker"])]
    roster = []
    seen_names = set()
    for name in names:
        if not isinstance(name, str) or not name.strip() or any(ord(c) < 32 for c in name):
            raise PrepareError("Each --person must be a nonempty name without control characters")
        if name not in seen_names:
            seen_names.add(name)
            roster.append({"id": "person-" + hashlib.sha256(name.encode()).hexdigest()[:24], "name": name})
    ffprobe = _required_tool("ffprobe")
    ffmpeg = _required_tool("ffmpeg")
    before = audio_path.stat()
    audio_digest = _sha256_file(audio_path)
    duration = _probe_duration(audio_path, ffprobe)
    for row in rows:
        if row["end"] > duration + END_TOLERANCE + 1e-9:
            raise PrepareError(f"CSV row {row['line']}: end exceeds audio duration (0.1 s tolerance)")
    peaks = _waveform(audio_path, duration, ffmpeg)
    after = audio_path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise PrepareError("Audio changed during import; retry with a stable source file")
    if project_id is None:
        basis = hashlib.sha256(b"audio-review-project-v1\0" + audio_digest + csv_bytes)
        project_id = "review-" + basis.hexdigest()
    occurrences = Counter()
    items = []
    for row in rows:
        raw = row["raw"]
        encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(encoded).hexdigest()[:24]
        occurrences[digest] += 1
        items.append({"id": f"line-{digest}-{occurrences[digest]}", "kind": "transcript",
                      "source_id": "main", "start": row["start"], "end": row["end"],
                      "speaker": raw["speaker"], "text": raw["text"],
                      "identity_status": "unknown" if _anonymous_label(raw["speaker"]) else "candidate"})
    return {"schema_version": 1, "project_id": project_id, "title": title,
            "people": roster,
            "sources": [{"id": "main", "label": "录音", "audio_path": str(audio_path),
                         "duration": duration, "clock": {"offset": 0, "scale": 1}, "peaks": peaks}],
            "items": items}


def _validate_project(path):
    spec = importlib.util.spec_from_file_location("_audio_review_project_validator", Path(__file__).with_name("server.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.Project(path)
    except module.ProjectError as exc:
        raise PrepareError(f"Workbench rejected the prepared project: {exc}") from exc


def prepare_project(csv_path, audio_path, output, *, overwrite=False, **options):
    """Validate with the workbench reader, then atomically publish the project."""
    requested_output = Path(output)
    output = _absolute_path(output, "--output")
    if requested_output.is_symlink():
        raise PrepareError("--output must not be a symbolic link")
    sources = {_absolute_path(csv_path, "--csv", must_exist=True),
               _absolute_path(audio_path, "--audio", must_exist=True)}
    if output in sources:
        raise PrepareError("--output must be separate from the source CSV and audio")
    if output.exists() and (not overwrite or not output.is_file()):
        raise PrepareError("Output already exists; choose another path or explicitly use --overwrite")
    project = build_project(csv_path, audio_path, **options)
    try:
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".review-project-", suffix=".json", dir=output.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(project, stream, ensure_ascii=False, allow_nan=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            _validate_project(temporary)
            if overwrite:
                os.replace(temporary, output)
            else:
                # link is an atomic no-clobber publish, including a racing writer.
                os.link(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    except FileExistsError as exc:
        raise PrepareError("Output already exists; choose another path or explicitly use --overwrite") from exc
    except OSError as exc:
        raise PrepareError("Project output could not be written; check the private destination directory") from exc
    return project


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="Absolute speaker_transcribe CSV path")
    parser.add_argument("--audio", required=True, help="Absolute path to the matching full recording")
    parser.add_argument("--output", required=True, help="Absolute private project JSON path")
    parser.add_argument("--title", default="录音校勘", help="Workbench title (default: 录音校勘)")
    parser.add_argument("--person", action="append", default=None, help="Candidate name for the roster; repeat as needed")
    parser.add_argument("--project-id", help="Explicit project identity; default is stable for the exact CSV and audio bytes")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace an existing output project, never the sources")
    args = parser.parse_args(argv)
    try:
        project = prepare_project(args.csv, args.audio, args.output, overwrite=args.overwrite,
                                  title=args.title, people=args.person, project_id=args.project_id)
    except (PrepareError, OSError) as exc:
        print(f"Cannot prepare audio review project: {exc}", file=sys.stderr)
        return 2
    print(f"Prepared {len(project['items'])} transcript items; {len(project['people'])} candidate people.")
    print(f"Project: {Path(args.output).resolve()}")
    print("All imported speaker identities remain unconfirmed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
