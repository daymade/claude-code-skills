# Instrumentation Patterns

## Contents
- When to instrument
- Env-gated TRACE pattern (the default)
- Log tag conventions
- Deployment checklist
- Worked example: TRACE_SSE_CHUNKS
- Analysis: extracting timing data from logs
- Persisting instrumentation versus removing it

## When to instrument

Instrument when a hypothesis cannot be confirmed or refuted from currently-available observability. If the system already emits the signal you need (distributed trace, access log field, metric), use that. If not, add instrumentation rather than guess.

Symptoms that justify adding instrumentation:

- "We do not know what the upstream is doing between these timestamps" — add chunk-level or event-level logging at the boundary
- "We think the client side disconnects but have no proof" — log client-close events on the server
- "The fix might not actually be triggering" — log entry/exit at the new code path

Do not instrument for symptoms that already have direct evidence. If `tcpdump` shows the RST, you do not need a new log line to confirm it.

## Env-gated TRACE pattern (the default)

Instrumentation added mid-incident tends to become tech debt. The right pattern makes it permanent but invisible:

1. **Defaults off.** Zero runtime cost in steady state. No risk to enable-by-default performance.
2. **One environment variable toggles it.** No code changes required to enable in production.
3. **Greppable log tag.** Single bracketed prefix (e.g., `[SSE-CHUNK]`) makes every emission easy to filter.
4. **Structured, key=value output.** `ts=... req=... bytes=... total=...` parses into a DataFrame in three lines of Python.
5. **Ships into production permanently.** Future incidents reuse the same knob without re-adding code.

### Template (Node.js)

```js
// Near config section
const TRACE_SSE_CHUNKS = (process.env.TRACE_SSE_CHUNKS || 'false').toLowerCase() === 'true';
if (TRACE_SSE_CHUNKS) console.log('[SSE-CHUNK] instrumentation ENABLED');

// At the observation point
proxyRes.on('data', (chunk) => {
  if (TRACE_SSE_CHUNKS && isAnthropicMessagesPath && isStreaming) {
    const reqId = (proxyRes.headers && proxyRes.headers['x-oneapi-request-id']) || 'n/a';
    const total = chunks.reduce((a, c) => a + c.length, 0);
    console.log(
      '[SSE-CHUNK] ts=' + Date.now() +
      ' req=' + reqId +
      ' bytes=' + chunk.length +
      ' total=' + total
    );
  }
  // ... existing logic untouched
});
```

### Template (Python)

```python
import os, time, logging
TRACE_SSE_CHUNKS = os.environ.get('TRACE_SSE_CHUNKS', '').lower() == 'true'
if TRACE_SSE_CHUNKS:
    logging.info('[SSE-CHUNK] instrumentation ENABLED')

# At the observation point
def on_chunk(chunk, req_id, running_total):
    if TRACE_SSE_CHUNKS:
        logging.info(
            f'[SSE-CHUNK] ts={int(time.time()*1000)} '
            f'req={req_id} bytes={len(chunk)} total={running_total}'
        )
```

### Enabling in a containerized deployment

```bash
# Edit docker-compose env or apply shell env then recreate:
TRACE_SSE_CHUNKS=true docker compose up -d <service>

# Or in Kubernetes:
kubectl set env deployment/<name> TRACE_SSE_CHUNKS=true
```

Disabling is the inverse — unset the variable and restart. No code change, no git commit, no deploy pipeline.

## Log tag conventions

Pick tags that are unlikely to false-match other logs. A good tag:

- Starts with a bracket to survive `grep`
- Uses `SCREAMING-KEBAB-CASE` for visual distinction from regular logs
- Is specific enough to identify the instrumentation site, not just the subsystem

Good: `[SSE-CHUNK]`, `[UPSTREAM-CONNECT-RTT]`, `[CLIENT-DISCONNECT]`
Bad: `[DEBUG]`, `[TRACE]`, `log.info("chunk arrived")`

Pair an ENABLED log line with the toggle so the presence of instrumentation is visible at service start — no guessing whether it actually took effect.

## Deployment checklist

When adding instrumentation to a running system:

