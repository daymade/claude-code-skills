# Case Study: SSE HTTP/2 RST at 130s (130s RST incident, April 2026)

A production incident where a user's Claude CLI kept failing with `ECONNRESET` after exactly 130 seconds on long tool_use tasks. The investigation took 5 hours and produced three wrong root-cause conclusions before a structured experiment resolved it in 10 minutes.

This case study is the canonical teaching material for this skill. Read it to understand the anatomy of how assumption-first investigations go wrong, and how to recognize when to switch to evidence-first.

## Contents
- Symptom
- Environment
- Investigation timeline (with wrong turns)
- The decisive experiment
- Final root cause
- Post-mortem lessons

## Symptom

The reporting user (handle: User A), using Claude CLI 2.1.116 on Windows (Node v24.3.0), submits long tasks via `ANTHROPIC_BASE_URL=https://api.example.com/openrouter`. Tasks involving Claude Sonnet 4.6 + long tool_use (writing long files with the Write tool) consistently fail with:

```
API Error: The socket connection was closed unexpectedly.
For more information, pass `verbose: true` in the second argument to fetch()
```

In CLI debug logs:

```
2026-04-22T13:43:38.261Z [DEBUG] [API REQUEST] /openrouter/v1/messages
2026-04-22T13:43:47.728Z [DEBUG] Stream started - received first chunk
2026-04-22T13:45:57.344Z [ERROR] Error in API request: The socket connection was closed unexpectedly.
2026-04-22T13:45:57.347Z [ERROR] Connection error details: code=ECONNRESET
```

From first chunk (`t=9s`) to ECONNRESET (`t=130s`): exactly 130 seconds. Reproducible across sessions.

## Environment

- Client: Claude CLI 2.1.116, Windows 11, Node v24.3.0
- Server: api.example.com (Cloudflare-proxied, origin is aliyun Japan, 203.0.113.10)
- Architecture: `CLI → CF → Caddy → lobe-provider-gateway → lobe-new-api → Qiniu (Anthropic proxy) → Sonnet 4.6`
- Not affected: same user's Haiku requests, other users' Sonnet 4.6 requests with shorter duration (all <45s)

## Investigation timeline (with wrong turns)

### Hour 1: VPN theory (wrong)

Observation: `Cf-Connecting-Ip` varied between China (198.51.100.42) and US (203.0.113.x) across requests, sometimes in the same session.

Hypothesis: User's VPN is unstable, rotating exit nodes, TCP dies when the route changes.

Evidence gathered: IP log showed the flipping. CF Ray always terminated at SJC (US).

Action taken: recommend user disable VPN and retry.

Falsification: User responds "disabled VPN, still fails at 130s." The requests with China-origin IP also fail.

**Trap**: Circumstantial evidence convergence (Trap 1). The IP flipping was real but the VPN was not the cause.

### Hour 2: CLI version bug theory (wrong)

Observation: Failing requests' response bodies archived to OSS all terminate at suspiciously similar byte positions (3538 / 3902 / 3946 bytes). In each case, the response truncates mid-way through a `tool_use` `input_json_delta` containing a path string with Chinese characters (`D:\翩姐\AI剪辑\培训...`).

Hypothesis: Claude CLI 2.1.116 has a bug parsing `input_json_delta` containing Chinese + Windows backslashes. Client closes the socket when it fails to parse.

Evidence gathered: Three failures, all at ~3.5-3.9 KB, all at similar character positions. Strong pattern.

Action tentative: recommend CLI upgrade to 2.1.117.

Falsification: User's CLI debug log shows the close happens **130 seconds after first chunk**, not at the instant the byte is received. If it were a parse bug, the close would be within milliseconds of the problematic byte. Additionally, CLI 2.1.2 (older) worked fine on similar content.

**Trap**: Field-semantic confusion (Trap 2). A misread of Caddy's `duration=5.95s` field led to believing the close was fast (5s), which made the parse-bug theory plausible. When CLI debug logs were examined, the actual timing was 130s, contradicting the hypothesis.

### Hour 3: Caddy IdleConnTimeout theory (wrong)

After a subagent suggested examining Caddy reverse_proxy defaults, a hypothesis formed: Caddy's HTTP/1.1 transport `IdleConnTimeout` defaults to 120s; combined with TTFB that explains the 130s.

