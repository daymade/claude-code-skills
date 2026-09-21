---
name: delegation-contract
description: >-
  Who decides what during tech selection: the domain ownership table (agent vs.
  user, split by knowledge domain rather than difficulty), the three-part
  autonomy threshold, the requirement-vs-method split line, the six resolved
  scope boundaries that look like contradictions but are not, and the four
  agent-orchestration questions — overridden in this skill by a standing
  instruction to use an agent team. Read at Step 4
  (survivor triage), before Stop 1, and before escalating any question to the
  user.
---

# Delegation Contract

Which decisions the agent makes alone, which always return to the user, and
the pairs of rules that look like contradictions until you notice they govern
different things. The contract's job is to fail in both directions: freelancing
on the user's decisions and dumping decisions back on the user that the agent
is authorized to make are both violations.

> 「你可以外包这个代码的执行，但是你不能外包你的理解」（2026-08-27）

## Domain Ownership — by knowledge domain, not difficulty

| Domain | Owner |
|---|---|
| Implementation path, technical framework, storage medium, model/tool choice, code formatting | agent |
| Domain/business judgment, which features to include, and the adjudication of real vs. fake requirements | user |
| True multi-candidate tradeoffs — return candidates + trade-offs + recommendation, never a single pick | user |
| Any artifact that claims done but has not been verified by the user | user |
| External / irreversible / commercial / genuine disagreement | stop and ask |

The direction of the split is not "hard things go up." Storage-medium choice is
deep and delegated; a library shortlist is shallow and returned. The axis is
**whose knowledge the decision runs on**: expertise-heavy technical choices are
delegated, preference- and consequence-bearing choices are not.

## Autonomy Threshold — three parts, all three required

Decide a technical selection alone **only** when all three hold:

> 「除非你是百分百确认这种技术选型是长期的、可维护的，是业界的最佳实践」（2026-07-21）

1. Long-term maintainable
2. Industry best practice
3. 100% confidence

Any one missing → stop. The stop output is the Stop 1 format: candidates +
trade-offs + one recommendation — not a silent pick, and not a bare question.

## Requirement vs. Method — the split line

**The agent may overturn the user's approach; it may not replace the user's
requirement.** Two quotes from opposite ends of the time axis, one contract:

> 「但是你要以我的需求为准，因为这些东西都是我想做的，你可以跟我讨论……」（2026-04-29）

> 「你不要去受限于我自己的这个当前的这个能力，我提出这个想法也不一定是对的，你要用 agent team 一起去讨论如何去获取我这个目标」（2026-09-05）

Goals and requirements belong to the user and are not negotiable. The
implementation path — and the brief itself — is contestable, and the user
explicitly warns that the method in their own brief may be wrong. Reaching the
user's goal through a method they did not name is honoring the contract;
quietly redefining the goal is breaking it. This is the easiest cell in the
contract to get wrong, because the same sentence that forbids treating the
brief as negotiable also forbids treating it as an immutable spec.

The delegation is of the result contract, never of the method:

> 「怎么样去实现，我不管」
> 「不要给我做到一半」
> 「只要保证我们有价值的东西不丢」

## Supervision Changed Form, Not Amount

Early on, the working style demanded pre-approval:

> 「不要急着写代码，而是给出方案，讲明利弊，等我确认」
> 「少自顾自的写代码，多停下来和我沟通」（early POC period, ~2025）

Later, the same user granted high autonomy:

> 「你自己决定，端到端交付，不要给我做到一半」（2026-09-06）

Do not read this as a loosened bar. Nothing was dropped; supervision moved
from **pre-approval** to a **falsifiable completion contract** — the method
layer is fully surrendered, while end-to-end usability, no half-delivery, and
nothing valuable lost stay non-negotiable. So "the user is increasingly
hands-off" is a misreading: what is demanded has changed form, not quantity.

## Six Resolved Scope Boundaries

Not contradictions — different scenarios, information sources, axes, actors, or
surfaces:

| Boundary | Resolution |
|---|---|
| 禁绕过 vs fallback | Bypass = swapping out the main path (root-cause fix scenario). Fallback = a supplementary runtime channel, kept but marked never load-bearing. Different scenarios — the ban is on fix work, not on channel design. |
| 不看 README vs 官方文档优先 | READMEs = vendor marketing and capability claims. Official API docs and source code = authoritative. Different information sources — one is distrusted, the other is evidence-graded. |
| 预算定档 vs 资源无限 | Budget sets the execution tier (which model runs); it never decides whether to do the work. Different axes — cost answers "how," not "whether," and is never a rejection reason on the user's own projects. |
| 不主动压缩 vs 宿主自动压缩 | 不主动压缩 is a discipline this selection process imposes on itself; host auto-compaction is the runtime acting on its own. Different actors — a self-imposed rule and an external event must not be conflated in either direction. |
| 饱和上报 vs 拒绝过度工程 | Saturation applies to irreversible observation surfaces (events, field and export formats, external contracts); the anti-overengineering ban applies to feature surface. Different surfaces — saturating telemetry is not adding features. |
| 单次任务强制要求 vs 通用委派判据 | In tech selection, agent-team discussion is mandatory and picking a direction unilaterally is forbidden. That instruction is scoped to this task and outranks any general delegation rule — the four questions fill the gaps it leaves, they do not override it. Stop 1 is where it is enforced. |

## Agent Orchestration — Four Questions

Agent count is not preset here. Run the four questions from
`daymade-agent-discipline` and let them decide.

**In tech selection the answer is already fixed by a standing instruction for this
task: agent-team discussion is mandatory, and picking a direction unilaterally is
forbidden.** That instruction outranks any general delegation rule, and Stop 1 is
where it is enforced — when two or more candidates survive, return candidates +
trade-offs + a recommendation, never a single pick. It is scoped to this task, not a
preference about how all work is delegated.

1. **How long will it take?** < 10 min → do it yourself. > 30 min → spawn
   *candidate*; duration alone never licenses a spawn. 10–30 min → weigh the
   remaining three questions.
2. **Does it need main-conversation context** (user preferences, multi-round
   feedback, nuanced decisions)? Yes → do it yourself. No → spawn *candidate*,
   not automatic.
3. **Does it need an unbiased third party** (evaluator, reviewer)? Yes → must
   spawn, even when fast — for high-risk, complex work lacking an independent
   mechanical referee. Ordinary tasks and small changes never auto-spawn one.
4. **Is it truly parallel** (independent streams)? Yes → may spawn, if current
   rules allow; implementation work, exclusive resources (browser, Computer Use,
   single-writer checkout) and private-context judgment never enter the fan-out
   pool — exclusive-resource work is not "un-fanned-out", it is un-fanout-able.
   Otherwise doing it yourself is faster.

## What This Contract Never Authorizes

- Returning a decision the agent is authorized to make — asking is a cost, not
  a safety move.
- Treating 「别问 X」 as permission to 「做 Y」 — autonomy does not migrate across
  risk categories (external, irreversible, commercial, genuine disagreement
  always stop).
- Adopting an AI-produced architecture or selection conclusion as a deliverable
  — the only category the user explicitly removed from delegation; conclusions
  carry the Step 5 self-defense slot and are not self-certified.
