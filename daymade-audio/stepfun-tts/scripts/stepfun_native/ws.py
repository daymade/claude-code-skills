"""StepFun's native text-to-speech WebSocket, separate from HTTP speech.

Uses websocket-client, as in the official example. It does not consume events,
retry, choose a voice, alter text, or translate native event names.
"""
from __future__ import annotations

import json
import shlex
import urllib.parse
from contextlib import contextmanager
from pathlib import Path

from .common import UNSET, merge_request, require_key, require_strings

WS_URL = "wss://api.stepfun.com/v1/realtime/audio"


def connect(*, api_key, model=UNSET, endpoint=WS_URL, query=None, headers=None,
            timeout=300, connect_options=None, factory=None):
    """Return the native WebSocket; caller owns recv/send/close and every event."""
    require_key(api_key)
    url = urllib.parse.urlsplit(endpoint)
    if url.scheme not in ("ws", "wss") or not url.netloc:
        raise ValueError("An explicit WS(S) endpoint is required")
    existing = urllib.parse.parse_qs(url.query, keep_blank_values=True)
    existing = {key: value[0] if len(value) == 1 else value for key, value in existing.items()}
    params = merge_request(existing, typed={"model": model}, extra=query)
    require_strings(params, "model")
    endpoint = urllib.parse.urlunsplit(url._replace(query=urllib.parse.urlencode(params, doseq=True)))
    supplied = dict(headers or {})
    if any(key.lower() == "authorization" for key in supplied):
        raise ValueError("Use api_key for Authorization; duplicate credentials are not accepted")
    options = dict(connect_options or {})
    if any(key in options for key in ("url", "header", "timeout")):
        raise ValueError("Use endpoint, headers, and timeout explicitly")
    if factory is None:
        try:
            from websocket import create_connection
        except ImportError as exc:
            requirements = Path(__file__).resolve().parents[1] / "requirements-ws.txt"
            raise RuntimeError(
                "Native WebSocket TTS requires websocket-client; no HTTP fallback. Install with: "
                f"python3 -m pip install -r {shlex.quote(str(requirements))}"
            ) from exc
        factory = create_connection
    return factory(endpoint, header={**supplied, "Authorization": f"Bearer {api_key}"},
                   timeout=timeout, **options)


@contextmanager
def session(**kwargs):
    """Yield the native client without consuming its connection/session events."""
    client = connect(**kwargs)
    try:
        yield client
    finally:
        client.close()


def create_event(*, session_id=UNSET, voice_id=UNSET, language=UNSET,
                 response_format=UNSET, sample_rate=UNSET, pronunciation_map=UNSET,
                 speed_ratio=UNSET, volume_ratio=UNSET, mode=UNSET, instruction=UNSET,
                 markdown_filter=UNSET, request=None, extra=None):
    """Compose tts.create data; unknown native fields are preserved via request/extra."""
    data = merge_request(request, typed=dict(session_id=session_id, voice_id=voice_id,
                         language=language, response_format=response_format, sample_rate=sample_rate,
                         pronunciation_map=pronunciation_map, speed_ratio=speed_ratio,
                         volume_ratio=volume_ratio, mode=mode, instruction=instruction,
                         markdown_filter=markdown_filter), extra=extra)
    require_strings(data, "session_id", "voice_id")
    return {"type": "tts.create", "data": data}


def send_event(client, event):
    """Send a complete native event unchanged, including future envelope fields."""
    client.send(json.dumps(event, ensure_ascii=False, allow_nan=False))


def receive_event(client):
    """Return the original message and parsed JSON when available; no filtering."""
    raw = client.recv()
    try:
        return {"raw": raw, "json": json.loads(raw)}
    except (ValueError, UnicodeError) as error:
        return {"raw": raw, "parse_error": str(error)}
