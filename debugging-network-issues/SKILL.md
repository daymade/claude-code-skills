---
name: debugging-network-issues
description: Evidence-driven investigation for network, streaming, and protocol-layer bugs. Use when debugging connection resets (ECONNRESET, HTTP/2 RST_STREAM, INTERNAL_ERROR), SSE or long-polling stalls, fixed-time connection drops, CDN/proxy/CGNAT idle timeouts, or any incident where symptoms do not match the obvious cause. Applies falsification-first methodology — layered isolation experiments to pin down the responsible network layer, env-gated runtime instrumentation for non-invasive observation, and counter-review agent teams to challenge single-cause assumptions. Strongly trigger on "socket closed unexpectedly", "stream interrupted", "ECONNRESET", "HTTP/2 INTERNAL_ERROR", "fails after N seconds", "works sometimes but not always", "upstream silent for X seconds", or any scenario where the investigator might jump to conclusions before evidence. Generalizes to any multi-layer system investigation where assumption-first thinking is the failure mode.
---

# Debugging Network Issues

Evidence-driven investigation methodology for incidents where the obvious cause is probably wrong. Built from a real 5-hour production case (see [references/case-sse-rst-130s.md](references/case-sse-rst-130s.md)) where assumption-stacking wasted hours that a 10-minute layered experiment would have resolved.

Apply this skill when the user reports a network/streaming/protocol symptom and the investigator feels tempted to diagnose from one log line or one circumstantial data point. The skill's job is to slow that reflex down.

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

### Step 1: Gather direct evidence at every hop

Before framing hypotheses, collect:

- Server-side logs at every hop in the request path
- Client-side logs (browser devtools HAR, CLI debug log, SDK traces)
- Metrics over the incident window (RPS, latency, error rate, connection count, CPU/mem)
- Distributed trace if available
- Packet capture if the symptom is at the wire level (see [references/packet-capture-recipes.md](references/packet-capture-recipes.md))

If any of these is missing and relevant, **fill the gap before guessing**. Adding a `TRACE_*` env flag and restarting a container beats an hour of hypothesis-stacking. The instrumentation patterns in [references/instrumentation-patterns.md](references/instrumentation-patterns.md) are low-risk, env-gated, and safe to ship into production permanently.

### Step 2: Hypotheses with falsifiers and threat-model boundaries

List three or more plausible causes. For each, write three sentences:

- **What would confirm it?** (easy and often misleading)
- **What would refute it?** (the falsifier — this is what matters)
- **Which layer boundary would the intervention target?** (the threat-model question — forces you to be precise about where the fix would apply)

The third question prevents a common anti-pattern: proposing a fix that operates on the wrong hop. For example, a "keepalive" fix that writes bytes downstream to the client is useless for an *upstream* idle timeout — the intervention targets a different boundary than the problem. Naming the boundary up-front surfaces this mismatch before coding starts.

If you cannot state a concrete refuter, the hypothesis is unfalsifiable. Flag it, but do not act on it. If you cannot state which boundary a proposed fix targets, you do not yet understand what the fix actually does.

### Step 3: Decisive experiment

For network-layer problems, the default is **layered isolation**: three paths differing by exactly one hop. Example for a CDN-fronted service:

| Path | Route | Rules out if it passes |
|------|-------|-----------------------|
| A | Full path via CDN | Nothing — this is the failing baseline |
| B | `--resolve` to origin IP (bypass CDN) | CDN layer |
| C | Server loopback (bypass CDN + LB) | CDN + LB |

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

See [references/instrumentation-patterns.md](references/instrumentation-patterns.md) for the exact template used to diagnose the Qiniu 125-second upstream silence in this incident.

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

See [references/cognitive-traps.md](references/cognitive-traps.md) for extended examples including this case study.

## Anti-patterns — things to explicitly avoid

- **Jumping to a fix before a falsifier is found.** "Probably it is X, let me restart / tweak / upgrade." This converts learning opportunities into mystery fixes that do not prevent recurrence.
- **Accepting agent counter-review findings wholesale.** Agents over-produce risk findings. Filter before acting (see four-question filter above).
- **Ad-hoc production edits that bypass IaC.** If the investigation requires changing production, change the source-of-truth first, then apply — otherwise the "fix" evaporates on the next deploy and the drift hides the real state.
- **Declaring root cause from a single observation.** Demand a falsifier attempt first.
- **Writing "should work now" without re-running the failing experiment.** Re-verify.

## Case study

The [references/case-sse-rst-130s.md](references/case-sse-rst-130s.md) walks through a full 5-hour investigation where the assistant repeatedly jumped to the wrong conclusion. The right answer — Cloudflare edge HTTP/2 stream idle timeout at 126 seconds, amplified by Qiniu not emitting SSE ping during Sonnet 4.6 tool_use generation — surfaced in 10 minutes once a subagent designed a 3-path layered isolation experiment with a mock idle upstream. Read the case study before applying this skill to an unfamiliar problem domain; the wrong-turn anatomy is the teaching.

## Reference files

- [references/layered-isolation-experiment.md](references/layered-isolation-experiment.md) — 3-path technique, mock upstream template, result matrix
- [references/instrumentation-patterns.md](references/instrumentation-patterns.md) — env-gated TRACE_*, greppable log tags, deployment checklist
- [references/packet-capture-recipes.md](references/packet-capture-recipes.md) — tcpdump filters for RST isolation, interface selection on Docker, HTTP/2 decoding
- [references/counter-review-pattern.md](references/counter-review-pattern.md) — 4-agent team composition, 4-question filter, integration workflow
- [references/cognitive-traps.md](references/cognitive-traps.md) — extended examples, rescue-cycle warnings
- [references/case-sse-rst-130s.md](references/case-sse-rst-130s.md) — canonical case study with wrong-turn timeline

## Scripts

- [scripts/mock-idle-upstream.py](scripts/mock-idle-upstream.py) — SSE server that emits one frame then idles N seconds. Use as the upstream in layered isolation experiments to precisely control the idle interval.
- [scripts/layered-isolation-probe.sh](scripts/layered-isolation-probe.sh) — Runs the 3-path A/B/C comparison and prints a diagnostic matrix.
