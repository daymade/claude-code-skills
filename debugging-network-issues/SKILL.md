---
name: debugging-network-issues
description: >-
  Evidence-driven investigation for network, streaming, and protocol-layer bugs where symptoms don't match the obvious cause. Use when debugging connection resets (ECONNRESET, HTTP/2 RST_STREAM, INTERNAL_ERROR), SSE or long-polling stalls, fixed-time connection drops, CDN/proxy/CGNAT idle timeouts, client-side proxy/VPN/TUN misrouting, CNAME-based proxy rule overrides, or symptoms like "socket closed unexpectedly", "stream interrupted", "fails after N seconds", "works sometimes but not always", "upstream silent for X seconds", ERR_CONNECTION_CLOSED, SSL_ERROR_SYSCALL, or certificate-verification errors (UNKNOWN_CERTIFICATE_VERIFICATION_ERROR, wrong-site certificate) that hit some domains while others work. Also use for throughput collapse where nothing errors at all — "it works, it's just slow", transfers crawling, downloads truncating. Also for LAN-layer mysteries: unknown device (mystery IP/MAC/banner), devices silenced by a subnet change, or a host declared "dead" that is alive on another segment.
---

# Debugging Network Issues

Evidence-driven investigation methodology for incidents where the obvious cause is probably wrong. Built from a real 5-hour production case (see [references/case-sse-rst-130s.md](references/case-sse-rst-130s.md)) where assumption-stacking wasted hours that a 10-minute layered experiment would have resolved.

Apply this skill when the user reports a network/streaming/protocol symptom and the investigator feels tempted to diagnose from one log line or one circumstantial data point. The skill's job is to slow that reflex down.

## Triage first — is this a known domain?

Before applying the general methodology below, check whether the symptom points at a stack that already has a dedicated skill in this repo. Those carry the domain-specific symptom→cause→fix tables this skill deliberately stays general about — start there, and come back here for methodology if the root cause turns out to be elsewhere.

