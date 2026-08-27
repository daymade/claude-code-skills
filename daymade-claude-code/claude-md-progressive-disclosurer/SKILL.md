---
name: claude-md-progressive-disclosurer
description: >-
  Audit and repair CLAUDE.md, AGENTS.md, path-scoped rules, Skill triggers, and hooks when the
  user explicitly asks for an instruction-stack audit, slimming, progressive disclosure, or a
  diagnosis of agent drift. Evaluates current content and runtime behavior, retires stale rules,
  assigns each surviving rule to the right carrier, and validates representative tasks. This is
  an explicit governance workflow, not an automatic prerequisite for ordinary implementation.
argument-hint: "[instruction files or observed drift]"
disable-model-invocation: true
---

# Instruction Stack Auditor

The outcome is not a smaller file. The outcome is an agent that completes the intended work with
less irrelevant ceremony, fewer conflicts, and no loss of current safety or business constraints.

Treat every existing rule—including this Skill—as a revisable hypothesis. Current user decisions,
current product behavior, authoritative business sources, and current host documentation outrank
old local methodology.

## 1. Fix the real symptom before editing

Write down three things in the working notes or conversation; do not create a governance document
just for this step:

1. The user-visible failure, such as task drift, repeated permission prompts, stale business facts,
   missed safety boundaries, or excessive startup context.
2. Two to five representative tasks that expose the failure. Include at least one small ordinary
   task and one task that should activate a real guardrail.
3. A falsifiable success condition. Example: “A typo fix proceeds without history retrieval, while
   an explicit ‘reuse our old implementation’ request retrieves prior work before writing.”

Do not define success as line count, byte reduction, number of references, number of hooks, review
count, or completion of this workflow.

## 2. Measure the actual loaded surface

Inventory the instruction sources the current host really loads. Do not infer loading from a file
existing on disk.

- Claude Code: use `/memory`, `/skills`, `/hooks`, `/doctor`, or the current debug/config surface.
- Codex: inspect `$CODEX_HOME/AGENTS.md`, the repository hierarchy, current `config.toml`, and
  `codex debug prompt-input` from the relevant working directory.
- Resolve symlinks before deciding ownership. Record the source-of-truth repository for every file
  that may be edited.
- Note duplicate Skill names, retired entries still advertised, and hooks that inject context on
  broad events.

Use `scripts/profile_claude_md.py <path>` when section size or long fused paragraphs may be hiding
the signal. Its output is diagnostic evidence, not an optimization target.

## 3. Audit content, not just placement

Read the full resident instruction file and every conditional file proposed for change. Classify
each actionable rule with exactly one disposition:

Do not widen an instruction-stack audit into a rewrite of unrelated domain Skills. A domain Skill's
trigger metadata may be in scope when over-activation is part of the observed drift; its creative or
business methodology is a separate audit requiring explicit scope, the domain SSOT, representative
accepted examples, and real outcome evidence. Generic safety or compliance preferences are not
evidence that a distinctive domain method has failed.

| Disposition | Use when | Required action |
|---|---|---|
| KEEP | Current, stable, broadly applicable, and changes the next action | Keep concise in the appropriate resident scope |
| REWRITE | The intent remains valid but wording, scope, trigger, or authority is wrong | Replace with current, testable language |
| ROUTE | Valid only for a recognizable task, path, product area, or tool | Move the current rule to a conditional carrier and leave a useful route only if discovery needs it |
| ENFORCE | A deterministic, low-false-positive machine check must run at a known event | Put the check in permissions or a hook; keep prose only for judgment the code cannot make |
| RETIRE | Superseded, stale, duplicated, ceremonial, or no longer changes a decision | Delete it and remove all active references; Git history is the archive |
| DECIDE | It encodes a live business or risk policy that available evidence cannot settle | Present the concrete choice to the user |

For every rule, answer:

- What event triggers it?
- What action changes because it exists?
- When does it stop applying?
- Which current source proves it is still true?
- Does another active rule contradict or duplicate it?
- What representative failure appears if it is removed?

If those questions have no concrete answer, the default disposition is RETIRE, not “archive in a
second file.” Do not preserve stale text merely to claim zero information loss.

### Common content defects

Actively look for these, because moving them to a reference does not fix them:

- historical project phases, prices, people, counts, versions, paths, or current-state claims;
- rules generalized from one incident without a demonstrated recurrence;
- a safety rule whose prose scope is broader than the hook that allegedly enforces it;
- a semantic judgment encoded in a regex hook;
- “always browse / always retrieve / always review / always spawn” gates applied to ordinary work;
- process receipts, self-review reports, or reviewer counts used as completion criteria;
- two authorities both defining the same mutable fact;
- an old Skill asserting that its own workflow is mandatory.

