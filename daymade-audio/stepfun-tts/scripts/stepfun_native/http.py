"""StepFun native HTTP speech, file, and cloned-voice operations.

No model, field, language, or format allowlist is imposed by this transport.
See references/api_reference.md for current official semantics and limitations.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .common import UNSET, merge_request, require_key, require_strings

API_BASE = "https://api.stepfun.com/v1"
API_URL = API_BASE + "/audio/speech"
MODEL = "stepaudio-2.5-tts"
DEFAULT_VOICE = "shuangkuaijiejie"


def build_speech_request(*, text=UNSET, model=UNSET, voice=UNSET, instruction=UNSET,
                         response_format=UNSET, speed=UNSET, volume=UNSET,
                         language=UNSET, sample_rate=UNSET, pronunciation_map=UNSET,
                         stream_format=UNSET, markdown_filter=UNSET, return_url=UNSET,
                         timestamp=UNSET, voice_label=UNSET, request=None, extra=None):
    # The old convenience interface used instruction=None for an omitted directive.
    typed = dict(input=text, model=model, voice=voice,
                 instruction=UNSET if instruction is None else instruction,
                 response_format=response_format, speed=speed, volume=volume,
                 language=language, sample_rate=sample_rate, pronunciation_map=pronunciation_map,
                 stream_format=stream_format, markdown_filter=markdown_filter,
                 return_url=return_url, timestamp=timestamp, voice_label=voice_label)
    defaults = (dict(model=MODEL, voice=DEFAULT_VOICE, response_format="mp3", speed=1.0, volume=1.0)
                if request is None else None)
    body = merge_request(request, typed=typed, extra=extra, defaults=defaults)
    require_strings(body, "model", "input", "voice")
    return body


def _endpoint(endpoint, api_base, path):
    target = api_base.rstrip("/") + path if endpoint is None else endpoint
    if not isinstance(target, str) or urllib.parse.urlsplit(target).scheme not in ("http", "https"):
        raise ValueError("An explicit HTTP(S) endpoint is required")
    return target


def open_response(*, api_key, endpoint, method="POST", request=None, query=None,
                  headers=None, data=None, timeout=300):
    """Return the native HTTPResponse without buffering; the caller must close it.

    HTTP errors retain urllib's native HTTPError (body/headers/status available).
    No retry, URL download, credential lookup, or endpoint/model fallback occurs.
    """
    require_key(api_key)
    endpoint = _endpoint(endpoint, API_BASE, "")
    supplied = dict(headers or {})
    if any(key.lower() == "authorization" for key in supplied):
        raise ValueError("Use api_key for Authorization; duplicate credentials are not accepted")
    if query:
        endpoint += ("&" if "?" in endpoint else "?") + urllib.parse.urlencode(query, doseq=True)
    if request is not None:
        if data is not None:
            raise ValueError("Use request or raw data, not both")
        data = json.dumps(request, ensure_ascii=False, allow_nan=False).encode()
        if not any(key.lower() == "content-type" for key in supplied):
            supplied["Content-Type"] = "application/json"
    req = urllib.request.Request(endpoint, data=data, method=method,
                                 headers={**supplied, "Authorization": f"Bearer {api_key}"})
    return urllib.request.urlopen(req, timeout=timeout)


def iter_sse(response):
    """Yield SSE frames without dropping unknown fields, JSON members or wire bytes."""
    lines = []
    for line in response:
        lines.append(line)
        if line.strip(b"\r\n"):
            continue
        yield _sse_frame(b"".join(lines))
        lines = []
    if lines:
        yield _sse_frame(b"".join(lines))


def _sse_frame(raw):
    fields = {}
    for line in raw.decode("utf-8").splitlines():
        if not line or line.startswith(":"):
            continue
        name, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        fields.setdefault(name, []).append(value)
    text = "\n".join(fields.get("data", []))
    try:
        value = json.loads(text)
    except ValueError:
        value = text
    return {"fields": fields, "data": value, "raw": raw}


def _read_result(response, *, endpoint, request):
    raw = response.read()
    status = response.status
    raw_headers = list(response.headers.items())
    headers = dict(raw_headers)
    content_type = response.headers.get("Content-Type", "").lower()
    result = dict(ok=200 <= status < 300, status=status, endpoint=endpoint,
                  request=request, headers=headers, raw_headers=raw_headers, raw_body=raw)
    if "event-stream" in content_type:
        try:
            events = list(iter_sse(io.BytesIO(raw)))
            result["events"] = events
            audio, complete, errors = [], False, []
            for event in events:
                data = event["data"]
                if data == "[DONE]":
                    complete = True
                elif isinstance(data, dict):
                    kind = data.get("type")
                    if kind == "speech.audio.delta":
                        audio.append(base64.b64decode(data["audio"], validate=True))
                    elif kind == "speech.audio.done":
                        complete = True
                    elif kind == "speech.audio.error" or "error" in data:
                        errors.append(data)
            result.update(audio_bytes=b"".join(audio), stream_complete=complete)
            if errors or not complete:
                result.update(ok=False, err="Speech stream error" if errors else "Speech stream ended without completion")
        except (ValueError, UnicodeError, KeyError, TypeError) as exc:
            result.update(ok=False, err=f"Invalid speech event stream: {exc}")
    elif "json" in content_type:
        try:
            result["json"] = json.loads(raw)
            if isinstance(result["json"], dict) and "error" in result["json"]:
                result.update(ok=False, err=raw.decode("utf-8", errors="replace"))
        except (ValueError, UnicodeError) as exc:
            result.update(ok=False, err=f"Invalid JSON response: {exc}")
    else:
        result["audio_bytes"] = raw
    if not result["ok"]:
        result.setdefault("err", raw.decode("utf-8", errors="replace"))
        result["censored"] = b"censorship_block" in raw
    return result


def request_api(*, api_key, endpoint, method="POST", request=None, query=None,
                headers=None, data=None, timeout=300):
    """Buffered convenience result, retaining the complete native response."""
    try:
        with open_response(api_key=api_key, endpoint=endpoint, method=method,
                           request=request, query=query, headers=headers, data=data, timeout=timeout) as response:
            return _read_result(response, endpoint=endpoint, request=request if request is not None else query)
    except urllib.error.HTTPError as error:
        result = _read_result(error, endpoint=endpoint, request=request if request is not None else query)
        result["ok"] = False
        result.setdefault("err", result["raw_body"].decode("utf-8", errors="replace"))
        result["censored"] = b"censorship_block" in result["raw_body"]
        return result
    except (urllib.error.URLError, TimeoutError) as error:
        return dict(ok=False, status=0, endpoint=endpoint, request=request,
                    err=str(error), network_error=type(error).__name__)


def open_speech_response(*, api_key, endpoint=API_URL, timeout=300, headers=None, **fields):
    return open_response(api_key=api_key, endpoint=endpoint, timeout=timeout, headers=headers,
                         request=build_speech_request(**fields))


def synthesize(*, api_key, text=UNSET, model=UNSET, voice=UNSET, instruction=UNSET,
               response_format=UNSET, speed=UNSET, volume=UNSET, language=UNSET,
               sample_rate=UNSET, pronunciation_map=UNSET, stream_format=UNSET,
               markdown_filter=UNSET, return_url=UNSET, timestamp=UNSET,
               voice_label=UNSET, request=None, extra=None, endpoint=API_URL,
               timeout=300, headers=None):
    fields = dict(text=text, model=model, voice=voice, instruction=instruction,
                  response_format=response_format, speed=speed, volume=volume,
                  language=language, sample_rate=sample_rate, pronunciation_map=pronunciation_map,
                  stream_format=stream_format, markdown_filter=markdown_filter,
                  return_url=return_url, timestamp=timestamp, voice_label=voice_label,
                  request=request, extra=extra)
    return request_api(api_key=api_key, endpoint=endpoint, timeout=timeout, headers=headers,
                       request=build_speech_request(**fields))


def create_voice(*, api_key, model=UNSET, file_id=UNSET, text=UNSET, sample_text=UNSET,
                 request=None, extra=None, endpoint=None, api_base=API_BASE, timeout=300, headers=None):
    body = merge_request(request, typed=dict(model=model, file_id=file_id, text=text,
                                            sample_text=sample_text), extra=extra)
    require_strings(body, "model", "file_id")
    return request_api(api_key=api_key, endpoint=_endpoint(endpoint, api_base, "/audio/voices"),
                       request=body, timeout=timeout, headers=headers)


def preview_voice(*, api_key, model=UNSET, file_id=UNSET, text=UNSET, sample_text=UNSET,
                  request=None, extra=None, endpoint=None, api_base=API_BASE, timeout=300, headers=None):
    body = merge_request(request, typed=dict(model=model, file_id=file_id, text=text,
                                            sample_text=sample_text), extra=extra)
    require_strings(body, "model", "file_id", "sample_text")
    return request_api(api_key=api_key, endpoint=_endpoint(endpoint, api_base, "/audio/voices/preview"),
                       request=body, timeout=timeout, headers=headers)


def list_voices(*, api_key, limit=UNSET, order=UNSET, before=UNSET, after=UNSET,
                query=None, extra=None, endpoint=None, api_base=API_BASE, timeout=300, headers=None):
    params = merge_request(query, typed=dict(limit=limit, order=order, before=before, after=after), extra=extra)
    return request_api(api_key=api_key, endpoint=_endpoint(endpoint, api_base, "/audio/voices"),
                       method="GET", query=params, timeout=timeout, headers=headers)


def system_voices(*, api_key, model=UNSET, query=None, extra=None,
                  endpoint=None, api_base=API_BASE, timeout=300, headers=None):
    params = merge_request(query, typed=dict(model=model), extra=extra)
    require_strings(params, "model")
    return request_api(api_key=api_key, endpoint=_endpoint(endpoint, api_base, "/audio/system_voices"),
                       method="GET", query=params, timeout=timeout, headers=headers)


def upload_file(*, api_key, file=None, url=UNSET, purpose="storage", extra=None,
                endpoint=None, api_base=API_BASE, timeout=300, headers=None):
    """Upload native multipart fields. A supplied file takes precedence server-side."""
    fields = merge_request(typed=dict(url=url, purpose=purpose), extra=extra)
    if file is None and not fields.get("url"):
        raise ValueError("A file or remote URL is required")
    boundary = "stepfun_" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        encoded = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{encoded}\r\n'.encode())
    record = dict(fields)
    if file is not None:
        if isinstance(file, tuple):
            filename, payload, content_type = file
        else:
            path = Path(file)
            filename, payload = path.name, path.read_bytes()
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if not isinstance(payload, bytes) or not payload:
            raise ValueError("A non-empty binary upload is required")
        if any(char in filename + content_type for char in '\r\n"'):
            raise ValueError("Invalid multipart filename or content type")
        parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode(), payload, b"\r\n"])
        record["file"] = dict(filename=filename, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    parts.append(f"--{boundary}--\r\n".encode())
    supplied = dict(headers or {})
    if any(key.lower() == "content-type" for key in supplied):
        raise ValueError("Multipart Content-Type is generated with its boundary")
    supplied["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    result = request_api(api_key=api_key, endpoint=_endpoint(endpoint, api_base, "/files"),
                         data=b"".join(parts), headers=supplied,
                         timeout=timeout)
    result["request"] = record
    return result


def file_operation(*, api_key, operation, file_id=None, query=None, extra=None,
                   endpoint=None, api_base=API_BASE, timeout=300, headers=None):
    """Native Files lifecycle; deletion is an explicit caller operation, never cleanup."""
    if operation not in ("list", "retrieve", "content", "delete"):
        raise ValueError("Use list, retrieve, content, or delete")
    path = "/files"
    if operation != "list":
        require_strings({"file_id": file_id}, "file_id")
        path += "/" + urllib.parse.quote(file_id, safe="")
        if operation == "content":
            path += "/content"
    params = merge_request(query, extra=extra)
    return request_api(api_key=api_key, endpoint=_endpoint(endpoint, api_base, path),
                       method="DELETE" if operation == "delete" else "GET", query=params, timeout=timeout, headers=headers)
