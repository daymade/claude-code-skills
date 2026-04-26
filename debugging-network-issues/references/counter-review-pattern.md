# Counter-Review Pattern

## Contents
- Why counter-review (not peer-review)
- The four-agent team composition
- The four-question filter
- Integration workflow
- When NOT to counter-review
- The case study: what counter-review surfaced

## Why counter-review

A lone investigator converging on a conclusion is highly susceptible to confirmation bias, especially after investing hours in a line of reasoning. Standard peer review is better but shares most of the investigator's context and inherits the same blind spots.

**Counter-review** is adversarial by design: the reviewer's job is to *falsify* the conclusion, not confirm it. They start from the same evidence but are explicitly instructed to find what the investigator missed, find weaker-evidence conclusions the investigator over-weighted, and propose experiments that could disprove the current hypothesis.

Counter-review works best when:

- Multiple reviewers run in parallel with distinct framings
- Each reviewer has their own search/research capability (not just re-reading the same investigator's notes)
- Their outputs are filtered before acting, not accepted wholesale

## The four-agent team composition

This composition was used in this investigation and proved effective. Roles are distinct on purpose — they cover orthogonal angles.

### 1. Independent diagnostician

**Prompt framing**: "You have the complete evidence set. Reach your own conclusion without being anchored by mine. Especially: what hypotheses did I not consider?"

**Typical value**: surfaces the "I forgot to check X" class of gap. In this case study, this agent was the first to raise Caddy's `IdleConnTimeout` default as a suspect — a layer the main investigator had not yet examined.

**Agent type**: `general-purpose` with SSH/Bash access

### 2. Assumption challenger

**Prompt framing**: "The main conclusion is X. Challenge it using external research (WebSearch authoritative sources, vendor docs, bug trackers). Cite URLs. Do not rely on training data."

**Typical value**: finds vendor-documented behavior that contradicts or qualifies the investigator's assumption. In this case study, this agent found published evidence that Anthropic's own official API also experiences SSE stalls during tool_use generation — downgrading the "Qiniu does not forward ping" hypothesis from "root cause" to "amplifying factor".

**Agent type**: `general-purpose` with WebSearch

### 3. Code reviewer (if a fix is proposed)

**Prompt framing**: "The proposed fix is this [diff]. Audit for: race conditions, cleanup paths, unintended interactions with existing code, boundary conditions. Read the surrounding code."

**Typical value**: catches "my fix would break the JSON response path" class of bug. In this case study, this agent caught that a proposed `setInterval` keepalive would corrupt non-streaming Anthropic JSON responses because `res.write` before `writeHead` triggers Node's implicit-header emission — a subtle bug the main investigator would likely have shipped.

**Agent type**: `Plan` agent or `codex:rescue` with code-read access

### 4. Decisive experiment designer

**Prompt framing**: "Design and execute an experiment that decisively confirms or refutes the current root cause. Layered isolation preferred. Clean up after yourself."

**Typical value**: converts hypothesis-stacking into definitive answer. In this case study, this agent set up a mock idle upstream, deployed temporary CF DNS and Caddy routes, ran 3 parallel paths, observed `126s RST only on Path A`, and cleaned everything up. What 5 hours of reasoning could not resolve, 10 minutes of experiment did.

**Agent type**: `general-purpose` with Bash/SSH/file access

### Launch pattern

Launch all four in parallel (one message, four `Agent` tool calls with `run_in_background: true`). Process notifications as they return; do not wait for all before starting to read. Some will finish in minutes, the experiment designer often takes longer.

## The four-question filter

Agent reviewers over-produce findings. A code reviewer will generate 10 risk items even when 3 are worth acting on; a challenger will list 6 counter-hypotheses even when 1 is plausible. Paste-the-raw-agent-output is the anti-pattern. Filter every finding through four questions:

### 1. Probability — will this actually happen?

Distinguish real risks from theoretical risks. A race condition in a code path that runs once at startup on a single thread is theoretical. A race condition in a request handler under load is real.

Ask: in the actual deployment, under actual load patterns, with actual input distributions, does this failure mode fire with >1% probability? If not, defer.

### 2. Cost — what is the cost of fixing versus ignoring?

For each finding:
- Cost of fixing: engineering time + regression risk + complexity added
- Cost of ignoring: expected incidents × their impact

Some findings are real but cheap to accept (log a warning, move on). Others are real and cheap to fix (one-line guard). Prioritize the second.

### 3. Realistic scenario — does this apply to the user's actual business case?

Agents generalize. A counter-review of an internal-only tool often surfaces findings appropriate for a consumer product (rate limiting, CSRF, input fuzzing). Filter to the actual deployment context.

### 4. Verification — can I cheaply confirm or refute this?

For findings that survive 1-3, can you test the claim in under 5 minutes? If yes, test. If the test comes back negative, discard. If positive, elevate to actionable.

Never accept a finding as real without at least one cheap verification.

### Classification after filtering

Classify each finding:

- **Real issue** — act on it
- **Partly right** — acknowledge and narrow scope before acting
- **Unlikely** — log but do not act
- **Actively harmful** — the suggested fix would introduce a new bug; explicitly reject

Report to the user with classification, not raw agent output.

## Integration workflow

```
┌────────────────────────────────────────────────────────┐
│ 1. Main investigator reaches tentative conclusion      │
│    and draft remediation                               │
├────────────────────────────────────────────────────────┤
│ 2. Launch 4 counter-review agents in parallel,         │
│    one message, run_in_background=true                 │
├────────────────────────────────────────────────────────┤
│ 3. As each returns, read full output                   │
├────────────────────────────────────────────────────────┤
│ 4. Apply 4-question filter to every finding            │
│    - probability, cost, realism, verifiability         │
├────────────────────────────────────────────────────────┤
│ 5. For every finding that survives filter,             │
│    run cheap verification                              │
├────────────────────────────────────────────────────────┤
│ 6. Reclassify findings after verification              │
│    (real / partly / unlikely / harmful)                │
├────────────────────────────────────────────────────────┤
│ 7. Update root cause / fix based on classified         │
│    findings                                            │
├────────────────────────────────────────────────────────┤
│ 8. Report to user: classification table + justified    │
│    action list. No raw paste.                          │
└────────────────────────────────────────────────────────┘
```

## When NOT to counter-review

Counter-review has overhead (5-30 minutes of parallel agent runs + filter time). Skip it when:

- The root cause is already directly verified (you have the smoking gun, not circumstantial evidence)
- The fix is mechanical (e.g., updating a hardcoded version number) with no design decisions
- The incident is ongoing and the priority is stabilization, not perfect root cause
- The cost of getting it 80% right and iterating is lower than the cost of getting it 100% right the first time

In other words: counter-review is for the **conclusion** phase, not the stabilization phase.

## The case study: what counter-review surfaced

Main investigator's tentative conclusion before counter-review: "Qiniu does not forward SSE ping, causing some middle layer to RST after ~130s. Fix: add server-side keepalive in provider-gateway."

Counter-review surfaced:

| Agent | Finding | Classification after filter |
|-------|---------|---------------------------|
| Challenger | Anthropic's official API also stalls 59-138s+ on tool_use (GitHub issues cited). "Qiniu not forwarding ping" is not sufficient as independent root cause. | Partly right — downgraded assumption from "root cause" to "amplifying factor" |
| Challenger | 130s matches Cisco CGNAT initial TCP timeout (120s + RTT) better than CF 100s. | Partly right — worth testing but did not change the fix |
| Code reviewer | Proposed keepalive would corrupt non-streaming Anthropic JSON responses (res.write before writeHead triggers implicit headers). | Real issue — fixed before deploy |
| Code reviewer | Several clearInterval paths missing (proxyReq.on error, proxyRes aborted). | Real issue — fixed before deploy |
| Code reviewer | SSE comment (`:` prefix) client-compatibility claim needed to be verified, not assumed. | Verified from primary sources (WHATWG EventSource spec + `@anthropic-ai/sdk` `SSEDecoder` source + `openai` SDK + lobe-chat EventSourceParserStream). Confirmed safe. Removed from risk list. |
| Independent | Caddy default IdleConnTimeout is 120s, could match the 130s constant. | Turned out wrong (ruled out by experiment) but good hypothesis |
| Experiment | 3-path layered isolation with mock idle upstream: Path A fails at 126s, B and C clean at 220s. | Definitive — pinpointed CF edge |

Raw count: 6 findings surfaced. Acted on: 3 (2 code fixes, 1 definitive experiment result). Discarded: 1 (wrong). Downgraded but kept as context: 2.

If the main investigator had pasted all six to the user as "here's what counter-review said", the user would have had to do the filtering work. The filter is the investigator's job.
