# Native StepFun speech API

## Authority and scope

The following official references were checked on 2026-11-10. Their limits are
service contracts, not local allowlists; use the account's current endpoint and
catalogue. The wrapper does not replace a rejected model, key or voice.

- [HTTP speech](https://platform.stepfun.ai/docs/en/api-reference/audio/create-audio)
- [WebSocket speech](https://platform.stepfun.ai/docs/en/api-reference/audio/ws-audio)
- [Create voice](https://platform.stepfun.ai/docs/en/api-reference/audio/create-voice),
  [preview](https://platform.stepfun.ai/docs/en/api-reference/audio/voices-preview),
  [list voices](https://platform.stepfun.ai/docs/en/api-reference/audio/list-voice),
  [system voices](https://platform.stepfun.ai/docs/en/api-reference/audio/system-voices)
- [Files](https://platform.stepfun.ai/docs/en/api-reference/files/create)
- [Delivery and cloning guide](https://platform.stepfun.ai/docs/en/guides/developer/tts)

The global documentation uses `api.stepfun.ai`; the compatible wrapper keeps
its existing `api.stepfun.com` default. Pass the actual `endpoint` or
`api_base` explicitly when changing region or account route. The global speech
and WS references also document Step Plan endpoints. Do not turn an older key's
failure into a universal Plan restriction. Pricing and entitlement require the
current account's authority; this bundle does not persist a price quote.

## HTTP synthesis and expression

The current speech reference names `stepaudio-2.5-tts` and `stepaudio-3-tts`,
official and cloned voice IDs, and an input limit of 1,000 characters. It documents
`instruction` for global emotional tone/persona and ASCII `()` inside input
as unspoken natural-language directions. The instruction limit is 200 characters
on 2.5 and 500 on 3.

The official HTTP example uses `(cold laugh)`; the WS example uses `(excited)`.
Chinese phrases such as `(轻声)` or `(加重)` are possible natural-language
directions, not documented fixed keywords or an exact numerical stress control.
Their audible effect on a particular cloned voice remains a listening question.
Do not convert this capability into an invented SSML vocabulary.
`pronunciation_map` changes readings; it is not an emphasis parameter.
The developer guide explicitly pairs 2.5 cloning with natural-language delivery
control. Global guidance and local directions can therefore accompany a clone;
they do not establish identity or expression quality by themselves.

Current HTTP fields include model/input/voice, language, response_format, speed,
volume, instruction, sample_rate, pronunciation_map, stream_format,
markdown_filter and return_url. See the linked official reference for limits and
current formats/languages, and
[build_speech_request](../scripts/stepfun_native/http.py) for typed Python
arguments. `timestamp` and `voice_label` remain pass-through compatibility
arguments; they are not listed as contextual controls by that current global
reference. A server may reject them for a selected model.

```python
# tts is the module loaded by llmreg.wrapper_for("stepfun-tts").tts_generate.
# key, endpoint and voice_id come from the caller's explicit account/profile.
body = {
    "model": "stepaudio-2.5-tts",
    "voice": voice_id,
    "language": "zh",
    "input": "(放慢一点，认真解释)这是一段完整的说明。",
    "instruction": "自然交谈，重点清楚，保持同一个人的连贯语气",
    "response_format": "wav",
}
result = tts.synthesize(api_key=key, endpoint=endpoint, request=body)
if not result["ok"]:
    raise RuntimeError(result)
audio = result["audio_bytes"]
```

This is an input-design example, not a verified audible result. Full
`request` bodies require model/input/voice; the convenience
`synthesize(text=...)` retains legacy defaults defined in the implementation.
Typed arguments and `extra` add native fields without a whitelist. A duplicate
with a different explicit value raises before I/O; equal duplicates are accepted.
Unknown future fields are forwarded, not represented as tested capabilities.

## Native responses and streaming

Buffered results retain status, request, endpoint, headers and raw_body. The
raw_headers list also retains repeated header fields. Binary
responses additionally expose audio_bytes; JSON responses retain the complete
json object, including URL, subtitles, usage, trace and unknown members if the
server sends them. return_url changes the response to JSON; it is not an audio
buffer. The CLI writes a response record and raw body beside audio unless
`--record` specifies another location. Headers may contain account information;
keep real records out of public examples.

HTTP errors retain their complete body and headers. There is no automatic retry
or model/voice fallback. Inspect ok/status and the native error before choosing
a recovery action. Censorship is a content decision, not permission to change a
customer's words or voice.

For SSE, use `stream_format="sse"`. Buffered synthesis preserves events and raw
wire bytes, and joins documented base64 audio delta chunks. Missing completion,
native error events or malformed audio produce an explicit failure. Unknown
events remain available. For incremental processing, own the unbuffered response:

```python
with tts.open_speech_response(api_key=key, endpoint=endpoint,
                              request=body, extra={"stream_format": "sse"}) as response:
    for event in tts.http.iter_sse(response):
        consume(event)  # Includes fields, parsed JSON when present, and raw bytes.
```

`tts.http.open_response` is the generic unbuffered HTTP entry; `request_api`
is its buffered counterpart. They accept native endpoint, method, body/data,
query and headers. They do not consume or rename an unbuffered server stream.
Do not provide Authorization both as api_key and a custom header.

## Voice and file lifecycle

The formal create/preview references currently name 2.5 for cloning, with
storage-uploaded MP3/WAV reference audio of 5–10 seconds. The developer guide's
shorter introductory duration is not the upload recipe. Use an accurate
reference transcript when available; omission lets the service recognize it.
Record the returned voice ID with its source and creation model: list responses
do not identify the creation model.

The [official September 29 v3 cookbook](https://platform.stepfun.com/cookbook/stepaudio-3-tts)
uses v3 in a cloning example, which conflicts with the formal clone API's model
description. V3 cloning is therefore unverified here; neither a blanket ban nor
a verified-support claim follows. The wrapper forwards an explicitly selected
model and preserves the response without falling back.

```python
uploaded = tts.upload_file(api_key=key, api_base=api_base,
                           file=reference_path, purpose="storage")
if not uploaded["ok"]:
    raise RuntimeError(uploaded)
created = tts.create_voice(
    api_key=key, api_base=api_base, model="stepaudio-2.5-tts",
    file_id=uploaded["json"]["id"], text=reference_transcript,
)
if not created["ok"]:
    raise RuntimeError(created)
voice_id = created["json"]["id"]
```

`upload_file` accepts a local file/path tuple or URL plus native fields.
`create_voice`, `preview_voice`, `list_voices` and `system_voices` expose the
official routes with full request/query extension channels. Preview returns
sample audio without creating a persistent voice. Inspect the full JSON rather
than assuming synthesis's binary shape. `file_operation` exposes list,
retrieve, content and delete; deletion is caller-directed and never an automatic
post-generation cleanup. The native HTTP entry remains available for new
lifecycle fields or routes.

## Native WebSocket client

Install the optional [WS dependency](../scripts/requirements-ws.txt). The
[ws module](../scripts/stepfun_native/ws.py) returns the underlying
`websocket-client` socket and supplies raw-event helpers. It has no private
llmreg dependency and does not consume the connection event.

```python
with tts.ws.session(api_key=key, model="stepaudio-2.5-tts",
                    endpoint=ws_endpoint) as socket:
    connected = tts.ws.receive_event(socket)  # Retains raw and parsed JSON.
    session_id = connected["json"]["data"]["session_id"]
    tts.ws.send_event(socket, tts.ws.create_event(
        session_id=session_id, voice_id=voice_id, language="zh",
        instruction="自然交谈，重点清楚", response_format="wav",
    ))
    created = tts.ws.receive_event(socket)
    # Check for tts.response.created; preserve/handle any error before sending text.
    if created.get("json", {}).get("type") != "tts.response.created":
        raise RuntimeError(created)
    tts.ws.send_event(socket, {"type": "tts.text.delta",
                              "data": {"session_id": session_id, "text": full_text}})
    tts.ws.send_event(socket, {"type": "tts.text.done",
                              "data": {"session_id": session_id}})
    # Receive through tts.response.audio.done; inspect errors and retain native events.
```

The official WS reference supports 2.5 and 3. Its create payload additionally
uses voice_id, speed_ratio, volume_ratio and mode; `create_event` exposes these
and the other documented fields plus full request/extra channels. `connect`
accepts native headers/query/socket options; `send_event` and `receive_event`
preserve arbitrary client/server envelopes and raw non-JSON messages.
No HTTP fallback or hidden event pump runs. The caller owns the event loop,
terminal/error handling and saving audio. The official guide warns that 2.5 WS
quality may be lower than non-streaming HTTP, so low latency is not a reason to
replace an offline voiceover's HTTP path.

## Offline verification

From the repository root run
`python3 -m unittest discover -s daymade-audio/stepfun-tts/tests -v`.
The contracts use synthetic transport stubs and the actual flat module-loading
shape; they consume no API quota. They verify field/event preservation,
identity/conflict failures and CLI compatibility. They do not verify account
entitlement, current voice identity, naturalness, local emphasis or sound quality.
