# Valid JSON can still be an incomplete HTTP response

Use this check when a bounded Python HTTP reader reports success even though the
server closed early. HTTP framing and application parsing are separate evidence:
`200` and a successful `json.loads` do not establish complete reception.

## Reproduce the false success first

The investigator can use a temporary server bound to `127.0.0.1`, with synthetic
responses and a short client timeout. Send this response, then close the socket:

```text
HTTP/1.1 200 OK\r\n
Content-Length: 18\r\n
Connection: close\r\n
\r\n
{"ok":true}
```

The body is exactly 11 bytes, with no final newline; the displayed `\r\n` denotes
wire CRLF, not literal backslashes. In CPython 3.12.13,
`HTTPResponse.read(limit + 1)` with `limit >= 18` returns those 11 bytes without
raising `IncompleteRead`. JSON parsing succeeds while `response.length` remains
7. A bad-JSON fixture would test parsing, missing this transport failure.

The [Python documentation](https://docs.python.org/3.12/library/http.client.html#http.client.HTTPResponse.read)
describes a bounded read as returning up to the requested amount. The
[CPython 3.12.13 implementation](https://github.com/python/cpython/blob/v3.12.13/Lib/http/client.py)
retains the remaining framed length after a bounded read; its unbounded path has
different incomplete-read behavior. `length` is an implementation detail: inspect
and replay on the target runtime before applying this pattern to another version
or HTTP library.

## Keep the size bound and check framing before parsing

For this CPython reader, after obtaining a successful body-bearing response:

```python
import http.client
import json

def read_json(response, limit):  # retain the application's existing byte limit
    body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("response_too_large")
    if response.length is not None and response.length != 0:
        raise http.client.IncompleteRead(body, response.length)
    return json.loads(body)
```

Let HTTP framing errors, timeouts and parse failures reach the caller's failure
path; do not return a success result from partial bytes. Do not replace the
bounded read with an unbounded one to obtain stricter framing at the cost of the
memory limit. Do not compare body length blindly with the raw `Content-Length`
header: the client can ignore it when chunked transfer encoding governs framing.
Do not require the header on every response.

## Verify the changed outcome and the healthy paths

Rerun the same caller against controlled wire responses. Record received bytes,
remaining framed length or framing exception, and the caller's success/failure:

| Fixture | Required outcome |
| --- | --- |
| Declared 18 bytes, valid 11-byte JSON, then EOF | Failure before publishing parsed data |
| Matching `Content-Length`, complete JSON | Success |
| Complete chunked body, including terminal zero chunk | Success |
| Complete chunked body with a conflicting raw length header | Follow the client's framing; no false length rejection |
| No length header, valid close-delimited JSON | Success |
| Chunked JSON missing its terminal chunk | Framing failure |
| Complete body exactly at the limit / one byte above | Success / size failure |

These controls test the caller's behavior, not just whether the diagnostic prints
a warning. Close-delimited EOF has no declared length to check: it cannot prove
that the sender intended no further application data. Where that guarantee is
needed, retain an application-level count, digest or completion contract.
