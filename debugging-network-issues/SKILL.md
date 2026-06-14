---
name: debugging-network-issues
description: >-
  Evidence-driven investigation for network, streaming, and protocol-layer bugs where symptoms don't match the obvious cause. Use when debugging connection resets (ECONNRESET, HTTP/2 RST_STREAM, INTERNAL_ERROR), SSE or long-polling stalls, fixed-time connection drops, CDN/proxy/CGNAT idle timeouts, client-side proxy/VPN/TUN misrouting, CNAME-based proxy rule overrides, or symptoms like "socket closed unexpectedly", "stream interrupted", "fails after N seconds", "works sometimes but not always", "upstream silent for X seconds", ERR_CONNECTION_CLOSED, SSL_ERROR_SYSCALL. Applies falsification-first layered isolation to pin down the responsible network layer instead of stacking assumptions.
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

### 4. Counter-review before committing

Before committing to a root cause or shipping a fix, have independent reviewers challenge the conclusion — not confirm it. Agents are good at surfacing risks a single investigator did not think of; they are bad at weighing them. Apply the four-question filter (see [references/counter-review-pattern.md](references/counter-review-pattern.md)) to every finding before it shapes action.

## Workflow

Copy this checklist into the investigation notes and check items off:

```
Investigation Progress:
- [ ] Step 0:   Scope the symptom (exact error, exact times, who, who-not, what changed)
- [ ] Step 0.5: Verify the premise — does direct evidence show the symptom is actually happening?
- [ ] Step 0.6: **For large POST bodies: distinguish upload-timeout from processing-timeout** (see recipe below)
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

See [references/cognitive-traps.md](references/cognitive-traps.md) for extended examples including this case study.

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

Three canonical cases illustrate the methodology in different failure modes:

1. [references/case-sse-rst-130s.md](references/case-sse-rst-130s.md) — a 5-hour investigation where the assistant repeatedly jumped to the wrong conclusion. The right answer — Cloudflare edge HTTP/2 stream idle timeout at 126 seconds, amplified by <upstream-provider> not emitting SSE ping during <model-name> tool_use generation — surfaced in 10 minutes once a subagent designed a 3-path layered isolation experiment with a mock idle upstream.

2. [references/case-cloudflare-524-upload.md](references/case-cloudflare-524-upload.md) — a Cloudflare 524 on `<api-domain>/<openrouter-path>` where a ~6 MB POST body took longer to upload from the US client to the <origin-region> origin than Cloudflare's default origin read timeout allowed. The key insight came from comparing `bytes_read` (4.1 MB) to `Content-Length` (6.0 MB) and confirming the request never reached `<upstream-capture-service>` or `<new-api-container>`. This case is the source of the upload-vs-processing recipe and the "edge timeouts masquerading as client aborts" trap above.

3. [references/case-proxy-tun-cname-override.md](references/case-proxy-tun-cname-override.md) — a client-side `<proxy-client>` TUN case where `<auth-domain>` failed with `ERR_CONNECTION_CLOSED` even though explicit PROXY rules were at the top of the config. The root cause was a `DOMAIN-SUFFIX,<cname-suffix>,DIRECT` rule matching the target's CNAME chain, plus the proxy node's own DNS returning a different IP than the client's DoH query. The fix pattern uses `[Host]` mapping and `use-local-host-item-for-proxy`.

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

## Scripts

- [scripts/mock-idle-upstream.py](scripts/mock-idle-upstream.py) — SSE server that emits one frame then idles N seconds. Use as the upstream in layered isolation experiments to precisely control the idle interval.
- [scripts/layered-isolation-probe.sh](scripts/layered-isolation-probe.sh) — Runs the 3-path A/B/C comparison and prints a diagnostic matrix.
