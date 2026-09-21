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
violate a principle. Which candidate to adopt is not the agent's decision: when
two or more candidates survive, return candidates + trade-offs + a recommendation
to the user. Never a single pick.

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

**Lightweight path.** A choice is reversible, local, under 10 minutes, and has no external contract → run Steps 0, 1, and 3 only, record the business result and the prior-art layer, and proceed. Skip Steps 2, 4, 5, 6, and 7. Choosing a JSON library inside a bug fix is this path; choosing the project's storage engine is not. When unsure which path applies, take the full protocol.

### Step 0 · Frame

Write two things before comparing any candidate:
1. The **named business result** this choice serves.
2. The **named failure mode** — what observable phenomenon would prove the choice wrong.

Derive the business result from context, not from the request text. A bare "which DB" carries no result on its face — read the project's decision log, the user's recent corrections, and what this choice unblocks downstream. If no context exists to derive from, say so explicitly rather than fabricating one.

> Checkpoint: Cannot derive a business result from any available context → this is an execution task, not a selection task. Exit skill. Business result written as "tests pass" or "pipeline complete" → that's a proxy metric. Rewrite.

### Step 1 · Inventory Prior Art

Fixed order: internal/paid assets → external world-class + community solutions → build from scratch (last resort). Tag each candidate with which layer it came from.

Where to look for layer 1: existing credentials and paid-service capability catalogues, installed skills, the current repository's existing pipelines, and the project's decision log. Do not limit layer 1 to `grep` in the current repo — that returns zero hits for paid services and skills, and a zero from a narrow search is not absence.

Layer 2 has a minimum coverage requirement: use a search tool to enumerate what exists, not memory alone. "Searched, found 2" is not coverage — name the search queries run, or state explicitly that no search tool was available and this is a memory-only inventory.

> Checkpoint: If the final recommendation falls to layer 3 (build) with no recorded reason from layers 1–2 → flag as 闭门造车. Zero hits from layer 1 must distinguish "searched by structural token" from "searched by remembered name" — the latter's zero hit does not mean absence.

**User-named candidates.** When the user names a specific option ("use Redis or Postgres?", "should we add a vector store?"), that option enters the candidate set like any other — it is subject to the same axes and the same three-value verdict. It is neither exempt from filtering (a named candidate is not a requirement) nor disposable (killing a user-named candidate requires naming the axis and the failure mode, exactly like any other). If the user named exactly two options, they are the minimum candidate set; add any layer-1 or layer-2 candidates the inventory surfaced, and say so.

### Step 2 · Probe for Evidence

The only admissible evidence is behavior you ran and observed. READMEs, vendor pages, docs, and source-code claims are all downgraded. Termination clause: max two attempts across methods per candidate; two failures → "this cannot be done now."

> Checkpoint: Every load-bearing claim must name its probe. A claim sourced only from a README → mark `unknown`, not `pass`.

### Step 3 · Filter Each Candidate

Read `references/decision-axes.md`. For each candidate, give a three-value verdict per axis: `pass` / `fail` (name the failure mode) / `unknown` (needs probe).

A `fail` on a core axis kills the candidate. A `fail` on a C-class criterion from `references/scoped-criteria.md` **does not kill** — record it as a "declared preference against" note on that candidate and continue. Only core-axis failures remove a candidate from the survivor set.

> Checkpoint: `unknown` is not `pass`. A candidate carrying `unknown` **does not enter** the Step 4 survivor set. Do not output a "winner" from this step.

### Step 4 · Triage Survivors — The Core Gate

- **0 survivors**: Report which axis killed which candidate, and whether the axis was wrong or the candidate set was incomplete. If candidates died from `unknown` rather than `fail`, the honest output is: each candidate, the probe it stalled on, and what input the user could supply to unblock it. Do not fabricate a verdict to escape the zero.
- **1 survivor**: May declare only if all three autonomy conditions hold: long-term maintainable, industry best practice, 100% confidence. If any is missing → treat as ≥2 survivors and stop. Must also carry the Step 5 self-defense.
- **≥2 survivors**: **STOP.** Return candidates + trade-offs + one recommendation. Do not single-pick. Do not silently drop rejected candidates.

> Checkpoint: Can the output name which candidate was demoted and by which axis? If not, the gate was hollowed out.

### Step 5 · Self-Defense Slot

Any conclusion produced by this skill carries a "why this isn't garbage" paragraph, and it must **not be self-certified** by this skill alone.

> Checkpoint: Every sentence in the self-defense traces to a probe or an axis verdict. Generic principles (e.g. "it's a mature library") = invalid.

### Step 6 · Saturate Irreversible Surfaces