| If the symptom is…                                                                                                                                                                                       | Start with                                   |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| macOS Tailscale ⨯ proxy/VPN conflict (Shadowrocket / Clash / Surge): `tailscale ping` works but SSH/curl/git fails, `Connection closed by 198.18.x.x`, TUN DNS hijack, ~60s `getaddrinfo` resolver stall | **tunnel-doctor**                            |
| Cloudflare config: `ERR_TOO_MANY_REDIRECTS`, SSL-mode mismatch, DNS / proxy-status issues behind the orange cloud                                                                                        | **cloudflare-troubleshooting**               |
| Windows App / AVD / W365 RDP connection quality: WebSocket instead of UDP Shortpath, high RTT, STUN/TURN interference                                                                                    | **windows-remote-desktop-connection-doctor** |
| Client-side proxy / VPN / TUN misrouting: one specific site fails with `ERR_CONNECTION_CLOSED` or `SSL_ERROR_SYSCALL`, other sites work, DNS returns fake/TUN IPs, and adding a PROXY rule did not help | **this skill** — read [references/case-proxy-tun-cname-override.md](references/case-proxy-tun-cname-override.md) first |
| TLS certificate-verification errors (`UNKNOWN_CERTIFICATE_VERIFICATION_ERROR`, a cert for the wrong site) or mid-handshake EOFs on **every** DIRECT-routed/domestic domain at once, while proxied domains work — and any proxy health watchdog still reports green                                        | **tunnel-doctor** (TUN DIRECT split-brain step) |
| **Nothing errors — it is just slow.** Every request returns 200, latency and health checks look fine, but transfers crawl, bulk jobs overrun their estimates, or files arrive truncated | **this skill** — go straight to [Step 0.7](#step-07-throughput-collapse--when-nothing-errors-and-everything-is-slow); the error-driven steps have nothing to bite on |

If none match — or you tried a domain skill and the evidence points elsewhere — continue below. The methodology generalizes to any multi-layer system.

> **Note for this skill specifically**: If the symptom is a Cloudflare 524/522 on a **large `POST` body** (e.g., `/<openrouter-path>` with `Content-Length` > 1 MB), the failure is often **upload time to origin exceeding Cloudflare's origin read timeout**, not backend slowness. Use the upload-vs-processing checklist below before assuming a backend stall.

## Core principles

### 1. Evidence over assumption

If you cannot point to a concrete artifact — log line, pcap frame, probe output, metric sample — you are guessing, not diagnosing. Before stating "X is the cause", require yourself to name the direct evidence. If it does not exist yet, add instrumentation (see [references/instrumentation-patterns.md](references/instrumentation-patterns.md)) or capture it (see [references/packet-capture-recipes.md](references/packet-capture-recipes.md)) before continuing.

### 2. Falsification over confirmation

N independent sources "confirming" a hypothesis does not make it true. One falsifying observation rules it out. Before acting on a hypothesis, answer:

> "What observation would make me abandon this hypothesis?"

If the answer is "nothing" or "I cannot think of one", the hypothesis is unfalsifiable and must not drive the investigation. If the answer is concrete, go look for that observation before committing to action.

### 3. Layered isolation

Multi-hop systems (client → CDN → LB → reverse proxy → app → upstream) concentrate bugs at the seams between layers. When a symptom could plausibly come from several layers, **do not reason about which layer; test**. The canonical technique: run the same logical request through three or more paths that differ by exactly one hop, then compare where the symptom appears. This resolves in minutes what stacking hypotheses cannot resolve in hours. See [references/layered-isolation-experiment.md](references/layered-isolation-experiment.md).

**The same technique isolates capacity, not just correctness.** When the symptom is a rate rather than an error, vary the *stack* instead of the *hop*: measure the same direction over two channels that share the network path but share no application code. It is the cheapest way to stop tuning an application that was never the bottleneck. Resist compressing the reading into "agreement means the path" — that holds only when both channels are *slow*; two fast channels mean the probe failed to reproduce the symptom and prove nothing at all. See Step 0.7 for how to read each of the four outcomes.

### 4. Counter-review before committing

Before committing to a root cause or shipping a fix, have independent reviewers challenge the conclusion — not confirm it. Agents are good at surfacing risks a single investigator did not think of; they are bad at weighing them. Apply the four-question filter (see [references/counter-review-pattern.md](references/counter-review-pattern.md)) to every finding before it shapes action.

### 5. A green health check certifies only the path it probes

Monitors watch the paths their authors thought to probe. Multi-plane systems — a TUN proxy with a DIRECT plane and a proxied plane, a service with a data plane and a control plane, a stack with a backend API and a web login page — fail one plane at a time, and a watchdog that probes only the other plane stays green through the entire outage. In the incident behind this principle, a proxy health daemon probed one overseas endpoint through the proxy every 5 minutes and logged "healthy" for 2+ hours while the direct plane was completely down.

Before accepting "the monitor says it's healthy" as evidence, ask: **which exact path does that check exercise?** Its green counts as evidence for that path alone. Enumerate the planes the system actually forwards or serves, and probe the failing one directly — the check that would have caught the outage is usually one curl away.

**A check also certifies only the *quantity* it is large enough to measure.** Path coverage is one axis; scale is the other, and it is the one that hides throughput collapse. A liveness probe returns a few hundred bytes, so its timing is dominated by handshake and round-trip — in the case study it answered in 40 ms all day, unchanged, across a 100× swing in the link's actual capacity, and it was not lying: it genuinely did what it measures. Same for `ping`/RTT, which times a small packet's round trip and says nothing about capacity.

The practical rule: **a probe measures the link only once transfer time dominates its total time.** So size it by the answer you need, not by convenience — if a probe returns in well under a second, essentially all of that was setup and you have measured setup. Sidestep the sizing question entirely by budgeting *time* instead of bytes (stream for N seconds, divide what arrived by N), which is what Step 0.7's commands do and why they stay cheap on a link that is already crawling. Extend the question to: **which path, and at what scale?**

## Workflow

Copy this checklist into the investigation notes and check items off:

```
Investigation Progress:
- [ ] Step 0:   Scope the symptom (exact error, exact times, who, who-not, what changed)
- [ ] Step 0.5: Verify the premise — does direct evidence show the symptom is actually happening?
- [ ] Step 0.6: **For large POST bodies: distinguish upload-timeout from processing-timeout** (see recipe below)
- [ ] Step 0.7: **If nothing errors and it is just slow: measure a rate, then two-channel it** (see recipe below)
- [ ] Step 1:   Gather direct evidence at every hop before hypothesizing
- [ ] Step 2:   Frame ≥3 hypotheses; for each, name (a) what falsifies it, (b) which layer boundary the intervention would target
- [ ] Step 3:   Design a decisive experiment (for network: layered isolation)
- [ ] Step 4:   Add instrumentation if evidence gaps block direct observation
- [ ] Step 5:   Execute, record actual vs predicted
- [ ] Step 6:   Counter-review before acting
- [ ] Step 7:   Fix + re-run the same experiment to verify
- [ ] Step 8:   Document wrong turns as teaching material
```

### Step 0: Scope

A tight scope is the difference between a 20-minute investigation and a 5-hour one. Before looking at anything, extract:

- **Exact error string** (copy-paste, not paraphrase). `socket closed` is not the same as `ECONNRESET` is not the same as `HTTP/2 RST_STREAM INTERNAL_ERROR (err 2)`.
- **Exact timestamps** (ISO-8601 with timezone, not "yesterday evening")
- **Reproducibility** (every time / intermittent / only specific users)
- **Who is affected, who is not** (differential observations narrow the search)
- **What changed recently** (deploys, config, upstream dependencies, client versions)

Distinguish symptom from diagnosis. "Slow" is not a symptom. "Request took 130.898s then returned HTTP/2 INTERNAL_ERROR" is.

**But do not let that sentence route a real incident into the bin.** It demands quantification, not an error code — and a whole failure family quantifies as a *rate* with no error code anywhere: every request returns 200, nothing resets, and the system is still unusable. "Slow" becomes a symptom the moment you write it as **bytes per second over a stated payload size** ("8.4 MB in 95 s = 0.09 MB/s, HTTP 200 throughout"). Once you have that number, Step 0.7 has a decisive experiment for it. What stays out of scope is the *unmeasured* complaint — "users say it feels slow" — which is Step 0.5's problem, not this one.

### Step 0.5: Verify the premise

Before investing in a full investigation, confirm the reported symptom is actually happening — not just inferred from downstream effects or user frustration. One cheap direct observation beats hours spent investigating a non-problem.

Ask: **"What direct evidence shows this symptom is real?"**

- If the user reports "timeout at 130s": is that from a timestamped log, a browser network panel, or a recollection?
- If the user reports "connection reset": did they see the packet or is it inferred from a retry spike?
- If the user reports "fails for some but not others": has it been reproduced in a controlled test, or is it anecdotal?

Acceptable premises:

- Log line with timestamp and error string
- Browser DevTools Network screenshot showing the failure
- Reproduction command that shows the symptom on demand
- Metrics chart showing the specific error count rising

Not sufficient as premise:

- "Users are saying it feels slow"
- "The alert fired but I did not check what actually failed"
- "Last week someone mentioned..."

If the premise fails verification, the fix is observation — not investigation. Add the missing telemetry, wait for the next occurrence with instrumentation in place, and return when you have real data. Resist the sunk-cost instinct to investigate anyway "since we are already here".

### Step 0.6: Upload-timeout vs processing-timeout for large POST bodies

For CDN-fronted `POST`/`PUT` endpoints with large bodies, the most common misdiagnosis is blaming backend slowness when the real problem is **time-to-upload-body exceeding the CDN/proxy origin timeout**.

Apply this sub-checklist when the symptom is a 524/522/504 on a request with `Content-Length > ~500 KB`:

1. **Locate the edge/reverse-proxy access log** (Caddy, nginx, Envoy, Cloudflare Logpush).
2. **Compare `bytes_read` (or equivalent) to `Content-Length`**:
   - `bytes_read == Content-Length` and `status` is an error → likely backend/processing problem.
   - `bytes_read < Content-Length` and the connection closed around the timeout window → **upload problem**.
3. **Check `duration` / `request_time` semantics**:
   - Caddy `duration` = wall time from first byte read to response end.
   - nginx `$request_time` = same.
   - <upstream-capture-service> / app `request_time` = time backend spent processing after body was fully received.
   - If proxy `duration` ≈ timeout but upstream `request_time` is short or never logged, the body upload is the bottleneck.
4. **Look for `status=0` (Caddy) or `-` (nginx)**:
   - `status=0` means the proxy never wrote an HTTP response, usually because the downstream/client side closed first.
5. **Correlate with upstream logs**:
   - If the request ID / ray ID / trace ID **does not appear** in upstream (<new-api-container>, <upstream-capture-service>, app) logs, the request never finished uploading.

**Example signature of an upload-timeout 524:**

```json
{
  "status": 0,
  "duration": 125.0,
  "bytes_read": 4111422,
  "request": {
    "headers": { "Content-Length": ["6042141"] }
  }
}
```

Interpretation: the proxy kept the connection for 125 s, read 4.1 MB of a 6 MB body, then Cloudflare closed it and returned 524.

**Example signature of a processing-timeout:**

```json
{
  "status": 504,
  "duration": 120.1,
  "bytes_read": 6042141,
  "request": { "headers": { "Content-Length": ["6042141"] } }
}
```

Interpretation: full body uploaded, but backend did not respond before proxy timeout → backend/processing problem.

### Step 0.7: Throughput collapse — when nothing errors and everything is slow

The recipe above (0.6) handles a *timeout* — an error code you can grep for. This one handles the family with **no error at all**: every request succeeds, every health check is green, and the system is unusable because bytes arrive at a fraction of the expected rate. It is the failure mode most likely to be misdiagnosed for hours, because the entire error-driven toolkit has nothing to bite on.

**Why the usual signals go green** — each of these was observed simultaneously with a 100×-degraded link:

| Signal | What it read | Why it is green anyway |
| --- | --- | --- |
| HTTP status | `200` on everything | Slow is not an error; the response completes, just late |
| Round-trip latency | 12 ms | RTT measures a small packet's round trip; it is **not** a capacity measurement |
| Liveness/health endpoint | `0.04 s` | Its response is handshake-sized, so its timing is all RTT and none of it transfer. **A probe that finishes before the link becomes the limiting factor cannot measure the link** — see Principle 5 |
| Transport status field | `active; direct <endpoint>` | Reports the **path type**, not the path's capacity — see trap 16 |

So the first move is to stop reading status and **measure a rate**.

**The decisive experiment: two independent channels, same direction, same time budget.**

This is Principle 3's layered isolation applied to capacity instead of correctness. Pick two channels that reach the same host over the same network path but share **no application code** — the point is that a result they agree on cannot be caused by either one's internals.

Both commands below are **time-budgeted, not size-budgeted**: they stream for a fixed number of seconds and report whatever arrived. That keeps the probe's cost constant no matter how bad the link is — a fixed 8 MB payload took under a second on the healthy path in the case study and about 90 seconds on the degraded one, and a degradation deeper than that scales the wait without bound, exactly when you can least afford it. It is also why the two numbers are comparable: same seconds, same direction, both measured **at the receiving end**.

```bash
BUDGET=20

# Channel A — the service under suspicion. Point it at the largest object you can name.
# --max-time aborts mid-transfer; -w still prints, and curl exits 28. That is a
# successful measurement, not a failure — read the rate, ignore the exit code here.
curl -s -o /dev/null --max-time "$BUDGET" \
  -w 'A: %{size_download} B in %{time_total}s = %{speed_download} B/s\n' \
  "http://<host>:<port>/<a-large-object>"

# Channel B — a completely different stack to the same host. `cat /dev/zero` streams
# until cut off, so the byte count is decided by the link, not by the payload size.
B=$(timeout "$BUDGET" ssh <host> 'cat /dev/zero' 2>/dev/null | wc -c)
echo "B: $B B in ${BUDGET}s = $((B / BUDGET)) B/s"
```

> **Do not substitute `dd`'s own summary line for channel B's number.** `dd if=/dev/zero … ` reports how fast it wrote into *its stdout*, which for a piped SSH transfer is absorbed by the pipe and SSH's channel window — it measures the local write, not the wire, and it never sees connection setup. Measured on the case study's healthy path, raw SSH moved 33.6 MB end-to-end at 44 MB/s while `dd` self-reported 54.9 MB/s on the same transfer. A sender-side rate is an upper bound on the wire rate, never a measurement of it. Time the whole invocation from the receiving end, as above.

**Expect the two channels to disagree in absolute terms — that is not a problem.** On the same healthy path, raw SSH measured ~44 MB/s while fetches through the media service measured 11–16 MB/s, because channel A pays for the service's own read and encode work on top of the wire. This is why the decision rule below is about **order of magnitude**, not equality: what you are testing is whether both channels sit in the same band, not whether they print the same number. Two channels that differ by 3× on a healthy link and both collapse to 0.1 MB/s on a degraded one have told you exactly what you needed.

**Before reading the table, confirm both probes actually ran.** This is trap 17 applied to your own recipe, and it is the easiest way to get a confidently wrong answer here: a probe that never transferred anything produces a *low or zero rate*, which the table below reads as "slow" and routes straight to "the path" — a conclusion drawn from a measurement that never happened. Two checks, both cheap:

- **Channel A**: is `size_download` close to the object's real size? A DNS failure (curl exit 6), a refused connection (exit 7), or a 404 error page all return quickly and tiny — which can even read as *fast* and land you in the wrong row from the other direction. Only exit 28 (`--max-time` fired mid-transfer) means "the measurement is good, the object was just bigger than the budget".
- **Channel B**: is `$B` plausibly non-zero? `2>/dev/null` in that command hides SSH's own errors, so a host you cannot authenticate to yields `B=0` silently. Re-run it once without `2>/dev/null` if the number looks wrong.

Read the result as a four-way test — all four outcomes are reachable, and three of them tell you to stop what you were about to do:

| Channel A | Channel B | Conclusion |
| --- | --- | --- |
| slow | slow | **The path.** Two unrelated stacks cannot be slow for unrelated reasons at the same rate. Stop tuning the application — nothing inside it will help. Go to "what changed about the path" below. |
| slow | fast | **The application/service.** The path can clearly move bytes; A cannot. You now have a working control to bisect against. |
| fast | slow | **Neither conclusion yet — your control is the anomaly.** SSH-specific cost (cipher on a weak CPU, a hop that shapes SSH), or B crossed a different path. Do not conclude "the service is fine"; replace B with a third stack and re-run. |
| fast | fast | **The probe did not reproduce the symptom.** Do not declare the incident closed. The real workload differs in some dimension you have not replicated — direction (upload vs download), concurrency, object size, or time of day. Change one of those and re-measure before believing the green result. |

**How close is "the same rate"?** Treat agreement within **~20%** as the same rate for this purpose — the two channels differ in framing, encryption and per-object overhead, so exact equality is not expected and not required. The judgement is order-of-magnitude: two stacks reading 0.09 and 0.11 MB/s agree; 0.1 and 12 MB/s do not. If the gap is between ~20% and ~2×, treat it as unresolved and widen the budget or the object size rather than picking a side.

**Pairing channel B when there is no SSH.** The requirement is only *same host, same direction, no shared application code* — SSH is convenient, not special. Any of these works: a second unrelated service on the host (a metrics endpoint, an object store, a static file server), a container-runtime transfer (`docker cp` from that host), a raw throughput tool if you can run one on both ends (`iperf3 -c`), or the host's own package/artifact mirror. What does **not** count is a second endpoint of the same service — that shares the code you are trying to exonerate, so agreement proves nothing.

**Then find what changed about the path.** Once the path is implicated, the variable is usually topology, not hardware: which route the traffic actually takes today versus yesterday. For mesh VPNs (Tailscale, Nebula, ZeroTier) and split-tunnel proxies, the same logical address can be served by a LAN-direct path, a WAN-direct path, or a relay — with order-of-magnitude different capacity and **no change in the status field or the address you connect to**. Ask the transport to report the path it is actually using (`tailscale ping <host>` prints the endpoint and whether the reply came via a relay).

If no prior known-good measurement exists to compare against — the common case in a first incident — you can still make progress without one, because the question "did this change?" has a cheaper substitute: **measure the same path from somewhere else.** A second client on a different network, or the host measuring *itself* over loopback, brackets the problem without any history. Then record today's number as the baseline you did not have; the second occurrence of this incident is much cheaper than the first, and only if someone writes the number down.

**Finally, audit what the wrong assumption already broke.** A degraded link does not just make things slow — it silently invalidates every timeout you calibrated on the fast path, and those timeouts produce *corrupt artifacts that look like successes*. Before declaring the incident over, re-verify anything transferred during the degraded window; see trap 18 and Step 7.

### Step 1: Gather direct evidence at every hop

Before framing hypotheses, collect:

- Server-side logs at every hop in the request path
- Client-side logs (browser devtools HAR, CLI debug log, SDK traces)
- Metrics over the incident window (RPS, latency, error rate, connection count, CPU/mem)
- Distributed trace if available
- Packet capture if the symptom is at the wire level (see [references/packet-capture-recipes.md](references/packet-capture-recipes.md))

If any of these is missing and relevant, **fill the gap before guessing**. Adding a `TRACE_*` env flag and restarting a container beats an hour of hypothesis-stacking. The instrumentation patterns in [references/instrumentation-patterns.md](references/instrumentation-patterns.md) are low-risk, env-gated, and safe to ship into production permanently.

#### Reading reverse-proxy access logs for upload/processing split

Caddy and nginx logs are the cheapest way to falsify "backend is slow". Focus on three fields:

| Field               | Caddy JSON key                   | nginx var                 | Meaning                                                            |
| ------------------- | -------------------------------- | ------------------------- | ------------------------------------------------------------------ |
| Total wall time     | `duration`                       | `$request_time`           | First byte from client → last byte to client (or connection close) |
| Body bytes received | `bytes_read`                     | `$request_length` (rough) | Bytes the proxy actually read from the client                      |
| Declared body size  | `request.headers.Content-Length` | `$content_length`         | What the client said it would send                                 |
| Response status     | `status`                         | `$status`                 | `0` / `-` means the proxy never wrote a response                   |

**Key patterns:**

- `bytes_read < Content-Length` and `duration ≈ timeout` → upload-timeout.
- `bytes_read == Content-Length` and `status` is 5xx → processing-timeout.
- `status == 0` and `bytes_read < Content-Length` → client/CDN closed before upload finished.

#### Tracing a single request across the stack

For the <project> stack (Cloudflare → Caddy → <provider-gateway-service> → <upstream-capture-service> → <new-api-container>), the canonical trace is:

1. **Cloudflare**: get `Cf-Ray` and timestamp from the client error or Cloudflare Logpush.
2. **Caddy**: `docker logs <gateway-container> | grep <Cf-Ray>` → extract `X-Request-Id` (Caddy `uuid`) and confirm `bytes_read`, `duration`, `status`.
3. **<provider-gateway-service>**: `docker logs <provider-gateway-service>` for `Client request error: aborted` or request/response logs.
4. **<upstream-capture-service>**: `grep <X-Request-Id or timestamp> /data/<upstream-capture-service>/log/access.log` → confirms whether the request reached <new-api-container> and how long upstream processing took.
5. **<new-api-container>**: `docker logs <new-api-container>` for billing/channel errors.

If the request ID never appears in steps 3–5, the failure happened at the edge or during body upload.

#### Aggregating by client IP to spot patterns

A single 524 can be a fluke; a pattern of 524s concentrated on one IP + one path is a smoking gun. Run an aggregation like:

```bash
# Caddy JSON example: count failures by IP and body size for an endpoint
python3 -c "
import sys, json
from collections import Counter, defaultdict
stats = defaultdict(lambda: {'total': 0, 'fail': 0, 'slow': 0, 'max_cl': 0})
for line in sys.stdin:
    d = json.loads(line)
    req = d.get('request', {})
    if req.get('uri', '').startswith('/<openrouter-path>'):
        ip = req.get('headers', {}).get('Cf-Connecting-Ip', [''])[0]
        cl = int(req.get('headers', {}).get('Content-Length', ['0'])[0] or 0)
        dur = d.get('duration', 0)
        status = d.get('status', 0)
        s = stats[ip]
        s['total'] += 1
        s['max_cl'] = max(s['max_cl'], cl)
        if status == 0:
            s['fail'] += 1
        elif status == 200 and dur > 60:
            s['slow'] += 1
for ip, s in sorted(stats.items(), key=lambda x: -x[1]['fail']):
    print(f\"{ip}: total={s['total']} fail={s['fail']} slow={s['slow']} max_cl={s['max_cl']}\")
" < caddy-access-log.jsonl
```

If one IP dominates failures and its `max_cl` is large, investigate upload bandwidth/path before backend.

### Step 2: Hypotheses with falsifiers and threat-model boundaries

List three or more plausible causes. For each, write three sentences:

- **What would confirm it?** (easy and often misleading)
- **What would refute it?** (the falsifier — this is what matters)
- **Which layer boundary would the intervention target?** (the threat-model question — forces you to be precise about where the fix would apply)

The third question prevents a common anti-pattern: proposing a fix that operates on the wrong hop. For example, a "keepalive" fix that writes bytes downstream to the client is useless for an _upstream_ idle timeout — the intervention targets a different boundary than the problem. Naming the boundary up-front surfaces this mismatch before coding starts.

If you cannot state a concrete refuter, the hypothesis is unfalsifiable. Flag it, but do not act on it. If you cannot state which boundary a proposed fix targets, you do not yet understand what the fix actually does.

### Step 3: Decisive experiment

For network-layer problems, the default is **layered isolation**: three paths differing by exactly one hop. Example for a CDN-fronted service:

| Path | Route                                 | Rules out if it passes                 |
| ---- | ------------------------------------- | -------------------------------------- |
| A    | Full path via CDN                     | Nothing — this is the failing baseline |
| B    | `--resolve` to origin IP (bypass CDN) | CDN layer                              |
| C    | Server loopback (bypass CDN + LB)     | CDN + LB                               |

If only A fails, the CDN is the cause. If A and B fail but C passes, the LB is. Compose more variants as needed. See [references/layered-isolation-experiment.md](references/layered-isolation-experiment.md) for a runnable template using a mock idle upstream — the experiment does not need a cooperating production request to trigger, the idle interval can be controlled precisely.

For non-network domains:

- Performance: controlled benchmark with one variable changed
- Correctness bug: failing test case that reproduces
- Intermittent: sampled tracing + wait for recurrence

### Step 4: Instrumentation when needed

If the decisive experiment requires an observation that cannot currently be made, add it — do not skip it. The canonical pattern is env-gated instrumentation that:

- Defaults off (zero runtime cost in steady state)
- Turns on via one environment variable, without code changes
- Writes greppable log tags (`[SSE-CHUNK] ts=... req=... bytes=...`)
- Ships into production permanently — future incidents reuse it

See [references/instrumentation-patterns.md](references/instrumentation-patterns.md) for the exact template used to diagnose the <upstream-provider> 125-second upstream silence in this incident.

### Step 5: Execute and record

Run the experiment once, fully documented: command, environment, inputs, observed outputs, wall-clock timestamps. Compare against the prediction made in Step 2. If actual matches predicted, the hypothesis is calibrated. If not, the hypothesis is wrong — **do not rescue it with ad-hoc auxiliary hypotheses** ("oh, but maybe X also interferes..."). Return to Step 2 and write new hypotheses from scratch.

### Step 6: Counter-review

Before committing to a root cause or shipping a fix, spawn independent reviewers to challenge the conclusion. Give them the same evidence, ask them to falsify, not confirm. Apply the four-question filter to each finding they raise:

1. **Probability** — will this actually happen?
2. **Cost** — what is the cost of fixing versus ignoring?
3. **Realistic scenario** — does this apply to the user's actual business case?
4. **Verification** — can I cheaply confirm or refute this?

Classify every finding: real issue / partly right / unlikely / actively harmful. Never paste raw agent output to the user; filter first. See [references/counter-review-pattern.md](references/counter-review-pattern.md).

### Step 7: Fix and verify

Apply the fix. Rerun the same decisive experiment from Step 3. Confirm the symptom no longer reproduces with the same setup that was reliably producing it. If the pre-fix state can no longer be reproduced after the fix, the fix cannot be proven — figure out why the repro was lost before declaring victory.

### Step 8: Document wrong turns

The wrong turns in the investigation are more valuable than the right answer. Write an incident report capturing:

- Symptom + direct evidence
- Each hypothesis tried + how it was falsified
- Decisive experiment design + result
- Fix + verification
- New monitoring or instrumentation added

Future investigators — including future self — will read this to avoid the same cognitive traps.

## Common cognitive traps

1. **Circumstantial evidence convergence.** Five indirect clues all pointing the same direction feel like proof. They are not. If a direct probe is cheap, run it.
2. **Field-semantic confusion.** `duration=5.95s` can mean total wall time (one tool), handler execution phase (another tool), or TTFB (a third). Never cite a numeric field without verifying its semantics against documentation or code.
3. **Single-cause bias.** Multi-layer systems fail from multi-layer defect compositions. Fix the direct cause but document the amplifying factors so the next layer of defense can also be hardened.
4. **Naming assumption.** A resource labeled `spot-instance` may not actually be a spot instance. Verify attributes via API, not metadata names.
5. **Probe self-verification.** A diagnostic that runs through the broken connection to test the broken connection yields uninterpretable results. Always cross-verify with an independent probe.
6. **Assumption-rescue cycle.** When evidence contradicts a hypothesis, the temptation is to add a modifier ("yes, but only in case X"). Resist. If the first falsifier fires, scrap the hypothesis.
7. **Unverified premise.** Investigating a symptom that was never directly observed — inferred from user frustration, alert titles, or downstream effects. Verify first (Step 0.5). Do not investigate anecdotes.
8. **Threat-model mismatch.** Proposing a fix that targets the wrong layer — writing bytes downstream to solve an upstream problem, tuning a timeout on a hop that never fires it. Naming the boundary each hypothesis targets (Step 2) surfaces this.
9. **Reverse-path / directional asymmetry.** A→B healthy ≠ B→A healthy. An external probe to a node proves only that node's return/inbound direction; network paths and congestion are directional. Measure the same direction the user's traffic flows, from the user's side (TCP-mode `mtr`/`nexttrace` from the affected origin), before declaring a hop healthy.
10. **Edge timeouts masquerading as upstream client aborts.** A 524 from Cloudflare can cause the origin proxy (Caddy/nginx) to log the upstream connection as a "client abort" (`status=0`, `Client request error: aborted`). The abort is real at the origin, but the _cause_ is the CDN edge timing out first. Always correlate edge error codes, edge timestamps, and origin logs before attributing an abort to the client. See the upload-vs-processing recipe in Step 0.6.
11. **Assuming a top-of-list proxy rule beats CNAME matching.** Proxy clients that resolve CNAMEs may apply rules to the resolved CNAME chain, not just the original hostname. A `DOMAIN-SUFFIX,<cname-suffix>,DIRECT` rule can override an explicit `DOMAIN,<target>,PROXY` rule. Verify by inspecting the config and by testing hostname vs IP paths through the proxy.
12. **Proxy-node DNS = client DNS.** The proxy node may resolve a hostname differently than the client. A client-side DoH query can return a working IP while the proxy node returns a blocked or non-routable IP. Test with `curl -x proxy -H 'Host: host' -I https://<working-ip>` to separate DNS from reachability.
13. **Fingerprint ≠ identity.** A service banner, a port signature, or a MAC OUI is a mimicry-prone hint, not proof of what a device is. A port-5000 responder with a `Server: AirTunes/…` header and no `_raop` mDNS broadcast "looked like" a DIY Linux AirPlay receiver (shairport-sync) — it was a macOS AirPlay Receiver (ControlCenter listens on 5000/7000), and the modern `OpenSSH_10.x` banner was the tell. In the same incident, a Realtek OUI MAC suggested "same vendor family as the NAS" but actually came from a USB-Ethernet dongle attached to a Mac. Before concluding what a device IS, check self-identity evidence: SSH host key against `~/.ssh/known_hosts` (decisive — one host, one key), mDNS hostname resolution, AirPlay `/info` plist (self-reported name/model/osBuildVersion). Treat banners and OUIs as hypotheses to falsify, never as the conclusion.
14. **Unreachable on one segment ≠ dead.** A probe certifies only the L2 domain it ran on. After a router swap, the old router answered no ARP on Ethernet — "dead" — while its Wi-Fi AP kept broadcasting and serving DHCP, so devices with stored credentials silently joined a network with no WAN. Verify absence from the target's own vantage point (its other interfaces, e.g. `ipconfig getifaddr en1` on the device itself) before declaring it gone; and after any topology change, physically power off retired gear — a "dead" router that still serves DHCP is a trap that keeps collecting devices.
15. **Topology changes orphan manual-IP devices.** DHCP clients follow the new network automatically; manual/static-IP devices keep their old gateway and DNS and become silent islands — reachable from nothing, able to reach nothing. macOS makes this sneakier with "Manually Using DHCP Router Configuration" (manual IP + router learned from old DHCP): the address looks deliberate while the gateway is stale. After any router/subnet change, sweep before declaring the migration done: ARP entries on the old subnet, mDNS names resolving to old-subnet addresses, and every known static-IP box (servers, NAS, printers) re-verified for gateway and DNS.

16. **Reading a path-*type* field as a path-*capacity* field.** Mesh-VPN and proxy status lines report how a peer is reached — `direct` vs `relay`, and the endpoint address. That answers "is it hole-punched?", never "how fast is it?" The two come apart hard: in the incident behind this trap the status line read `active; direct <endpoint>` in **both** a 0.09–0.11 MB/s state and an 11–16 MB/s state — same field, same word, two orders of magnitude apart — because the slow one was a direct path across the WAN and the fast one was a direct path across the LAN. RTT was no better a predictor: the *slower* state had the *lower*-looking 12 ms, the faster one 4 ms. Both are real measurements of something; neither measures capacity. Measure the rate (Step 0.7) and treat the status field as topology trivia.

17. **Blaming the far host for what your own probe did.** Before concluding "the server is slow", confirm the request you sent is the request you meant to send. A malformed identifier often takes a *slower* path than a valid one — a lookup miss triggers a full scan, then returns an error — so a broken probe manufactures exactly the "the other end is struggling" signature you are looking for. Real instance: a Windows-style object key (`…\archive\…`) was interpolated through a shell that ate `\a` as a BEL byte; the corrupted key missed every index, the service scanned for ~21 seconds, and returned a 17-byte `404`. Read as "21 seconds to return nothing — the host is overloaded", it nearly redirected the whole investigation. The tell is the payload size: **21 seconds to deliver 17 bytes is not a bandwidth symptom**, it is a server-side scan, and a scan for something that does not exist is usually your key, not their disk. Rebuild the probe without the shell in the path (a script with an argument vector) and re-measure before attributing anything.

18. **A wrong capacity assumption silently corrupts artifacts and passes the success check.** Degraded throughput does not stay contained as "slow" — it invalidates every timeout calibrated on the healthy path, and a transfer killed by *your own* timeout leaves a truncated file behind, not an error. Whether you notice depends entirely on what your success check measures — and a *plausible-looking* size floor does not save you. In the incident behind this trap the fetch loop checked `HTTP 200 && bytes > 1000`, which sounds like a real integrity check, and it passed **all 35** downloads while 14 of them were truncated. A 180-second cap that was generous at the healthy rate was impossible at the degraded one; the killed transfers still carried a `200`, because the status line arrives long before the body stops, and they still cleared 1000 bytes, because a truncated multi-megabyte file is enormous compared to any threshold you would think to write. **No byte floor can distinguish "complete" from "most of it"** — that is a property of the file's format, not of its size. Two durable fixes: **check the exit status of the transfer, not just the response status** (an HTTP 200 describes the response's beginning; only the exit code describes its end), and **verify the artifact by its own format** — a container with a terminator (`%%EOF`, `IEND`, a closing frame) can prove its own completeness. That check is also how you audit the blast radius afterwards: files carrying the terminator and files the parser accepted matched exactly, 21 and 21, which turned "some downloads may be bad" into a precise list.

