# Layered Isolation Experiment

## Contents

- Why layered isolation
- The 3-path pattern
- Mock upstream pattern
- Result matrix and interpretation
- Failure modes and probe self-verification
- Intermittent failures: return to the original condition
- Extended variants (4+ paths, client-side variation)
- Canonical reference case (case-study SSE RST)

## Why layered isolation

Multi-hop network systems concentrate bugs at the seams. A request from a user to a backend service typically traverses: client → ISP → CGNAT → CDN/edge → load balancer → reverse proxy → application → upstream dependency. Each hop introduces a timeout policy, a connection pool, a rewrite rule, a header translation, or a flow-control window. When something fails, hypothesis-stacking ("maybe it's the CDN, no maybe the LB, actually probably the app…") tends to burn hours with circumstantial evidence on each candidate.

Layered isolation inverts the approach: run the same logical request through paths with known differences, then localize the symptom to those differences. Name every removed hop before interpreting a comparison. Attribute a single layer only when the actual paths and request conditions isolate it; a direct-origin request can bypass several layers at once.

## The 3-path pattern

For a CDN-fronted service with the topology `Client → CDN → LB → Origin`:

| Path  | How it routes | Difference from the full path |
| ----- | ------------- | ----------------------------- |
| **A** | Client → CDN → LB → Origin | Baseline: reproduce the symptom |
| **B** | Client → Origin directly (e.g., `curl --resolve host:443:origin-ip`) | Bypass both CDN and LB, plus their connecting route |
| **C** | Server loopback (`curl http://127.0.0.1:port/...` on the origin host itself) | Also remove the external client-to-origin route; name any local proxy still traversed |

Interpretation:

- If **A fails, B passes, C passes**: localize the difference to the CDN/LB path removed by B; this comparison alone does not distinguish CDN from LB
- If **A fails, B fails, C passes**: investigate the external client-to-origin route or external listener omitted by C; the bypassed LB alone cannot explain B failing
- If **A fails, B fails, C fails**: investigate the shared application/upstream stack and the probe itself; matching failure labels alone do not prove a common cause
- If **all three pass**: the failure condition was not actually reproduced; re-examine the assumed trigger

To distinguish CDN from LB, add `Client → LB → Origin` while preserving hostname, TLS/SNI, request body, protocol and origin configuration. Confirm that the target really is the LB address, rather than assume `--resolve` preserves it. Differences in network route remain possible confounders; use endpoint logs or packet evidence to narrow them. Changing client geography is a separate comparison for ISP/CGNAT hypotheses.

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

- **Controlled timing**: 200-second idle is a knob; a real <model-name> request has variable thinking duration
- **Cheap**: no model inference cost
- **Reproducible**: deterministic bytes, deterministic timing
- **Isolated from app bugs**: rules out "maybe the app itself has a bug"
- **Safe**: does not consume user quota or affect real traffic

Deploy the mock on a port the reverse proxy can reach, add a temporary route in the proxy config pointing a test hostname/path to it, and run the 3 paths against that hostname.

## Result matrix and interpretation

After running the experiment, tabulate:

```
              | Path A (via CDN + LB) | Path B (direct origin) | Path C (loopback) |
--------------|------------------|---------------------|-------------------|
Result        | RST @ 126s       | Clean @ 220s        | Clean @ 220s      |
Observed by   | curl + server    | curl + server       | curl + server     |
```

Always record observations from both ends (curl-side time_total AND server-side peer-close timestamp). Discrepancies between the two are themselves diagnostic: if curl reports a close at 69s but the server saw the connection alive for 126s, the close happened in a middlebox between them.

The observed constant in the failing path (here: 126s) is usually close to a known layer's default idle policy. Cross-reference against:

| Layer                                          | Common idle default           |
| ---------------------------------------------- | ----------------------------- |
| Cloudflare Free/Pro proxy_read_timeout         | 100s (but see caveat below)   |
| Cloudflare HTTP/2 stream idle                  | empirically ~126s in our case |
| AWS ALB idle                                   | 60s default, configurable     |
| Nginx `proxy_read_timeout`                     | 60s default, configurable     |
| Node http server `headersTimeout`              | 60s (Node ≥ 18)               |
| Node undici `bodyTimeout`                      | 300s default                  |
| CGNAT TCP initial timeout (Cisco ISM)          | 120s typical                  |
| Linux kernel TCP `net.ipv4.tcp_keepalive_time` | 7200s (rarely relevant)       |

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

## Intermittent failures: return to the original condition

When A fails and a changed condition B succeeds, return once to the original A within a declared time/attempt budget before attributing the recovery to B. The investigator records the actual route, input, options, timestamps and result for each attempt; this causal judgment is manual, not enforced by the probe script. Keep all other controllable conditions fixed and record any that changed or remain unknown.

- **A fails → B succeeds → A succeeds:** the original failure no longer reproduces. Report causation unestablished; do not remove the toggled feature or declare it exonerated on these observations alone.
- **A fails → B succeeds → A fails:** the contrast recurs under these conditions. Use it to choose the next isolating probe, together with endpoint evidence; three attempts are not statistical proof or a guarantee against time-dependent confounding.
- **Original A cannot be restored safely or the budget expires:** stop the experiment and retain the causal uncertainty. Do not keep retrying until a preferred answer appears.

For example, a request failing with a plugin, succeeding without it, then succeeding with it again does not establish that the plugin caused the failure. Preserve the feature while investigating any remaining symptom. A successful transfer can still satisfy its file-integrity acceptance criterion even when the earlier timeout's cause remains unknown.

## Extended variants

### 4-path with client-side variation

```
A: client via CDN via LB
B: different client (mobile hotspot) via CDN via LB   # ISP/CGNAT differential
C: same client --resolve to verified LB IP (retain LB, bypass CDN)
D: server loopback
```

Use when Path A fails and you suspect client-side network (ISP/VPN/NAT) is the cause.

### Time-of-day variant

For symptoms correlated with time (load, scheduled jobs), run the same matrix at a known-good window and a known-failing window. Compare.

### Observability variant

For each path, record at minimum: HTTP status code, total elapsed time, bytes received, close reason (if available from curl or tcpdump). Paths that all return "success" but with vastly different byte counts hint at partial-response truncation rather than a clean failure/success dichotomy.

## Canonical reference case

The 130s RST incident (documented in [case-sse-rst-130s.md](case-sse-rst-130s.md)) ran exactly this 3-path matrix after 5 hours of hypothesis-stacking failed to converge. The result:

| Path                        | Result                                        |
| --------------------------- | --------------------------------------------- |
| A: via Cloudflare           | RST @ 126.01-126.02s, HTTP/2 INTERNAL_ERROR   |
| B: `--resolve` to origin IP | Clean @ 220s (bounded by client `--max-time`) |
| C: server loopback          | Clean @ 220s                                  |

In that case's documented `Client → Cloudflare → Caddy → application` topology, the direct-origin request retained Caddy and the application, repeated results agreed, and the peer-sent HTTP/2 reset supplied additional evidence for the edge diagnosis. Do not transfer that conclusion to the CDN-plus-LB topology above: its direct-origin path removes an additional layer.

The lesson: **when multiple layers could be the cause, do not reason about which one — test**.