Evidence: Caddy source code shows `IdleConnTimeout = 120s` default. 120 + 10s TTFB = 130s close match.

Action tentative: add explicit `keepalive_timeout 30m` to Caddy config.

Falsification: A probe from the server itself, `curl --resolve api.example.com:443:127.0.0.1 https://api.example.com/openrouter/v1/messages ...`, runs for 200+ seconds without closing. This path goes through Caddy (just not through CF). If Caddy's IdleConnTimeout were the cause, this probe would also fail at 130s. It does not.

**Trap**: Assumption-rescue cycle (Trap 6) was tempting — "maybe Caddy only triggers IdleConnTimeout under specific conditions" — but the direct probe was decisive. Abandoned the hypothesis cleanly.

### Hour 4: Qiniu no-ping theory (partial)

Observation: Scanning 38 archived response bodies shows all of them contain zero `event: ping` frames and zero SSE comment-only frames (`:` prefix lines). Anthropic protocol specifies periodic `ping` events during long inactivity. Qiniu appears to strip or not forward them.

Hypothesis: Qiniu does not forward SSE ping → connection looks idle to the CDN → CDN closes at its idle threshold.

Evidence: 38 bodies, ping count = 0, consistent.

Action tentative: deploy server-side keepalive in provider-gateway to compensate.

Partial refutation (from counter-review agent): Anthropic's own official API has been reported (GitHub issues `claude-code#18028`, `claude-agent-sdk-typescript#44`) to stall 59-138+ seconds with no event during tool_use generation. So Qiniu's no-ping behavior, while real, is not sufficient as an independent root cause — the upstream itself is silent, Qiniu has nothing to forward.

This hypothesis is partly correct — Qiniu does not emit ping — but it is not the direct cause of the close. It is an amplifying factor (absence of keepalive that would have prevented the idle timeout somewhere).

**Progress**: we now know "something on the wire is quiet for ~125 seconds during tool_use generation" but we still do not know which layer is closing the connection.

### Hour 5: The decisive experiment

Subagent designed and executed a 3-path layered isolation experiment:

1. **Mock upstream**: Python/Flask on port 19999 that emits one SSE frame then sleeps 200 seconds — precisely simulating the observed upstream silence pattern.

2. **Temporary routing**: Added CF DNS record for `test-idle.example.com` pointing at origin (proxied: true), plus a Caddy conf snippet forwarding that hostname to the mock.

3. **Three paths**, run in parallel:
   - **Path A** (via CF): `curl https://test-idle.example.com/...`
   - **Path B** (bypass CF): `env -i curl --resolve test-idle.example.com:443:203.0.113.10 ...`
   - **Path C** (server loopback): `ssh server 'curl http://127.0.0.1:19999/probe-c'`

Results (multiple runs, consistent):

| Path | Close time | Curl error |
|------|------------|-----------|
| A (via CF) | 126.01s | HTTP/2 stream 1 was not closed cleanly: INTERNAL_ERROR (err 2) |
| B (bypass CF) | 220s (clean, hit client --max-time) | none (curl side closed on --max-time) |
| C (loopback) | 220s (clean, hit client --max-time) | none |

**Interpretation**: Only Path A closes early. B and C traverse the same Caddy/origin/upstream stack but bypass CF. Therefore the close originates at Cloudflare's edge, not at any layer below it.

Additionally, curl's error `HTTP/2 stream N was not closed cleanly: INTERNAL_ERROR (err 2)` indicates the reset was a peer-sent `RST_STREAM` HTTP/2 frame, not a TCP RST. Confirmation that CF sent an HTTP/2-layer close while the TCP connection itself remained healthy for other streams.

### One subtle wrinkle from the experiment

The first run of Path B appeared to close at 126s too, which would have falsely implicated the origin. Investigation revealed the client machine had a system-level Shadowrocket proxy on `http_proxy=http://127.0.0.1:1082` that was silently routing the `--resolve`-bypassed traffic back through CF. `env -i curl` (strip all environment) then correctly showed Path B clean at 220s.

This is **Trap 5** (probe self-verification) caught in real time. Mitigation: `env -i curl ...` is now a mandatory reflex when running bypass-comparison experiments.