[references/cognitive-traps.md](references/cognitive-traps.md) carries extended write-ups for traps 1–12 (rescue-cycle warnings, field-semantic examples). Traps 13–18 are documented in the case studies they came from rather than there: 13–15 in the LAN/topology material, 16–18 in [references/case-throughput-collapse-no-errors.md](references/case-throughput-collapse-no-errors.md).

## Client-side proxy / VPN / TUN misrouting

When the symptom is **client-specific** (browser on one machine fails, other devices or networks work, or the failure disappears when the proxy/VPN is turned off), the proxy client itself is a network hop. Treat it like one.

Quick differential checklist:

1. **DNS**: What IP does the OS resolve? If it is a fake/TUN IP (e.g. `198.18.x.x`), the proxy client is intercepting DNS.
2. **Route**: `route -n get <ip>` shows which interface the packet leaves. A fake IP routed through `utun5` is normal for TUN mode; a real IP routed only through TUN while the physical interface cannot reach it means local direct is broken.
3. **Proxy port**: Is the local proxy listening? `lsof -P -i TCP:<port>` confirms. Test both with and without it.
4. **Hostname vs IP through proxy**:
   - `curl -x http://127.0.0.1:<port> -I https://<host>`
   - Resolve the host yourself (DoH), then `curl -x http://127.0.0.1:<port> -k -H 'Host: <host>' -I https://<ip>`
   If the second works and the first fails, the proxy node’s DNS is returning a different/bad IP than the client’s DoH query.
