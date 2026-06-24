# Evaluation Disciplines — why the probes work the way they do

Every rule below exists because skipping it produced a wrong number in a real evaluation.
They are cheap to follow and expensive to ignore.

## 1. Pass keys by env-var name, never on the command line

`--key-env MY_KEY` reads the value at runtime; `--key sk-...` would put the secret into
`ps` output, shell history, and any command echoed into a log or a saved report. The probes
read `os.environ[name]` and never print or persist the value. Corollary: never hardcode a
key into a use-case file, a wrapper script, or a fallback like `key = os.environ.get("X") or
"sk-real..."` — that last pattern is exactly how live keys leak into public repos.

## 2. Thinking-aware throughput — the inflated-tokens/sec trap

Reasoning models (o1-style, R1-style, many "flash" variants) stream their chain-of-thought
in a separate delta field (`reasoning_content`, sometimes `reasoning`), but the `usage.
completion_tokens` count **includes** those thinking tokens.

The failure mode: collect only the visible `content`, measure time-to-first-*content*-token
as TTFT, then divide `completion_tokens` by the remaining time. The thinking tokens were
generated during what you labeled "TTFT", so you attribute a huge token count to a tiny
window. A real ~750 tok/s model measured as **4700 tok/s** this way — a 6× overcount.

The fix the speed probe implements:
- TTFT = first token of **either** kind (thinking or content).
- decode throughput = `completion_tokens / (total − TTFT)` — total output over the whole
  decode window, thinking included. This is the honest "how fast does it generate" number.
- Report real-task throughput AND the sustained-decode ceiling separately. They differ
  legitimately: short outputs never reach steady state, so real-task numbers are lower than
  the ceiling. Reporting only one of them misleads.

## 3. N ≥ 10 for any probabilistic feature

A single request cannot distinguish "feature not implemented" from "implemented but fires
with probability < 100%". One real Anthropic-compatible endpoint honored `thinking: enabled`
on only **~13%** of requests while two competitors hit 100%. A single sample would have
called it either "works" or "broken" — both wrong. Default `--repeat 10`; report the rate
and a three-state verdict (`fully-implemented` / `intermittent k/N` / `not-implemented`),
never a binary from one shot.

## 4. `Connection: close` — defeat load-balancer sticky routing

With HTTP keep-alive, repeated requests can ride one TCP connection that the vendor's load
balancer pins to a single upstream replica. You then sample one replica's behavior and miss
the cross-fleet distribution. A real protocol probe saw **0/10 with keep-alive vs 17/90 with
`Connection: close`** on the same endpoint — keep-alive made a partially-working feature look
completely broken. Force a fresh connection per request whenever you're measuring a rate.

## 5. `trust_env=False` — isolate the endpoint from your proxy

If the environment has an HTTP/SOCKS proxy set, the client library will route every request
through it by default. You then measure the proxy's concurrency limit and the proxy's
(possibly cross-border) latency, not the model's. For a domestic endpoint behind a local
proxy this is the difference between "model does 50 concurrent at 0.4s" and a garbage number.
The concurrency probe sets `trust_env=False`; when measuring speed against a domestic API,
also strip proxy env vars for that run (`env -u http_proxy -u https_proxy …`).

**`env -u` is not enough under a TUN-mode proxy.** Tools like Shadowrocket / Clash in TUN
mode intercept at the network layer: they hand the SDK a fake-IP for the target host and
route the real connection through `utun`, so stripping `http_proxy` / `https_proxy` env vars
(which only defeat env-var-level proxying) still leaves you measuring the tunnel. Symptoms:
the target resolves to a `198.18.x.x` / `100.64.x.x` fake-IP, or latency to a domestic host
is implausibly uniform. To truly bypass: resolve the host's real IP via a public DNS, then
pin it at the socket (bind a physical interface + a `--resolve`-style connection, preserving
SNI) — equivalent to `curl --interface en0 --resolve host:443:<real-ip>`. And confirm it
mattered by measuring BOTH paths: if direct and via-tunnel come out the same, the tunnel was
already routing that host DIRECT and you got lucky — but you only learn that by testing both.

## 5b. Prefer the server's self-reported decode speed; client throughput lies under batch-flush

Some endpoints (notably speculative-decoding ones like DFlash) flush many tokens per SSE
chunk instead of one at a time, and separately expose a ground-truth decode rate in a `pd`
block inside `usage` (`decode_tokens_per_second`). Two consequences:
- The client-side decode throughput (`completion_tokens / (total − ttft)`) reads **~2× too
  high** when the stream is batch-flushed, because a batch of tokens lands in one instant and
  the client can't see the real per-token cadence. A real run measured 1407 tok/s client-side
  while the server self-reported ~890.
- So: **prefer the server's `decode_tokens_per_second` when present** (it knows its own GPU
  cadence), count tokens-per-chunk to detect batch-flush, and when batch-flushed without a
  server field, report END-TO-END throughput (`completion_tokens / total`) rather than a
  client-side "decode" number that flatters the model. `speed_probe.py` does all three.

## 6. Don't let the model grade itself

A model asked to score its own output anchors on having produced it and grades optimistically.
The same risk applies to a single external grader. The quality dimension uses **independent
blind judges** that never see each other's verdict — see `quality_blind_judge.md`.

## 7. Forensic discipline when reading results

The probes produce numbers; these habits keep you from believing wrong ones.

- **Separate measured from inferred.** "The endpoint returned `decode_tokens_per_second: 749`"
  is measured. "So the model does ~750 tok/s" is an inference that's only as good as the
  measurement conditions (network, load, sample size). State which is which.
- **An impossible number is an artifact, not a result.** Throughput far above the vendor's
  own claim, a protocol verdict from one sample, a "100% pass" on a use-case set you know is
  hard — investigate before reporting. The 4700 tok/s figure in §2 was caught exactly this way.
- **Output that hit `max_tokens` is truncated — its quality and throughput numbers are void.**
  The speed probe flags `truncated`; a truncated reasoning-model answer may be almost entirely
  thinking with the real answer cut off. Re-run with a higher cap before judging.
- **High keyword-hit-count ≠ lots of evaluation content.** When mining logs or transcripts for
  "did we test model X", a model name appearing thousands of times is usually request metadata
  (the session *ran on* that model), not test results. Grep the body, not the metadata, before
  concluding a model was benchmarked.
- **A negative claim needs exhaustive search, not one miss.** "We never tested model X" is a
  claim about non-existence — one failed grep doesn't prove it. Search variants (exact id,
  date-stamped snapshots, quantization suffixes) and separate "ran on it" from "tested it"
  before asserting absence. Getting this wrong wastes the user's trust on something they
  remember clearly.

## 8. Identical conditions for comparisons

Comparing two models only means something if the probes ran with identical flags — same
concurrency levels, same use-case set, same max_tokens, same proxy treatment, ideally the same
time window (load varies by hour). Change one variable and the "winner" may just be the one you
tested at 3am.