## 4. Choose the smallest correct carrier

Use the current host’s behavior rather than a universal two-layer diagram.

| Carrier | Put here | Do not put here |
|---|---|---|
| Root CLAUDE.md / AGENTS.md | Small set of cross-task conventions, decision boundaries, core commands, and a map to current sources | Detailed SOPs, war stories, volatile project state, every tool’s manual |
| Nested AGENTS.md / CLAUDE.md or path rule | Rules whose scope follows a directory or file pattern | Global user preferences or Bash events unrelated to files |
| Skill | A reusable workflow or body of knowledge with a recognizable intent | Generic mandatory preflight for every task |
| Hook / permission | Deterministic event automation or a precisely detectable irreversible boundary | Open-ended semantic review, business judgment, or “make the agent think globally” |
| Reference / product docs | Authoritative detail that a live route actually opens when needed | A retirement graveyard or an unverified pointer |
| Code / config / schema | Facts the runtime can read directly | Duplicated values in prose |

OpenAI’s current harness guidance treats a short `AGENTS.md` as a map rather than an encyclopedia.
Claude Code likewise separates always-on `CLAUDE.md`, path-scoped rules, on-demand Skills, and
deterministic hooks. These are defaults to test against the actual installation, not fixed byte or
line quotas.

### Routes must be operational

A route is useful only when it names a recognizable trigger and a current source. Before writing a
pointer:

1. Verify the target exists now.
2. Verify the target actually contains the promised rule or fact.
3. Verify the host or Skill will load it before the decision it governs.
4. Remove old pointers and duplicate active definitions.

If a retired file has no live caller, delete it. Do not replace it with a marker saying it was
retired. Changelog and Git history already preserve provenance.

## 5. Edit with repository ownership intact

- Inspect `git status -sb` in every owning repository and preserve unrelated work.
- Prefer the tracked pre-edit revision as the baseline. For an untracked source that truly needs a
  recovery copy, use a system temporary path and remove it after verification; do not leave backup
  snapshots in an active instruction or reference tree.
- Make explicit, scoped edits. Do not mechanically copy whole sections merely because deletion
  feels risky.
- When changing a mutable fact, find active duplicates before editing and converge them on one
  authority.
- When changing a Skill, update its trigger description and host metadata as part of the same
  change. Manual-only governance Skills should not advertise themselves on ordinary tasks.
- When changing a hook, inspect its matcher and real decision code, then add both a healthy control
  and a triggering control.

## 6. Validate behavior, not ceremony

Run the smallest checks that can disprove the desired result.

### Structural checks

- YAML/JSON/TOML parses.
- All live pointers resolve and contain the claimed content.
- Retired names and duplicate definitions are absent from active discovery surfaces.
- The actual host prompt shows the intended files and Skill descriptions, without unexpected
  compatibility copies.
- Hook matchers fire only for the intended event class.

### Representative-task checks

Exercise the tasks recorded in section 1. At minimum verify:

1. A small ordinary task does not activate history retrieval, mandatory review, agent delegation,
   or unrelated setup.
2. An explicit prior-work request does activate the retrieval route.
3. A real irreversible action still reaches its deterministic guardrail.
4. A domain request loads the intended Skill and obtains volatile facts from the current business
   source rather than resident prose.
5. The originally reported drift case now takes the action that advances the business outcome.

Use an independent reviewer only when the edited policy is high-risk or ambiguous and no mechanical
or business-source oracle can decide it. A fixed reviewer requirement would recreate the process
problem this Skill is meant to remove.

## 7. Report the semantic delta

The final handoff should state:

- which behaviors changed for ordinary tasks;
- which rules were kept, rewritten, routed, enforced, or retired, with the reason that matters;
- which current authority now owns volatile facts;
- which representative checks passed and what remains unverified;
- any live business-policy choice still needing the user.

Size measurements may be included as context-load diagnostics, never as proof that the agent will
produce better business outcomes.

## Current primary sources

- OpenAI, “Harness engineering: leveraging Codex in an agent-first world”:
  https://openai.com/index/harness-engineering/
- OpenAI, “Unrolling the Codex agent loop”:
  https://openai.com/index/unrolling-the-codex-agent-loop/
- Claude Code, “Extend Claude Code”:
  https://code.claude.com/docs/en/features-overview
- Claude Code, “How Claude remembers your project”:
  https://code.claude.com/docs/en/memory
- Claude Code, “Extend Claude with skills”:
  https://code.claude.com/docs/en/slash-commands
- Claude Code, “Hooks reference”:
  https://code.claude.com/docs/en/hooks

Recheck these sources when host behavior or supported frontmatter changes; do not freeze their
current details into permanent doctrine.