5. **Physical interface reachability**: Force the real IP out `en0` (or the active physical interface) temporarily. If it fails while the TUN path works, the local network cannot reach the target; the proxy/TUN is required.
6. **Rule/CNAME interaction**: Inspect the proxy config for rules matching the CNAME suffix of the target. A `DOMAIN-SUFFIX,<cname-suffix>,DIRECT` rule can override an explicit `DOMAIN,<host>,PROXY` rule if the client evaluates rules against resolved CNAMEs.

If all of the above point to a proxy client that resolves a bad CNAME or relies on a bad proxy-node DNS, see the fix pattern in [references/case-proxy-tun-cname-override.md](references/case-proxy-tun-cname-override.md).

## Anti-patterns — things to explicitly avoid

- **Jumping to a fix before a falsifier is found.** "Probably it is X, let me restart / tweak / upgrade." This converts learning opportunities into mystery fixes that do not prevent recurrence.
- **Accepting agent counter-review findings wholesale.** Agents over-produce risk findings. Filter before acting (see four-question filter above).
- **Ad-hoc production edits that bypass IaC.** If the investigation requires changing production, change the source-of-truth first, then apply — otherwise the "fix" evaporates on the next deploy and the drift hides the real state.
- **Declaring root cause from a single observation.** Demand a falsifier attempt first.
- **Writing "should work now" without re-running the failing experiment.** Re-verify.

