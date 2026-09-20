---
name: tech-selection
description: >-
  Gated checklist for choosing between technologies: library, framework, storage,
  data format, model, build-vs-buy, architecture. Runs before committing, not after.
  Candidates must clear a business-result anchor, prior-art inventory, an
  observed-behavior probe, and the maintenance, boring-tech, data-structure,
  operator-skill gates; READMEs are not evidence. Filters violators rather than
  ranking options: when two or more survive, STOP and return candidates plus
  trade-offs plus a recommendation, never a single pick. Use when choosing a
  technical direction even if the user never says 技术选型: 用哪个, 选哪个,
  选什么框架, 存哪里, 哪个模型, 要不要自建, 自己造还是用现成的,
  先看看有没有现成的, 有没有成熟的方案, 别闭门造车, 不要重复造轮子,
  不要过度工程, A 还是 B, 这个方案行不行, 这样设计可以吗, 这是最佳实践吗,
  which library, build or buy, review this design, architecture decision. Also
  fires when the agent itself picks a library, format, model or storage medium.
  Not for research reports (deep-research), implementing or debugging settled
  code, bug fixes, or a price comparison.
argument-hint: "<decision to make>"
---

# Tech Selection — Gated Checklist

A checklist for choosing between technologies, not a scoring rubric. The core
insight: these criteria are **filters, not sorters** — they kill candidates that
violate a principle, and the survivors are decided by business-result anchoring,
not by ranking. When two or more candidates survive, the correct output is
candidates + trade-offs + a recommendation, never a single pick.

Two outcomes end the protocol early:
1. **Multi-candidate human tradeoff** — ≥2 survivors after filtering. Stop and return.
2. **Unverified completion claim** — the artifact claims done but has not been probed. Stop and return.

## Not This

- Not an interview framework — the user delegates implementation, not direction. Don't ask "which do you prefer" when you can probe and decide.
- Not a scoring rubric — no weighted scores, no "winner" ranking. Filters, then business anchor.
- Not self-certifying — the "why this isn't garbage" defense is written by this skill but must be independently checkable, not self-approved.
- Not a cost gate — budget sets execution tier (which model runs), never whether to do it. Don't use cost as a rejection reason for the user's own projects.
- Not a scope expander — no unrequested features, frameworks, or complexity.
- Not package-size-driven — line count and bundle size are proxies, not quality.

## Execution Protocol

### Step 0 · Frame

Write two things before comparing any candidate:
1. The **named business result** this choice serves.
2. The **named failure mode** — what observable phenomenon would prove the choice wrong.

> Checkpoint: Cannot write a business result → this is an execution task, not a selection task. Exit skill. Business result written as "tests pass" or "pipeline complete" → that's a proxy metric. Rewrite.

### Step 1 · Inventory Prior Art

Fixed order: internal/paid assets → external world-class + community solutions → build from scratch (last resort). Tag each candidate with which layer it came from.

> Checkpoint: If the final recommendation falls to layer 3 (build) with no recorded reason from layers 1–2 → flag as 闭门造车. Zero hits from layer 1 must distinguish "searched by structural token" from "searched by remembered name" — the latter's zero hit does not mean absence.

### Step 2 · Probe for Evidence

The only admissible evidence is behavior you ran and observed. READMEs, vendor pages, docs, and source-code claims are all downgraded. Termination clause: max two attempts across methods per candidate; two failures → "this cannot be done now."

> Checkpoint: Every load-bearing claim must name its probe. A claim sourced only from a README → mark `unknown`, not `pass`.

### Step 3 · Filter Each Candidate

Read `references/decision-axes.md`. For each candidate, give a three-value verdict per axis: `pass` / `fail` (name the failure mode) / `unknown` (needs probe).

> Checkpoint: `unknown` is not `pass`. A candidate carrying `unknown` **does not enter** the Step 4 survivor set. Do not output a "winner" from this step.

### Step 4 · Triage Survivors — The Core Gate

