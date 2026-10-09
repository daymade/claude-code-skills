---
name: description-triggering
description: >-
  Build realistic trigger evaluations and diagnose infrastructure silence, competitor loss or low-threshold self-execution. Read after an observed miss/misfire, before running a separately authorized description loop and before accepting its result.
---

# Diagnose and optimize actual Skill triggering

Start with Description Optimization and How skill triggering works to decide whether the probe can measure this Skill. Use query generation and user review only for an authorized optimizer run. Read the full optimization-loop section before launch or accepting best_description: its error, silence, near-zero recall and repeat-count conditions are part of result interpretation. Stop a structurally blind probe and use its declared interactive/output verification path; otherwise return the accepted description to the normal edit/migration/release gates.

## Contents

- [Description Optimization](#description-optimization)
  - [Step 1: Generate trigger eval queries](#step-1-generate-trigger-eval-queries)
  - [Step 2: Review with user](#step-2-review-with-user)
  - [Step 3: Run the optimization loop](#step-3-run-the-optimization-loop)
  - [How skill triggering works](#how-skill-triggering-works)
  - [Step 4: Apply the result](#step-4-apply-the-result)

## Description Optimization

The description field in SKILL.md frontmatter is the primary mechanism that determines whether Claude invokes a skill. This loop is optional and not a default step: use it only when real sessions have shown the skill missing or misfiring, and build the eval set from those real prompts. Most description problems are fixed faster by editing the description by hand against the rules in the frontmatter section.

### Step 1: Generate trigger eval queries

Create 20 eval queries — a mix of should-trigger and should-not-trigger. Save as JSON:

```json
[
  {"query": "the user prompt", "should_trigger": true},
  {"query": "another prompt", "should_trigger": false}
]
```

The queries must be realistic and something a Claude Code or Claude.ai user would actually type. Not abstract requests, but requests that are concrete and specific and have a good amount of detail. For instance, file paths, personal context about the user's job or situation, column names and values, company names, URLs. A little bit of backstory. Some might be in lowercase or contain abbreviations or typos or casual speech. Use a mix of different lengths, and focus on edge cases rather than making them clear-cut (the user will get a chance to sign off on them).

Bad: `"Format this data"`, `"Extract text from PDF"`, `"Create a chart"`

Good: `"ok so my boss just sent me this xlsx file (its in my downloads, called something like 'Q4 sales final FINAL v2.xlsx') and she wants me to add a column that shows the profit margin as a percentage. The revenue is in column C and costs are in column D i think"`

For the **should-trigger** queries (8-10), think about coverage. You want different phrasings of the same intent — some formal, some casual. Include cases where the user doesn't explicitly name the skill or file type but clearly needs it. Throw in some uncommon use cases and cases where this skill competes with another but should win.

For the **should-not-trigger** queries (8-10), the most valuable ones are the near-misses — queries that share keywords or concepts with the skill but actually need something different. Think adjacent domains, ambiguous phrasing where a naive keyword match would trigger but shouldn't, and cases where the query touches on something the skill does but in a context where another tool is more appropriate.

The key thing to avoid: don't make should-not-trigger queries obviously irrelevant. "Write a fibonacci function" as a negative test for a PDF skill is too easy — it doesn't test anything. The negative cases should be genuinely tricky.

### Step 2: Review with user

Present the eval set to the user for review using the HTML template:

1. Read the template from `assets/eval_review.html`
2. Replace the placeholders:
   - `__EVAL_DATA_PLACEHOLDER__` → the JSON array of eval items (no quotes around it — it's a JS variable assignment)
   - `__SKILL_NAME_PLACEHOLDER__` → the skill's name
   - `__SKILL_DESCRIPTION_PLACEHOLDER__` → the skill's current description
3. Write to a temp file (e.g., `/tmp/eval_review_<skill-name>.html`) and open it: `open /tmp/eval_review_<skill-name>.html`
4. The user can edit queries, toggle should-trigger, add/remove entries, then click "Export Eval Set"
5. The file downloads to `~/Downloads/eval_set.json` — check the Downloads folder for the most recent version in case there are multiple (e.g., `eval_set (1).json`)

This step matters — bad eval queries lead to bad descriptions.

### Step 3: Run the optimization loop

Tell the user: "This will take some time — I'll run the optimization loop in the background and check on it periodically."

Save the eval set to the workspace, then run in the background:

```bash
cd <skill-creator-path>
uv run --frozen python -m scripts.run_loop \
  --eval-set <path-to-trigger-eval.json> \
  --skill-path <path-to-skill> \
  --model <model-id-powering-this-session> \
  --max-iterations 5 \
  --verbose
```

Use the model ID from your system prompt (the one powering the current session) so the triggering test matches what the user actually experiences.

While it runs, periodically tail the output to give the user updates on which iteration it's on and what the scores look like.

This handles the full optimization loop automatically. It splits the eval set into 60% train and 40% held-out test, evaluates the current description (running each query 3 times to get a reliable trigger rate), then calls Claude to propose improvements based on what failed. It re-evaluates each new description on both train and test, iterating up to 5 times. When it's done, it opens an HTML report in the browser showing the results per iteration and returns JSON with `best_description` — selected by test score rather than train score to avoid overfitting.

**The loop self-aborts after iteration 1 if it detects total silence — you don't have to catch this by hand.** This is a code-level guard in `run_loop.py`, not just advice, and it distinguishes two causes of "iteration 1 came back with zero triggers on every should-trigger query":

- `exit_reason: "infra_error: ..."` — some query executions (should-trigger *or* not-should-trigger) raised exceptions (claude CLI not on PATH, timeout too short, network down) rather than cleanly returning "no trigger." Checked *first*, and deliberately fires on any nonzero error count, even a single flaky run out of dozens — a crash, however rare, is a more specific and actionable lead than "nothing fired," and the fix is environmental, not a description rewrite. The ratio in the message (e.g. `3/15`) is the read on severity: a large fraction means "stop, fix your environment"; a small fraction alongside a lot of clean 0-trigger runs means the environment probably has a minor flake worth checking *and* the description may genuinely be bad — check both. Check stderr for `Warning: query failed` lines either way.
- `exit_reason: "degenerate_harness: ..."` — checked only once the branch above rules out any execution errors, so this means every should-trigger *and* not-should-trigger query *actually ran* and *still* fired zero times (this is what "precision=100%" via a zero-denominator default actually means: not "perfect," but "nothing to divide"). The probe genuinely measures nothing — go diagnose competitor collision or a low-threshold domain (below) before touching the description at all.

Both checks run **only against iteration 1**, and **only when zero should-trigger queries fired** — a weak-but-nonzero iteration 1 (say 1/9 triggers) is a different, potentially-recoverable case and is deliberately left to iterate. `degenerate_harness` additionally requires not-should-trigger queries to have fired zero times too: if the description is merely polarity-inverted — missing every positive while accidentally matching several negatives — the probe is proven to work and `improve_description` has real gradient to act on, so the guard does not abort that case (only a genuinely dead probe does). And it requires zero execution errors on *either* side — a not-should-trigger query that raised an exception never actually ran, so its "0 triggers" can't be used as evidence the probe is dead; that's exactly what routes to `infra_error` instead. Either way it breaks immediately and skips `improve_description` entirely — the JSON and HTML still report `best_description`/`best_score` normally (nothing is suppressed), the exit reason is the signal that this particular run's numbers shouldn't be read as "this is a good description." (Real case, 2026-08: a full 5-iteration loop was launched with no pre-check; two complete iterations — each a full eval batch, minutes of wall time and dozens of `claude -p` subprocess calls — came back precision=100%/recall=0%/identical scores before anyone looked at the numbers, and every should-trigger *and* not-should-trigger query alike had fired zero times. The failure was diagnosable from iteration 1 alone; nothing in iterations 2+ added information.) The HTML report also renders a banner when either exit reason fires, so the browser view carries the same signal as the JSON/stderr, not just the two lower-visibility channels. (An earlier draft of this guard checked should-trigger triggers alone; two rounds of independent review — a fresh agent each round, the second checking the first round's fixes rather than re-covering old ground — constructed the polarity-inverted counter-example, the infra-vs-description ambiguity, the negative-side-errors gap, and a pre-existing `--holdout 0` report crash it surfaced along the way, all fixed before shipping.)

One caveat this guard can't cover: with `--runs-per-query 1` (the default is 3), a single should-trigger query with a genuinely-50%-ish trigger rate has a real chance of reading 0/1 by chance alone and tripping the guard on noise, not on a dead probe. The default `runs_per_query=3` is what makes "zero across every repeat of every positive query" a strong signal — if you override it down, this guard's false-positive risk goes up with it.

**Sanity-check the harness before you trust `best_description` — it can still return hollow output even when neither guard above fired.** Both checks only catch a *total* failure at iteration 1; a harness can also limp along with a persistently weak-but-nonzero signal across all 5 iterations without ever tripping either one. If every iteration reports **recall staying near 0% with identical or near-identical scores** past iteration 1, that's the same underlying problem the guards couldn't rule out — the "winning" description is usually just noise around iteration 1 unchanged. Before applying any `best_description`, run one obviously-should-trigger query yourself and confirm recall > 0. A recall-flat result across iterations means the harness is a hidden variable (commonly: the skill is losing the trigger to installed competitors — see Coexistence below) — do NOT apply its "best"; hand-author the description and verify it with real probes instead. (methodology Cases 12, 14) There is a second recall-0 root cause, distinct from competitor loss: the skill's task domain is *low-threshold* — the model does the job itself and never consults any skill — spelled out at the end of *How skill triggering works* below. Distinguish the two before reacting, because the fixes are opposite: a competitor is fixed by precedence/supersede, a low-threshold domain by abandoning the trigger probe entirely for production-as-eval.

**When you probe triggering yourself with `claude -p`, collect ALL skill calls in the run, not just the first — and remember tool-invocation is a proxy.** A `UserPromptSubmit`/`SessionStart` hook can inject an unrelated skill *before* the model chooses, so an "exit on the first Skill call" probe will misreport a false "didn't trigger." And "did it call the Skill tool" is not the same as "did the skill's content shape the output" (the model may read the skill without a visible Skill call) nor "is the output correct." A buggy probe is itself a hidden variable that keeps you optimizing against a wrong conclusion.

### How skill triggering works

Understanding the triggering mechanism helps design better eval queries. Skills appear in Claude's `available_skills` list with their name + description, and Claude decides whether to consult a skill based on that description. The important thing to know is that Claude only consults skills for tasks it can't easily handle on its own — simple, one-step queries like "read this PDF" may not trigger a skill even if the description matches perfectly, because Claude can handle them directly with basic tools. Complex, multi-step, or specialized queries reliably trigger skills when the description matches — with one systematic exception (a low-threshold task domain) spelled out at the end of this section.

This means your eval queries should be substantive enough that Claude would actually benefit from consulting a skill. Simple queries like "read file X" are poor test cases — they won't trigger skills regardless of description quality.

**But some skills fail this test for a reason no query rewrite can fix — the skill's whole *job* is a low-threshold task.** The paragraph above blames the query ("write a more substantial one"); this is the orthogonal case, where the skill's *domain* is what blocks triggering. If a skill exists to do something Claude will just do itself with a basic tool — convert audio to 16 kHz, downsample, extract one field, bulk-rename — then even a fully-specified query ("downsample this 48k stereo wav to 16k mono for whisper," path and all) won't trigger it: the model reaches straight for `Bash`/`ffmpeg` and never consults any skill. Query substance can't fix this, because the "I can just do this" judgment is about the *task*, not the wording.

Diagnose it before you burn an optimization loop: run one realistic query through `claude -p` and watch whether the model *ever* consults the skill across the whole run (per the ALL-skill-calls rule above), or goes straight to `Bash` and does the job itself. If it never consults, the trigger probe is structurally blind to this skill — recall reads ~0 no matter what you write, and that zero measures the model's do-it-myself reflex, not your description. Stop tuning against `claude -p` recall and verify the real way: production-as-eval (the user's next real, *interactive* use — headless `-p` is more action-biased than a real session and systematically under-reports triggering), plus output comparison where the skill produces a checkable artifact. (Observed on an audio-preprocessing skill: a headless run_eval sweep read recall 0 on *every* query — including an obvious "transcribe this recording" one — and a manual `claude -p` probe showed the model going straight to `Bash` to find and process the file, `Skill`=0 across the run. The zero measured headless action-bias, not the description; the real signal only shows up in interactive use.)

### Step 4: Apply the result

Take `best_description` from the JSON output and update the skill's SKILL.md frontmatter. Show the user before/after and report the scores.

For ordinary frontmatter shortening, use [the authoring rule](authoring-and-reuse.md#write-the-skillmd); preserve each distinct trigger job through [existing-skill-migration.md](existing-skill-migration.md). A failed trigger probe is not automatically evidence that the description needs rewriting.

For historical evidence behind these procedures, inspect [developer-casebook.md](developer-casebook.md) only when investigating that failure.
