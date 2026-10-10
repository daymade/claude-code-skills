# tech-selection trigger evals

Use [the query set](trigger-evals.json) as the original trigger input. Its labels
are expectations, not current invocation or task-result measurements.

## Current execution route

For a separately authorized trigger check, load `skill-creator` and follow its
[trigger-diagnosis procedure](../../../daymade-skill/skill-creator/references/description-triggering.md).
That owner defines measurement validity and interpretation; use the installed
creator's base directory when outside this maintainer source checkout.

From this repository, inspect the current CLI before running the query set:

```bash
cd <repo>/daymade-skill/skill-creator
uv run --frozen python -m scripts.run_eval --help
```

Pass this directory's query-set path and the intended source Skill path to the
authorized run. Select concurrency, repeats and deadline under that plan rather
than copying a machine-specific preset. For source, installed entry and fresh-host
readback, follow [Testing Skills Locally](../../../CLAUDE.md#testing-skills-locally).

## Historical harness observations (2026-09-20)

These recorded observations describe the harness and machine profile used then;
they do not establish current loading or measurement validity.

1. **Module invocation.** The direct script invocation was recorded as exiting 1
   with `ModuleNotFoundError: No module named 'scripts'`.
2. **Isolated config and timeout.** The then-used eval form staged a synthetic
   command file and accepted that synthetic name, while the machine's profile
   had the real plugin loaded, so a positive query could fire
   the *real* skill and the synthetic name did not match — positives went
   systematically false-negative (measured 1/2 on a 2-sample smoke). Separately,
   the default `--timeout 30` was below that machine's observed latency (a trivial
   answer took 33s), and the then-used harness scored a timeout as `trigger=False` rather than an
   error — the report attributed false-fail positives and false-pass negatives to
   this behavior. It used config isolation and a longer timeout to address those
   conditions.

## Recorded baseline (2026-09-20)

14/14 pass under `run_eval`'s own threshold (positive rate ≥ 0.5, negative < 0.5).
The score is an **upper bound**, not the production truth:

| Sample | Isolated | Production |
|---|---|---|
| 「要不要自己造向量检索模块，还是用现成的框架？先看看有没有现成的，别闭门造车。」 | 3/3 | fires (Skill tool_use, success) |
| 「这个配置存哪里比较好，JSON 文件还是 SQLite？」 | 3/3 | **does not fire** |
| 「我打算把用户事件直接写进 Postgres 一张宽表，这是最佳实践吗？帮我 review 这个设计。」 | 2/3 | untested |
| 「对比一下 AWS、GCP、Azure 的 GPU 实例价格，按性价比排个序」 (negative) | 1/3 → **0/6 on re-run** | untested |
| 「读一下 tech-selection 的 SKILL.md，帮我 review 它的 Step 4 Gate 写得好不好」 (negative) | 1/3 → **0/6 on re-run** | untested |

The stored query set retains the simple-storage divergence and the negative
price-comparison/self-reference cases. Their historical observations remain in
the table; they are not current trigger guarantees. Read the creator procedure
above before interpreting a new run or editing the description.
