---
name: llm-eval-harness
description: >-
  Evaluate any LLM behind an OpenAI- or Anthropic-compatible endpoint across four
  dimensions: speed (TTFT + thinking-aware tokens/sec), concurrency/stability (success
  rate, p50/p90 latency, the level where it breaks), Anthropic protocol compliance
  (thinking-block trigger rate), and quality regression against your own accumulated
  use cases (blind-judge precision). Use whenever someone wants to benchmark, 测评, or
  压测 a model, verify a vendor's tokens-per-second claim, compare two
  models head-to-head, decide whether a newly released model is fast/stable/good enough
  before adopting it, measure TTFT or decode throughput, probe concurrency limits before
  a workshop or batch job, or check whether an "Anthropic-compatible" endpoint really
  implements thinking blocks. Triggers on "benchmark this model", "测一下这个模型的速度/
  质量", "is X tok/s real", "compare model A vs B", "这个模型能不能扛住并发", "接入新模型
  先测一下", even without the word "eval".
---

# LLM Eval Harness

## Overview

Give this skill an endpoint (`base_url` + `model` + an API key in an env var) and it
measures whether the model is actually fast, stable, protocol-correct, and good enough —
instead of trusting the vendor's headline numbers. It unifies four evaluation dimensions
that are usually scattered across ad-hoc scripts:

| Dimension | Script | Answers |
|---|---|---|
| **Speed** | `scripts/speed_probe.py` | TTFT + sustained decode tok/s, **thinking-aware** |
| **Concurrency / stability** | `scripts/concurrency_probe.py` | success rate, p50/p90 latency, where it breaks |
| **Protocol compliance** | `scripts/protocol_probe.py` | does the Anthropic `thinking` block actually fire (N≥10)? |
| **Quality / use-case regression** | `scripts/usecase_runner.py` + blind judges | does it pass *your* accumulated cases? |

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
(below). Pick dimensions by what the user actually asked — don't run all four if they only
asked "is it fast?".

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

## Dimension 3 — Protocol compliance (Anthropic thinking block)

```bash
uv run python scripts/protocol_probe.py \
  --url <…/v1/messages> --model <model> --key-env <ENV> --repeat 10 --output /tmp/proto.json
```

- Only relevant for endpoints claiming Anthropic `/v1/messages` compatibility. It checks
  whether `thinking: {type: enabled}` actually produces `thinking_delta` / `signature_delta`
  SSE events.
- **Compliance is often probabilistic, not binary.** One real vendor honored the thinking
  block on only ~13% of requests (vs 100% for two competitors). That's why `--repeat`
  defaults to 10 and the verdict has three states: `fully-implemented`, `intermittent
  (k/N)`, `not-implemented`. Never conclude from a single sample.
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
   which probes apply (protocol probe is Anthropic-only).
2. **Run the dimensions the user cares about** — speed and concurrency for "is it fast/stable",
   add protocol for an Anthropic vendor, add quality when they have a use-case suite. Write each
   probe's `--output` JSON to a run directory.
3. **Report honestly, separating measured from inferred.** Lead with the headline the user
   asked about (e.g. "sustained decode ceiling exceeds the vendor's claimed tok/s, while
   real-task throughput runs lower").
   If a number looks impossible (e.g. throughput far above the vendor claim, or a single-sample
   protocol verdict), treat it as a measurement artifact to investigate, not a result — that
   skepticism is the whole point of this harness.
4. **Comparing two models?** Run the identical probes against each with the same flags, and put
   the two JSON outputs side by side. Keep the test conditions identical (same concurrency
   levels, same use cases) or the comparison is meaningless.

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