## Case studies

Four canonical cases illustrate the methodology in different failure modes:

1. [references/case-sse-rst-130s.md](references/case-sse-rst-130s.md) — a 5-hour investigation where the assistant repeatedly jumped to the wrong conclusion. The right answer — Cloudflare edge HTTP/2 stream idle timeout at 126 seconds, amplified by <upstream-provider> not emitting SSE ping during <model-name> tool_use generation — surfaced in 10 minutes once a subagent designed a 3-path layered isolation experiment with a mock idle upstream.

2. [references/case-cloudflare-524-upload.md](references/case-cloudflare-524-upload.md) — a Cloudflare 524 on `<api-domain>/<openrouter-path>` where a ~6 MB POST body took longer to upload from the US client to the <origin-region> origin than Cloudflare's default origin read timeout allowed. The key insight came from comparing `bytes_read` (4.1 MB) to `Content-Length` (6.0 MB) and confirming the request never reached `<upstream-capture-service>` or `<new-api-container>`. This case is the source of the upload-vs-processing recipe and the "edge timeouts masquerading as client aborts" trap above.

3. [references/case-proxy-tun-cname-override.md](references/case-proxy-tun-cname-override.md) — a client-side `<proxy-client>` TUN case where `<auth-domain>` failed with `ERR_CONNECTION_CLOSED` even though explicit PROXY rules were at the top of the config. The root cause was a `DOMAIN-SUFFIX,<cname-suffix>,DIRECT` rule matching the target's CNAME chain, plus the proxy node's own DNS returning a different IP than the client's DoH query. The fix pattern uses `[Host]` mapping and `use-local-host-item-for-proxy`.

