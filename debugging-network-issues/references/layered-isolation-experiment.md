# Layered Isolation Experiment

## Contents
- Why layered isolation
- The 3-path pattern
- Mock upstream pattern
- Result matrix and interpretation
- Failure modes and probe self-verification
- Extended variants (4+ paths, client-side variation)
- Canonical reference case (case-study SSE RST)

## Why layered isolation

Multi-hop network systems concentrate bugs at the seams. A request from a user to a backend service typically traverses: client → ISP → CGNAT → CDN/edge → load balancer → reverse proxy → application → upstream dependency. Each hop introduces a timeout policy, a connection pool, a rewrite rule, a header translation, or a flow-control window. When something fails, hypothesis-stacking ("maybe it's the CDN, no maybe the LB, actually probably the app…") tends to burn hours with circumstantial evidence on each candidate.

Layered isolation inverts the approach: instead of reasoning about which hop caused the symptom, run the same logical request through several paths that differ by exactly one hop, then observe where the symptom appears. The differential directly names the responsible layer.

## The 3-path pattern

For a CDN-fronted service with the topology `Client → CDN → LB → Origin`:

| Path | How it routes | Excludes if clean |
|------|--------------|-------------------|
| **A** | Client → CDN → LB → Origin (full production path) | (baseline — this reproduces the symptom) |
| **B** | Client → Origin directly (e.g., `curl --resolve host:443:origin-ip`) | The CDN layer |
| **C** | Server loopback (`curl http://127.0.0.1:port/...` on the origin host itself) | CDN + LB + any intermediate network |

Interpretation:

- If **A fails, B passes, C passes**: the CDN is the cause
- If **A fails, B fails, C passes**: the LB / origin external network path is the cause
- If **A fails, B fails, C fails**: the cause is in the application or upstream dependency (hypothesis-stacking was wrong from the start)
- If **all three pass**: the failure condition was not actually reproduced; re-examine the assumed trigger

Add a fourth path as needed — e.g., bypass only the LB by hitting the origin VM's private IP from within the VPC, or test from a different client geography if ISP/CGNAT is suspect.

## Mock upstream pattern

The experiment needs a way to reliably and repeatably trigger the failure condition. For idle-timeout symptoms (the most common class addressed by this skill), the cleanest trigger is a **mock upstream that emits one response header + one data frame, then goes silent for a controlled duration**.

See [scripts/mock-idle-upstream.py](../scripts/mock-idle-upstream.py) for a runnable Flask implementation. The essence:

```python
def gen():
    yield b'event: message_start\ndata: {"type":"message_start"}\n\n'
    time.sleep(IDLE_SECONDS)  # configurable, e.g. 200
    yield b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
```

Why this is better than using a real long-tail production request to trigger the failure:

- **Controlled timing**: 200-second idle is a knob; a real Sonnet 4.6 request has variable thinking duration
- **Cheap**: no model inference cost
- **Reproducible**: deterministic bytes, deterministic timing
- **Isolated from app bugs**: rules out "maybe the app itself has a bug"
- **Safe**: does not consume user quota or affect real traffic

Deploy the mock on a port the reverse proxy can reach, add a temporary route in the proxy config pointing a test hostname/path to it, and run the 3 paths against that hostname.

## Result matrix and interpretation

After running the experiment, tabulate:

```
              | Path A (via CDN) | Path B (bypass CDN) | Path C (loopback) |
--------------|------------------|---------------------|-------------------|
Result        | RST @ 126s       | Clean @ 220s        | Clean @ 220s      |
Observed by   | curl + server    | curl + server       | curl + server     |
```

Always record observations from both ends (curl-side time_total AND server-side peer-close timestamp). Discrepancies between the two are themselves diagnostic: if curl reports a close at 69s but the server saw the connection alive for 126s, the close happened in a middlebox between them.

The observed constant in the failing path (here: 126s) is usually close to a known layer's default idle policy. Cross-reference against:

