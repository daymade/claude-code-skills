---
name: llm-eval-harness
description: >-
  Test/evaluate any LLM behind an OpenAI- or Anthropic-compatible endpoint:
  availability (max_tokens-aware), request fidelity (does system prompt/tools/history
  REACH the model, or does the gateway silently drop it), speed (TTFT+tok/s),
  concurrency (before a workshop), Anthropic protocol compliance, quality regression,
  vendor bug reports, deployment gates, resident canaries. Reach for this BEFORE
  hand-rolling a curl loop against any LLM endpoint — that instinct is the trap: it
  skips the N=10 sampling, Connection:close, and env-var key handling this bakes in. Use when someone tests/benchmarks/测评/压测 a model/endpoint, onboards a
  provider, decides whether to switch or temporarily fail over to an alternate channel
  (e.g. outage or quota exhaustion), writes a supported-models list, debugs "model
  ignores system prompt", or verifies a tok/s claim. Triggers on "benchmark this
  model", "测一下这个模型/渠道/API", "接入新模型先测一下", "system prompt 不生效",
  "这个渠道能不能用/稳不稳", "临时切换过去顶一阵子" — even without "eval", even wrapped
  in business narrative.
---

# LLM Eval Harness

## Overview

Give this skill an endpoint (`base_url` + `model` + an API key in an env var) and it
measures whether the endpoint actually works and whether the model is fast, stable,
protocol-correct, and good enough — instead of trusting the vendor's headline numbers.
Six dimensions, usually scattered across ad-hoc scripts that get rewritten (with the
same bugs) every time:

| Dimension | Script | Answers |
|---|---|---|
| **Availability** | `scripts/availability_probe.py` | which model IDs work here, with 3-state error classification |
| **Request fidelity** | `scripts/fidelity_probe.py` | do system prompt / tools / history actually REACH the model? |
| **Speed** | `scripts/speed_probe.py` | TTFT + sustained decode tok/s, **thinking-aware** |
| **Concurrency / stability** | `scripts/concurrency_probe.py` | success rate, p50/p90 latency, where it breaks |
| **Protocol compliance** | `scripts/protocol_probe.py` | does the Anthropic `thinking` block actually fire when requested, AND does the endpoint accept one already sitting in history on a later turn (N≥10, both are separate checks — see Dimension 3)? |
| **Quality / use-case regression** | `scripts/usecase_runner.py` + blind judges | does it pass *your* accumulated cases? |

## Which dimensions to run

Route from what the user is actually doing:

- "接入新模型/新网关先测一下" / onboarding a provider → **Availability → Fidelity**,
  then speed/concurrency if adoption looks likely
- "这个 ID 能不能用 / 写个支持列表" → **Availability** (and read disciplines §9 before
  writing any "unavailable" verdict)
- "模型不听 system prompt / agent 行为怪但没报错" → **Fidelity** (system canary)
- "快不快 / tok/s 是真的吗" → **Speed**; "扛不扛得住" → **Concurrency**
- "这个兼容端点是真兼容吗" → **Protocol** + Fidelity's tools/auth checks
- "这个模型/渠道用着用着就 400 了 / session 断了 / continue 不下去了" (extended-thinking client,
  multi-turn session) → **Protocol `--check history-replay`** specifically — this symptom is the
  generation check passing while history-replay silently doesn't; don't stop at generation
- "换模型质量会不会掉" → **Quality regression**
- "要给厂商报 bug" → run the relevant probe with `--output`, then follow
  [references/vendor_evidence_protocol.md](references/vendor_evidence_protocol.md)
- "部署闸门 / 常驻监控 / 告警老误报" →
  [references/production_testing_patterns.md](references/production_testing_patterns.md)

Don't run all six ritually — pick what answers the user's question.

**Key handling (non-negotiable):** every script takes the API key by **env-var name**
(`--key-env MY_KEY`), never the key value on the command line — so it stays out of `ps`,
shell history, and any saved report. Never hardcode a key into a use-case file or a
wrapper. Read [references/evaluation_disciplines.md](references/evaluation_disciplines.md)
for the full reasoning behind this and the other disciplines.

**Your private data lives outside this bundle.** Use-case libraries, model rosters, and
keys belong in `~/.llm-eval/` (or wherever you keep secrets), NOT in this skill directory —
the skill is generic and public; your test suite is yours. See "Use-case library" below.

## Quick start

Detect what you have, then run the dimensions that apply. For an OpenAI-compatible model:

