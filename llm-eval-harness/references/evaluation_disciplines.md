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

This is the single most independently-rediscovered rule in this file: four unrelated codebases
(a protocol probe, two cache investigations, a system-prompt delivery investigation) each hit it
separately before it was written down. Whatever property you measure — thinking-block rate, cache
hits, field delivery — if it can vary per replica or per channel, connection reuse will hide the
variance. Treat "fresh connection per request" as the default for every rate measurement, not an
option to remember.

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

## 9. Availability verdicts: what a failed call does and does not prove

Four traps, each of which has shipped a false conclusion into a real document:

- **A generous `max_tokens` is part of the probe, not a tuning detail.** Reasoning models spend
  the budget on thinking BEFORE emitting text; a cap of a few dozen tokens returns HTTP 200 with
  empty content, which reads as "model broken". Probe with thousands (the availability probe
  defaults to 8192), and treat 200-with-empty-content as a budget artifact until proven otherwise.
- **"My invented ID returned 404" is not evidence of a missing capability.** A 404/400 on an ID
  that never existed tells you nothing about the vendor. Before writing any "unavailable" list,
  confirm each ID against the vendor's or model developer's official docs — current-generation
  names live past your training data, and suffixes (dated variants, `-preview`, tier names) decide
  routability. An "unavailable" list where half the IDs were invented is worse than no list.
- **The `/v1/models` listing is not the availability truth.** Real gateways route models the
  listing omits (and list models that error). Probe the IDs you care about directly.
- **A model's self-reported identity is worthless as routing evidence.** Models mis-identify
  themselves constantly — deny having a system prompt they received, claim to be a different
  vendor's model. Never write "the gateway serves a different model than advertised" on the
  strength of asking the model who it is.

## 10. Calibrate the meter before believing it

Any instrument you use to judge delivery — token accounting, a log field, a usage counter — must
itself be validated **on the exact dimension you will read**, before its readings count as
evidence. Calibrating an adjacent dimension does not transfer: in one real investigation,
`input_tokens` was proven sensitive to user-message length, then trusted to judge system-prompt
delivery — but that gateway forwarded the system prompt while NOT counting it in usage, so the
"meter" branded a perfectly working model as 38%-broken and flipped the customer recommendation
backwards. A wrongly-oriented instrument is worse than a small sample: every repeat errs in the
same direction, so repetition only inflates confidence in the wrong answer. Behavioral evidence
(the canary echo) is the verdict; accounting evidence corroborates. When they disagree, say so in
the report — the disagreement is itself a finding (billing and forwarding out of sync).

## 11. Neutral canaries — identity and obedience probes carry confounds

To test whether an instruction channel (system prompt) is delivered, plant a fact the model could
never guess and ask for it back. But the fact must be **external to the model's identity**:
"your internal codename is X" collides with assistant identity/safety training, and some model
families will deny having a codename EVEN WHEN the system prompt arrived — indistinguishable from
non-delivery. Obedience probes ("reply with only the word OK") fail the other way: compliance
varies with the model's stylistic training, so non-compliance is temperament, not transport.
Neutral external facts ("this session's project number is X") get relayed without resistance.
When a probe involves the model's self-concept or its willingness to obey, the probe measures the
model's personality entangled with the channel — redesign it until refusing is not an option.

## 12. Time-varying systems: a single time slice is not a steady state

Gateways route across multiple upstream channels whose weights change. A delivery/compliance rate
measured once — even with a clean N≥10 — describes that hour, not the system: the same
model+format combination has measured 6/16, then 12/12, then 1/6 across one day (and the token
counts were strictly bimodal — payload fully counted or not at all, no middle — the signature of
mixed routing rather than noise). Two rules follow. (1) Before publishing any rate, re-sample in
a separate time window; write "unstable, varies by time" rather than freezing one window's number
into a doc that outlives it. (2) When two careful measurements disagree, FIRST check whether they
measured the same metric the same way (behavioral vs accounting, §10) — inventing "it must vary
over time" to reconcile a metric mismatch is how one investigation papered over its own
instrument error; time-variance must be demonstrated with same-metric multi-window data, never
assumed to make contradictions comfortable.

## 13. The probe is a suspect too

Before a probe's failure means anything, the probe must pass on a known-good control. This is §7's
forensic stance turned on your own tooling, and it recurs: a resident canary "detected an outage"
that was its own too-short fixed sleep; a shell pipeline "detected empty content" that was its own
quote-mangling of JSON (move JSON through files or direct HTTP libraries, never through shell
string interpolation); a cache A/B tool permanently FAILs one vendor whose API reports
cache_creation=0 unconditionally — a judging assumption that simply doesn't hold there. Two
habits: run every new probe against a model/vendor where the answer is known before pointing it
at the suspect; and when reusing a probe on a new vendor, re-verify its pass/fail assumptions
against that vendor's API semantics (then write the exclusion into the probe's NOT-FOR header so
the next person doesn't rediscover it).

## 14. Report the failure MODE, not just the failure rate

"90% success at concurrency 10" and "hard ceiling at 50 with instant clean 429s" can describe the
same vendor — and the second is far more usable. Failure modes differ in user impact by an order
of magnitude: a fast explicit 429 is retriable and nearly invisible; a silent TCP drop that hangs
20 seconds before timing out stalls a room full of workshop attendees. When a probe fails, record
HOW: status code vs hang, time-to-failure, retriable-or-not. And separate the ceiling's SHAPE:
a sharp knee (stable 100% → cliff) locates a hard limit; a gradual slide suggests load-dependent
degradation. Translate the number back into the real workload before concluding ("your peak is
6-8 concurrent; the knee is at 50 → 6-8x headroom") — a benchmark that stops at the number has
not answered the question that motivated it.
