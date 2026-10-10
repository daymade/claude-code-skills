---
name: cross-task-improvement
description: >-
  Derive minimal improvements to existing Skills from authorized historical
  successes, failures and user corrections across task types. Read after bounded
  history retrieval and before selecting owners or changes.
---

# Improve existing methods from matched historical cases

Use this route when the user authorizes earlier-history research to improve how
work is done across task types, including Skill edits, competitor research,
deep research, code analysis or work that never named a Skill. A task label is a
search lead, not evidence that every case shares a method. For a correction whose
evidence is already in the live conversation, use the ordinary update path.

The task owner executes this route with the existing history readers and source
Skills. The semantic comparisons below have no automatic enforcement; preserve
their evidence and use the shared task-result and independent-review gates.

## Retrieve cases before distilling them

Follow [the workflow's retrieval route](../workflow.md#choose-retrieval-or-selected-corpus-distillation).
Reuse its authoritative index and provider-specific exact reader; do not build
a second history parser. Search both task vocabulary and observed actions such
as comparing, verifying, recovering or choosing an owner, so unnamed work can
enter the candidate set. Keep the approved query, source/time/session boundaries
and index coverage with the private research output. Search hits locate evidence;
they do not establish what the user said or whether a task succeeded.

Use bounded exact-reader output to verify the selected request, attempted action,
failure or success, user correction and subsequent result. Preserve roles and
source coordinates; omit hidden reasoning and embedded summaries as primary
evidence. Prepare selected role-preserving exports through the workflow's
manifest → discover → redact → chunk route when distilling a corpus. Only
sanitized evidence goes to research agents; keep private coordinates outside
public source. Reuse an already authorized role/shard plan and prepared evidence
without adding approval rounds or repeating extraction.

## Match successful and failed decisions

For each proposed improvement, find a successful case and a failure or user
correction with comparable decision conditions. Identify the original user result,
the decisive action, its actual receiver and the observation that distinguishes
success from merely completing a procedure. If only one side is available, keep
the causal explanation provisional and choose a probe that could disprove it.

Label evidence by what it proves:

| Evidence | Supported claim |
|---|---|
| Observed historical output or tool result | That result occurred under the recorded conditions |
| User correction or acceptance | What the user rejected or accepted in that exchange |
| Author's completion report | The author reported completion; the underlying result still needs evidence |
| Current source or runtime probe | The present contract or behavior at the named ref/environment |

Do not count retries, duplicated exports or a summary of the same exchange as
independent cases. Historical success does not establish today's installation or
availability. Verify current claims against the actual source or consumer before
using them as implementation premises.

## Extract conditions and counterexamples

Compare what changed between the matched cases: evidence available at the decision,
loaded owner, chosen execution path, authorization, receiver and success criterion.
State the smallest causal condition that explains the difference, then find a
case where the proposed rule should **not** apply. Distinguish a supported
mechanism from a plausible explanation; do not turn an untested transfer into a
new domain's mandatory workflow.

Synthetic example: an export reached its requested records after the executor
checked the source's total, while an earlier export stopped on a short page. The
transferable condition is a source that reports a reliable total; a stream with
no such total needs its own completion signal. This does not support adding a
total-count check to every task.

Use the existing [grounding contract](../../../references/authoring-and-reuse.md#ground-technical-and-methodological-claims)
for technical and domain claims and the existing
[check-calibration contract](../../../references/change-verification.md#calibrate-checks-before-writing-or-trusting-them)
for healthy/failing controls. Those contracts remain under their owners.

## Find the current owner and classify the failure

Before writing, use `skills-search` with capability and action vocabulary across
the configured public, team and personal-private source repositories. Discover
those roots from its current configuration rather than hardcoding machine paths.
Record coverage gaps and inspect the matched owner's current immutable source.
Use [the ownership decision](../../../references/authoring-and-reuse.md#the-extend-vs-create-check--runs-before-any-specialized-branch)
to resolve entry, execution, increment and update ownership.

Classify each finding before choosing a maintenance point:

| Failure | Minimal next action |
|---|---|
| Missing mechanism | Add the supported decision or helper under the existing owner |
| Existing owner was not loaded, or its action was bypassed | Repair the action-time route or execute the maintained helper; retain its canonical rule |
| Success criterion measured the wrong result | Replace the proxy with an observation of the original receiver's result |
| Implementation violated the existing contract | Reproduce and repair that implementation under its owner |
| Constraint no longer fits current authority or an explicit user decision | Verify that authority, then update or retire only the affected constraint |

An existing rule is not missing merely because a session failed to follow it.
If a named Skill already covers the remedy, link and execute it. Do not build a
universal improvement Skill, global hook or parallel SOP from the case collection.

## Change the next decision and verify the original result

For each retained change, put the following in the existing task plan or research
handoff: the user result to improve, matched evidence and its limits, causal
conditions and counterexample, current owner, failure class, exact maintenance
point, next choice changed, and decisive probe. Reuse the existing plan or evidence
ledger; do not create a second status system. If removing a sentence would not
change a future choice, leave it in the private research archive or omit it.

Select the change type and evidence tier through
[change verification](../../../references/change-verification.md); new methodology
is Tier 3, which does not automatically authorize heavy evaluation. Preserve
unchanged jobs through the [migration gate](../../../references/existing-skill-migration.md).
Return to ordinary editing, validation and delivery; history research is not the
final deliverable when the user also authorized implementation.

Use the original failed task and a healthy counterexample to check the affected
behavior. The observation must be able to catch doing the wrong work even when
static checks pass. Synthetic probes test the rule's shape; they do not establish
live service or device success. Fix the authorized original artifact as well as
its reusable maintenance point when both are in scope.

Stop when the retained changes alter the intended choices, the named task-result
and preservation checks pass, and the authorized delivery is read back. Keep
missing runtime evidence unresolved and omit unmeasured claims about speed or
long-term success rates. Findings that change no next action do not justify more
research or another rule.
