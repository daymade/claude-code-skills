# Production Testing Patterns — gates, canaries, and the statistics that lie

The four probe dimensions answer "is this model good enough to adopt?". This
file covers what comes AFTER adoption: tests that run repeatedly against a
live system — deployment gates, resident canaries, fault-injection mocks — and
the monitoring-statistics traps that make healthy systems look broken and
broken systems look healthy. Distilled from operating a production LLM gateway
for months; every pattern here exists because its absence caused a real
incident.

## Contents
- Layer your tests by WHEN they run, cost, and depth
- Deployment gate pattern (one-shot, blocking)
- Resident canary pattern (forever-running, alerting)
- Transient vs real failure: the retry-classification rule
- pass / fail / error are THREE states, not two
- Fault-injection mocks: testing your infrastructure, not the vendor
- Monitoring statistics that lie
- Probe engineering conventions

## Layer your tests by WHEN they run, cost, and depth

Organize by lifecycle position, not by what is tested — the same capability
(say, "can we complete a chat call") appears at several layers with different
budgets:

| Layer | When | Budget | Depth |
|---|---|---|---|
| L0 preflight | before any deploy starts | seconds, free | config sanity, env vars present |
| L1 health | during/after deploy | seconds | URLs up, auth accepted |
| Deployment gate | end of deploy, BLOCKING | ~a minute, cents | full product chain, synthetic account |
| Post-deploy real probe | after gate passes | one real request | the path a real user takes |
| Resident canary | 24/7 | pennies/day | one narrow invariant, feeding alerts |

Two placement rules that came from incidents:

- **Per-model availability does NOT belong in the deployment gate.** Upstream
  vendors wobble independently of your deploy; putting every model in the gate
  makes deploys flap on failures unrelated to the change being shipped. The
  gate tests one cheap pinned model; the full model sweep is a separate
  non-blocking job (run it before workshops / after channel config changes).
- **The gate must verify each hop, not infer the chain from the final answer.**
  One real gate asserts the relay's own request counter incremented — proving
  traffic went THROUGH the relay — instead of assuming a correct final answer
  implies the intended path. Correct answers arrive via wrong paths all the
  time (a fallback route, a cache, a different upstream).

## Deployment gate pattern (one-shot, blocking)

The shape that survived production use:

1. Synthetic account end-to-end: register/login → check or top-up quota →
   create token → call the product API non-streaming → call it streaming.
2. **Random marker per run** ("Reply EXACTLY: <fresh-uuid>") with an exact-echo
   assertion — a fixed prompt can pass on a stale cache from the previous run.
3. Thinking-aware text extraction — reasoning models may put everything in the
   thinking channel; an assertion that only reads text content fails spuriously
   (this exact false alarm has recurred in three independent codebases).
4. Cost guard: hard-assert the gate's model IS the designated cheap one, so
   nobody's config edit silently makes CI burn a frontier model.
5. Security piggyback: while touching the token API anyway, assert the token
   list endpoint does NOT echo back full token values.

## Resident canary pattern (forever-running, alerting)

A canary is not a probe in a loop; it has design constraints probes don't:

- **Never crash.** Top-level catch-all around the loop body. A crashed canary
  triggers the "canary logs went silent" meta-alert with a misleading cause.
- **Dynamic pacing.** Sleep proportional to the previous request's measured
  latency (with floor and cap), not a fixed interval — a fixed 2s sleep
  produced false alarms whenever the upstream slowed down.
- **Fresh session per cycle** — connection reuse masks the routing/cache
  behavior you exist to observe (see disciplines §4; independently rediscovered
  in four codebases).
- **Prefer the authoritative usage frame**: in streaming responses take the
  final `message_delta` usage; the opening frame's numbers are provisional.

## Transient vs real failure: the retry-classification rule

An explicit regex/classifier decides which failures earn a retry:

- Retriable (bounded retries + pause): 5xx, 429, connection reset — transient
  upstream weather. One unretried transient 500 once killed a ~30-minute
  deploy at the last step.
- NOT retriable (fail immediately): 4xx auth errors, contract-shape
  mismatches, missing models — retrying config errors just delays the truth.

Write the classification down in the gate itself; "retry everything three
times" hides real breakage and "retry nothing" makes deploys flaky.

## pass / fail / error are THREE states, not two

The single most valuable canary discipline: separate "the tested invariant
failed" from "the test could not run".

