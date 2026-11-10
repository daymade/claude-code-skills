#!/usr/bin/env python3
"""StepFun speech convenience entry and native HTTP/WebSocket access.

Legacy synthesize(api_key=..., text=...) and single/batch CLI calls remain valid.
request/extra preserve native fields; conflicting explicit values fail before I/O.
Protocol details live in stepfun_native.http and stepfun_native.ws.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path


def _native_package():
    # llmreg loads this file directly, without adding scripts/ to sys.path.
    directory = Path(__file__).resolve().with_name("stepfun_native")
    name = "_stepfun_native_" + hashlib.sha256(str(directory).encode()).hexdigest()[:16]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, directory / "__init__.py",
                                                     submodule_search_locations=[str(directory)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return name


_package = _native_package()
http = importlib.import_module(_package + ".http")
ws = importlib.import_module(_package + ".ws")
UNSET = http.UNSET
API_URL, MODEL, DEFAULT_VOICE = http.API_URL, http.MODEL, http.DEFAULT_VOICE
synthesize = http.synthesize
build_speech_request = http.build_speech_request
open_speech_response = http.open_speech_response
upload_file = http.upload_file
create_voice = http.create_voice
preview_voice = http.preview_voice
list_voices = http.list_voices
system_voices = http.system_voices
file_operation = http.file_operation


def load_api_key():
    key = os.environ.get("STEPFUN_API_KEY", "").strip()
    if not key:
        print("ERROR: set STEPFUN_API_KEY in the calling environment; no credential fallback.", file=sys.stderr)
        raise SystemExit(2)
    return key


def read_batch(path):
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            yield json.loads(line)


def _json_argument(value):
    if value is None:
        return None
    return json.loads(Path(value[1:]).read_text() if value.startswith("@") else value)


def _json_default(value):
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
    raise TypeError(type(value).__name__)


def _save_result(result, out, record=None):
    out = Path(out)
    target = Path(record) if record else out.with_name(out.name + ".response.json")
    metadata = {key: value for key, value in result.items() if key not in ("audio_bytes", "raw_body")}
    if result.get("ok") and "audio_bytes" in result:
        out.write_bytes(result["audio_bytes"])
        print(f"OK wrote {out} ({len(result['audio_bytes'])} bytes)")
    raw = result.get("raw_body")
    if raw is not None:
        if raw == result.get("audio_bytes") and result.get("ok"):
            metadata["raw_body_file"] = os.path.relpath(out.resolve(), target.parent.resolve())
        else:
            raw_path = out.with_name(out.name + ".response-body")
            raw_path.write_bytes(raw)
            metadata["raw_body_file"] = os.path.relpath(raw_path.resolve(), target.parent.resolve())
    target.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False,
                                 default=_json_default) + "\n")
    print(f"Native response record: {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--text")
    mode.add_argument("--batch", type=Path,
                      help="JSONL: id plus text or full request; row fields override global option defaults")
    mode.add_argument("--request", type=Path, help="Complete native speech JSON body")
    parser.add_argument("--extra", help="Native JSON object, or @path/to/file.json")
    parser.add_argument("--out")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--record", type=Path, help="Single-call response metadata path")
    parser.add_argument("--endpoint", default=API_URL)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--delay-ms", type=int, default=400)
    parser.add_argument("--dry-run", action="store_true", help="Print actual native request; no key or network")
    for name in ("model", "voice", "instruction", "language", "response-format", "stream-format"):
        parser.add_argument("--" + name, default=UNSET)
    for name in ("speed", "volume"):
        parser.add_argument("--" + name, type=float, default=UNSET)
    parser.add_argument("--sample-rate", type=int, default=UNSET)
    parser.add_argument("--pronunciation-map", default=UNSET, help="Native JSON pronunciation_map object")
    for name in ("markdown-filter", "return-url", "timestamp"):
        parser.add_argument("--" + name, action=argparse.BooleanOptionalAction, default=UNSET)
    args = parser.parse_args()
    names = ("model", "voice", "instruction", "language", "response_format", "stream_format",
             "speed", "volume", "sample_rate", "pronunciation_map", "markdown_filter", "return_url", "timestamp")
    typed = {name: getattr(args, name) for name in names}
    if typed["pronunciation_map"] is not UNSET:
        typed["pronunciation_map"] = _json_argument(typed["pronunciation_map"])
    extra = _json_argument(args.extra)

    def body_for(item):
        fields = {**typed, **{name: item[name] for name in names if name in item}}
        if "text" in item:
            fields["text"] = item["text"]
        return build_speech_request(request=item.get("request"),
                                    extra=http.merge_request(extra, extra=item.get("extra")), **fields)

    if args.batch is None:
        if not args.dry_run and not args.out:
            parser.error("--out is required")
        item = {"request": json.loads(args.request.read_text())} if args.request else {"text": args.text}
        body = body_for(item)
        if args.dry_run:
            print(json.dumps(body, ensure_ascii=False, allow_nan=False))
            return 0
        result = synthesize(api_key=load_api_key(), request=body, endpoint=args.endpoint, timeout=args.timeout)
        _save_result(result, args.out, args.record)
        if not result["ok"]:
            print(f"FAIL status={result['status']}: {result.get('err', '')}", file=sys.stderr)
        return 0 if result["ok"] else 1

    if not args.dry_run and args.out_dir is None:
        parser.error("--out-dir is required with --batch")
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    key = None if args.dry_run else load_api_key()
    failed, censored = [], []
    for item in read_batch(args.batch):
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or Path(identifier).name != identifier or identifier in (".", ".."):
            raise ValueError("Each batch item requires a safe, non-empty id")
        body = body_for(item)
        if args.dry_run:
            print(json.dumps({"id": identifier, "request": body}, ensure_ascii=False, allow_nan=False))
            continue
        result = synthesize(api_key=key, request=body, endpoint=args.endpoint, timeout=args.timeout)
        extension = body.get("response_format", "mp3")
        if not isinstance(extension, str) or not extension.isalnum():
            extension = "audio"
        _save_result(result, args.out_dir / f"{identifier}.{extension}")
        if result.get("censored"):
            censored.append(identifier)
            print(f"CENSORED {identifier}: no audio generated; no automatic fallback")
        elif not result["ok"]:
            failed.append(identifier)
            print(f"FAIL {identifier}: {result.get('err', '')}", file=sys.stderr)
        time.sleep(args.delay_ms / 1000)
    if censored:
        print("Censored IDs: " + ", ".join(censored))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
