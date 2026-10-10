---
name: delegation-contract
description: >-
  Who decides what during tech selection: the domain ownership table (agent vs.
  user, split by knowledge domain rather than difficulty), current authorization,
  the requirement-vs-method split line, resolved
  scope boundaries that look like contradictions but are not, and
  agent-orchestration questions — overridden by explicit current-task
  instructions. Read at Step 4
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
| Implementation path, technical framework, storage medium, model/tool choice, code formatting within the authorized result and side-effect boundary | agent |
| Domain/business judgment, which features to include, and the adjudication of real vs. fake requirements | user |
| Unresolved business, product or genuine preference trade-offs — return candidates + trade-offs + recommendation | user |
| Technical/consumer verification the agent can run within authorization | agent; execute and report observations |
| Human acceptance of a concrete artifact | user; keep unobserved acceptance unconfirmed |
| New scope, external commitments, irreversible actions or genuine disagreement not covered by existing authorization | stop the dependent action and ask |

The direction of the split is not "hard things go up." Storage-medium choice is
deep and may be delegated; a library choice may require a genuine user preference. The axis is
**whose knowledge the decision runs on**: expertise-heavy technical choices are
delegated, preference- and consequence-bearing choices are not.

## Autonomy Threshold — apply current authorization

The earlier restriction was:

> 「除非你是百分百确认这种技术选型是长期的、可维护的，是业界的最佳实践」（2026-07-21）

Preserve that restriction when it remains the current instruction for the task.
Later autonomous-delivery authorization changes its applicability: necessary
local reversible implementation choices are made by the agent, with evidence,
maintainability and relevant industry practice checked. Do not invent “100%
confidence,” turn an unknown into a survivor or manufacture a second survivor to
force a question. Candidate count and elapsed time do not grant or revoke authority.

Before deciding, check the current instruction and existing authorization for this
action, its scope, consequences and recovery path. Reuse an applicable prior answer;
ask only when information is truly missing or a user-owned choice/authorization
boundary remains. Execute available authorized probes before escalating unknowns.
This is agent judgment, not a mechanically enforced permission check.

## Requirement vs. Method — the split line

**The agent may overturn the user's approach; it may not replace the user's
requirement.** The source statements are:

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

## Resolved Scope Boundaries

Not contradictions — different scenarios, information sources, axes, actors, or
surfaces:

| Boundary | Resolution |
|---|---|
| <a id="bypass-and-fallback"></a>禁绕过 vs fallback | Bypass = swapping out the main path (root-cause fix scenario). Fallback = a supplementary runtime channel, kept but marked never load-bearing. Different scenarios — the ban is on fix work, not on channel design. |
| <a id="official-docs-and-readmes"></a>不看 README vs 官方文档优先 | README/vendor claims do not prove usability. Official docs/source can establish a source contract; runtime and business-result claims require their own observations. |
| <a id="budget-and-resources"></a>预算定档 vs 资源无限 | Budget sets the execution tier (which model runs); it never decides whether to do the work. Different axes — cost answers "how," not "whether," and is never a rejection reason on the user's own projects. |
| <a id="selection-context-and-host-compaction"></a>不主动压缩 vs 宿主自动压缩 | During Steps 0–6, do not drop source material to save context — the candidate table and probe records stay complete. Host auto-compaction is outside this skill's control and is not a reason to pre-emptively thin the output. 不主动压缩 is the selection process's discipline; host auto-compaction is the runtime acting on its own. Different actors — do not conflate them. |
| <a id="irreversible-surfaces-and-overengineering"></a>饱和上报 vs 拒绝过度工程 | Saturation applies to irreversible observation surfaces (events, field and export formats, external contracts); the anti-overengineering ban applies to feature surface. Different surfaces — saturating telemetry is not adding features. |
| <a id="current-task-delegation"></a>单次任务强制要求 vs 通用委派判据 | Read [Agent Orchestration](#agent-orchestration) for the current-task instruction boundary. |

## Agent Orchestration

Agent count is not preset here. Run the delegation questions from
`daymade-agent-discipline` and let them decide.

An explicit instruction in the current task to use team discussion or avoid a
unilateral direction takes precedence for that task. A historical task instruction
does not make every later selection a team task; apply the current delegation
discipline where no explicit instruction governs.

1. **How long will it take?** < 10 min → do it yourself. > 30 min → spawn
   *candidate*; duration alone never licenses a spawn. 10–30 min → weigh the
   remaining questions.
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

Set concurrency within the actual host limit and current delegation discipline;
a historical measured ceiling is not a portable fan-out default.

## What This Contract Never Authorizes

- Returning a decision the agent is authorized to make — asking is a cost, not
  a safety move.
- Treating 「别问 X」 as permission to 「做 Y」 — autonomy does not migrate across
  risk categories; external, irreversible or commercial actions still require
  their own authorization, and unresolved business/preferences remain user-owned.
- Adopting an AI-produced architecture or selection assertion as verified without
  evidence. Full-protocol conclusions carry the Step 5 self-defense; lightweight
  conclusions carry their named reason and evidence. Both require independently
  checkable observations; agent verification does not establish unobserved human acceptance.