- **0 survivors**: Report which axis killed which candidate. Determine whether the axis was wrong or the candidate set was incomplete. Do not lower a gate to make the process finish.
- **1 survivor**: May declare, but must carry the Step 5 self-defense.
- **≥2 survivors**: **STOP.** Return candidates + trade-offs + one recommendation. Do not single-pick. Do not silently drop rejected candidates.

> Checkpoint: Can the output name which candidate was demoted and by which axis? If not, the gate was hollowed out.

### Step 5 · Self-Defense Slot

Any conclusion produced by this skill carries a "why this isn't garbage" paragraph, and it must **not be self-certified** by this skill alone.

> Checkpoint: Every sentence in the self-defense traces to a probe or an axis verdict. Generic principles (e.g. "it's a mature library") = invalid.

### Step 6 · Saturate Irreversible Surfaces

Scan for surfaces that cannot be patched after release: telemetry/events, field and export formats, external contracts, irreversible external actions. If any exist → saturate from v0.

> Checkpoint: Explicitly list irreversible surfaces, or explicitly write "none." Silence = not checked. Revertible local changes do not trigger this step.

### Step 7 · Completion Declaration

Distinguish "I verified" from "I claim." Every done statement is followed by what was actually executed and observed.

> Checkpoint: Go to the second stop — artifacts claiming done but unverified stop here.

## Two Stops That Return to the User

### Stop 1 · Multi-candidate human tradeoff

When ≥2 candidates survive filtering, the output is:
- Each surviving candidate
- Its trade-offs (what it costs, what it gives up)
- One recommendation with reasoning

Never a single pick. Never a ranked list. Never silently dropping rejected candidates.

The autonomy threshold for a tech selection is three-part, all three required or stop:
1. Long-term maintainable
2. Industry best practice
3. 100% confidence

### Stop 2 · Unverified completion claim

Any artifact that claims done but has not been probed by the user stops here. "Tests pass" is not the same as "you verified it works."

## Agent Orchestration — Four Questions

Agent count is determined by task shape, not a fixed default. Ask:

1. **Estimated time?** < 10 min → do it yourself. > 30 min → spawn. 10–30 min → check other dimensions.
2. **Need main-session context (user preferences, multi-round feedback, nuanced decisions)?** Yes → do it yourself. No → spawn candidate.
3. **Need an unbiased third party (evaluator/reviewer)?** Yes → must spawn (even if fast).
4. **Truly parallel (independent streams)?** Yes → must spawn. Otherwise doing it yourself is faster.

Concurrency ceiling: 8–10. Exceeding it risks quota truncation of the entire batch.

## References

| File | Read when |
|---|---|
| `references/decision-axes.md` | Step 3 — the 13 core filter axes with mechanical criteria |
| `references/scoped-criteria.md` | Step 3 supplementary — 13 narrower criteria with scope labels; C-class items are preferences, not default gates |
| `references/rejection-modes.md` | Before proposing — 16 rejection patterns + anti-patterns with self-test sentences |
| `references/delegation-contract.md` | Step 4 — domain ownership table, autonomy threshold, the 5 resolved scope boundaries |

## Boundary Quick Reference

| Boundary | Resolution |
|---|---|
| 禁绕过 vs fallback | Bypass = replacing the main path (fix scenario). Fallback = supplementary path (runtime channel). Different scenarios. |
| 不看 README vs 官方文档优先 | READMEs = vendor marketing/capability claims. Official API docs/source code = authoritative. Different information sources. |
| 预算定档 vs 资源无限 | Budget sets execution tier (which model runs). It never decides whether to do it. Different axes. |
| 不主动压缩 vs 宿主自动压缩 | Skill governs "don't compress during selection." Host auto-compaction is separate. Different actors. |
| 饱和上报 vs 拒绝过度工程 | Saturation applies to irreversible telemetry (events, export formats, external contracts), not feature surface. Different surfaces. |
