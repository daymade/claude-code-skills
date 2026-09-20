# tech-selection trigger evals

14 samples (7 positive / 7 negative) for `run_eval.py`, plus the two machine
corrections this machine requires and the measured baseline.

## Run it

```bash
cd <repo>/daymade-skill/skill-creator
rm -rf /tmp/ts-eval-config && mkdir -p /tmp/ts-eval-config
CLAUDE_CONFIG_DIR=/tmp/ts-eval-config uv run --no-project python -m scripts.run_eval \
  --eval-set <repo>/daymade-claude-code/tech-selection/evals/trigger-evals.json \
  --skill-path <repo>/daymade-claude-code/tech-selection \
  --num-workers 10 --runs-per-query 3 --timeout 120 --verbose
```

## Two corrections this machine requires — skip them and the score lies

1. **`python -m scripts.run_eval`, not `python scripts/run_eval.py`.** The direct
   path exits 1 with `ModuleNotFoundError: No module named 'scripts'`.
2. **An empty `CLAUDE_CONFIG_DIR`, and `--timeout 120`.** The default eval form
   stages a synthetic command file and only accepts that synthetic name, but this
   machine's profile always has the real plugin loaded, so a positive query fires
   the *real* skill and the synthetic name never matches — positives go
   systematically false-negative (measured 1/2 on a 2-sample smoke). Separately,
   the default `--timeout 30` is below this machine's latency floor (a trivial
   answer takes 33s), and a timeout is scored `trigger=False` rather than an
   error — so it biases positives to false-fail and negatives to false-pass at
   the same time. Isolating the config removes the first bias; raising the
   timeout removes the second.

Both biases push toward "the skill does not fire", which is the one conclusion a
trigger eval must never reach by instrumentation error.

## Measured baseline (2026-09-20, 3 runs per sample)

14/14 pass under `run_eval`'s own threshold (positive rate ≥ 0.5, negative < 0.5).
The score is an **upper bound**, not the production truth:

| Sample | Isolated | Production |
|---|---|---|
| 「要不要自己造向量检索模块，还是用现成的框架？先看看有没有现成的，别闭门造车。」 | 3/3 | fires (Skill tool_use, success) |
| 「这个配置存哪里比较好，JSON 文件还是 SQLite？」 | 3/3 | **does not fire** |
| 「我打算把用户事件直接写进 Postgres 一张宽表，这是最佳实践吗？帮我 review 这个设计。」 | 2/3 | untested |
| 「对比一下 AWS、GCP、Azure 的 GPU 实例价格，按性价比排个序」 (negative) | 1/3 → **0/6 on re-run** | untested |
| 「读一下 tech-selection 的 SKILL.md，帮我 review 它的 Step 4 Gate 写得好不好」 (negative) | 1/3 → **0/6 on re-run** | untested |

The two negatives that leaked once each were re-run at `--runs-per-query 6` and
returned 0/6 apiece, so the original 1/3 was noise rather than a boundary defect.
Re-raise the run count before treating a single firing as a real leak.

Three things that score hides:

- **The 「存哪里」 divergence is deliberate and unresolved.** The description
  lists 存哪里 as a trigger, and the isolated condition fires it 3/3, while
  production answers it directly as a simple question. Keep the sample so the gap
  stays visible as data instead of becoming an assumption.
- **A single firing is not a boundary defect.** A GPU price comparison (which the
  description explicitly excludes) and a "review this SKILL.md" self-reference each
  fired 1 of 3 runs in the first pass, and both pass on the 0.5 threshold. Re-run at
  `--runs-per-query 6` returned 0/6 for each, so the first pass was noise. Raise the
  run count before editing the description — the cost of wrongly narrowing the
  trigger surface is a skill that never fires, which no score reports.
- **Triggering is semantic, not keyword.** The 「存哪里」 query contains the
  description's literal trigger phrase and still did not fire in production, while
  a query built from 自己造 / 现成的 / 闭门造车 did. The same literal phrase
  appears on both sides of the trigger boundary, so a grep of the description
  against a query predicts nothing.

## Before trusting any score

Three free mechanical checks (no API cost) decide whether the run means anything:

```bash
diff ~/.claude/plugins/cache/daymade-skills/daymade-claude-code/<version>/tech-selection/SKILL.md \
     <repo>/daymade-claude-code/tech-selection/SKILL.md  # empty = cache fresh
claude plugin list | grep -A3 'daymade-claude-code@daymade-skills'   # Status: enabled
cd /tmp && timeout 90 env -u CLAUDECODE claude -p "reply ok" \
  --output-format stream-json --verbose < /dev/null > /tmp/init.jsonl 2>&1
grep -c 'daymade-claude-code:tech-selection' /tmp/init.jsonl           # ≥1 = visible to the model
```

If positives and negatives both score 0, the instrument is dead, not the skill —
check for a trigger collision first. `prior-work-retrieval`'s description
overlaps this skill's on 别闭门造车 / 不要重复造轮子 / 先看看有没有现成的, and in
production the model has been observed weighing that skill before choosing this
one. Record *which* skill won; a positive that fires nothing often lost to
something specific rather than to nothing.