```bash
export MY_KEY=sk-...                       # the key never appears in a command below

# Speed: real-task throughput + sustained decode ceiling
uv run --with openai python scripts/speed_probe.py \
  --base-url https://api.example.com/v1 --model some-model --key-env MY_KEY --mode both

# Concurrency: ramp until it breaks
uv run --with aiohttp python scripts/concurrency_probe.py \
  --url https://api.example.com/v1/chat/completions --model some-model --key-env MY_KEY \
  --format openai --concurrency 10 20 40 60
```

If the endpoint is Anthropic-Messages-shaped (`/v1/messages`), also run the protocol probe
(below). Pick dimensions by what the user actually asked — don't run all six if they only
asked "is it fast?".

## Dimension 0 — Availability (which model IDs actually work)

```bash
uv run --with aiohttp python scripts/availability_probe.py \
  --base-url <base> --key-env <ENV> --format both \
  --models model-a vendor/model-b @models.txt --output /tmp/avail.json
```

- Verdicts are 3-state per failure, not pass/fail: `no-channel` (no route for this
  ID), `upstream-error` (route exists, upstream failing — retry later), `empty-content`
  (usually a max_tokens artifact on reasoning models, NOT a broken model). The probe
  keeps `--max-tokens` at 8192 by default precisely so thinking models don't read as
  dead — do not "optimize" it downward.
- **Before writing any "unavailable" list**: verify each failing ID exists in official
  docs. Current-generation model names postdate your training data — WebSearch the
  vendor's / model developer's model page instead of enumerating guesses; suffixes
  (`-preview`, dated variants, tier names) decide routability. Full traps: disciplines §9.
- **Never probe a client-side marker as if it were a real model ID.** Bracket-suffixed
  strings like `some-model[1m]` are frequently a CLI client's own local convention (Claude
  Code parses and strips `[1m]` before the request is ever built — see
  claude-switch-models-setup's "Configuring Context Window Size" section for the full
  mechanism) — they never appear on the wire. The probe warns when it sees one, but the
  discipline is yours: probe the bare model ID the vendor actually documents, not a string
  copied out of a Claude Code `ANTHROPIC_MODEL` env var.
- The gateway's `/v1/models` listing is one input, never the verdict — real gateways
  route models the listing omits.

## Dimension 0.5 — Request fidelity (does your payload reach the model?)

```bash
uv run --with aiohttp python scripts/fidelity_probe.py \
  --base-url <base> --model <model> --key-env <ENV> \
  --format anthropic --check all --repeat 10 --output /tmp/fidelity.json
```

- Four checks: `system` (canary code planted in the system prompt — can the model echo
  it back?), `tools` (full round-trip including returning a tool result and verifying
  the final answer uses it), `multiturn` (plant facts across turns, recall them all),
  `auth` (x-api-key vs Bearer on both protocol endpoints — gateways commonly accept
  both on one path and only one on the other, and the wrong-header 401 reads exactly
  like a dead key).
- This is the dimension that catches the nastiest gateway failure: **everything returns
  200 and chats fluently, but the system prompt never reached the model** — so any tool
  whose rules live in the system prompt silently misbehaves with no error anywhere. On
  one real gateway, one model alias never delivered the system prompt in 100+ samples
  across every legal way of sending it, while sibling aliases delivered intermittently
  with rates that changed by the hour.
- Delivery through routed gateways is **probabilistic and time-varying** — hence
  `--repeat` (default 10) and a three-state verdict (delivered / intermittent k-of-N /
  not-delivered). A clean single-window result is still just that window: re-sample in
  another time slice before publishing a number (disciplines §12).
- The probe reports token-accounting corroboration but never trusts it alone —
  behavioral evidence rules; see disciplines §10 (calibrate the meter) and §11 (why the
  canary is a neutral external fact, not an identity or obedience test).

## Dimension 1 — Speed (thinking-aware)

```bash
uv run --with openai python scripts/speed_probe.py \
  --base-url <…/v1> --model <model> --key-env <ENV> --mode both --output /tmp/speed.json
```