4. [references/case-throughput-collapse-no-errors.md](references/case-throughput-collapse-no-errors.md) — the only case here with **no error string at all**: HTTP 200 throughout, 12 ms RTT, health endpoint at 0.04 s, and a link moving 0.09–0.11 MB/s. Three hours went into "the verification pass is slow" → "the host's uplink must be ~1 Mbps" → "it's the relay", all plausible, none verified. Two channels sharing the path but no application code (an HTTP service and plain SSH) agreed within ~20% and settled it in one command: the path, not the service. Source of Step 0.7 and traps 16–18, including how a 180 s timeout derived from the wrong rate truncated 14 of 35 downloads that all passed a `200 && bytes > 1000` check.

Read these before applying this skill to an unfamiliar problem domain; the wrong-turn anatomy is the teaching.

## Reference files

- [references/layered-isolation-experiment.md](references/layered-isolation-experiment.md) — 3-path technique, mock upstream template, result matrix
- [references/instrumentation-patterns.md](references/instrumentation-patterns.md) — env-gated TRACE\_\*, greppable log tags, deployment checklist
- [references/packet-capture-recipes.md](references/packet-capture-recipes.md) — tcpdump filters for RST isolation, interface selection on Docker, HTTP/2 decoding
- [references/counter-review-pattern.md](references/counter-review-pattern.md) — 4-agent team composition, 4-question filter, integration workflow
- [references/cognitive-traps.md](references/cognitive-traps.md) — extended examples, rescue-cycle warnings
- [references/case-sse-rst-130s.md](references/case-sse-rst-130s.md) — canonical case study with wrong-turn timeline
- [references/case-cloudflare-524-upload.md](references/case-cloudflare-524-upload.md) — upload-timeout vs processing-timeout recipe
- [references/case-proxy-tun-cname-override.md](references/case-proxy-tun-cname-override.md) — client-side proxy/TUN CNAME rule override and fix pattern
- [references/case-throughput-collapse-no-errors.md](references/case-throughput-collapse-no-errors.md) — degraded throughput with every signal green; two-channel capacity isolation; the truncated-artifact aftermath

## Scripts

- [scripts/mock-idle-upstream.py](scripts/mock-idle-upstream.py) — SSE server that emits one frame then idles N seconds. Use as the upstream in layered isolation experiments to precisely control the idle interval.
- [scripts/layered-isolation-probe.sh](scripts/layered-isolation-probe.sh) — Runs the 3-path A/B/C comparison and prints a diagnostic matrix.
