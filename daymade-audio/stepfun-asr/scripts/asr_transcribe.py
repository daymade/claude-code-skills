#!/usr/bin/env python3
"""
stepaudio-3-asr-max transcription — single file, SSE endpoint.

Endpoint: POST https://api.stepfun.com/v1/audio/asr/sse (NOT /v1/audio/transcriptions)

Why a dedicated script: naive implementations try to reuse the step-asr-era endpoint
(/v1/audio/transcriptions with multipart), get back `model stepaudio-3-asr-max not supported`,
and waste time debugging what looks like a model/permission issue. The actual cause is
that stepaudio-3-asr-max is a different endpoint entirely — SSE streaming, JSON body,
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
MODEL = "stepaudio-3-asr-max"

# 官方 /v1/audio/asr/sse 请求字段清单 —— 这是 scripts/check_params.py 的对账基准。
# 参数不额外计费，所以默认策略是「能发就发」；每个不发的字段必须在此写明理由。
# 官方字段表新增了这里没有的字段时，check_params.py 非零退出。
REQUEST_PARAMS = {
    "audio.data":                              "always: base64 音频",
    "audio.input.transcription.model":         "always: --model",
    "audio.input.transcription.language":      "always: --language",
    "audio.input.transcription.enable_itn":    "always: true，--no-itn 关闭",
    "audio.input.transcription.enable_timestamp": "always: true。不发时 start_time/end_time 字段仍返回但恒为 0",
    "audio.input.transcription.hotwords":      "opt-in: --hotwords。2026-09-18 实测对结果无影响，保留接口",
    "audio.input.format.type":                 "always: 由扩展名推断，--format 覆盖",
    "audio.input.format.codec":                "opt-in: --codec，仅 pcm 需要",
    "audio.input.format.rate":                 "opt-in: --rate，pcm 必填",
    "audio.input.format.bits":                 "opt-in: --bits，pcm 必填",
    "audio.input.format.channel":              "opt-in: --channel，pcm 必填",
}

# 本脚本真正消费的响应字段。服务端发来别的字段时 unhandled_response_fields 会报出来
# ——这次的时间戳漏接就属于此类：start_time/end_time 一直在发，解析器一直在丢。
CONSUMED_RESPONSE_FIELDS = {
    "transcript.text.delta": {"type", "delta", "start_time", "end_time", "meta"},
    "transcript.text.done": {"type", "text", "usage", "meta"},
    "error": {"type", "message", "meta"},
}

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
    enable_timestamp: bool = True,
    hotwords: list[str] | None = None,
    fmt_extra: dict[str, Any] | None = None,
    model: str = MODEL,
    timeout: int = 1200,
) -> dict[str, Any]:
    """
    Returns {ok, text?, usage?, elapsed, deltas_count, segments?,
             unhandled_response_fields?, err?, errors, censored?}.
    `errors` is always present: the raw SSE `error`-event payloads seen on
    this call (dicts), or an empty list if none fired — even when `ok` is
    True, since `ok` only turns False when there was no text at all.
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
                        "model": model,
                        "enable_itn": enable_itn,
                        # 默认开。不发时服务端仍返回 start_time/end_time 字段，
                        # 但值恒为 0——只判字段存在会同时支撑「支持」和「不支持」
                        # 两个相反结论，必须比对数值。参数不额外计费，没有关闭的理由。
                        "enable_timestamp": enable_timestamp,
                        **({"hotwords": hotwords} if hotwords else {}),
                    },
                    "format": {"type": audio_format, **(fmt_extra or {})},
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
        return {"ok": False, "status": e.code, "err": err, "errors": [], "elapsed": time.time() - t0, "censored": censored}

    elapsed = time.time() - t0
    text = ""
    usage: dict[str, Any] | None = None
    deltas = 0
    segments: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    unhandled: dict[str, set[str]] = {}
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
        extra = set(ev) - CONSUMED_RESPONSE_FIELDS.get(t, {"type"})
        if extra:
            unhandled.setdefault(t or "?", set()).update(extra)
        if t == "transcript.text.delta":
            deltas += 1
            # 形如 {"delta":"Understand ","start_time":228,"end_time":1108}（毫秒）。
            # 旧实现只做 deltas += 1，把整个载荷连同时间戳一起丢了。
            if enable_timestamp and ("start_time" in ev or "end_time" in ev):
                segments.append({
                    "text": ev.get("delta", ""),
                    "start_ms": ev.get("start_time"),
                    "end_ms": ev.get("end_time"),
                })
        elif t == "transcript.text.done":
            text = ev.get("text", "")
            usage = ev.get("usage")
        elif t == "error":
            # 原始 payload 整个留着，不只留 message——调用方可能需要按
            # type/meta 判断具体是哪一类 error，不止是拼一句人类可读文案。
            errors.append(ev)

    if not text and errors:
        msg = "; ".join(e.get("message", "") for e in errors)
        return {"ok": False, "status": 200, "err": msg, "errors": errors, "elapsed": elapsed}
    out = {"ok": True, "text": text, "usage": usage, "elapsed": elapsed, "deltas_count": deltas, "errors": errors}
    if segments:
        out["segments"] = segments
    if unhandled:
        out["unhandled_response_fields"] = {k: sorted(v) for k, v in unhandled.items()}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="stepaudio-3-asr-max transcription (SSE endpoint)")
    ap.add_argument("audio", type=Path, help="Path to audio file (mp3/wav/ogg/opus/pcm)")
    ap.add_argument("--language", default="zh", help="Language code (zh/en). Default: zh")
    ap.add_argument("--format", help="Audio format override (mp3/wav/ogg/pcm)")
    ap.add_argument("--no-itn", action="store_true", help="Disable inverse text normalization")
    ap.add_argument("--model", default=MODEL,
                    help=f"ASR model on /v1/audio/asr/sse. Default: {MODEL}. "
                         "Older: stepaudio-2.5-asr, stepaudio-2-asr-pro")
    ap.add_argument("--hotwords", help="Comma-separated hotwords. Measured 2026-09-18 as having no "
                                       "effect on output; wired up anyway because it costs nothing.")
    ap.add_argument("--codec", help="pcm only: raw|opus")
    ap.add_argument("--rate", type=int, help="pcm only: sample rate, e.g. 16000")
    ap.add_argument("--bits", type=int, help="pcm only: sample width, currently only 16")
    ap.add_argument("--channel", type=int, help="pcm only: 1 or 2")
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
        hotwords=[w.strip() for w in args.hotwords.split(",")] if args.hotwords else None,
        fmt_extra={k: v for k, v in (("codec", args.codec), ("rate", args.rate),
                                     ("bits", args.bits), ("channel", args.channel)) if v is not None},
        model=args.model,
    )

    if result.get("unhandled_response_fields"):
        print(f"NOTE: server sent fields this script ignores: {result['unhandled_response_fields']} "
              "— check whether a request param would make them useful.", file=sys.stderr)

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
