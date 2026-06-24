# Quality dimension — the blind-judge method

Speed and concurrency are objective; quality is not. The honest way to measure it without
fooling yourself is to separate **collecting** answers from **judging** them, and to make the
judging independent and adversarial rather than self-confirming.

## Why not just ask the model (or one grader) to score?

A model grading its own output anchors on having produced it. A single external grader anchors
on whatever it saw first. Both drift optimistic. The fix is plural, isolated judgment plus a
precision statistic that exposes systematic error.

## The method

**1. Collect (deterministic, scripted).** `usecase_runner.py` runs every case in your library
and saves one file per answer: `{prompt, answer, reasoning, rubric, tags}`. Keep `reasoning`
separate so a reasoning model's chain-of-thought isn't judged as if it were the answer.

**2. Judge blind (N independent agents).** For each answer, spawn 3 judges (fewer for a quick
pass, 5 when a category looks shaky). Each judge receives ONLY the prompt, the answer, and that
case's `rubric`, plus an explicit instruction: *you are judging in isolation; you have no
knowledge of other judges' scores or any prior evaluation; score strictly against the rubric.*
That isolation clause is what prevents the judges from converging on a wrong consensus.

**3. Aggregate with precision, not just a pass count.**
- A case **passes** only on majority agreement.
- Compute **precision per category** using each case's `tags`. A category where the judges
  systematically disagree with the rubric is a real weakness, not noise. On one real evaluation a
  whole category scored **12.5% precision** — it turned out one kind of input was being
  systematically misclassified, which a single overall pass-rate had completely hidden.
- **Silence ≠ consent.** Only an explicit verdict counts. A judge that returned nothing is not a
  pass — counting non-responses as passes is automation bias and inflates the score.

## Accumulate ground truth so the eval gets sharper over time

The point of a use-case library is that it compounds. When a human reviews and corrects a
judgment, record it as ground truth (a `gt.jsonl` keyed by case id) in a **private** repo. On the
next run:
- Cases a human already judged use the human label directly and skip re-judging — cheaper, and
  human verdicts are never overwritten by a model.
- Report "fraction not yet human-confirmed" as a trust-floor metric.

Two rules that keep accumulated labels valid:
- **Freeze category ids — only ever add new ones (7, 8, …), never reuse a retired id.** Otherwise
  old human labels silently mean something different.
- When you change the rubric or add a category, you don't have to re-judge everything — re-judge
  only the cases plausibly affected (a whitelist) and explicitly carry forward the rest. On a real
  suite this cut a re-evaluation from full cost to roughly a fifth.

## Division of labor with promptfoo-evaluation

These compose; they don't compete:
- **promptfoo `llm-rubric`** — fast per-case pass/fail gating across many cases and models, with a
  single grader and a numeric threshold. Good for the regular regression sweep. Point its
  `providers` at the same endpoint you're probing.
- **Blind judges (this method)** — slower, plural, isolated; reserve it for a category you suspect
  is weak or a result you don't trust, where precision matters more than throughput.

A practical pattern: run promptfoo for the broad sweep, then escalate any category below your
pass-rate bar to a blind-judge precision pass.

## Judge prompt template

Give each blind-judge agent exactly this shape (fill the braces), and nothing about other judges
or history:

```
You are independently grading one model answer. You have no knowledge of any other
grader's verdict or any previous evaluation — judge only what is below, strictly
against the rubric.

PROMPT:
{prompt}

MODEL ANSWER:
{answer}

RUBRIC:
{rubric}

Return: a score in [0,1], a one-line reason, and the single most decisive piece of
evidence from the answer. If the answer is empty or off-task, score 0 — do not abstain.
```