## Final root cause

**Direct cause**: Cloudflare edge closes HTTP/2 streams that go idle for ~126 seconds (empirically observed constant, matches the 120-130s close-time range on Path A across runs).

**Amplifying factors**:

1. Qiniu proxy does not emit SSE `event: ping` during upstream silence (38/38 observed bodies had zero ping)
2. Upstream Claude Sonnet 4.6 during tool_use generation emits initial output then batch-generates the tool_use.input for 100+ seconds with no interim chunks
3. Claude CLI does not implement a client-side idle watchdog to detect the stall before the peer resets

Any one of these, in isolation, would likely not produce the observed failure. All three together + the CF idle timeout produce it reliably for Sonnet 4.6 + long tool_use requests from this account.

## Remediation

Not shipped as part of this case study, but the intended fix vector:

- **Server-side SSE keepalive in provider-gateway**: if the upstream has not emitted for N seconds, inject `: keepalive\n\n` comment frames (SSE-safe, ignored by clients, but keeps bytes flowing on the wire). This prevents CF from observing a full N-second idle.
- **Does not require client or upstream changes**. Single point of defense for all client/upstream combinations.

Code reviewer counter-review (see [counter-review-pattern.md](counter-review-pattern.md)) caught two non-trivial bugs in the first keepalive draft before they shipped:

- Writing keepalive bytes before the response header has been flushed triggers Node's implicit-header emission, corrupting non-streaming Anthropic JSON responses
- Several error-path `clearInterval` omissions that would leak timers

Counter-review also verified (not assumed) one claim that could have been silently wrong: **SSE comment frames with `:` prefix are safely ignored by all standard clients**. Cross-checked against the WHATWG `EventSource` spec (lines beginning with `:` are interpreted as comments and discarded), the `@anthropic-ai/sdk` source (`SSEDecoder` skips comment lines), the `openai` SDK (`openai/streaming` follows the same contract), and lobe-chat's `EventSourceParserStream`. This verification was cheap — 5 minutes with grep — and removed an otherwise plausible failure mode ("what if some client treats our keepalive bytes as malformed SSE and errors out?") from the risk list. The lesson: when a code review produces a compatibility claim, verify it from primary sources (spec + SDK source), do not leave it as "probably fine".

## Post-mortem lessons

### What went wrong

- **5 hours before the experiment was proposed**. The experiment was cheap (~10 minutes to set up) but nobody proposed it until a counter-review agent did. The main investigator was stuck in hypothesis-stacking mode.
- **Three wrong hypotheses acted on before falsification.** Each was plausible. Each had circumstantial supporting evidence. None had a cheap falsifier run before acting.
- **One field-semantic mistake** (Caddy `duration=5.95s`) anchored an entire wrong direction for ~1 hour.
- **The user had to push back explicitly** ("I turned off VPN, still fails") to break the first wrong direction. The system should have surfaced that test earlier.

### What went right

- When the experiment was finally run, it was rigorous: 3 paths, multiple runs, server-side + client-side observation, explicit cleanup.
- Counter-review caught two real code bugs in the remediation.
- Instrumentation added mid-incident (env-gated TRACE_SSE_CHUNKS) yielded decisive evidence for the 125-second upstream silence, *and* is now permanent observability for future incidents.
- Docker compose was refactored mid-incident to bind-mount `server.cjs` from the host, eliminating the "rebuild image to add a log line" cycle permanently.

### Transferable methodology (codified in this skill)

1. When circumstantial evidence converges on a cause, demand one direct falsifier before acting. See [cognitive-traps.md](cognitive-traps.md), Trap 1.
2. When multiple layers could be responsible, do not reason — test. See [layered-isolation-experiment.md](layered-isolation-experiment.md).
3. When observability is missing, add it as an env-gated permanent feature. See [instrumentation-patterns.md](instrumentation-patterns.md).
4. Before committing to a root cause or shipping a fix, counter-review. See [counter-review-pattern.md](counter-review-pattern.md).
5. When a probe shares infrastructure with the subject of the probe, it is not a valid probe. Cross-verify. See [cognitive-traps.md](cognitive-traps.md), Trap 5.

These five rules, applied at hour 1, would have resolved the incident in ~30 minutes instead of 5 hours.
