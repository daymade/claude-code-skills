#!/usr/bin/env python3
"""Use an already-running ASR endpoint; bind plain text to source and producer.

Read the existing endpoint/model/noproxy/max_timeout config. Optional health_url
adds observed model_loaded/device identity; self_hosted requires CUDA identity.
Never load, unload, restart or choose a service model. The receipt is for the
plain-text leg, not speaker attribution or recognition accuracy.
"""
import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".asr-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def curl_json(url, cfg, forms=()):
    fd, name = tempfile.mkstemp(prefix="asr-response-", suffix=".json")
    os.close(fd)
    try:
        command = ["curl", "--silent", "--show-error", "--fail-with-body",
                   "--max-time", str(cfg.get("max_timeout", 900)), "--output", name]
        if cfg.get("noproxy", True):
            command += ["--noproxy", "*"]
        for form in forms:
            command += ["--form-string" if form.startswith("model=") else "--form", form]
        command.append(url)
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"ASR request failed (curl exit {result.returncode})")
        if Path(name).stat().st_size > 64 * 1024 * 1024:
            raise RuntimeError("ASR response exceeds the supported JSON size")
        value = json.loads(Path(name).read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("error"):
            raise RuntimeError("ASR endpoint returned an error or non-object JSON")
        return value
    finally:
        Path(name).unlink(missing_ok=True)


def runtime_identity(cfg, fetch=None):
    fetch = fetch or curl_json
    health_url = cfg.get("health_url")
    if not health_url:
        if cfg.get("self_hosted"):
            raise RuntimeError("self_hosted ASR requires an explicit health_url")
        return {"model": None, "revision": None, "device": None, "verification": "unknown"}
    health_timeout = cfg.get("health_timeout", 10)
    if (isinstance(health_timeout, bool) or not isinstance(health_timeout, (int, float))
            or not math.isfinite(health_timeout) or health_timeout <= 0):
        raise ValueError("health_timeout must be a finite positive number")
    value = fetch(health_url, {**cfg, "max_timeout": health_timeout})
    model, device = value.get("model_loaded"), value.get("device")
    if value.get("status") != "ok" or not isinstance(model, str) or not model.strip():
        raise RuntimeError("ASR health does not identify a ready loaded model")
    if (re.fullmatch(r"cpu(?::\d+)?", str(device).lower())
            or (cfg.get("self_hosted") and not re.fullmatch(r"cuda(?::\d+)?", str(device)))):
        raise RuntimeError("self-hosted ASR requires observed CUDA; CPU inference is refused")
    expected = cfg.get("expected_runtime_model")
    if expected is not None and expected != model:
        raise RuntimeError("ASR loaded model does not match expected_runtime_model")
    revision = value.get("model_revision")
    return {"model": model, "revision": revision if isinstance(revision, str) and revision else None,
            "device": device, "verification": "health_observed"}


def transcribe(source, output, cfg, force=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError("transcript cannot overwrite its source")
    for field in ("endpoint", "model"):
        if not isinstance(cfg.get(field), str) or not cfg[field].strip():
            raise ValueError(f"config requires {field}")
    if not cfg["endpoint"].startswith(("https://", "http://")):
        raise ValueError("endpoint must be an HTTP URL")
    started = time.monotonic()
    source_hash = sha256(source)
    producer_hash = sha256(__file__)
    identity = runtime_identity(cfg)
    receipt_path = Path(str(output) + ".asr.json")
    endpoint_hash = hashlib.sha256(cfg["endpoint"].encode()).hexdigest()
    if output.exists() and not force:
        try:
            old = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = None
        expected = {"schema": 1, "kind": "plain_text_asr_leg", "source_sha256": source_hash,
                    "producer_sha256": producer_hash, "requested_model": cfg["model"],
                    "endpoint_sha256": endpoint_hash, "runtime": identity}
        if (isinstance(old, dict) and all(old.get(k) == v for k, v in expected.items())
                and old.get("text_sha256") == sha256(output)
                and output.read_text(encoding="utf-8").strip()):
            return {**old, "cache_reused": True,
                    "original_run_wall_seconds": old.get("wall_seconds"),
                    "wall_seconds": time.monotonic() - started}
        raise RuntimeError("existing text lacks matching provenance; preserve it and use a fresh output or explicit --force")
    # Curl multipart paths must not be interpreted as additional form options.
    quoted_source = str(source).replace("\\", "\\\\").replace('"', '\\"')
    data = curl_json(cfg["endpoint"], cfg,
                     [f'file=@"{quoted_source}"', f'model={cfg["model"]}'])
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("ASR returned no readable text")
    if sha256(source) != source_hash:
        raise RuntimeError("source changed during transcription")
    if runtime_identity(cfg) != identity:
        raise RuntimeError("ASR runtime identity changed during transcription")
    if sha256(__file__) != producer_hash:
        raise RuntimeError("ASR runner changed during transcription")
    atomic_write(output, text + ("" if text.endswith("\n") else "\n"))
    receipt = {"schema": 1, "kind": "plain_text_asr_leg",
               "source_sha256": source_hash, "text_sha256": sha256(output),
               "producer_sha256": producer_hash, "requested_model": cfg["model"],
               "endpoint_sha256": endpoint_hash,
               "runtime": identity, "accuracy_verified": False,
               "wall_seconds": time.monotonic() - started}
    atomic_write(str(output) + ".asr.json", json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="Explicitly replace existing text; otherwise reuse valid provenance or preserve it")
    args = parser.parse_args()
    try:
        result = transcribe(args.source, args.output,
                            json.loads(args.config.read_text(encoding="utf-8")), force=args.force)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"ASR failed: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