| Layer | Common idle default |
|-------|---------------------|
| Cloudflare Free/Pro proxy_read_timeout | 100s (but see caveat below) |
| Cloudflare HTTP/2 stream idle | empirically ~126s in our case |
| AWS ALB idle | 60s default, configurable |
| Nginx `proxy_read_timeout` | 60s default, configurable |
| Node http server `headersTimeout` | 60s (Node ≥ 18) |
| Node undici `bodyTimeout` | 300s default |
| CGNAT TCP initial timeout (Cisco ISM) | 120s typical |
| Linux kernel TCP `net.ipv4.tcp_keepalive_time` | 7200s (rarely relevant) |

**Do not** treat this table as authoritative for your environment. These are starting points to cross-check against your measured constant. Confirm via vendor documentation or direct testing before citing as cause.

## Failure modes and probe self-verification

The experiment is only as valid as its isolation. Common ways to poison the result:

### Local proxy contamination

If the client has a system-level HTTP proxy (Shadowrocket, corporate proxy, VPN client), `curl` will silently route through it even when `--resolve` is set. Path B (intended to bypass CDN) gets routed through the same proxy and the isolation fails.

**Mitigation**: use `env -i curl` to strip the environment before running the probe, and explicitly unset `http_proxy / https_proxy / HTTP_PROXY / HTTPS_PROXY / ALL_PROXY / NO_PROXY`. Verify the path with `curl -v` and check the `* Trying IP:port` line matches the expected target.

Real example from this case study: run 1 Path B appeared to fail at 126s, which would have falsely implicated the origin. It turned out the client's Shadowrocket was proxying localhost-targeted requests back through Cloudflare. `env -i curl --resolve ...` reproduced the clean 220s that correctly exonerated the origin.

### Probe self-verification

If the probe depends on the infrastructure being tested, its output is not independent evidence. Example: running `mtr` through the CDN to test CDN behavior — if the CDN drops ICMP, mtr shows gaps that look like the symptom but are artifacts. Always compare against at least one structurally different probe (e.g., curl + server-side tcpdump alongside mtr).

### Container network namespace differences

When the target runs in Docker, Path C (loopback) behavior differs depending on whether you run `curl` from the host or from inside the container. Host `curl localhost:3002` may hit a port-mapped container, while container-internal `curl localhost:3002` hits the service directly. They are different isolation paths — pick based on which hops you are trying to include/exclude and be explicit about which one you ran.

## Extended variants

### 4-path with client-side variation

```
A: client via CDN via LB
B: different client (mobile hotspot) via CDN via LB   # ISP/CGNAT differential
C: client --resolve to origin IP (bypass CDN only)
D: server loopback
```

Use when Path A fails and you suspect client-side network (ISP/VPN/NAT) is the cause.

### Time-of-day variant

For symptoms correlated with time (load, scheduled jobs), run the same matrix at a known-good window and a known-failing window. Compare.

### Observability variant

For each path, record at minimum: HTTP status code, total elapsed time, bytes received, close reason (if available from curl or tcpdump). Paths that all return "success" but with vastly different byte counts hint at partial-response truncation rather than a clean failure/success dichotomy.

## Canonical reference case

The 130s RST incident (documented in [case-sse-rst-130s.md](case-sse-rst-130s.md)) ran exactly this 3-path matrix after 5 hours of hypothesis-stacking failed to converge. The result:

| Path | Result |
|------|--------|
| A: via Cloudflare | RST @ 126.01-126.02s, HTTP/2 INTERNAL_ERROR |
| B: `--resolve` to origin IP | Clean @ 220s (bounded by client `--max-time`) |
| C: server loopback | Clean @ 220s |

Interpretation was immediate: the RST comes from Cloudflare's edge, not the origin or any network in between. What 5 hours of circumstantial reasoning could not resolve (Caddy? Qiniu? VPN? CGNAT? CLI bug?), the 3-path experiment resolved in the 10 minutes it took to set up.

The lesson: **when multiple layers could be the cause, do not reason about which one — test**.
