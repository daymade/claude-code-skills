# Same-byte HTTP request-compression comparison

Use when a request encoding such as zstd is a plausible failure axis. A generic
400 alone is not that evidence. First capture the complete response, identifiers,
actual transport and request provenance; then test one discriminating variable.

## Select safe input and state what was captured

Prefer an existing pure model/API request whose replay cannot perform external
mutations. Do not execute returned model tool calls. A model request can still
incur usage; stay within the task's authorization. For a mutating endpoint, use
an approved isolated environment or a synthetic equivalent rather than replaying
the production action. An idempotency assumption is not replay permission.

Freeze one JSON byte file before testing, with its length and SHA-256. Distinguish
original failed encoded entity, original pre-compression JSON bytes, parsed and
reserialized trace, and synthetic fixture. Parsing JSON and writing it back can
change key order, escaping and whitespace. Recompressing original JSON also
creates a new representation; codec version, level and frame layout can matter.
Neither reconstruction is the original failed encoded entity.

When the original encoded entity was retained, preserve it unchanged and decode
a separate copy for the plain arm. When only JSON bytes exist, encode a separate
copy with an existing codec such as `zstd`, recording version/options. Confirm the
encoded file decodes losslessly to the frozen JSON bytes before sending anything.
Use existing `cmp`, `wc` and SHA-256 tooling; matching JSON values alone is weaker
than matching bytes. Do not replace an original entity with a fresh encoding and
call it an exact replay.

For already prepared task-owned files, the essential local checks are:

```bash
zstd --version
zstd --test request.zst
zstd --decompress --stdout request.zst > decoded.json
cmp request.json decoded.json
shasum -a 256 request.json decoded.json request.zst
wc -c request.json request.zst decoded.json
```

Choose fresh output paths before redirection. Inspect each command's status and
result before proceeding; `cmp` exit 0 establishes byte equality. Do not combine
preparation, a failed check and a network send into an unchecked command chain.

## Freeze the experiment conditions

Record endpoint/path, method, account identity, model, content type, other request
headers, HTTP version/transport, client version and route. Reuse the same JSON
bytes and identity. Change only the encoded entity, `Content-Encoding` and the
corresponding length/framing. Verify the actual sent headers: stale
`Content-Length` or duplicate encoding headers invalidate the comparison.

Use the application's supported transport controls and **observe** HTTP versus
WebSocket on every arm. A configuration override on an inactive provider is not
evidence that HTTP ran. If curl is the independent HTTP client, use
`--data-binary @request.json` / `--data-binary @request.zst` to preserve body bytes;
do not paste JSON into a shell string or use `--compressed` to request upload
compression (that option negotiates response compression).

Load authorization through the existing protected credential/header mechanism,
never a literal token in a shared command, fixture or report. Retain complete
response headers and body in separate task-owned files using curl's
`--dump-header` and `--output`, and record exit status and HTTP status. Keep an
auth-redacted sent-header record as well. HTTP 200 alone is insufficient for a
streaming API: check the documented terminal success event and absence of an
error event. Preserve all attempts, including timeouts and partial responses.

## Run a bounded return to baseline

Declare the attempts before the run; for example compressed A, plain B, then
compressed A again. Keep bytes and conditions fixed. For an intermittent symptom,
a second authorized pair can separate a repeatable contrast from one lucky retry;
do not retry until a desired result appears. Record each attempt in order:

| Attempt | Entity SHA / length / encoding | Actual transport | HTTP and application result | Request ID / response bytes |
| --- | --- | --- | --- | --- |
| A1 | Captured or newly encoded file | Observed | Recorded | Recorded |
| B1 | Frozen plain file | Observed | Recorded | Recorded |
| A2 | Same file as A1 | Observed | Recorded | Recorded |

A repeated A failure with B success localizes the defect to handling of the
tested encoded representation along the verified path. It does not identify
which server hop or decoder failed. Other compressed inputs succeeding falsifies
“all compressed requests fail,” not the controlled contrast. If A2 succeeds,
retain the intermittent result and investigate time/route state rather than
claiming the encoding alone explains every failure.

## Apply the result to the reported incident

A synthetic fixture is useful for proving a defect without exposing a private
conversation. It cannot by itself prove why an earlier session failed. A reported
Codex case had a valid synthetic zstd entity fail repeatedly while its identical
decoded JSON succeeded, but a compressed fork of the original history also
succeeded. The failed original on-wire entity had not been retained. The supported
conclusions were a reproducible compression-related path defect for the fixture
and an unresolved causal link to the original individual failure.

Do not turn an observed payload size, image count, compression ratio or zstd block
boundary into a universal server limit. An [upstream Codex report](https://github.com/openai/codex/issues/60594)
contains related comparisons; it is corroborating incident evidence, not an
official statement of the backend's exact implementation or a portable threshold.

For Codex feature changes and original-session recovery, continue with
[verification at the actual consumer](https://github.com/daymade/claude-code-skills/blob/main/daymade-codex/local-codex/references/model-request-diagnostics.md#mitigate-and-verify-at-the-actual-consumer).
