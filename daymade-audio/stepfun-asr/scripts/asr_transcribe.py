#!/usr/bin/env python3
"""
stepaudio-2.5-asr transcription — single file, SSE endpoint.

Endpoint: POST https://api.stepfun.com/v1/audio/asr/sse (NOT /v1/audio/transcriptions)

Why a dedicated script: naive implementations try to reuse the step-asr-era endpoint
(/v1/audio/transcriptions with multipart), get back `model stepaudio-2.5-asr not supported`,
and waste time debugging what looks like a model/permission issue. The actual cause is
that stepaudio-2.5-asr is a different endpoint entirely — SSE streaming, JSON body,
base64-encoded audio.

Handles:
- Auto-detects audio format from file extension (mp3 / wav / ogg / pcm)
- base64 encodes and wraps in the nested {audio: {data, input: {transcription, format}}} body
- Parses SSE stream: collects transcript.text.delta, returns transcript.text.done.text
- Flags "content blocked" errors distinctly from transport errors
- 32K context / up to ~30 min audio in a single call — no client-side chunking needed

Usage:
    python3 asr_transcribe.py path/to/audio.mp3
    python3 asr_transcribe.py path/to/audio.mp3 --json   # include usage (tokens/timing)
    python3 asr_transcribe.py path/to/audio.mp3 --language zh
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ASR_URL = "https://api.stepfun.com/v1/audio/asr/sse"
MODEL = "stepaudio-2.5-asr"

# Extensions that StepAudio 2.5 ASR accepts natively (no conversion needed)
EXT_TO_FORMAT = {
    ".mp3": "mp3",
    ".wav": "wav",
    ".ogg": "ogg",
    ".opus": "ogg",  # opus in ogg container
    ".pcm": "pcm",
}


def load_api_key() -> str:
    """Env first, then ${CLAUDE_PLUGIN_DATA}/config.json. Fail fast."""
    k = os.environ.get("STEPFUN_API_KEY", "").strip()
    if k:
        return k
    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
    if plugin_data:
        cfg = Path(plugin_data) / "config.json"
        if cfg.exists():
            try:
                k = json.loads(cfg.read_text()).get("api_key", "").strip()
                if k:
                    return k
            except json.JSONDecodeError:
                pass
    print(
        "ERROR: no API key found.\n"
        "  Set $STEPFUN_API_KEY, or create ${CLAUDE_PLUGIN_DATA}/config.json with {\"api_key\": \"...\"}",
        file=sys.stderr,
    )
    sys.exit(2)


def detect_format(path: Path, override: str | None) -> str:
    if override:
        return override
    fmt = EXT_TO_FORMAT.get(path.suffix.lower())
    if not fmt:
        print(
            f"ERROR: cannot detect audio format from extension {path.suffix!r}.\n"
            f"  Supported: {', '.join(EXT_TO_FORMAT)}.\n"
            f"  Or pass --format explicitly.",
            file=sys.stderr,
        )
        sys.exit(2)
    return fmt


def transcribe(
    *,
    api_key: str,
    audio_path: Path,
    audio_format: str,
    language: str = "zh",
    enable_itn: bool = True,
    timeout: int = 1200,
) -> dict[str, Any]:
    """
    Returns {ok, text?, usage?, elapsed, deltas_count, err?, censored?}.
    Parses the SSE stream; takes the text from transcript.text.done.
    """
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")
    body = json.dumps(
        {
            "audio": {
                "data": audio_b64,
                "input": {
                    "transcription": {
                        "language": language,
                        "model": MODEL,
                        "enable_itn": enable_itn,
                    },
                    "format": {"type": audio_format},
                },
            }
        }
    ).encode()
    req = urllib.request.Request(
        ASR_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")[:500]
        censored = "censorship" in err.lower() or "blocked" in err.lower()
        return {"ok": False, "status": e.code, "err": err, "elapsed": time.time() - t0, "censored": censored}

    elapsed = time.time() - t0
    text = ""
    usage: dict[str, Any] | None = None
    deltas = 0
    errors: list[str] = []
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        try:
            ev = json.loads(payload)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "transcript.text.delta":
            deltas += 1
        elif t == "transcript.text.done":
            text = ev.get("text", "")
            usage = ev.get("usage")
        elif t == "error":
            errors.append(ev.get("message", ""))

    if not text and errors:
        return {"ok": False, "status": 200, "err": "; ".join(errors), "elapsed": elapsed}
    return {"ok": True, "text": text, "usage": usage, "elapsed": elapsed, "deltas_count": deltas}


def main() -> int:
    ap = argparse.ArgumentParser(description="stepaudio-2.5-asr transcription (SSE endpoint)")
    ap.add_argument("audio", type=Path, help="Path to audio file (mp3/wav/ogg/opus/pcm)")
    ap.add_argument("--language", default="zh", help="Language code (zh/en). Default: zh")
    ap.add_argument("--format", help="Audio format override (mp3/wav/ogg/pcm)")
    ap.add_argument("--no-itn", action="store_true", help="Disable inverse text normalization")
    ap.add_argument("--json", action="store_true", help="Output full JSON (text + usage + timing)")
    args = ap.parse_args()

    if not args.audio.exists():
        print(f"ERROR: audio file not found: {args.audio}", file=sys.stderr)
        return 2

    api_key = load_api_key()
    fmt = detect_format(args.audio, args.format)
    result = transcribe(
        api_key=api_key,
        audio_path=args.audio,
        audio_format=fmt,
        language=args.language,
        enable_itn=not args.no_itn,
    )

    if not result["ok"]:
        if result.get("censored"):
            print("ERROR: content blocked by StepFun censorship. The audio likely contains sensitive content.", file=sys.stderr)
        else:
            print(f"ERROR status={result.get('status')}: {result.get('err', '')}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["text"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
