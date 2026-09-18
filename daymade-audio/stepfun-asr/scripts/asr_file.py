#!/usr/bin/env python3
"""Speaker-labeled transcription via StepFun's async file endpoint.

The SSE endpoint this skill is built around has NO speaker capability (14 candidate
field names measured inert, 2026-09-18). Speaker diarization lives here instead:
POST /v1/audio/asr/file/submit + /v1/audio/asr/file/query.

The catch: this endpoint only takes a publicly fetchable URL. Base64 is rejected, and
so is StepFun's own file store (see references/known_issues.md for the three dead ends).
So this script takes a URL, never a local path — putting audio somewhere public is the
caller's decision, not this script's.

  python3 asr_file.py https://example.com/talk.mp3 --json > out.json
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE = "https://api.stepfun.com/v1/audio/asr/file"
MODEL = "stepaudio-2.5-asr"  # v3 (stepaudio-3-asr-max) is not offered on this endpoint


def _key() -> str:
    k = os.environ.get("STEPFUN_API_KEY")
    if k:
        return k
    cfg = Path(os.environ.get("CLAUDE_PLUGIN_DATA", "")) / "config.json"
    if cfg.is_file():
        k = json.loads(cfg.read_text()).get("api_key")
    if not k:
        sys.exit("ERROR: no API key. Set $STEPFUN_API_KEY or ${CLAUDE_PLUGIN_DATA}/config.json")
    return k


def _post(path: str, obj: dict[str, Any], key: str, timeout: int = 300) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{BASE}/{path}", data=json.dumps(obj).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_err": e.read().decode("replace")[:300]}


def transcribe(url: str, *, key: str, audio: dict[str, Any], model: str = MODEL,
               attempts: int = 4, poll: int = 5, max_wait: int = 3600) -> dict[str, Any]:
    """`audio_download` failures are transient: the same URL measured 2026-09-18 failed
    twice then succeeded on the third submit. Retry rather than concluding the URL is bad.
    A URL that fails every attempt really is unreachable to them (a github.com redirect
    and an auth-requiring URL each failed 3/3)."""
    last: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        sub = _post("submit", {"audio": {**audio, "url": url},
                               "request": {"model_name": model, "show_utterances": True,
                                           "enable_speaker_info": True}}, key)
        if "task_id" not in sub:
            return {"ok": False, "stage": "submit", "err": sub}
        t0 = time.time()
        while time.time() - t0 < max_wait:
            q = _post("query", {"task_id": sub["task_id"]}, key)
            if "result" in q:
                return {"ok": True, "attempt": attempt, **q}
            if q.get("status") == "FAILED" or "_http" in q:
                last = q
                break
            time.sleep(poll)
        else:
            return {"ok": False, "stage": "poll", "err": "timed out", "task_id": sub["task_id"]}
        if last.get("error", {}).get("stage") != "audio_download":
            return {"ok": False, "stage": "asr", "err": last}
        print(f"attempt {attempt}/{attempts}: audio_download failed, retrying", file=sys.stderr)
    return {"ok": False, "stage": "audio_download", "err": last}


def as_text(res: dict[str, Any]) -> str:
    """`speaker.id` is `speaker_0` / `speaker_1` — the docs say `spk_1`; the docs are wrong."""
    lines = []
    for block in res.get("result", []):
        for u in block.get("utterances", []):
            spk = u.get("speaker", {}).get("id", "?")
            lines.append(f"[{u['start_time']/1000:7.2f}-{u['end_time']/1000:7.2f}] {spk}: {u['text'].strip()}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Speaker-labeled ASR (StepFun async file endpoint)")
    ap.add_argument("url", help="Publicly fetchable audio URL, <100MB. Redirects are NOT followed.")
    ap.add_argument("--format", default="mp3", help="wav|mp3|pcm|ogg|m4a. Default: mp3")
    ap.add_argument("--codec", help="pcm only: raw|opus")
    ap.add_argument("--rate", type=int, help="pcm only, required there")
    ap.add_argument("--bits", type=int, help="pcm only, 16")
    ap.add_argument("--channel", type=int, default=1, help="1 or 2; must match the file")
    ap.add_argument("--channel-split", action="store_true", help="Per-channel results; needs --channel 2")
    ap.add_argument("--model", default=MODEL, help=f"Default: {MODEL}. Also: step-asr-1.1")
    ap.add_argument("--json", action="store_true", help="Full JSON instead of speaker-labeled text")
    a = ap.parse_args()

    audio = {k: v for k, v in (("format", a.format), ("codec", a.codec), ("rate", a.rate),
                               ("bits", a.bits), ("channel", a.channel)) if v is not None}
    res = transcribe(a.url, key=_key(), audio=audio, model=a.model)
    if not res.get("ok"):
        print(f"ERROR at {res['stage']}: {json.dumps(res.get('err'), ensure_ascii=False)}", file=sys.stderr)
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else as_text(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
