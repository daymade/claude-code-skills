# Case study: Cloudflare 524 on a 6 MB <openrouter-service> request body

This case study walks through a 2026-06-12 incident on `<api-domain>` where a Cloudflare 524 was initially easy to misattribute to backend slowness. The actual cause was the request body upload time exceeding Cloudflare's default origin read timeout.

## Symptom

Cloudflare returned a 524 for `POST https://<api-domain>/<openrouter-path>`:

```json
{
  "type": "https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-524/",
  "title": "Error 524: A timeout occurred",
  "status": 524,
  "detail": "The origin web server did not return a complete response within the 120-second Proxy Read Timeout window.",
  "instance": "<cf-ray-id>",
  "ray_id": "<cf-ray-id>",
  "timestamp": "2026-06-12T11:30:28Z"
}
```

The error explicitly says "origin web server did not return a complete response", which naturally points at the origin. The risk is to start tuning backend timeouts or restarting services.

## Direct evidence that changed the diagnosis

### 1. Caddy access log for the Ray ID

```bash
ssh root@<origin-ip> \
  'docker logs --since "2026-06-12T11:28:00Z" --until "2026-06-12T11:33:00Z" \
   <gateway-container> 2>&1 | grep "<cf-ray-id>"'
```

Key fields from the JSON log:

```json
{
  "ts": 1781263801.0,
  "duration": 125.0,
  "status": 0,
  "size": 0,
  "bytes_read": 4111422,
  "request": {
    "method": "POST",
    "host": "<api-domain>",
    "uri": "/<openrouter-path>",
    "headers": {
      "Content-Length": ["6042141"],
      "Cf-Connecting-Ip": ["<client-ip>"],
      "User-Agent": ["<claude-cli-user-agent>"],
      "Cf-Ray": ["<cf-ray-id>-<colo>"]
    }
  }
}
```

The proxy read **4,111,422 bytes of a declared 6,042,141-byte body** and never returned a response. That is an incomplete upload, not a backend hang.

### 2. Provider-gateway logged a client abort

```bash
ssh root@<origin-ip> \
  'docker logs --since "2026-06-12T11:28:00Z" --until "2026-06-12T11:35:00Z" \
   <provider-gateway-service> 2>&1 | head -20'
```

Output:

```
Client request error: aborted
Client request error: aborted
...
```

The relevant code:

```js
// <provider-gateway-service-source>
req.on("error", (err) => {
  console.error("Client request error:", err.message);
  // Client aborted mid-request-body (Node surfaces it as 'aborted'/
  // ECONNRESET) or the request stream failed — record the terminal
  // client_abort row.
  maybeLogClientAbort();
  if (!res.headersSent) {
    res.writeHead(400);
    res.end("Bad Request");
  }
});
```

This tells us the request stream was aborted before it finished. It does **not** tell us _who_ aborted it. The edge (Cloudflare) aborting first and the origin seeing a downstream abort is the expected pattern for a CDN timeout.

### 3. The request never reached <upstream-capture-service> or <new-api-container>

```bash
ssh root@<origin-ip> \
  'grep -E "\"ts\":\"2026-06-12T11:30:0[0-9]" /data/<upstream-capture-service>/log/access.log | \
   python3 -c "import sys,json; [print(json.dumps({k:d.get(k) for k in [\"ts\",\"channel_id\",\"status\",\"request_length\",\"request_time\"]})) for d in (json.loads(l) for l in sys.stdin)]"'
```

Only one unrelated request appeared at `11:30:03` (channel 3, 174 KB). The 6 MB request never made it past the body-reading stage.

### 4. Successful large requests from the same client took ~122 s total

A successful request at `11:02:14` with the same body size:

- Caddy `duration`: 122.2 s
- Caddy `status`: 200
- <upstream-capture-service> `request_time`: 31.2 s (channel 7 DeepSeek)

The ~91 s gap is the time spent uploading the body. When the upload was slower than ~100–120 s, Cloudflare cut the connection and returned 524.

### 5. Pattern by client IP

Over a 3-hour window:

| Metric                              | Count |
| ----------------------------------- | ----- |
| Total `/<openrouter-path>` requests | 628   |
| `status=0` failures                 | 7     |
| `status=200` successes              | 618   |
| Failures from `<client-ip>`         | 7 / 7 |

All failures were from the same US client IP, all on large bodies.

## Root cause

Cloudflare's default origin read timeout (~100–120 s) was shorter than the time needed for this US client to upload a ~6 MB request body to the <origin-region> origin. When the upload did not finish in time, Cloudflare returned 524. Caddy and <provider-gateway-service> then observed the abort as a closed client stream.

## Why this is easy to get wrong

1. **The error message blames the origin.** "Origin web server did not return a complete response" reads like a backend problem.
2. **Provider-gateway logs look like a client problem.** "Client request error: aborted" suggests the user killed the request, but the actual closer was Cloudflare.
3. **Backend services are all healthy.** Without checking `bytes_read` vs `Content-Length`, the natural next step is to look for slow upstream LLM calls.

## Decisive observation

The falsifier for "backend is slow" was: **if the request never reached <upstream-capture-service>, backend slowness is impossible.** Confirming that falsifier required only two greps (Caddy + <upstream-capture-service>) and took under a minute.

## Lessons

- Always compare `bytes_read` to `Content-Length` in proxy logs when diagnosing 524/522/504 on large `POST` bodies.
- `status=0` in Caddy (or `-` in nginx) means no HTTP response was written — a strong signal that the connection was closed by an upstream-of-origin layer.
- Correlate edge error codes (Cloudflare Ray ID) with origin proxy logs; do not let origin-side "client abort" logs mislead you about who closed the connection.
- Aggregate by client IP and body size. A pattern concentrated on one IP is usually a network/path problem, not a systemic backend issue.

## Related files in the main incident report

- `docs/reports/incident-2026-06-12-cloudflare-524-openrouter-upload.md` — full production incident report with exact commands and timeline.
