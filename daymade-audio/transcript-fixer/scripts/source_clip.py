#!/usr/bin/env python3
"""Prepare a local/authorized SSH source and fetch identity-bound audio windows.

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
MAX_WINDOW = 180.0

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


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("refusing symlink output")
    fd, temp = tempfile.mkstemp(prefix=".clip-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
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
        self.spec = json.loads(Path(spec_path).read_text())
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
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        cached, metadata = self.cache / (key+".wav"), self.cache / (key+".json")
        lock = self.cache / (key+".lock")
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
                    reused = proof.get("identity") == identity and sha256(cached) == proof.get("clip_sha256")
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
            target = Path(output).expanduser().absolute()
            if target.is_symlink():
                raise ValueError("refusing symlink output")
            data = cached.read_bytes()
            if hashlib.sha256(data).hexdigest() != proof["clip_sha256"]:
                raise ValueError("cache changed before output publication")
            atomic_write(target, data)
            receipt = {**proof, "cache_reused": reused, "output": str(target),
                       "source_sha256": self.spec["sha256"], "source_start": start,
                       "source_end": end, "speed": 1}
            atomic_write(Path(str(target)+".source.json"), (json.dumps(receipt, ensure_ascii=False, indent=2)+"\n").encode())
            return receipt
        finally:
            lock.unlink()


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
            atomic_write(Path(args.output), (json.dumps(result, ensure_ascii=False, indent=2)+"\n").encode())
        else:
            result = SourceClips(args.source_spec, args.cache_dir).fetch(args.start, args.end, args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