- `pass` — invariant held.
- `fail` — request succeeded, invariant violated (e.g. cache did not hit).
  ONLY this state pages a human.
- `error` — network/5xx/parse failure: the canary could not observe. Logged,
  counted, never paged as the invariant — a separate absence/error-rate alert
  watches the canary itself.

Folding `error` into `fail` poisons the alert's meaning and trains responders
to ignore it (the alarm that cried wolf); folding it into `pass` blinds you.
Probes exit-code the same trichotomy: OK / NON_COMPLIANT / CONFIG / TRANSPORT
so automation can react differently to "vendor broke the contract" vs "my env
var is missing" vs "the network ate it".

## Fault-injection mocks: testing your infrastructure, not the vendor

Orthogonal direction: instead of probing a real vendor, stand up a
byte-accurate FAKE upstream that misbehaves on purpose — an SSE server that
streams normally then goes idle for 150s — to answer "which hop in MY stack
(CDN, reverse proxy, client) kills slow streams, and at what timeout?".
Waiting for a real vendor to be slow is unreproducible; the mock makes the
failure a controlled experiment. Design notes that mattered:

- Idle duration is chosen to EXCEED the typical CDN idle-timeout band
  (100–130s), making the test a falsifier for a specific hypothesis, not a
  vibe check.
- Server records exactly when the peer disconnects; client records what it
  observed; the two logs cross-confirm which side cut.
- Multiple identical routes (`/probe-a`, `/probe-b`) let you A/B different
  network paths through the same mock.

## Monitoring statistics that lie

Aggregate views that hide real failures (each burned us once):

- **Aggregated error-rate alerts dilute per-model failures.** A healthy
  high-volume model averages a broken model's 42% error rate below the alert
  threshold. Group by model/channel or you'll learn about outages from users.
- **Success-only log tables show "all healthy" during a limiting event** —
  if the table only records completed requests, 429s never appear in it. Know
  which layer's log actually records failures before declaring health.
- **A rate without its denominator is noise.** 3 requests at 100% error is a
  blip; 200 at 40% is an incident. Print N next to every percentage.
- **Averages flatten time structure.** 77% pass over 24h decomposed into
  100% off-peak + 50% at peak — "sensitive to upstream load" was the actual
  story, invisible in the mean. Group by hour before believing a daily figure.
- **Sample-size floor**: a written SOP line worth stealing — "anything less
  than 24h of samples is a rumour, not a fact."
- **Ratio alerts need BOTH a count floor and a volume floor**; N=2 once pushed
  a ratio to 999 and paged sev-10 for a single user's cold start.
- **Yesterday's triage rule is not a law of nature.** "That vendor just has
  30-40% baseline errors, ignore it" — written from surface symptoms — later
  masked a real capacity incident with identical numbers but a different
  error class underneath. Re-verify baseline folklore against raw error
  bodies periodically; classify upstream errors by parsed class, never by
  HTTP status alone (the same 429 string covers six different root causes
  requiring opposite responses).
- **The auto-recovery you're waiting for may not cover this failure mode** —
  an auto-ban that triggers on consecutive 5xx will never fire on a vendor
  politely returning 429s. Check the mechanism's trigger condition matches
  the symptom before "waiting for it to self-heal".

## Probe engineering conventions

Conventions that keep a growing probe collection usable:

- **Header contract** in every probe file: `SCOPE` (what it measures),
  `NOT-FOR` (what it must not be used for — the most valuable line: a generic
  cache A/B tool was structurally invalid for one vendor whose API reports
  cache_creation=0 unconditionally, and only a NOT-FOR line stops the next
  person from reading its permanent FAIL as truth), `AUTHORITY` (which
  methodology/reference it extends).
- **Vendor discovery via env-var triplets** (`<NAME>_ENDPOINT`,
  `<NAME>_MODEL`, `<NAME>_API_KEY`): adding a vendor to a comparison = adding
  three env vars, no code change. Expensive vendors (first-party frontier
  APIs) are opt-in only — absent by default so a casual sweep can't burn them.
- **Request/analysis separation**: probes write raw JSON artifacts; analysis
  scripts consume them. Re-slicing data must not require re-spending API
  calls.
- **Public engine, private config**: the probe scripts are generic and
  publishable; your model rosters, use-case suites, and keys live outside the
  bundle (`~/.llm-eval/` or a private repo). See the use-case library section
  of SKILL.md — same rule for every asset here.