Scan for surfaces that cannot be patched after release: telemetry/events, field and export formats, external contracts, irreversible external actions. If any exist → saturate from v0. This axis is single-scenario evidence — apply it when the choice produces a released artifact, not to internal or revertible changes, and never use it to raise the standard on work that has no irreversible surface.

> Checkpoint: Explicitly list irreversible surfaces, or explicitly write "none." Silence = not checked. Revertible local changes do not trigger this step.

### Step 7 · Completion Declaration

Distinguish "I verified" from "I claim." Every done statement is followed by what was actually executed and observed.

> Checkpoint: Go to the second stop — artifacts claiming done but unverified stop here.

## Output Shape

Every run of this skill produces all six fields below, in this order. Omitting
a field is a protocol failure — the checkpoints audit the output against these
fields.

1. **Business result + failure mode** (Step 0) — the two lines.
2. **Candidate table** (Steps 1–3) — each candidate with its layer tag, its
   per-axis verdict (`pass`/`fail`/`unknown`), and the probe name behind each
   `pass`. A candidate carrying `unknown` is marked, not hidden.
3. **Survivor demotion record** (Step 4) — for each demoted candidate, which
   axis killed it and the named failure mode. If no candidate was demoted, say
   "no candidate eliminated" and list the axes that passed everything.
4. **Decision branch** (Step 4) — declare exactly one of:
   - `≥2 survivors → STOP` with candidates + trade-offs + one recommendation
   - `1 survivor, autonomy met` with the Step 5 self-defense
   - `0 survivors` with the diagnosis (axis wrong vs candidate set incomplete)
5. **Self-defense** (Step 5) — each sentence traces to a probe or an axis
   verdict. Write only for branch 2; branches 1 and 3 defer to the user.
6. **Irreversible surface list** (Step 6) — the surfaces found, or the word
   "none." Never omit.

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

Agent count is not preset here. Run the four questions from
`daymade-agent-discipline` and let them decide.

**In tech selection the answer is already fixed by a standing instruction for this
task: agent-team discussion is mandatory, and picking a direction unilaterally is
forbidden.** That instruction outranks any general delegation rule, and Stop 1 is
where it is enforced — when two or more candidates survive, return candidates +
trade-offs + a recommendation, never a single pick. It is scoped to this task, not a
preference about how all work is delegated.

1. **Estimated time?** < 10 min → do it yourself. > 30 min → spawn *candidate* only; duration alone never licenses a spawn. 10–30 min → check other dimensions.
2. **Need main-session context (user preferences, multi-round feedback, nuanced decisions)?** Yes → do it yourself. No → spawn *candidate*, not automatic.
3. **Need an unbiased third party (evaluator/reviewer)?** Yes → must spawn (even if fast) — for high-risk, complex work lacking an independent mechanical referee. Ordinary tasks and small changes never auto-spawn one.
4. **Truly parallel (independent streams)?** Yes → may spawn, if current rules allow; implementation work, exclusive resources (browser, Computer Use, single-writer checkout) and private-context judgment never enter the fan-out pool. Otherwise doing it yourself is faster.

Concurrency ceiling: 8–10 (measured, not theoretical). Exceeding it risks quota truncation of the entire batch.

## References

| File | Read when |
|---|---|
| `references/decision-axes.md` | Step 3 — the 13 core filter axes with mechanical criteria |
| `references/scoped-criteria.md` | Step 3 supplementary — 13 narrower criteria with scope labels; C-class items are preferences, not default gates |
| `references/rejection-modes.md` | Before proposing — 28 entries (16 rejection patterns + 18 anti-patterns, deduplicated) with self-test sentences |
| `references/delegation-contract.md` | Step 4 — domain ownership table, autonomy threshold, the 6 resolved scope boundaries |

## Boundary Quick Reference

| Boundary | Resolution |
|---|---|
| 禁绕过 vs fallback | Bypass = replacing the main path (fix scenario). Fallback = supplementary path (runtime channel). Different scenarios. |
| 不看 README vs 官方文档优先 | READMEs = vendor marketing/capability claims. Official API docs/source code = authoritative. Different information sources. |
| 预算定档 vs 资源无限 | Budget sets execution tier (which model runs). It never decides whether to do it. Different axes. |
| 不主动压缩 vs 宿主自动压缩 | During Steps 0–6, do not drop source material to save context — the candidate table and probe records stay complete. Host auto-compaction is outside this skill's control and is not a reason to pre-emptively thin the output. Different actors. |
| 饱和上报 vs 拒绝过度工程 | Saturation applies to irreversible telemetry (events, export formats, external contracts), not feature surface. Different surfaces. |
| 单次任务强制要求 vs 通用委派判据 | In tech selection, agent-team discussion is mandatory and picking a direction unilaterally is forbidden. That instruction is scoped to this task and outranks any general delegation rule — the four questions fill the gaps it leaves, they do not override it. Stop 1 is where it is enforced. |
