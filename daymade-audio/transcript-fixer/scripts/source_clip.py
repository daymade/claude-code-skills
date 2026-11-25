#!/usr/bin/env python3
"""Prepare a local/authorized SSH source and fetch identity-bound audio windows or video frames.

SSH is opt-in through an exact host, hostname and account. Credentials and machine
addresses belong in the caller's private source spec, never the shipped package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

SCHEMA = "transcript-source-v1"
CLIP_SCHEMA = "transcript-source-clip-v1"
FRAME_SCHEMA = "transcript-source-frame-v1"
LOCATE_SCHEMA = "transcript-source-locate-v1"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_WINDOW = 180.0
_TS_PATTERN = r"(?:\d{1,2}:)?[0-5]\d:[0-5]\d(?:\.\d+)?"
_TURN_SUFFIX_RE = re.compile(rf"^(?P<speaker>.+?)\s+(?P<bracket>\[)?(?P<ts>{_TS_PATTERN})(?(bracket)\])\s*[:：]?\s*$")
_TURN_PREFIX_BRACKET_RE = re.compile(rf"^\[(?P<ts>{_TS_PATTERN})\]\s+(?P<rest>.+?)\s*$")
_TURN_PREFIX_BARE_RE = re.compile(rf"^(?P<ts>{_TS_PATTERN})\s+(?P<rest>.+?)\s*$")
_INLINE_SPEAKER_RE = re.compile(r"^(?P<speaker>[^:：。！？.?!]{1,40})\s*[:：]\s*(?P<text>.+)$")
_PROSE_TIME_OF_DAY_RE = re.compile(r"(?:上午|下午|中午|晚上|凌晨|早上|今天|明天|昨天|周[一二三四五六日天]|星期)")

# One implementation runs locally or over the existing SSH command plane.
# The request is JSON data on stdin; paths never become shell commands.
WORKER = r'''
import getpass,hashlib,json,os,pathlib,socket,subprocess,sys,tempfile
def fingerprint(p):
    s=p.stat()
    if not p.is_file() or p.is_symlink(): raise ValueError("source must be a regular physical file")
    return {k:getattr(s,"st_"+k) for k in ("dev","ino","size","mtime_ns","ctime_ns")}
def main(a):
    p=pathlib.Path(a["path"])
    if not p.is_absolute(): raise ValueError("absolute source path required")
    if a.get("hostname") and socket.gethostname()!=a["hostname"]: raise ValueError("SSH hostname mismatch")
    if a.get("user") and getpass.getuser()!=a["user"]: raise ValueError("SSH account mismatch")
    before=fingerprint(p)
    if a.get("fingerprint") is not None and before!=a["fingerprint"]: raise ValueError("source version changed")
    if a["action"]=="probe":
        digest=hashlib.sha256()
        with p.open("rb") as f:
            for b in iter(lambda:f.read(1048576),b""): digest.update(b)
        if digest.hexdigest()!=a["sha256"]: raise ValueError("source SHA-256 mismatch")
        duration=float(subprocess.check_output([a.get("ffprobe","ffprobe"),"-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(p)],timeout=30))
        if before!=fingerprint(p): raise ValueError("source changed during probe")
        print(json.dumps({"fingerprint":before,"duration":duration,"hostname":socket.gethostname(),"user":getpass.getuser()}));return
    if a["action"]=="check":
        print(json.dumps({"fingerprint":before}));return
    if a["action"]=="frame":
        with tempfile.TemporaryDirectory(prefix="transcript-source-frame-") as td:
            out=pathlib.Path(td)/"frame.png"
            cp=subprocess.run([a.get("ffmpeg","ffmpeg"),"-nostdin","-hide_banner","-loglevel","error","-ss",str(a["timestamp"]),"-i",str(p),"-frames:v","1","-f","image2","-c:v","png",str(out)],capture_output=True,timeout=90)
            if cp.returncode: raise ValueError("ffmpeg frame extraction failed: "+cp.stderr.decode(errors="replace")[-600:])
            if not out.is_file(): raise ValueError("no video frame extracted at timestamp (source may lack a video stream)")
            data=out.read_bytes()
            if not data.startswith(b"\x89PNG\r\n\x1a\n"): raise ValueError("extracted frame is not a valid PNG")
            if before!=fingerprint(p): raise ValueError("source changed during frame extraction")
            print(json.dumps({"sha256":hashlib.sha256(data).hexdigest(),"size":len(data)}),flush=True)
            sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
        return
    with tempfile.TemporaryDirectory(prefix="transcript-source-clip-") as td:
        out=pathlib.Path(td)/"clip.wav"
        cp=subprocess.run([a.get("ffmpeg","ffmpeg"),"-nostdin","-hide_banner","-loglevel","error","-ss",str(a["start"]),"-i",str(p),"-t",str(a["end"]-a["start"]),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(out)],capture_output=True,timeout=90)
        if cp.returncode: raise ValueError("ffmpeg extraction failed: "+cp.stderr.decode(errors="replace")[-600:])
        duration=float(subprocess.check_output([a.get("ffprobe","ffprobe"),"-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(out)],timeout=15))
        if abs(duration-(a["end"]-a["start"]))>0.05: raise ValueError("truncated or mis-sized clip")
        if before!=fingerprint(p): raise ValueError("source changed during extraction")
        data=out.read_bytes()
        print(json.dumps({"sha256":hashlib.sha256(data).hexdigest(),"size":len(data),"duration":duration}),flush=True)
        sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
try: main(json.load(sys.stdin))
except Exception as e:
    print(type(e).__name__+": "+str(e),file=sys.stderr);sys.exit(2)
'''


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1048576), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes, *, replace: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("refusing symlink output")
    fd, temp = tempfile.mkstemp(prefix=".clip-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        if replace:
            os.replace(temp, path)
        else:
            os.link(temp, path)  # Exclusive publication; never replace an existing source/spec.
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def run_worker(spec: dict, request: dict) -> bytes:
    if spec.get("kind") not in ("local", "ssh"):
        raise ValueError("source kind must be local or ssh; existing --audio URLs remain supported separately")
    if not isinstance(spec.get("path"), str) or not spec["path"].startswith("/"):
        raise ValueError("absolute physical source path required")
    command = [sys.executable, "-c", WORKER]
    for tool in ("ffmpeg", "ffprobe"):
        if tool in spec:
            if not isinstance(spec[tool], str) or not Path(spec[tool]).is_absolute():
                raise ValueError("explicit media tool paths must be absolute on the source host")
            request = {**request, tool: spec[tool]}
    if spec["kind"] == "ssh":
        ssh = spec.get("ssh", {})
        if (not isinstance(ssh, dict) or any(not isinstance(ssh.get(k), str) or not ssh[k].strip()
                                           for k in ("host", "hostname", "user"))
                or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@:-]*", ssh["host"])):
            raise ValueError("SSH requires a safe explicit alias, expected hostname and user")
        request = {**request, "hostname": ssh["hostname"], "user": ssh["user"]}
        # Fixed command, encoded program in argv; the request remains stdin data.
        import base64
        encoded = base64.b64encode(WORKER.encode()).decode()
        remote = "python3 -c 'import base64;exec(base64.b64decode(\"" + encoded + "\"))'"
        command = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "--", ssh["host"], remote]
    result = subprocess.run(command, input=json.dumps({**request, "path": spec["path"]}).encode(),
                            capture_output=True, timeout=120)
    if result.returncode:
        raise ValueError("source operation failed: " + result.stderr.decode(errors="replace")[-900:])
    return result.stdout


def prepare(spec: dict) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", spec.get("sha256", "")):
        raise ValueError("expected source SHA-256 is required")
    proof = json.loads(run_worker(spec, {"action": "probe", "sha256": spec["sha256"]}))
    if not math.isfinite(proof["duration"]) or proof["duration"] <= 0:
        raise ValueError("invalid source duration")
    return {**spec, "schema": SCHEMA, "fingerprint": proof["fingerprint"],
            "duration": proof["duration"], "verified_at": time.time()}


class SourceClips:
    def __init__(self, spec_path: str | Path, cache: str | Path):
        self.spec_path = Path(spec_path).resolve()
        self.spec = json.loads(self.spec_path.read_text())
        if (self.spec.get("schema") != SCHEMA or not self.spec.get("fingerprint")
                or not re.fullmatch(r"[0-9a-f]{64}", self.spec.get("sha256", ""))
                or not math.isfinite(self.spec.get("duration", 0)) or self.spec["duration"] <= 0):
            raise ValueError("prepare and verify the source spec before fetching clips")
        self.duration = self.spec["duration"]
        self.cache = Path(cache).expanduser().resolve()
        self.cache.mkdir(parents=True, exist_ok=True)

    def check(self):
        json.loads(run_worker(self.spec, {"action": "check", "fingerprint": self.spec["fingerprint"]}))

    def fetch(self, start: float, end: float, output: str | Path) -> dict:
        if (not all(math.isfinite(v) for v in (start, end)) or start < 0
                or start >= end or end > self.duration + 0.001 or end-start > MAX_WINDOW):
            raise ValueError("invalid source-clock window (maximum 180 seconds)")
        self.check()
        identity = {"schema": CLIP_SCHEMA,
                    "source": {k: v for k, v in self.spec.items() if k != "verified_at"},
                    "start": start, "end": end,
                    "sample_rate": 16000, "channels": 1, "codec": "pcm_s16le"}
        target = Path(output).expanduser().absolute()
        sidecar = Path(str(target)+".source.json")
        reserved = {self.spec_path}
        if self.spec["kind"] == "local":
            reserved.add(Path(self.spec["path"]).resolve())
        if any(p.is_symlink() or p.resolve() in reserved for p in (target, sidecar)):
            raise ValueError("output conflicts with a source/spec or symlink")
        if target.exists() or sidecar.exists():
            try:
                previous = json.loads(sidecar.read_text())
                if not isinstance(previous, dict) or previous.get("identity") != identity or (target.exists() and sha256(target) != previous["clip_sha256"]):
                    raise ValueError("unbound existing output")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError("refusing to replace an existing output without its matching clip receipt") from exc
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        cached, metadata = self.cache / (key+".wav"), self.cache / (key+".json")
        lock = self.cache / (key+".lock")
        if any(path.resolve() in reserved for path in (cached, metadata, lock)):
            raise ValueError("cache path conflicts with the source/spec")
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ValueError("clip key is in use; reuse the current writer's result after it finishes") from exc
        os.close(fd)
        try:
            reused = False
            if cached.is_file() and metadata.is_file() and not cached.is_symlink() and not metadata.is_symlink():
                try:
                    proof = json.loads(metadata.read_text())
                    reused = isinstance(proof, dict) and proof.get("identity") == identity and sha256(cached) == proof.get("clip_sha256")
                except (OSError, ValueError):
                    reused = False
            if not reused:
                wire = run_worker(self.spec, {"action": "extract", "fingerprint": self.spec["fingerprint"],
                                              "start": start, "end": end})
                header, data = wire.split(b"\n", 1)
                info = json.loads(header)
                if (len(data) != info["size"] or hashlib.sha256(data).hexdigest() != info["sha256"]
                        or abs(info["duration"] - (end-start)) > 0.05):
                    raise ValueError("clip transfer/duration mismatch")
                proof = {"identity": identity, "clip_sha256": info["sha256"],
                         "clip_size": info["size"], "duration": info["duration"]}
                atomic_write(cached, data)
                atomic_write(metadata, (json.dumps(proof, ensure_ascii=False, indent=2)+"\n").encode())
            self.check()
            data = cached.read_bytes()
            if hashlib.sha256(data).hexdigest() != proof["clip_sha256"]:
                raise ValueError("cache changed before output publication")
            atomic_write(target, data)
            receipt = {**proof, "cache_reused": reused, "output": str(target),
                       "source_sha256": self.spec["sha256"], "source_start": start,
                       "source_end": end, "speed": 1}
            atomic_write(sidecar, (json.dumps(receipt, ensure_ascii=False, indent=2)+"\n").encode())
            return receipt
        finally:
            lock.unlink()

    def fetch_frame(self, timestamp: float, output: str | Path) -> dict:
        if not math.isfinite(timestamp) or timestamp < 0 or timestamp > self.duration + 0.001:
            raise ValueError("invalid source-clock timestamp")
        self.check()
        identity = {"schema": FRAME_SCHEMA,
                    "source": {k: v for k, v in self.spec.items() if k != "verified_at"},
                    "timestamp": timestamp, "format": "png"}
        target = Path(output).expanduser().absolute()
        sidecar = Path(str(target)+".source.json")
        reserved = {self.spec_path}
        if self.spec["kind"] == "local":
            reserved.add(Path(self.spec["path"]).resolve())
        if any(p.is_symlink() or p.resolve() in reserved for p in (target, sidecar)):
            raise ValueError("output conflicts with a source/spec or symlink")
        if target.exists() or sidecar.exists():
            try:
                previous = json.loads(sidecar.read_text())
                if not isinstance(previous, dict) or previous.get("identity") != identity or (target.exists() and sha256(target) != previous["frame_sha256"]):
                    raise ValueError("unbound existing output")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError("refusing to replace an existing output without its matching frame receipt") from exc
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        cached, metadata = self.cache / (key+".png"), self.cache / (key+".json")
        lock = self.cache / (key+".lock")
        if any(path.resolve() in reserved for path in (cached, metadata, lock)):
            raise ValueError("cache path conflicts with the source/spec")
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ValueError("frame key is in use; reuse the current writer's result after it finishes") from exc
        os.close(fd)
        try:
            reused = False
            if cached.is_file() and metadata.is_file() and not cached.is_symlink() and not metadata.is_symlink():
                try:
                    proof = json.loads(metadata.read_text())
                    reused = isinstance(proof, dict) and proof.get("identity") == identity and sha256(cached) == proof.get("frame_sha256")
                except (OSError, ValueError):
                    reused = False
            if not reused:
                wire = run_worker(self.spec, {"action": "frame", "fingerprint": self.spec["fingerprint"],
                                              "timestamp": timestamp})
                header, data = wire.split(b"\n", 1)
                info = json.loads(header)
                if (len(data) != info["size"] or hashlib.sha256(data).hexdigest() != info["sha256"]
                        or not data.startswith(PNG_MAGIC)):
                    raise ValueError("frame transfer/format mismatch")
                proof = {"identity": identity, "frame_sha256": info["sha256"], "frame_size": info["size"]}
                atomic_write(cached, data)
                atomic_write(metadata, (json.dumps(proof, ensure_ascii=False, indent=2)+"\n").encode())
            self.check()
            data = cached.read_bytes()
            if hashlib.sha256(data).hexdigest() != proof["frame_sha256"]:
                raise ValueError("cache changed before output publication")
            atomic_write(target, data)
            receipt = {**proof, "cache_reused": reused, "output": str(target),
                       "source_sha256": self.spec["sha256"], "source_timestamp": timestamp}
            atomic_write(sidecar, (json.dumps(receipt, ensure_ascii=False, indent=2)+"\n").encode())
            return receipt
        finally:
            lock.unlink()


def _parse_timestamp_seconds(raw: str) -> float:
    parts = raw.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = int(parts[0]), float(parts[1])
        if minutes < 0 or seconds < 0 or seconds >= 60.0:
            raise ValueError(f"invalid timestamp component: {raw!r}")
        return minutes * 60.0 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
        if hours < 0 or minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60.0:
            raise ValueError(f"invalid timestamp component: {raw!r}")
        return hours * 3600.0 + minutes * 60.0 + seconds
    raise ValueError(f"unsupported timestamp format: {raw!r}")


def _strip_header_markup(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned)
    cleaned = cleaned.strip("*_` ")
    return cleaned


def _split_frontmatter_end(lines: list[str]) -> int:
    if not lines or lines[0].strip() != "---":
        return 0
    for idx in range(1, len(lines)):
        if lines[idx].strip() in ("---", "..."):
            return idx + 1
    return 0


def _looks_like_speaker_label(text: str) -> bool:
    cleaned = _strip_header_markup(text)
    if not cleaned or len(cleaned) > 30:
        return False
    if re.search(r"[。！？.?!，,；;]", cleaned):
        return False
    return True


def _parse_transcript_turns(lines: list[str]) -> list[dict]:
    start_idx = _split_frontmatter_end(lines)
    turns: list[dict] = []
    current: dict | None = None
    for idx in range(start_idx, len(lines)):
        lineno = idx + 1
        raw_line = lines[idx]
        stripped = raw_line.strip()
        if not stripped:
            continue
        leading_ws = len(raw_line) - len(raw_line.lstrip())
        header_match = None
        speaker = ""
        inline_text = None
        inline_col = 0
        m_suffix = _TURN_SUFFIX_RE.match(stripped)
        if m_suffix and len(stripped) <= 100 and not re.search(r"[。！？.?!]", m_suffix.group("speaker")):
            cand_speaker = _strip_header_markup(m_suffix.group("speaker"))
            ts_str = m_suffix.group("ts")
            is_two_part_unbracketed = (ts_str.count(":") == 1) and (m_suffix.group("bracket") is None)
            if (
                cand_speaker
                and not cand_speaker.startswith("---")
                and not (is_two_part_unbracketed and (_PROSE_TIME_OF_DAY_RE.search(cand_speaker) or len(cand_speaker) > 30))
            ):
                header_match = ts_str
                speaker = cand_speaker
        if header_match is None:
            m_br = _TURN_PREFIX_BRACKET_RE.match(stripped)
            if m_br:
                header_match = m_br.group("ts")
                rest = m_br.group("rest")
                rest_col = leading_ws + m_br.start("rest")
                m_inline = _INLINE_SPEAKER_RE.match(rest)
                if m_inline:
                    speaker = _strip_header_markup(m_inline.group("speaker"))
                    inline_text = m_inline.group("text")
                    inline_col = rest_col + m_inline.start("text")
                elif _looks_like_speaker_label(rest):
                    speaker = _strip_header_markup(rest)
                else:
                    speaker = ""
                    inline_text = rest
                    inline_col = rest_col
        if header_match is None:
            m_bare = _TURN_PREFIX_BARE_RE.match(stripped)
            if m_bare:
                ts_str = m_bare.group("ts")
                rest = m_bare.group("rest")
                rest_col = leading_ws + m_bare.start("rest")
                m_inline = _INLINE_SPEAKER_RE.match(rest)
                if m_inline:
                    header_match = ts_str
                    speaker = _strip_header_markup(m_inline.group("speaker"))
                    inline_text = m_inline.group("text")
                    inline_col = rest_col + m_inline.start("text")
                elif ts_str.count(":") == 2 and _looks_like_speaker_label(rest):
                    header_match = ts_str
                    speaker = _strip_header_markup(rest)
        if header_match is not None:
            turn_start = _parse_timestamp_seconds(header_match)
            current = {
                "header_line": lineno,
                "speaker": speaker,
                "turn_start": turn_start,
                "body_lines": [],
                "turn_chars": 0,
            }
            turns.append(current)
            if inline_text is not None:
                current["body_lines"].append((lineno, inline_text, inline_col))
                current["turn_chars"] += len(re.sub(r"\s+", "", inline_text))
        elif current is not None:
            current["body_lines"].append((lineno, raw_line, 0))
            current["turn_chars"] += len(re.sub(r"\s+", "", raw_line))
    return turns


def _clamp_window(center: float, pad: float, duration: float | None) -> tuple[list[float], bool]:
    width = 2.0 * pad
    start = center - pad
    end = center + pad
    clamped = False
    if duration is not None:
        eff_width = min(width, duration)
        if start < 0.0:
            start = 0.0
            end = min(duration, eff_width)
            clamped = True
        if end > duration:
            end = duration
            start = max(0.0, duration - eff_width)
            clamped = True
        r_start = round(start, 3)
        r_end = round(end, 3)
        if r_end <= r_start:
            return [round(max(0.0, start), 6), round(duration, 6)], True
        return [r_start, r_end], clamped
    if start < 0.0:
        start = 0.0
        end = width
        clamped = True
    return [round(start, 3), round(end, 3)], clamped


def locate_in_transcript(
    transcript_path: str | Path,
    needle: str,
    *,
    line: int | None = None,
    speech_rate: float = 4.2,
    tight_pad: float = 6.0,
    medium_pad: float = 20.0,
    duration: float | None = None,
    source_spec: str | Path | None = None,
    offset: float = 0.0,
) -> dict:
    """Compute exploratory intra-turn clip windows for needle occurrences in a transcript."""
    if not needle:
        raise ValueError("needle must be non-empty")
    for label, val in (("speech_rate", speech_rate), ("tight_pad", tight_pad), ("medium_pad", medium_pad)):
        if not math.isfinite(val) or val <= 0:
            raise ValueError(f"{label} must be a positive finite number")
    if medium_pad < tight_pad:
        raise ValueError("medium_pad must be >= tight_pad")
    if 2.0 * medium_pad > MAX_WINDOW:
        raise ValueError(f"2 * medium_pad ({2.0 * medium_pad}) exceeds MAX_WINDOW ({MAX_WINDOW}s)")
    if not math.isfinite(offset):
        raise ValueError("offset must be finite")
    if line is not None and line < 1:
        raise ValueError("line must be >= 1")
    if duration is None and source_spec is not None:
        spec = json.loads(Path(source_spec).read_text(encoding="utf-8"))
        raw_dur = spec.get("duration") if isinstance(spec, dict) else None
        if not isinstance(spec, dict) or spec.get("schema") != SCHEMA or isinstance(raw_dur, bool) or not isinstance(raw_dur, (int, float)):
            raise ValueError("invalid source spec for duration lookup")
        duration = float(raw_dur)
    if duration is not None and (isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0):
        raise ValueError("duration must be a positive finite number")

    path = Path(transcript_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"transcript file not found: {path}")
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    turns = _parse_transcript_turns(lines)
    if not turns:
        raise ValueError("no timestamped speaker turns found in transcript")

    matches: list[dict] = []
    for turn_idx, turn in enumerate(turns):
        next_turn_start = turns[turn_idx + 1]["turn_start"] if turn_idx + 1 < len(turns) else None
        if next_turn_start is not None and next_turn_start <= turn["turn_start"]:
            next_turn_start = None
        prefix_non_ws = 0
        for lineno, text, col_offset in turn["body_lines"]:
            if line is None or lineno == line:
                search_from = 0
                while True:
                    pos = text.find(needle, search_from)
                    if pos == -1:
                        break
                    local_non_ws = len(re.sub(r"\s+", "", text[:pos]))
                    char_offset = prefix_non_ws + local_non_ws
                    turn_chars = turn["turn_chars"]
                    if next_turn_start is not None and turn_chars > 0:
                        turn_span = next_turn_start - turn["turn_start"]
                        if (turn_chars / turn_span) >= 0.5:
                            transcript_est = turn["turn_start"] + (char_offset / turn_chars) * turn_span
                            method = "turn_interpolation"
                        else:
                            transcript_est = min(next_turn_start, turn["turn_start"] + char_offset / speech_rate)
                            method = "speech_rate_capped"
                    else:
                        transcript_est = turn["turn_start"] + char_offset / speech_rate
                        method = "speech_rate"
                    source_est = transcript_est + offset
                    tight_window, tight_clamped = _clamp_window(source_est, tight_pad, duration)
                    medium_window, medium_clamped = _clamp_window(source_est, medium_pad, duration)
                    snip_start = max(0, pos - 24)
                    snip_end = min(len(text), pos + len(needle) + 24)
                    matches.append({
                        "line": lineno,
                        "column": col_offset + pos + 1,
                        "speaker": turn["speaker"],
                        "turn_header_line": turn["header_line"],
                        "turn_start": round(turn["turn_start"], 3),
                        "next_turn_start": round(next_turn_start, 3) if next_turn_start is not None else None,
                        "turn_chars": turn_chars,
                        "char_offset": char_offset,
                        "method": method,
                        "estimated_transcript_seconds": round(transcript_est, 3),
                        "estimated_source_seconds": round(source_est, 3),
                        "tight_window": tight_window,
                        "medium_window": medium_window,
                        "clamped_to_duration": tight_clamped or medium_clamped,
                        "context_snippet": text[snip_start:snip_end].strip(),
                    })
                    search_from = pos + len(needle)
            prefix_non_ws += len(re.sub(r"\s+", "", text))

    if not matches:
        if line is not None:
            raise ValueError(f"needle {needle!r} not found in timestamped transcript body at line {line}")
        raise ValueError(f"needle {needle!r} not found in timestamped transcript body")

    return {
        "schema": LOCATE_SCHEMA,
        "transcript": str(path),
        "needle": needle,
        "exploratory": True,
        "clock_offset": round(offset, 3),
        "duration": round(duration, 3) if duration is not None else None,
        "speech_rate": speech_rate,
        "matches": matches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare", help="Full-hash an existing local/authorized SSH source once")
    p.add_argument("--path", required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--ssh-host")
    p.add_argument("--expected-hostname")
    p.add_argument("--expected-user")
    p.add_argument("--ffmpeg", help="Verified absolute ffmpeg path on source host, if absent from SSH PATH")
    p.add_argument("--ffprobe", help="Verified absolute ffprobe path on source host, if absent from SSH PATH")
    p.add_argument("--output", required=True)
    p = commands.add_parser("fetch", help="Fetch a verified source-clock window, with bounded cache reuse")
    p.add_argument("--source-spec", required=True)
    p.add_argument("--cache-dir", required=True)
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--output", required=True)
    p = commands.add_parser("frame", help="Extract a single verified PNG frame at a calibrated source-clock timestamp")
    p.add_argument("--source-spec", required=True)
    p.add_argument("--cache-dir", required=True)
    p.add_argument("--timestamp", type=float, required=True)
    p.add_argument("--output", required=True)
    p = commands.add_parser("locate", help="Compute exploratory intra-turn clip windows for a phrase in a transcript")
    p.add_argument("--transcript", required=True)
    p.add_argument("--needle", required=True)
    p.add_argument("--line", type=int)
    p.add_argument("--speech-rate", type=float, default=4.2)
    p.add_argument("--tight-pad", type=float, default=6.0)
    p.add_argument("--medium-pad", type=float, default=20.0)
    p.add_argument("--duration", type=float)
    p.add_argument("--source-spec")
    p.add_argument("--offset", type=float, default=0.0)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            spec = {"kind": "ssh" if args.ssh_host else "local", "path": args.path, "sha256": args.sha256}
            if args.ssh_host:
                spec["ssh"] = {"host": args.ssh_host, "hostname": args.expected_hostname, "user": args.expected_user}
            for tool in ("ffmpeg", "ffprobe"):
                if getattr(args, tool):
                    spec[tool] = getattr(args, tool)
            result = prepare(spec)
            atomic_write(Path(args.output), (json.dumps(result, ensure_ascii=False, indent=2)+"\n").encode(), replace=False)
        elif args.command == "frame":
            result = SourceClips(args.source_spec, args.cache_dir).fetch_frame(args.timestamp, args.output)
        elif args.command == "locate":
            result = locate_in_transcript(
                args.transcript,
                args.needle,
                line=args.line,
                speech_rate=args.speech_rate,
                tight_pad=args.tight_pad,
                medium_pad=args.medium_pad,
                duration=args.duration,
                source_spec=args.source_spec,
                offset=args.offset,
            )
        else:
            result = SourceClips(args.source_spec, args.cache_dir).fetch(args.start, args.end, args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
