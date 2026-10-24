#!/usr/bin/env python3
"""Local audio review workbench. Python 3.10+, standard library only."""

from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import csv
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import hashlib
import io
import ipaddress
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import struct
import socket
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit
import webbrowser


MAX_BODY = 64 * 1024
STATUSES = {"confirmed", "unknown", "skipped"}
PCM_FRAME_SNAP_TOLERANCE = Decimal("0.000001")


class ProjectError(ValueError):
    pass


class StateError(ValueError):
    pass


class APIError(Exception):
    def __init__(self, status, code, message, **extra):
        self.status, self.code, self.message, self.extra = status, code, message, extra


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def speaker_identity(project, value, *, name_first=False):
    """Resolve raw source IDs or canonical decision names without aliasing them."""
    matches = [person for person in project.people.values() if person["name"] == value]
    if matches and name_first:
        return value, matches[0]["id"] if len(matches) == 1 else ""
    if value in project.people:
        return project.people[value]["name"], value
    return value, matches[0]["id"] if len(matches) == 1 else ""


def _reject_constant(value):
    raise ValueError("Non-finite JSON numbers are not accepted")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def identifier(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 128 or any(ord(c) < 32 for c in value):
        raise ProjectError(f"{label} must be a nonempty string of at most 128 characters")
    return value


def _audio_mime(path):
    with path.open("rb") as stream:
        head = stream.read(16)
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"fLaC"):
        return "audio/flac"
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _pcm_wav(path, size):
    """Read only RIFF chunk headers; unsupported encodings keep ordinary playback."""
    with path.open("rb") as stream:
        head = stream.read(12)
        if len(head) != 12 or head[:4] != b"RIFF" or head[8:] != b"WAVE":
            return None
        limit = struct.unpack_from("<I", head, 4)[0] + 8
        if limit > size:
            return None
        fmt = data = None
        position = 12
        while position + 8 <= limit:
            stream.seek(position)
            chunk = stream.read(8)
            if len(chunk) != 8:
                return None
            tag, length = struct.unpack("<4sI", chunk)
            offset = position + 8
            if offset + length > limit:
                return None
            if tag == b"fmt ":
                if fmt is not None or length < 16:
                    return None
                raw = stream.read(16)
                if len(raw) != 16:
                    return None
                encoding, channels, rate, byte_rate, alignment, bits = struct.unpack("<HHIIHH", raw)
                if (encoding != 1 or not channels or not rate or bits not in {8, 16, 24, 32}
                        or alignment != channels * (bits // 8) or byte_rate != rate * alignment):
                    return None
                fmt = {"channels": channels, "sample_rate": rate, "block_align": alignment, "bits": bits}
            elif tag == b"data":
                if data is not None:
                    return None
                data = {"offset": offset, "length": length}
            position = offset + length + (length % 2)
        if fmt is None or data is None or not data["length"] or data["length"] % fmt["block_align"]:
            return None
        return {**fmt, **data, "frames": data["length"] // fmt["block_align"]}


def _wav_header(pcm, data_size):
    return struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + data_size + data_size % 2,
                       b"WAVE", b"fmt ", 16, 1, pcm["channels"], pcm["sample_rate"],
                       pcm["sample_rate"] * pcm["block_align"], pcm["block_align"], pcm["bits"],
                       b"data", data_size)


def _snap_pcm_frame(position):
    """Remove clock arithmetic noise, without treating missing samples as covered."""
    nearest = position.to_integral_value()
    return nearest if abs(position - nearest) <= PCM_FRAME_SNAP_TOLERANCE else position


def _available_pcm_frames(source):
    declared = _snap_pcm_frame(Decimal(str(source["public"]["duration"])) * source["pcm"]["sample_rate"])
    return min(source["pcm"]["frames"], int(declared.to_integral_value(rounding=ROUND_FLOOR)))


class Project:
    def __init__(self, path):
        path = Path(path)
        if not path.is_absolute():
            raise ProjectError("--project must be an absolute path")
        try:
            data = read_json(path)
        except (OSError, ValueError) as exc:
            raise ProjectError("Project JSON cannot be read or parsed") from exc
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ProjectError("Project schema_version must be 1")
        self.project_id = identifier(data.get("project_id"), "project_id")
        self.evidence_hashes = None
        if "evidence_hashes" in data:
            hashes = data["evidence_hashes"]
            if not isinstance(hashes, dict) or not hashes:
                raise ProjectError("Project evidence_hashes must be a nonempty object")
            if any(not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", key)
                   or not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
                   for key, value in hashes.items()):
                raise ProjectError("Project evidence_hashes must map ASCII identifiers to lowercase SHA-256 hashes")
            self.evidence_hashes = copy.deepcopy(hashes)
        if not isinstance(data.get("title"), str) or not data["title"].strip():
            raise ProjectError("Project title must be a nonempty string")
        if "subtitle" in data and not isinstance(data["subtitle"], str):
            raise ProjectError("Project subtitle must be a string")
        for field in ("people", "sources", "items"):
            if not isinstance(data.get(field), list):
                raise ProjectError(f"Project {field} must be an array")
        if not data["sources"]:
            raise ProjectError("Project needs at least one audio source")
        self.people = {}
        for person in data["people"]:
            if not isinstance(person, dict):
                raise ProjectError("Each person must be an object")
            pid = identifier(person.get("id"), "Person id")
            if pid in self.people:
                raise ProjectError("Duplicate person id")
            if not isinstance(person.get("name"), str) or not person["name"].strip():
                raise ProjectError("Each person needs a name")
            if "color" in person and not isinstance(person["color"], str):
                raise ProjectError("Person color must be a string")
            self.people[pid] = {key: copy.deepcopy(person[key]) for key in ("id", "name", "color") if key in person}
        self.sources = {}
        public_sources = []
        fingerprint_sources = []
        for source in data["sources"]:
            if not isinstance(source, dict):
                raise ProjectError("Each source must be an object")
            sid = identifier(source.get("id"), "Source id")
            if sid in self.sources:
                raise ProjectError("Duplicate source id")
            if not isinstance(source.get("label"), str):
                raise ProjectError("Source label must be a string")
            if not finite_number(source.get("duration")) or source["duration"] <= 0:
                raise ProjectError("Source duration must be finite and positive")
            clock = source.get("clock")
            if not isinstance(clock, dict) or not finite_number(clock.get("offset")) or not finite_number(clock.get("scale")) or clock["scale"] <= 0:
                raise ProjectError("Source clock needs a finite offset and positive scale")
            peaks = source.get("peaks")
            if not isinstance(peaks, list) or len(peaks) > 100000 or any(not finite_number(p) or not 0 <= p <= 1 for p in peaks):
                raise ProjectError("Source peaks must be an array of finite numbers from 0 to 1")
            audio_path = source.get("audio_path")
            if not isinstance(audio_path, str) or not Path(audio_path).is_absolute():
                raise ProjectError("Source audio_path must be an absolute file path")
            audio_path = Path(audio_path).resolve()
            try:
                if not audio_path.is_file():
                    raise OSError("Not a file")
                digest = hashlib.sha256()
                with audio_path.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                stat = audio_path.stat()
                mime = _audio_mime(audio_path)
                pcm = _pcm_wav(audio_path, stat.st_size) if mime == "audio/wav" else None
            except OSError as exc:
                raise ProjectError(f"Audio for source {sid} is not a readable file") from exc
            public = {key: copy.deepcopy(source[key]) for key in ("id", "label", "duration", "clock", "peaks")}
            public["media_url"] = f"/media/{quote(sid, safe='')}"
            public["mime"] = mime
            public_sources.append(public)
            fingerprint_sources.append({**public, "content_sha256": digest.hexdigest()})
            self.sources[sid] = {"path": audio_path, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "mime": mime, "pcm": pcm, "public": public}
        self.items = {}
        for item in data["items"]:
            if not isinstance(item, dict):
                raise ProjectError("Each item must be an object")
            iid = identifier(item.get("id"), "Item id")
            if iid in self.items:
                raise ProjectError("Duplicate item id")
            if not isinstance(item.get("kind"), str) or item["kind"] not in {"transcript", "speaker_sample"}:
                raise ProjectError("Item kind must be transcript or speaker_sample")
            if not isinstance(item.get("identity_status"), str) or item["identity_status"] not in {"candidate", "human_confirmed", "unknown"}:
                raise ProjectError("Item identity_status is invalid")
            if not finite_number(item.get("start")) or not finite_number(item.get("end")) or not 0 <= item["start"] < item["end"]:
                raise ProjectError("Item interval must have finite 0 <= start < end")
            if not isinstance(item.get("source_id"), str) or item["source_id"] not in self.sources:
                raise ProjectError("Item refers to an unknown source")
            if not isinstance(item.get("text"), str) or not isinstance(item.get("speaker"), str):
                raise ProjectError("Item text and speaker must be strings")
            if "title" in item and not isinstance(item["title"], str):
                raise ProjectError("Item title must be a string")
            if "priority" in item and not (isinstance(item["priority"], str) or finite_number(item["priority"])):
                raise ProjectError("Item priority must be a string or finite number")
            source = self.sources[item["source_id"]]["public"]
            local_start = (item["start"] - source["clock"]["offset"]) / source["clock"]["scale"]
            local_end = (item["end"] - source["clock"]["offset"]) / source["clock"]["scale"]
            if local_start < -0.1 or local_end > source["duration"] + 0.1:
                raise ProjectError("Item interval lies outside its audio source")
            self.items[iid] = {key: copy.deepcopy(item[key]) for key in ("id", "kind", "start", "end", "text", "speaker", "identity_status", "source_id", "priority", "title") if key in item}
        self.public = {"schema_version": 1, "project_id": self.project_id, "title": data["title"], "subtitle": data.get("subtitle", ""), "people": list(self.people.values()), "sources": public_sources, "items": list(self.items.values())}
        legacy_basis = {**self.public, "sources": fingerprint_sources}
        self.legacy_fingerprint = hashlib.sha256(json.dumps(legacy_basis, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
        # Only evidence that can change the meaning of a saved review binds it.
        # Peaks, labels, colors and presentation order can evolve independently.
        basis = {
            "fingerprint_version": 2,
            "project_id": self.project_id,
            "sources": sorted([
                {"id": source["id"], "duration": float(source["duration"]),
                 "clock": {key: float(source["clock"][key]) for key in ("offset", "scale")},
                 "content_sha256": source["content_sha256"]}
                for source in fingerprint_sources
            ], key=lambda source: source["id"]),
            "items": sorted([
                {**{key: item[key] for key in ("id", "kind", "text", "speaker", "identity_status", "source_id")},
                 "start": float(item["start"]), "end": float(item["end"])}
                for item in self.items.values()
            ], key=lambda item: item["id"]),
        }
        if self.evidence_hashes is not None:
            basis.update(fingerprint_version=3, evidence_hashes=self.evidence_hashes)
            self.public["evidence_hashes"] = copy.deepcopy(self.evidence_hashes)
        self.fingerprint = hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
        self.public["fingerprint"] = self.fingerprint
        # Runtime media URLs and capabilities do not change the evidence binding.
        for source in self.sources.values():
            source["public"]["media_url"] += "?" + urlencode({"project_fingerprint": self.fingerprint})
            source["public"]["bounded_clip"] = source["pcm"] is not None
            if source["pcm"] is not None:
                source["public"]["sample_rate"] = source["pcm"]["sample_rate"]
                source["public"]["available_frames"] = _available_pcm_frames(source)
                source["public"]["available_duration"] = source["public"]["available_frames"] / source["pcm"]["sample_rate"]

    def assert_sources_unchanged(self):
        for source in self.sources.values():
            try:
                stat = source["path"].stat()
            except OSError as exc:
                raise APIError(409, "source_changed", "An audio source is unavailable; restart after restoring the project") from exc
            if stat.st_size != source["size"] or stat.st_mtime_ns != source["mtime_ns"]:
                raise APIError(409, "source_changed", "An audio source changed; reload the project before reviewing")

    def assert_fingerprint(self, fingerprint):
        if not isinstance(fingerprint, str) or not fingerprint.strip():
            raise APIError(400, "invalid_project_fingerprint", "project_fingerprint must be a nonempty string")
        if fingerprint != self.fingerprint:
            raise APIError(409, "project_mismatch", "This page belongs to different project data or audio; open the current project before reviewing")

    def clip(self, query):
        params = parse_qs(query, keep_blank_values=True)
        binding = params.get("project_fingerprint", [None])
        self.assert_fingerprint(binding[0] if len(binding) == 1 else None)
        allowed = {"project_fingerprint", "item_id", "source_id", "context", "reference"}
        if set(params) - allowed or any(len(values) != 1 for values in params.values()):
            raise APIError(400, "invalid_clip", "Clip parameters must be unique and supported")
        values = {key: entries[0] for key, entries in params.items()}
        item_id, source_id = values.get("item_id"), values.get("source_id")
        item, source = self.items.get(item_id), self.sources.get(source_id)
        if item is None:
            raise APIError(404, "unknown_item", "Clip item was not found")
        if source is None:
            raise APIError(404, "unknown_source", "Audio source was not found")
        context, reference = values.get("context", "0"), values.get("reference", "0")
        if context not in {"0", "3"} or reference not in {"0", "1"} or (reference == "1" and context != "0"):
            raise APIError(400, "invalid_clip", "Use context 0 or 3; references require context 0")
        self.assert_sources_unchanged()
        pcm = source["pcm"]
        if pcm is None:
            raise APIError(415, "unsupported_clip_format", "Exact clip playback requires an uncompressed PCM WAV source")
        start, end = Decimal(str(item["start"])), Decimal(str(item["end"]))
        if reference == "1":
            end = min(end, start + 8)
        requested_start, requested_end = max(Decimal(0), start - int(context)), end + int(context)
        clock = source["public"]["clock"]
        offset, scale = Decimal(str(clock["offset"])), Decimal(str(clock["scale"]))
        rate = pcm["sample_rate"]
        start_position = _snap_pcm_frame((requested_start - offset) / scale * rate)
        end_position = _snap_pcm_frame((requested_end - offset) / scale * rate)
        available_frames = _available_pcm_frames(source)
        if _snap_pcm_frame((end - offset) / scale * rate) <= 0 or _snap_pcm_frame((start - offset) / scale * rate) >= available_frames:
            raise APIError(416, "clip_unavailable", "This source does not cover the selected item")
        # Include only whole frames contained in the requested interval.
        start_frame = max(0, int(start_position.to_integral_value(rounding=ROUND_CEILING)))
        end_frame = min(available_frames, int(end_position.to_integral_value(rounding=ROUND_FLOOR)))
        if start_frame >= end_frame:
            raise APIError(416, "clip_unavailable", "This source has no complete audio samples in the selected interval")
        actual_start, actual_end = start_frame / rate, end_frame / rate
        normalized = {"project_fingerprint": self.fingerprint, "item_id": item_id, "source_id": source_id,
                      "context": int(context), "reference": int(reference)}
        public = {**normalized, "start_frame": start_frame, "end_frame": end_frame, "sample_rate": rate,
                  "local_start": actual_start, "local_end": actual_end, "duration": (end_frame - start_frame) / rate,
                  "canonical_start": float(offset + Decimal(start_frame) / rate * scale),
                  "canonical_end": float(offset + Decimal(end_frame) / rate * scale),
                  "coverage_complete": start_position >= 0 and end_position <= available_frames,
                  "media_url": "/clip?" + urlencode(normalized)}
        data_size = (end_frame - start_frame) * pcm["block_align"]
        return {"public": public, "source": source, "header": _wav_header(pcm, data_size),
                "offset": pcm["offset"] + start_frame * pcm["block_align"], "data_size": data_size}


class StateStore:
    def __init__(self, project, directory):
        self.project = project
        self.lock = threading.RLock()
        directory = Path(directory)
        if not directory.is_absolute():
            raise StateError("--state-dir must be an absolute path")
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "state.json"
        self._transaction_depth = 0
        with self._disk_guard():
            self._load_initial(project)

    def _load_initial(self, project):
        if self.path.exists():
            try:
                state = read_json(self.path)
                migrate_fingerprint = project.evidence_hashes is None and isinstance(state, dict) and state.get("fingerprint") == project.legacy_fingerprint
                if migrate_fingerprint:
                    # This match includes the current full input and audio bytes,
                    # so it proves the older binding refers to this exact project.
                    state["fingerprint"] = project.fingerprint
                self._validate(state)
                if migrate_fingerprint:
                    self._persist(state)
            except StateError:
                raise
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise StateError("Saved state is invalid; preserve state.json and repair it explicitly") from exc
            self.data = state
        else:
            self.data = {"schema_version": 1, "fingerprint": project.fingerprint, "revision": 0, "decisions": {}, "updated_at": None, "audit": [], "undo_stack": [], "requests": {}}
            self._persist(self.data)

    @contextmanager
    def _disk_guard(self):
        # Separate processes must agree on the same revision before replacing it.
        with (self.path.parent / ".state.lock").open("a+b") as stream:
            if os.name == "nt":
                import msvcrt
                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _locked_state(self):
        with self.lock:
            if self._transaction_depth:
                yield
                return
            with self._disk_guard():
                try:
                    state = read_json(self.path)
                    self._validate(state)
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    raise APIError(503, "state_unreadable", "Saved state cannot be verified; preserve it before recovery") from exc
                self.data = state
                self._transaction_depth += 1
                try:
                    yield
                finally:
                    self._transaction_depth -= 1

    def _validate(self, state):
        if not isinstance(state, dict) or state.get("schema_version") != 1:
            raise StateError("Invalid saved state")
        if state.get("fingerprint") != self.project.fingerprint:
            raise StateError("Saved state belongs to different project data or audio; use a separate state directory")
        rev = state.get("revision")
        if not isinstance(rev, int) or isinstance(rev, bool) or rev < 0:
            raise StateError("Invalid state revision")
        if not isinstance(state.get("decisions"), dict) or not isinstance(state.get("audit"), list) or not isinstance(state.get("undo_stack"), list) or not isinstance(state.get("requests"), dict):
            raise StateError("Invalid saved state structure")
        if len(state["audit"]) != rev:
            raise StateError("Saved state audit is incomplete")
        replay = {}
        stack = []
        for index, entry in enumerate(state["audit"], 1):
            if not isinstance(entry, dict) or type(entry.get("revision")) is not int or entry["revision"] != index or not isinstance(entry.get("item_id"), str) or entry["item_id"] not in self.project.items or not isinstance(entry.get("action"), str) or entry["action"] not in {"decision", "undo"} or not isinstance(entry.get("at"), str):
                raise StateError("Invalid audit entry")
            iid = entry["item_id"]
            if entry.get("before") != replay.get(iid):
                raise StateError("Audit history does not match saved decisions")
            after = entry.get("after")
            if after is not None:
                self._validate_decision(after)
                replay[iid] = after
            else:
                replay.pop(iid, None)
            if entry["action"] == "decision":
                stack.append(index)
            else:
                if not stack or entry.get("undoes_revision") != stack.pop():
                    raise StateError("Invalid undo history")
                original = state["audit"][entry["undoes_revision"] - 1]
                if original["item_id"] != iid or original["before"] != after:
                    raise StateError("Undo does not restore the original decision")
        if replay != state["decisions"] or stack != state["undo_stack"]:
            raise StateError("Saved state cannot be reconciled with its audit")
        if state.get("updated_at") != (state["audit"][-1]["at"] if rev else None):
            raise StateError("Invalid saved state timestamp")
        for request_id, record in state["requests"].items():
            if not isinstance(request_id, str) or not isinstance(record, dict) or not isinstance(record.get("digest"), str) or type(record.get("revision")) is not int or not 1 <= record["revision"] <= rev:
                raise StateError("Invalid idempotency record")

    @staticmethod
    def _validate_decision(decision):
        if not isinstance(decision, dict) or not decision or set(decision) - {"speaker", "text", "status", "note"}:
            raise StateError("Invalid decision")
        if "status" in decision and (not isinstance(decision["status"], str) or decision["status"] not in STATUSES):
            raise StateError("Invalid decision")
        for key, maximum in (("speaker", 80), ("text", 32768), ("note", 8192)):
            if key in decision and (not isinstance(decision[key], str) or len(decision[key]) > maximum):
                raise StateError(f"Invalid decision {key}")

    def _persist(self, data):
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=self.path.parent)
            with os.fdopen(fd, "wb") as stream:
                stream.write(json_bytes(data))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            # The replacement must survive a process or machine interruption.
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def snapshot(self, revision=None):
        with self._locked_state():
            if revision is None or revision == self.data["revision"]:
                return copy.deepcopy({key: self.data[key] for key in ("revision", "decisions", "updated_at", "fingerprint")})
            decisions = {}
            for entry in self.data["audit"][:revision]:
                if entry["after"] is None:
                    decisions.pop(entry["item_id"], None)
                else:
                    decisions[entry["item_id"]] = entry["after"]
            return {"revision": revision, "decisions": copy.deepcopy(decisions), "updated_at": self.data["audit"][revision - 1]["at"] if revision else None, "fingerprint": self.project.fingerprint}

    def mutate(self, action, payload):
        if not isinstance(payload, dict):
            raise APIError(400, "invalid_body", "JSON body must be an object")
        self.project.assert_fingerprint(payload.get("project_fingerprint"))
        allowed = {"project_fingerprint", "base_revision", "request_id"} | ({"item_id", "changes"} if action == "decision" else set())
        if set(payload) - allowed:
            raise APIError(400, "invalid_body", "JSON body contains unsupported fields")
        revision = payload.get("base_revision")
        request_id = payload.get("request_id")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise APIError(400, "invalid_revision", "base_revision must be a nonnegative integer")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request_id):
            raise APIError(400, "invalid_request_id", "request_id must contain 1–128 letters, digits, dots, dashes, colons or underscores")
        digest = hashlib.sha256(json.dumps({"action": action, **payload}, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
        with self._locked_state():
            self.project.assert_sources_unchanged()
            previous = self.data["requests"].get(request_id)
            if previous:
                if previous["digest"] != digest:
                    raise APIError(409, "request_id_reused", "request_id was already used for a different request", state=self.snapshot())
                return self.snapshot(previous["revision"])
            if revision != self.data["revision"]:
                raise APIError(409, "revision_conflict", "Another edit was saved; reload the current state before retrying", state=self.snapshot())
            next_data = copy.deepcopy(self.data)
            if action == "decision":
                item_id = payload.get("item_id")
                if not isinstance(item_id, str) or item_id not in self.project.items:
                    raise APIError(400, "unknown_item", "item_id does not exist in this project")
                changes = payload.get("changes")
                if not isinstance(changes, dict) or not changes or set(changes) - {"speaker", "text", "status", "note"}:
                    raise APIError(400, "invalid_changes", "changes must contain speaker, text, status or note")
                before = next_data["decisions"].get(item_id)
                # Editing words or notes does not change the identity evidence.
                after = {**(before or {}), **changes}
                if "speaker" in changes and "status" not in changes:
                    raise APIError(400, "missing_status", "A speaker change needs an explicit identity decision")
                try:
                    self._validate_decision(after)
                except StateError as exc:
                    raise APIError(400, "invalid_changes", str(exc)) from exc
                if after.get("status") == "unknown":
                    after["speaker"] = ""
                if "speaker" in changes and after.get("status") != "unknown":
                    after["speaker"] = speaker_identity(self.project, after["speaker"], name_first=True)[0]
                if after.get("status") == "confirmed":
                    # Existing decisions contain names; note/text edits must not
                    # reinterpret a saved name as somebody else's source ID.
                    effective_speaker = after.get("speaker")
                    if effective_speaker is None:
                        effective_speaker = speaker_identity(self.project, self.project.items[item_id]["speaker"])[0]
                    if not effective_speaker.strip():
                        raise APIError(400, "missing_speaker", "Choose a speaker before confirming an identity")
                    after["speaker"] = effective_speaker.strip()
                next_data["undo_stack"].append(revision + 1)
                extra = {}
            else:
                if not next_data["undo_stack"]:
                    raise APIError(409, "nothing_to_undo", "There is no saved decision to undo", state=self.snapshot())
                target_revision = next_data["undo_stack"].pop()
                target = next_data["audit"][target_revision - 1]
                item_id = target["item_id"]
                before = next_data["decisions"].get(item_id)
                after = target["before"]
                extra = {"undoes_revision": target_revision}
            if after is None:
                next_data["decisions"].pop(item_id, None)
            else:
                next_data["decisions"][item_id] = after
            now = utc_now()
            next_data["revision"] = revision + 1
            next_data["updated_at"] = now
            next_data["audit"].append({"revision": revision + 1, "action": action, "item_id": item_id, "before": before, "after": after, "at": now, "request_id": request_id, **extra})
            next_data["requests"][request_id] = {"digest": digest, "revision": revision + 1}
            try:
                self._persist(next_data)
            except OSError as exc:
                # replace() may have committed before a directory fsync failed.
                # Reconcile that result while still holding the process lock.
                try:
                    observed = read_json(self.path)
                    self._validate(observed)
                    self.data = observed
                except (OSError, ValueError, TypeError, KeyError):
                    pass
                raise APIError(507, "save_failed", "The save could not be confirmed; reload the saved state before retrying") from exc
            self.data = next_data
            return self.snapshot()


def derived_items(project, state):
    rows = []
    for item in project.items.values():
        decision = state["decisions"].get(item["id"])
        name_first = False
        if decision and "status" in decision:
            status = {"confirmed": "human_confirmed", "unknown": "unknown", "skipped": "skipped"}[decision["status"]]
            speaker = decision.get("speaker", item["speaker"]) if status == "human_confirmed" else ""
            name_first = "speaker" in decision
        else:
            status = item["identity_status"]
            speaker = item["speaker"] if status != "unknown" else ""
        speaker, speaker_id = speaker_identity(project, speaker, name_first=name_first)
        original_speaker = speaker_identity(project, item["speaker"])[0]
        rows.append({"id": item["id"], "kind": item["kind"], "start": item["start"], "end": item["end"], "source_id": item["source_id"], "speaker": speaker, "speaker_id": speaker_id, "identity_status": status, "original_speaker": original_speaker, "original_identity_status": item["identity_status"], "text": decision.get("text", item["text"]) if decision else item["text"], "note": decision.get("note", "") if decision else ""})
    return rows


def clock_text(seconds):
    value = max(0, int(seconds))
    return f"{value // 3600:02d}:{value // 60 % 60:02d}:{value % 60:02d}"


def markdown_escape(text):
    return re.sub(r"([\\`*_{}\[\]<>#|~])", r"\\\1", text).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "  \n")


def export_document(project, state, kind):
    rows = derived_items(project, state)
    if kind == "json":
        document = {"schema_version": 1, "project_id": project.project_id, "title": project.public["title"], **state, "items": rows}
        return json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2).encode(), "application/json; charset=utf-8"
    if kind == "csv":
        stream = io.StringIO(newline="")
        fields = ["id", "kind", "start", "end", "source_id", "speaker", "identity_status", "original_speaker", "original_identity_status", "text", "note"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # A local export may be opened in a spreadsheet; neutralize formulas.
            writer.writerow({k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v) for k, v in row.items()})
        return ("\ufeff" + stream.getvalue()).encode(), "text/csv; charset=utf-8"
    labels = {"human_confirmed": "人工确认", "candidate": "候选 · 待核", "unknown": "未知 · 待核", "skipped": "已跳过 · 待核"}
    parts = [f"# {markdown_escape(project.public['title'])}", "", f"裁决版本：{state['revision']}  ", f"项目指纹：{project.fingerprint}", "", "候选与待核姓名不代表人工确认。", ""]
    for row in rows:
        label = labels[row["identity_status"]]
        name = row["speaker"] or "未定说话人"
        parts.extend([f"**{clock_text(row['start'])}–{clock_text(row['end'])} · {markdown_escape(name)} · {label}**", "", markdown_escape(row["text"]), ""])
        if row["note"]:
            parts.extend([f"备注：{markdown_escape(row['note'])}", ""])
    return "\n".join(parts).encode(), "text/markdown; charset=utf-8"


def byte_range(header, size):
    """Return inclusive bounds, or raise ValueError for an unsatisfiable range."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not match or size == 0:
        raise ValueError("Invalid range")
    left, right = match.groups()
    if not left:
        if not right or int(right) <= 0:
            raise ValueError("Invalid suffix range")
        return max(0, size - int(right)), size - 1
    start = int(left)
    end = min(int(right), size - 1) if right else size - 1
    if start >= size or end < start:
        raise ValueError("Unsatisfiable range")
    return start, end


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, project, store, static_dir=None):
        self.project, self.store = project, store
        self.static_dir = (Path(static_dir) if static_dir else Path(__file__).parent / "static").resolve()
        if ":" in address[0]:
            self.address_family = socket.AF_INET6
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "AudioReview/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Do not print item text, query values, or submitted decisions.
        sys.stderr.write(f"{self.log_date_time_string()} {self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ''}\n")

    def _local_request(self, write=False):
        try:
            parsed = urlsplit("//" + self.headers.get("Host", ""))
            host = parsed.hostname
            port = parsed.port or 80
            if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
                raise ValueError()
            if port != self.server.server_port:
                raise ValueError()
        except (ValueError, TypeError):
            raise APIError(403, "invalid_host", "Only local workbench requests are accepted")
        origin = self.headers.get("Origin")
        if origin:
            try:
                check = urlsplit(origin)
                if check.scheme != "http" or check.hostname != host or (check.port or 80) != port or check.path or check.query or check.fragment:
                    raise ValueError()
            except ValueError:
                raise APIError(403, "invalid_origin", "Cross-origin requests are not accepted")
        if write and self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise APIError(403, "invalid_origin", "Cross-site writes are not accepted")

    def _headers(self, status, mime, length, **headers):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for key, value in headers.items():
            self.send_header(key.replace("_", "-"), value)
        self.end_headers()

    def _json(self, value, status=200):
        body = json_bytes(value)
        self._headers(status, "application/json; charset=utf-8", len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, error):
        self._json({"error": error.code, "message": error.message, **error.extra}, error.status)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self._local_request()
            parsed = urlsplit(self.path)
            if parsed.path == "/api/project":
                self.server.project.assert_sources_unchanged()
                self._json(self.server.project.public)
            elif parsed.path == "/api/state":
                self.server.project.assert_sources_unchanged()
                self._json(self.server.store.snapshot())
            elif parsed.path == "/api/clip":
                self._json(self.server.project.clip(parsed.query)["public"])
            elif parsed.path == "/clip":
                self._clip_media(self.server.project.clip(parsed.query))
            elif parsed.path == "/api/export":
                self.server.project.assert_sources_unchanged()
                kind = parse_qs(parsed.query).get("format", ["json"])[0]
                if kind not in {"json", "csv", "md"}:
                    raise APIError(400, "invalid_format", "Export format must be json, csv or md")
                body, mime = export_document(self.server.project, self.server.store.snapshot(), kind)
                self._headers(200, mime, len(body), Content_Disposition=f'attachment; filename="review.{kind}"')
                if self.command != "HEAD":
                    self.wfile.write(body)
            elif parsed.path.startswith("/media/"):
                self._media(unquote(parsed.path[len("/media/"):]), parsed.query)
            elif parsed.path.startswith("/api/"):
                raise APIError(404, "not_found", "API endpoint was not found")
            else:
                self._static(unquote(parsed.path))
        except APIError as exc:
            self._error(exc)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _media(self, source_id, query):
        source = self.server.project.sources.get(source_id)
        if source is None:
            raise APIError(404, "unknown_source", "Audio source was not found")
        params = parse_qs(query, keep_blank_values=True)
        binding = params.get("project_fingerprint", [None])
        self.server.project.assert_fingerprint(binding[0] if len(binding) == 1 else None)
        if set(params) != {"project_fingerprint"}:
            raise APIError(400, "invalid_media", "Only a project_fingerprint is accepted for media requests")
        self.server.project.assert_sources_unchanged()
        size = source["size"]
        range_header = self.headers.get("Range")
        start, end = 0, size - 1
        if range_header:
            try:
                start, end = byte_range(range_header, size)
            except ValueError:
                self._headers(416, source["mime"], 0, Content_Range=f"bytes */{size}", Accept_Ranges="bytes")
                return
        length = max(0, end - start + 1)
        headers = {"Accept_Ranges": "bytes"}
        if range_header:
            headers["Content_Range"] = f"bytes {start}-{end}/{size}"
        try:
            stream = source["path"].open("rb")
        except OSError as exc:
            raise APIError(404, "audio_unavailable", "Audio source cannot be opened") from exc
        with stream:
            self._headers(206 if range_header else 200, source["mime"], length, **headers)
            if self.command == "HEAD":
                return
            stream.seek(start)
            while length:
                chunk = stream.read(min(length, 256 * 1024))
                if not chunk:
                    self.close_connection = True
                    break
                self.wfile.write(chunk)
                length -= len(chunk)

    def _clip_media(self, clip):
        header, data_size = clip["header"], clip["data_size"]
        size = len(header) + data_size + data_size % 2
        start, end = 0, size - 1
        range_header = self.headers.get("Range")
        if range_header:
            try:
                start, end = byte_range(range_header, size)
            except ValueError:
                self._headers(416, "audio/wav", 0, Content_Range=f"bytes */{size}", Accept_Ranges="bytes")
                return
        source = clip["source"]
        try:
            stream = source["path"].open("rb")
        except OSError as exc:
            raise APIError(404, "audio_unavailable", "Audio source cannot be opened") from exc
        with stream:
            stat = os.fstat(stream.fileno())
            if stat.st_size != source["size"] or stat.st_mtime_ns != source["mtime_ns"]:
                raise APIError(409, "source_changed", "An audio source changed; reload the project before reviewing")
            headers = {"Accept_Ranges": "bytes"}
            if range_header:
                headers["Content_Range"] = f"bytes {start}-{end}/{size}"
            self._headers(206 if range_header else 200, "audio/wav", end - start + 1, **headers)
            if self.command == "HEAD":
                return
            if start < len(header):
                self.wfile.write(header[start:min(end + 1, len(header))])
            audio_start, audio_end = max(start, len(header)), min(end + 1, len(header) + data_size)
            remaining = max(0, audio_end - audio_start)
            stream.seek(clip["offset"] + audio_start - len(header))
            while remaining:
                chunk = stream.read(min(remaining, 256 * 1024))
                if not chunk:
                    self.close_connection = True
                    return
                self.wfile.write(chunk)
                remaining -= len(chunk)
            if data_size % 2 and end == size - 1:
                self.wfile.write(b"\0")

    def _static(self, path):
        if "\x00" in path or "\\" in path:
            raise APIError(404, "not_found", "Page was not found")
        relative = path[len("/static/"):] if path.startswith("/static/") else path.lstrip("/")
        requested = self.server.static_dir / (relative or "index.html")
        try:
            resolved = requested.resolve()
            if not resolved.is_relative_to(self.server.static_dir) or not resolved.is_file():
                raise OSError()
            body = resolved.read_bytes()
        except OSError:
            raise APIError(404, "not_found", "Page was not found")
        mime = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        self._headers(200, mime + ("; charset=utf-8" if mime.startswith("text/") or mime == "application/javascript" else ""), len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_POST(self):
        try:
            self._local_request(write=True)
            if urlsplit(self.path).path not in {"/api/decision", "/api/undo"}:
                raise APIError(404, "not_found", "API endpoint was not found")
            if self.headers.get("Transfer-Encoding"):
                raise APIError(400, "invalid_body", "Transfer-Encoding is not supported")
            if self.headers.get_content_type() != "application/json":
                raise APIError(415, "invalid_content_type", "Use application/json for writes")
            length = self.headers.get("Content-Length")
            if length is None or not length.isdigit():
                raise APIError(411, "length_required", "A valid Content-Length is required")
            length = int(length)
            if length > MAX_BODY:
                raise APIError(413, "body_too_large", "Request exceeds the 64 KiB limit")
            self.connection.settimeout(15)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise APIError(400, "incomplete_body", "Request body was incomplete")
            try:
                payload = json.loads(raw, parse_constant=_reject_constant)
            except (UnicodeDecodeError, ValueError):
                raise APIError(400, "invalid_json", "Request body is not valid JSON")
            action = "decision" if urlsplit(self.path).path == "/api/decision" else "undo"
            self._json(self.server.store.mutate(action, payload))
        except APIError as exc:
            self.close_connection = True
            self._error(exc)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except TimeoutError:
            self.close_connection = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Absolute project JSON path")
    parser.add_argument("--state-dir", required=True, help="Absolute private state directory")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.host != "localhost" and not ipaddress.ip_address(args.host).is_loopback:
            raise ValueError()
    except ValueError:
        parser.error("--host must be localhost or a loopback address")
    try:
        project = Project(args.project)
        store = StateStore(project, args.state_dir)
        server = WorkbenchServer((args.host, args.port), project, store)
    except (ProjectError, StateError, OSError) as exc:
        # Never print a source audio path or raw JSON on an error.
        print(f"Cannot start audio review workbench: {exc}", file=sys.stderr)
        return 2
    host = f"[{args.host}]" if ":" in args.host else args.host
    url = f"http://{host}:{server.server_port}/"
    print(f"Audio review workbench: {url}", flush=True)
    print(f"Project: {project.public['title']} · {len(project.items)} items · revision {store.data['revision']}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
