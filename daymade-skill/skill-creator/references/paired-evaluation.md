---
name: paired-evaluation
description: >-
  Prepare full-eval cases, execute with-Skill/baseline pairs, grade and review outputs, improve and optionally compare blind. Read only after the separate heavy-eval authorization gate passes; use improvement guidance for the selected ordinary evidence plan.
---

# Run the separately authorized evaluation plan

Read cases and pipeline execution only after [the heavy-eval gate](change-verification.md#heavy-eval-authorization-gate--separate-from-tier-classification) passes. Read Improving the skill when applying feedback under any selected tier; it does not authorize paired execution. Read iteration or blind comparison only when that evidence is part of the authorized plan. Honor cancellations throughout, stop when the named uncertainty or deliverable is resolved, then return to ordinary migration verification and delivery.

## Contents

  - [Full-eval test cases (separately authorized paired plan only)](#full-eval-test-cases-separately-authorized-paired-plan-only)
- [Full paired evaluation pipeline (separately authorized only)](#full-paired-evaluation-pipeline-separately-authorized-only)
  - [Step 1: Run the approved with-skill / baseline pairs](#step-1-run-the-approved-with-skill--baseline-pairs)
  - [Step 2: While runs are in progress, draft assertions](#step-2-while-runs-are-in-progress-draft-assertions)
  - [Step 3: As runs complete, capture timing data](#step-3-as-runs-complete-capture-timing-data)
  - [Step 4: Grade, aggregate, and launch the viewer](#step-4-grade-aggregate-and-launch-the-viewer)
  - [What the user sees in the viewer](#what-the-user-sees-in-the-viewer)
  - [Step 5: Read the feedback](#step-5-read-the-feedback)
- [Improving the skill](#improving-the-skill)
  - [How to think about improvements](#how-to-think-about-improvements)
  - [The iteration loop](#the-iteration-loop)
- [Advanced: Blind comparison](#advanced-blind-comparison)

### Full-eval test cases (separately authorized paired plan only)

Enter this section only when the heavy-eval authorization gate passes. Risk tier alone neither authorizes nor forbids this evidence; an explicit full-pipeline request does not reclassify the underlying change. Do not use it merely because a SKILL.md changed. A specialized workflow follows its substitution contract declared above.

For an existing-Skill preservation request, retain the
[required acceptance fixed before evidence selection](change-verification.md#fix-required-acceptance-before-selecting-evidence)
before choosing prompts or tuning the candidate. Bind the approved cases to those
affected jobs and output/performance criteria. Add newly discovered diagnostic
cases as needed; do not replace the original acceptance with easier development
cases or the candidate's successful examples.

After writing the skill draft, come up with 2-3 realistic test prompts — the kind of thing a real user would actually say. **For skills that act on live systems (a running service, a logged-in client, production data), give each test prompt an explicit side-effect budget** — e.g. "probe read-only and conclude; do NOT execute the download / drive the UI." An eval that mutates a live environment while "just testing" is a real action, not a test. Present them via **AskUserQuestion**:

```
Skill draft is ready. Here are [N] test cases I'd like to run:

1. "[test prompt 1]" — tests [what aspect]
2. "[test prompt 2]" — tests [what aspect]
3. "[test prompt 3]" — tests [what aspect]

Each test runs the skill + a baseline (no skill) for comparison.
Estimated time: ~[X] minutes total.

RECOMMENDATION: Run all [N] test cases now.

Options:
A) Run all test cases (Recommended)
B) Run test cases, but let me modify them first
C) Add more test cases before running
D) Skip testing — the skill looks good enough to ship
```

Save test cases to `evals/evals.json`. Don't write assertions yet — just the prompts. You'll draft assertions in the next step while the runs are in progress.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User's task prompt",
      "expected_output": "Description of expected result",
      "files": []
    }
  ]
}
```

See `references/eval_pipeline_schemas.md` for the full schema (including the `assertions` field, which you'll add later).

## Full paired evaluation pipeline (separately authorized only)

Run this section only after the heavy-eval authorization gate passes. The risk tier remains whatever the changed behavior warrants. Execute the pipeline in decision-bearing stages and stop when the uncertainty or requested benchmark deliverable is resolved; do not pre-spawn downstream graders, aggregation, or viewer work. A user cancellation or de-escalation stops the heavy pipeline immediately. Do not use it without authorization or mechanically add generic mechanics that a specialized workflow explicitly replaces, and do not use `/skill-test` or any other testing skill.

Put results in `<skill-name>-workspace/` as a sibling to the skill directory. Within the workspace, organize results by iteration (`iteration-1/`, `iteration-2/`, etc.) and within that, each test case gets a directory (`eval-0/`, `eval-1/`, etc.). Don't create all of this upfront — just create directories as you go.

### Step 1: Run the approved with-skill / baseline pairs

Before making isolated input copies, follow
[materialization-budget.md](materialization-budget.md); export only the
declared paths from the frozen ref and run all arms under their shared budget.

For each approved test case, run one with-skill sample and its baseline under the same prompt and side-effect budget. These two arms intentionally share one failure axis but require isolated contexts; they are necessary experimental units, not extra reviewer roles. State the total arms and capped concurrency before launch. Run serially by default, and never exceed the authorized unit count.

**With-skill run:**

```
Execute this task:
- Skill path: <path-to-skill>
- Task: <eval prompt>
- Input files: <eval files if any, or "none">
- Save outputs to: <workspace>/iteration-<N>/eval-<ID>/with_skill/outputs/
- Outputs to save: <what the user cares about — e.g., "the .docx file", "the final CSV">
```

**Baseline run** (same prompt, but the baseline depends on context):
- **Creating a new skill**: no skill at all. Same prompt, no skill path, save to `without_skill/outputs/`.
- **Improving an existing skill**: the old version captured by the mandatory existing-skill regression gate before the first edit. Point the baseline subagent at that immutable snapshot and save to `old_skill/outputs/`. If no pre-edit snapshot exists, stop and reconstruct an authoritative baseline from Git before continuing; never use the already-edited tree as the old baseline. **Know what this comparison can resolve: it measures only this round's delta.** If the capability you most want to verify already exists in the pre-edit snapshot — a sibling session can commit exactly that fix just before you start — the with/old A/B has zero resolving power for it; pick an older ref as the baseline when that's the capability under test.

Write an `eval_metadata.json` for each test case (assertions can be empty for now). Give each eval a descriptive name based on what it's testing — not just "eval-0". Use this name for the directory too. If this iteration uses new or modified eval prompts, create these files for each new eval directory — don't assume they carry over from previous iterations.

```json
{
  "eval_id": 0,
  "eval_name": "descriptive-name-here",
  "prompt": "The user's task prompt",
  "assertions": []
}
```

### Step 2: While runs are in progress, draft assertions

Don't just wait for the runs to finish — you can use this time productively. Draft quantitative assertions for each test case and explain them to the user. If assertions already exist in `evals/evals.json`, review them and explain what they check.

Good assertions are objectively verifiable and have descriptive names — they should read clearly in the benchmark viewer so someone glancing at the results immediately understands what each one checks. **Write assertions against the intent, not a literal tool path** — "voice content survives into the answer", not "calls the sanctioned reader script". A run that reaches the intent through a different sanctioned route (e.g. reading an archive that already has the transcripts inlined) passes, and grading it as a literal-path failure manufactures a false negative you'll then "fix" in the wrong place. Subjective skills (writing style, design quality) are better evaluated qualitatively — don't force assertions onto things that need human judgment; their real verification paths (historical-task replay, production-as-eval with a write-back habit, render + human review) are listed under question 4 of "Capture Intent".

Update the `eval_metadata.json` files and `evals/evals.json` with the assertions once drafted. Also explain to the user what they'll see in the viewer — both the qualitative outputs and the quantitative benchmark.

### Step 3: As runs complete, capture timing data

Create the run directory before execution so an interrupted attempt remains visible.
When the host exposes actual usage and duration, save those observations promptly
to `timing.json`. Follow [the timing schema](eval_pipeline_schemas.md#timingjson)
for the measurement boundary, source and missing-field handling; do not assume
every host emits the same notification.

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.332,
  "time_scope": "executor",
  "token_scope": "executor"
}
```

Keep unavailable metrics absent or null, and preserve failed/interrupted attempts.
An observed zero is a measurement; missing data is not zero. Do not substitute
output characters for tokens or an executor duration for end-to-end delivery time.

### Step 4: Grade, aggregate, and launch the viewer

Once all runs are done:

1. **Grade each run** — spawn a grader subagent (or grade inline) that reads `agents/grader.md` and evaluates each assertion against the outputs. Save results to `grading.json` in each run directory. The grading.json expectations array must use the fields `text`, `passed`, and `evidence` (not `name`/`met`/`details` or other variants) — the viewer depends on these exact field names. For assertions that can be checked programmatically, write and run a script rather than eyeballing it — scripts are faster, more reliable, and can be reused across iterations. **But objective grep/script assertions cut both ways** (same-word-different-meaning false hits, wording-difference misses), so **benchmark pass-rate is a signal, not a verdict**: spot-check what each assertion actually matched, and watch for a baseline run that reveals a factual error in the skill itself (the "wait, the data IS in the API" moment). See methodology §5.3–5.6 + §6.4.

2. **Aggregate into benchmark** — run the aggregation script from the skill-creator directory:
   ```bash
   uv run --frozen python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```
   This produces `benchmark.json` and `benchmark.md` with pass_rate, time, and tokens for each configuration, with mean +/- stddev and the delta. If generating benchmark.json manually, see `references/eval_pipeline_schemas.md` for the exact schema the viewer expects.
Bind candidate and baseline explicitly when their names are custom or ambiguous,
using `--candidate <config> --baseline <config>`. Inspect per-metric coverage and
`comparison.status`; directory order and a successful CLI exit do not prove a
complete paired comparison. Withhold benefit claims when the relevant observations
or task outcomes are unresolved.

3. **Do an analyst pass** — read the benchmark data and surface patterns the aggregate stats might hide. See `agents/analyzer.md` (the "Analyzing Benchmark Results" section) for what to look for — things like assertions that always pass regardless of skill (non-discriminating), high-variance evals (possibly flaky), and time/token tradeoffs.

4. **Launch the viewer** with both qualitative outputs and quantitative data:
   ```bash
   cd <skill-creator-path>
   nohup uv run --frozen python eval-viewer/generate_review.py \
     <workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <workspace>/iteration-N/benchmark.json \
     > /dev/null 2>&1 &
   VIEWER_PID=$!
   ```
   For iteration 2+, also pass `--previous-workspace <workspace>/iteration-<N-1>`.

   **If the backgrounded viewer strands itself**: the process stays alive but nothing is listening — check with `lsof -a -p $VIEWER_PID -iTCP -sTCP:LISTEN` (empty) or curl the URL (fails); "no log output" is NOT a usable signal here because the launch line above redirects it to `/dev/null`. Kill it and fall back to `--static` rather than re-launching the same way.

   **Cowork / headless environments:** If `webbrowser.open()` is not available or the environment has no display, use `--static <output_path>` to write a standalone HTML file instead of starting a server. Feedback will be downloaded as a `feedback.json` file when the user clicks "Submit All Reviews". After download, copy `feedback.json` into the workspace directory for the next iteration to pick up.

Note: please use generate_review.py to create the viewer; there's no need to write custom HTML.
The generator reads the bundled [viewer template](../eval-viewer/viewer.html);
use its matching version for nullable benchmark data, as the schema requires.

5. **Tell the user** via **AskUserQuestion**:

```
Results are ready! I've opened the eval viewer in your browser.

- "Outputs" tab: click through each test case, leave feedback in the textbox
- "Benchmark" tab: quantitative comparison (pass rates, timing, tokens)

Take your time reviewing. When you're done, come back here.

RECOMMENDATION: Review the Outputs tab first — your qualitative feedback drives the next iteration more than the numbers do.

Options:
A) I've finished reviewing — read my feedback and improve the skill
B) I have questions about the results before giving feedback
C) Results look good enough — skip iteration, let's package the skill
D) Results need major rework — let's discuss before iterating
```

### What the user sees in the viewer

The "Outputs" tab shows one test case at a time:
- **Prompt**: the task that was given
- **Output**: the files the skill produced, rendered inline where possible
- **Previous Output** (iteration 2+): collapsed section showing last iteration's output
- **Formal Grades** (if grading was run): collapsed section showing assertion pass/fail
- **Feedback**: a textbox that auto-saves as they type
- **Previous Feedback** (iteration 2+): their comments from last time, shown below the textbox

The "Benchmark" tab shows the stats summary: pass rates, timing, and token usage for each configuration, with per-eval breakdowns and analyst observations.

Navigation is via prev/next buttons or arrow keys. When done, they click "Submit All Reviews" which saves all feedback to `feedback.json`.

### Step 5: Read the feedback

When the user tells you they're done, read `feedback.json`:

```json
{
  "reviews": [
    {"run_id": "eval-0-with_skill", "feedback": "the chart is missing axis labels", "timestamp": "..."},
    {"run_id": "eval-1-with_skill", "feedback": "", "timestamp": "..."},
    {"run_id": "eval-2-with_skill", "feedback": "perfect, love this", "timestamp": "..."}
  ],
  "status": "complete"
}
```

Empty feedback means the user thought it was fine. Focus your improvements on the test cases where the user had specific complaints.

Kill the viewer server when you're done with it:

```bash
kill $VIEWER_PID 2>/dev/null
```

---

## Improving the skill

This is the heart of the loop. Improve from the evidence plan: authoritative facts and deterministic checks for Tier 1, 1–2 named behavior replays for Tier 2, or user-reviewed paired results when the separate heavy-eval gate authorizes them at any tier. Do not import paired-eval artifacts into the default Tier 1/2 path without that authorization.

### How to think about improvements

1. **Generalize from the feedback.** The big picture thing that's happening here is that we're trying to create skills that can be used a million times (maybe literally, maybe even more who knows) across many different prompts. Here you and the user are iterating on only a few examples over and over again because it helps move faster. The user knows these examples in and out and it's quick for them to assess new outputs. But if the skill you and the user are codeveloping works only for those examples, it's useless. Rather than put in fiddly overfitty changes, or oppressively constrictive MUSTs, if there's some stubborn issue, you might try branching out and using different metaphors, or recommending different patterns of working. It's relatively cheap to try and maybe you'll land on something great.

2. **Keep the prompt lean without deleting the contract.** Remove things that aren't pulling their weight, but treat every deletion from an existing skill as a regression candidate until the old-vs-new audit classifies it. Move detailed but reusable behavior into a directly linked reference; do not leave it only in evals, a changelog, or your memory. Read the transcripts, not just final outputs—if the skill causes unproductive work, simplify the instruction and rerun the old capability cases rather than assuming fewer words means better behavior.

3. **Explain the why.** Try hard to explain the **why** behind everything you're asking the model to do. Today's LLMs are *smart*. They have good theory of mind and when given a good harness can go beyond rote instructions and really make things happen. Even if the feedback from the user is terse or frustrated, try to actually understand the task and why the user is writing what they wrote, and what they actually wrote, and then transmit this understanding into the instructions. If you find yourself writing ALWAYS or NEVER in all caps, or using super rigid structures, that's a yellow flag — if possible, reframe and explain the reasoning so that the model understands why the thing you're asking for is important. That's a more humane, powerful, and effective approach.

4. **Look for repeated work — in the eval transcripts AND in whatever conversation the skill was distilled from.** Read the transcripts from the test runs and notice if the subagents all independently wrote similar helper scripts or took the same multi-step approach to something. If all 3 test cases resulted in the subagent writing a `create_docx.py` or a `build_chart.py`, that's a strong signal the skill should bundle that script. Write it once, put it in `scripts/`, and tell the skill to use it. This saves every future invocation from reinventing the wheel. The same signal hides in a source conversation you distilled a skill from — code that session wrote even once is code every future run must rewrite; don't wait for eval runs to prove the repetition (skills whose eval loop is skipped never get that proof — the [Scripts check](existing-skill-migration.md#validation-and-escalation-probes) is the catch-point for those).

5. **Fold corrections back verbatim — same session, both levels.** For taste-calibrated skills the user's corrections ARE the eval set, but only if they land where a future run will read them. Two properties make the write-back converge: (a) **record the correction verbatim**, not paraphrased — exact words carry calibration signal a summary flattens ("绝对禁止这种东西" teaches a hard boundary; "user prefers fewer jumps" does not). Quote the words inside the rule they correct, with a date. (b) **Write back in the same session the correction happens, at both levels** — fix the artifact AND the skill's rule/reference/component; a correction that only fixes the artifact is invisible to every future run, and one deferred to "later" usually never lands. While writing it back, check whether the skill's own text *taught* the anti-pattern just banned — a correction often falsifies an existing instruction, and leaving the old advice standing guarantees recurrence (real case: a decision-page contract advised jump-style "goto anchors to the referenced figure"; the user banned exactly that, so the write-back had to amend the old sentence, not just add a new rule beside it). When the corrected thing is an interaction fragment, the write-back's final step is shelf promotion — see the [Component-shelf check](existing-skill-migration.md#validation-and-escalation-probes).

This task is pretty important (we are trying to create billions a year in economic value here!) and your thinking time is not the blocker; take your time and really mull things over. I'd suggest writing a draft revision and then looking at it anew and making improvements. Really do your best to get into the head of the user and understand what they want and need.

For Tier 1, apply an unambiguous evidence-backed correction directly; ask only when the evidence leaves a real choice. For Tier 2 or Tier 3, when user feedback exposes a meaningful design fork, present the improvement plan via **AskUserQuestion**:

```
I've read the feedback from [N] test cases. [X] had specific complaints, [Y] looked good.

Key issues:
- [Issue 1]: [plain-language summary]
- [Issue 2]: [plain-language summary]

RECOMMENDATION: [strategy] because [reason]

Options:
A) Iterative refinement — targeted fixes for the specific issues above (Recommended)
B) Structural redesign — the core approach needs rethinking (reclassifies Tier 1/2 work to Tier 3 before changing it)
C) Bundle a script — I noticed all test runs independently wrote similar code for [X] (reclassifies Tier 1/2 work to Tier 3 before adding the capability)
D) Expand test set first — add [N] more test cases to avoid overfitting (authorizes only the named extra evidence; risk tier still follows the changed behavior)
```

Selecting B or C may change the risk tier because it changes the implementation scope; selecting D does not. Each option authorizes only the named scope/evidence change. It does not authorize paired baselines, graders, benchmarks, a viewer, or additional roles unless those are named and the separate heavy-eval/fan-out gate passes.

### The iteration loop

After improving the skill:

1. Apply your improvements to the skill
2. Re-run the default tier evidence, plus any separately authorized evidence plan:
   - **Tier 1 default:** always re-run `quick_validate`, diff inspection, and the migration gate; then re-run only the matching subtype evidence — (a) exact readback/format check, (b) authoritative fact plus its narrow check, or (c) explicit existing contract plus deterministic regression. Do not create an iteration workspace unless a separate paired plan is authorized.
   - **Tier 2 default:** re-run only the same 1–2 named with-skill examples and narrow checks. Do not add a baseline, benchmark, viewer, or eval workspace unless a separate paired plan is authorized.
   - **Separately authorized generic paired run, at any tier:** rerun all approved test cases into a new `iteration-<N+1>/` directory, including baseline runs. For a new skill, the baseline is always `without_skill`; for an existing skill, the immutable original pre-edit version remains the preservation baseline for every iteration. An immediately previous iteration may supplement but never replace the original baseline.
3. Apply discipline #5 after a substantive rule, contract, or number change. For a separately authorized generic paired run, also launch the eval reviewer with `--previous-workspace` pointing at the previous iteration; specialized workflows use their declared reviewer mechanics.
4. For a separately authorized generic paired run, wait for the user to review the new viewer results; otherwise decide from the default tier evidence unless a real user choice remains.
5. Read the new evidence or feedback, improve again if it falsifies the current version, and repeat at the same tier.

A user-requested cancellation or de-escalation remains in force for the rest of the task without changing its classification. Do not restart paired evals, baselines, graders, aggregation, or viewer work unless the user explicitly re-authorizes that evidence plan.

At the end of each **separately authorized generic paired** iteration, use **AskUserQuestion** as a checkpoint:

```
Iteration [N] complete. Results: [pass_rate]% assertions passing, [delta vs previous].

RECOMMENDATION: [Continue / Accept / Revert] because [one-line reason from the delta and remaining feedback].

Options:
A) Continue iterating — I see more room for improvement
B) Accept this version — it's good enough, let's move to packaging
C) Revert to previous iteration — this round made things worse
D) Run blind comparison — rigorously compare this version vs the previous one
```

Keep going until:
- The user says they're happy
- The feedback is all empty (everything looks good)
- You're not making meaningful progress

---

## Advanced: Blind comparison

For situations where you want a more rigorous comparison between two versions of a skill (e.g., the user asks "is the new version actually better?"), there's a blind comparison system. Read `agents/comparator.md` and `agents/analyzer.md` for the details. The basic idea is: give two outputs to an independent agent without telling it which is which, and let it judge quality. Then analyze why the winner won.

This is optional, requires subagents, and most users won't need it. The human review loop is usually sufficient.

Use [host-adaptations.md](host-adaptations.md) only for actual missing subagent/display/CLI capabilities. Preserve the selected source identity, task outcome, side-effect budget and completion responsibility across that adaptation.

For historical evidence behind these procedures, inspect [developer-casebook.md](developer-casebook.md) only when investigating that failure.

Resolve numbered standing-discipline citations using [their named owners](change-verification.md#shared-discipline-names); the owning contract supplies the conditions and stopping rule.