- `mixed` runs representative tasks (what real usage feels like); `decode` forces one long
  output to find the **sustained ceiling** (the number to compare against a vendor's claim);
  `both` does both.
- **The trap this script exists to avoid:** reasoning models stream thinking in a separate
  `reasoning_content` field, but `completion_tokens` counts it. Collecting only `content`
  while dividing by `completion_tokens` produces wildly inflated numbers — a real ~750 tok/s
  model once measured as 4700 tok/s this way. The script captures both, takes TTFT as the
  first token of *either* kind, and reports `completion_tokens / (total − TTFT)`.
- **Read the output correctly:** real-task throughput is *lower* than the decode ceiling
  because short outputs never reach steady state — that's expected, not a bug. Report both
  numbers, and note when the model emits thinking (its end-to-end latency includes reasoning
  time, not just typing).

## Dimension 2 — Concurrency / stability

```bash
uv run --with aiohttp python scripts/concurrency_probe.py \
  --url <full endpoint URL> --model <model> --key-env <ENV> \
  --format openai|anthropic --concurrency 10 20 40 60 --output /tmp/conc.json
```

- Pass several `--concurrency` levels to ramp and find the ceiling — the level where success
  rate drops or latency explodes. A model that's fast single-threaded can still collapse at
  modest concurrency (real example: one provider held 50 concurrent at 0.4s while another
  dropped requests at just 5 concurrent).
- The script isolates from any ambient proxy (`trust_env=False`) and disables keep-alive
  pooling (`force_close`) — otherwise you measure the proxy's limit or one pinned upstream
  replica, not the model. It prints a "concurrency proof" (overlapping request pairs) so you
  can confirm requests really ran in parallel.
- Distinguish failure modes from the output: HTTP 429 (clean throttle, retriable) vs a TCP
  drop that hangs to timeout (much worse for UX) vs 5xx. They imply very different fixes.

## Dimension 3 — Protocol compliance (Anthropic thinking block: generation AND history-replay)

```bash
uv run python scripts/protocol_probe.py \
  --url <…/v1/messages> --model <model> --key-env <ENV> --check all --repeat 10 --output /tmp/proto.json
```

- Only relevant for endpoints claiming Anthropic `/v1/messages` compatibility. `--check all`
  (default) runs BOTH sub-checks — they test different code paths and a vendor can pass one
  while hard-failing the other:
  - **generation**: does `thinking: {type: enabled}` actually produce `thinking_delta` /
    `signature_delta` SSE events when you request it? (the original check)
  - **history-replay**: does the endpoint ACCEPT a `type: "thinking"` block that's already
    sitting in a prior assistant turn, when that history is replayed back on a later turn —
    exactly what Claude Code and every other agentic client does on every continuation?
    (`--check history-replay` to run just this one)
- **Real incident (2026-07-21) that motivated the history-replay check**: a Kimi/Moonshot
  model via a China reseller passed generation fine (emits thinking correctly when asked) but
  hard-rejected history-replay — 400 "invalid part type: thinking" the instant a prior
  thinking block came back as input, killing the session on every subsequent turn. Passing
  generation told us nothing about this; they're orthogonal failure modes (response
  generation vs. request validation).
- **Don't conclude "vendor/reseller X is broken" from one cross-axis comparison — and don't
  stop at the first single-axis comparison that confirms a vendor-documented parameter either.**
  This took three rounds to get right, kept in disciplines §§17-19 as the canonical cautionary
  tale: round 1 compared a different model AND a different reseller at once and (wrongly)
  blamed the reseller. Round 2 fixed that — same reseller, only the model varied — and the
  result matched a documented, named vendor parameter (Moonshot's own `preserve_thinking`), which
  looked like confirmation. Round 2 was STILL wrong: the probe never left that one reseller, so
  it couldn't see that the vendor's own direct/native endpoint handled the "rejected" model fine
  — real production traffic proved it. Read §19 before treating any single-reseller-confirmed
  result as final; check the vendor's own endpoint or real traffic for the actual channel in
  question before writing an "X doesn't support thinking" conclusion into anything.
- **Compliance is often probabilistic, not binary, for BOTH checks.** One real vendor honored
  the thinking block on only ~13% of generation requests (vs 100% for two competitors). That's
  why `--repeat` defaults to 10; generation's verdict has three states (`fully-implemented`,
  `intermittent (k/N)`, `not-implemented`), history-replay's has its own three-plus states
  (`accepts-thinking-in-history`, `rejects-thinking-in-history`, `inconsistent`, or
  `inconclusive` when errors look unrelated to thinking at all). Never conclude from a single
  sample.
- It forces `Connection: close` per request so a load balancer can't pin all samples to one
  replica and hide the real distribution (a real probe saw 0/10 with keep-alive vs 17/90
  with close on the same endpoint).

## Dimension 4 — Quality / use-case regression (blind judge)

This is two halves on purpose: **collect**, then **judge independently**.

**Step 1 — collect** the model's answers to your use-case library:

```bash
uv run --with openai python scripts/usecase_runner.py \
  --base-url <…/v1> --model <model> --key-env <ENV> \
  --usecases ~/.llm-eval/usecases.json --output-dir ~/.llm-eval/runs/<model>
```