- [ ] The gate defaults off (confirmed by reading the code — do not trust the comment)
- [ ] The gate reads from env at startup (warn the user that changes require restart, not a runtime-reload)
- [ ] The output is structured (key=value) — no prose log messages
- [ ] The tag is unique (grep the codebase for conflicts)
- [ ] Sampling or volume cap if high-frequency (e.g., per-chunk logs on a 1000-rps service need either sampling or a max-size file sink)
- [ ] An ENABLED banner line is emitted at startup when the gate is on
- [ ] The change is committed to source of truth (not only applied to the running server — see the IaC trap below)

## Worked example: TRACE_SSE_CHUNKS

Real artifact from this investigation. Goal: observe the upstream chunk arrival pattern to confirm/refute the hypothesis "Qiniu batches chunks and goes silent for >120s during tool_use generation".

**Before instrumentation**: the only available signal was aggregate `duration_ms` in the archive metadata. This told us the request took 315 seconds total but said nothing about *when* within those 315s bytes flowed.

**After instrumentation (10 lines added)**:

```
[SSE-CHUNK] ts=1776870300212 req=202604221504562... bytes=128 total=1993
[SSE-CHUNK] ts=1776870300213 req=202604221504562... bytes=131 total=2124
[SSE-CHUNK] ts=1776870300213 req=202604221504562... bytes=127 total=2251
...
[SSE-CHUNK] ts=1776870300627 req=202604221504562... bytes=128 total=5583
... (30 chunks over 1.2 seconds, then silence)
[SSE-CHUNK] ts=1776870425235 req=202604221504562... bytes=74 total=3865
```

Extracted: 30 chunks in the first 1.2 seconds (3791 bytes total), then a **125-second gap with zero bytes**, then 74 more bytes. The hypothesis was confirmed: Qiniu emits the beginning of the response in a burst, then stays silent for over 2 minutes while the model generates the tool_use arguments internally.

Without the instrumentation, this would have been invisible. With 10 lines of code gated on one env var, it became a permanent observability capability.

## Analysis: extracting timing data from logs

Once instrumentation is emitting structured logs, a few lines of Python turns log output into inter-arrival time analysis:

```python
import sys, re
from collections import defaultdict

chunks = []
for line in sys.stdin:
    m = re.search(r'ts=(\d+) req=(\S+) bytes=(\d+) total=(\d+)', line)
    if m:
        ts, req, b, tot = m.groups()
        chunks.append((int(ts), req, int(b), int(tot)))

by_req = defaultdict(list)
for ts, req, b, tot in chunks:
    by_req[req].append((ts, b, tot))

for req, seq in by_req.items():
    if len(seq) < 2: continue
    span = seq[-1][0] - seq[0][0]
    big_gaps = [seq[i][0] - seq[i-1][0] for i in range(1, len(seq)) if seq[i][0] - seq[i-1][0] > 1000]
    print(f'req={req[:20]} chunks={len(seq)} span={span}ms gaps>1s={len(big_gaps)} max_gap={max(big_gaps) if big_gaps else 0}ms')
```

Pipe `docker logs <container> | python analyze.py` and you have a per-request latency histogram. A request with `max_gap=125023ms` jumps out immediately.

## Persisting instrumentation versus removing it

Traditional wisdom says "remove debug logging after fix". That wisdom predates this pattern. With the env-gate approach, the correct default is:

**Keep the instrumentation code. Leave the env toggle off. Document the toggle in an ops runbook.**

Rationale:
- Adding instrumentation mid-incident under pressure is error-prone. Far better to have the gate already in place.
- Zero runtime cost when off.
- The env variable name is self-documenting.
- The next incident is cheaper.

The only time to remove instrumentation is when it has been superseded by better observability (e.g., you instrumented chunk timing, then later added full distributed tracing that subsumes it).

## The IaC trap

If the service is deployed via Infrastructure-as-Code (Terraform, Ansible, Kubernetes manifests), instrumentation applied directly to the running instance (`docker exec`, live file edit) will be overwritten on the next deploy. The drift hides the real state and frustrates the next investigator.

Always apply the code change to the source of truth first:

1. Edit the source repo (e.g., `js/service-name/server.js`)
2. Commit and push, or at minimum sync to the deploy pipeline's input
3. Run the normal deploy to propagate
4. Only after that, enable the env toggle

If time-critical: apply directly to the running server *and* to the source, in the same session. Never only to the running server.
