#!/usr/bin/env python3
"""
stepaudio-2.5-tts synthesis — single line or batch.

Endpoint: POST https://api.stepfun.com/v1/audio/speech

Key things this script handles that naive implementations miss:
- Does NOT send voice_label (would trigger "voice_label is not supported for v2 models")
- Puts emotion/prosody into `instruction` (natural-language, ≤200 chars)
- Preserves inline `()` directives in the text — these are consumed by the TTS as directions, not read aloud
- Per-line censorship_block fallback: log and skip, don't fail the whole batch
- Reads API key from $STEPFUN_API_KEY or $CLAUDE_PLUGIN_DATA/config.json

Usage:
    # Single line
    python3 tts_generate.py --text "你好，我是蕾格。" --out /tmp/hello.mp3 \\
        --instruction "温暖的希望感，语气鼓励"

    # Batch from JSONL (one JSON object per line: {"id": "...", "text": "...", "instruction": "..."})
    python3 tts_generate.py --batch lines.jsonl --out-dir /tmp/voices/

    # With inline prosody directives in the text itself
    python3 tts_generate.py --text "你好(停顿一下)我是蕾格(轻声)" --out /tmp/hello.mp3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

API_URL = "https://api.stepfun.com/v1/audio/speech"
MODEL = "stepaudio-2.5-tts"
DEFAULT_VOICE = "shuangkuaijiejie"  # 爽快姐姐 — verified in the 2026-04 test pass


def load_api_key() -> str:
    """Env first, then ${CLAUDE_PLUGIN_DATA}/config.json. Fail fast — no placeholder fallback."""
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
        "  Set $STEPFUN_API_KEY, or create ${CLAUDE_PLUGIN_DATA}/config.json with {\"api_key\": \"...\"}\n"
        "  Get a key at https://platform.stepfun.com/ → API Keys",
        file=sys.stderr,
    )
    sys.exit(2)


def synthesize(
    *,
    api_key: str,
    text: str,
    instruction: str | None = None,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    volume: float = 1.0,
    response_format: str = "mp3",
    timeout: int = 300,
) -> dict[str, Any]:
    """
    Call /v1/audio/speech with stepaudio-2.5-tts.

    Returns {ok, audio_bytes?, status, err?, censored?}.
    censored=True signals a censorship_block which callers should handle individually
    rather than aborting a batch.
    """
    body: dict[str, Any] = {
        "model": MODEL,
        "input": text,
        "voice": voice,
        "response_format": response_format,
        "speed": speed,
        "volume": volume,
    }
    if instruction:
        if len(instruction) > 200:
            return {"ok": False, "status": 0, "err": f"instruction too long: {len(instruction)} > 200 chars"}
        body["instruction"] = instruction

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": True, "status": resp.status, "audio_bytes": resp.read()}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        # Detect censorship_block so caller can decide whether to skip
        censored = "censorship_block" in raw or "blocked" in raw.lower()
        # Detect the known voice_label migration error and make the message actionable
        if "voice_label is not supported" in raw:
            hint = (
                "\n  HINT: stepaudio-2.5-tts does not accept voice_label. "
                "Put emotion/prosody into `instruction` (natural language) instead."
            )
            raw = raw + hint
        return {"ok": False, "status": e.code, "err": raw[:500], "censored": censored}


def read_batch(path: Path) -> Iterable[dict[str, Any]]:
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        yield json.loads(line)


def main() -> int:
    ap = argparse.ArgumentParser(description="stepaudio-2.5-tts single-line or batch synthesis")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--text", help="Single text to synthesize")
    g.add_argument("--batch", type=Path, help="JSONL file: {id, text, instruction?} per line")
    ap.add_argument("--out", help="Output mp3 path (single mode)")
    ap.add_argument("--out-dir", type=Path, help="Output directory (batch mode)")
    ap.add_argument("--instruction", help="Global tone directive (natural language, ≤200 chars)")
    ap.add_argument("--voice", default=DEFAULT_VOICE, help=f"Voice ID (default: {DEFAULT_VOICE})")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--volume", type=float, default=1.0)
    ap.add_argument("--delay-ms", type=int, default=400, help="Sleep between batch requests to avoid throttling")
    args = ap.parse_args()

    api_key = load_api_key()

    if args.text:
        if not args.out:
            print("ERROR: --out is required with --text", file=sys.stderr)
            return 2
        result = synthesize(
            api_key=api_key,
            text=args.text,
            instruction=args.instruction,
            voice=args.voice,
            speed=args.speed,
            volume=args.volume,
        )
        if not result["ok"]:
            print(f"FAIL status={result['status']}: {result.get('err', '')}", file=sys.stderr)
            return 1
        Path(args.out).write_bytes(result["audio_bytes"])
        print(f"OK wrote {args.out} ({len(result['audio_bytes'])} bytes)")
        return 0

    # Batch mode
    if not args.out_dir:
        print("ERROR: --out-dir is required with --batch", file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    success = 0
    censored: list[str] = []
    failed: list[tuple[str, str]] = []

    for item in read_batch(args.batch):
        line_id = item.get("id")
        text = item.get("text")
        if not line_id or not text:
            print(f"skip (missing id/text): {item}", file=sys.stderr)
            continue
        instr = item.get("instruction", args.instruction)
        result = synthesize(
            api_key=api_key,
            text=text,
            instruction=instr,
            voice=item.get("voice", args.voice),
            speed=item.get("speed", args.speed),
            volume=item.get("volume", args.volume),
        )
        out_path = args.out_dir / f"{line_id}.mp3"
        if result["ok"]:
            out_path.write_bytes(result["audio_bytes"])
            print(f"  ✓ {line_id} ({len(result['audio_bytes'])} bytes)")
            success += 1
        elif result.get("censored"):
            print(f"  ⚠ {line_id} CENSORED — skipped (consider rewriting or fallback to step-tts-2)")
            censored.append(line_id)
        else:
            err = result.get("err", "")[:160]
            print(f"  ✗ {line_id} status={result['status']}: {err}", file=sys.stderr)
            failed.append((line_id, err))
        time.sleep(args.delay_ms / 1000)

    print("")
    print(f"Done: {success} ok, {len(censored)} censored, {len(failed)} failed")
    if censored:
        print(f"  Censored IDs: {', '.join(censored)}")
    if failed:
        print("  Failed IDs:")
        for lid, err in failed:
            print(f"    {lid}: {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