**Step 2 — judge with independent blind judges (orchestrate inline — do NOT let the model
grade itself).** For each answer in the run directory, spawn 3 independent Task agents (or
fewer for a quick pass). Each judge gets ONLY: the prompt, the answer, and the case's
`rubric` — and is explicitly told it is judging in isolation, with no knowledge of other
judges' scores or any prior evaluation (this prevents anchoring). Then aggregate:

- A case **passes** only on majority agreement among judges.
- Compute **precision per category** (using each case's `tags`): a category where judges
  systematically disagree with the rubric is a real weakness — on one real eval, a whole
  category scored 12.5% precision and exposed a systematic misclassification that a single
  grader would have missed.
- **Count only explicit judgments.** A judge that didn't return a verdict is not a pass —
  silence ≠ consent. This guards against automation bias.

For the rubric-scoring mechanics (LLM-as-judge thresholds, `llm-rubric`), you can also
compose with the **promptfoo-evaluation** skill — point its `providers` at the same endpoint.
This harness's blind-judge method and promptfoo's rubric assertions are complementary: use
promptfoo for fast per-case pass/fail gating, blind judges for precision on a category you
suspect is weak. Full method: [references/quality_blind_judge.md](references/quality_blind_judge.md).

## Use-case library

Keep it OUTSIDE this bundle (e.g. `~/.llm-eval/usecases.json`) so it survives skill updates
and never lands in a public repo. It's a plain JSON list — version it in a private repo to
accumulate a regression suite over time:

```json
[
  {"id": "refund-window", "prompt": "A customer asks for a refund 20 days after purchase. Reply as support.",
   "rubric": "1.0 if it correctly cites the 30-day refund window; 0.0 if it refuses or invents a different window.",
   "tags": ["support", "policy"]},
  {"id": "lru-cache", "prompt": "Implement an LRU cache in Python with O(1) get/put.",
   "rubric": "1.0 if get and put are both O(1) via dict + doubly linked list and the self-test passes.",
   "tags": ["code"]}
]
```

`assets/example_usecases.json` is a starter you can copy. Only `id` and `prompt` are required;
`rubric`, `expected`, and `tags` make judging sharper.

## Running a full evaluation

When the user says "evaluate / benchmark this model", the typical flow is:

1. **Identify the shape** — OpenAI-compatible (`/v1/chat/completions`) or Anthropic-Messages
   (`/v1/messages`)? Hit `GET /v1/models` or read the vendor docs; don't assume. This decides
   which probes apply (protocol probe is Anthropic-only). Remember the listing is incomplete
   evidence either way (disciplines §9).
2. **For a new endpoint, availability and fidelity come first** — speed numbers for a model
   whose system prompt never arrives are answering the wrong question.
3. **Run the dimensions the user cares about** — speed and concurrency for "is it fast/stable",
   add protocol for an Anthropic vendor, add quality when they have a use-case suite. Write each
   probe's `--output` JSON to a run directory.
4. **Report honestly, separating measured from inferred.** Lead with the headline the user
   asked about (e.g. "sustained decode ceiling exceeds the vendor's claimed tok/s, while
   real-task throughput runs lower").
   If a number looks impossible (e.g. throughput far above the vendor claim, or a single-sample
   protocol verdict), treat it as a measurement artifact to investigate, not a result — that
   skepticism is the whole point of this harness. Rates on routed gateways are additionally
   time-varying: re-sample another window before freezing any number into a document
   (disciplines §12).
5. **Comparing two models?** Run the identical probes against each with the same flags, and put
   the two JSON outputs side by side. Keep the test conditions identical (same concurrency
   levels, same use cases) or the comparison is meaningless.
6. **Found a vendor bug worth reporting?** Don't paste raw probe output at their support
   channel — build the evidence package per
   [references/vendor_evidence_protocol.md](references/vendor_evidence_protocol.md)
   (self-audit first, observation wording, request-id table, pre-registered thresholds,
   adversarial counter-review).

For tests that will run repeatedly against a live system — deployment gates, resident
canaries, fault-injection mocks, and the monitoring statistics that lie — see
[references/production_testing_patterns.md](references/production_testing_patterns.md).

## Next step

After a run, offer the natural follow-ups:

```
Evaluation complete for <model>.

Options:
A) Render an HTML dashboard of the results — compose with a visualization skill (Recommended if sharing)
B) Compare against another model — same probes, side-by-side
C) Add the failing cases to ~/.llm-eval/usecases.json as a permanent regression guard
D) Done — the numbers answer the question
```
