# Turn evidence into a target improvement

Read this before interpreting historical work or proposing a positive mechanism.
The entry owns execution and delivery; this reference owns the inference that
makes a change worth doing.

## Bind the observation

Record the source identity, task, user requirement, relevant constraints, action,
observed result and evidence location. Mark whether the evidence is a direct
observation, an author's report, or a newly reproduced result. Preserve role and
record coordinates when using prepared historical extracts. A success in one
environment supports that environment's claim, not all future tasks.

Prefer the user's actual acceptance and consumer records over a later summary.
Keep source-contract, runtime and business-effect claims separate. Do not turn an
unknown into a negative finding or treat multiple summaries of one event as
independent corroboration.

Retain the input, execution/consumer observations and failed constraints that
explain a result, rather than diagnosing from an aggregate score alone. Use the
[GEPA adapter contract](https://github.com/gepa-ai/gepa/blob/462e437a09be67d2acb59564cc0ea59132f5777c/src/gepa/api.py#L121-L131)
as a concrete separation of execution and reflective evidence, not a requirement
to install its optimizer or a claim about this target's benefit.

## Diagnose a deviation with matched cases

Select a successful case and a failure or user correction with comparable task,
input, environment and authorization. Vary only what the evidence can justify;
note differences that could explain the result instead of attributing everything
to the Skill. When no usable counterpart exists, retain the uncertainty and use a
bounded probe; do not invent a historical success or failure.

Extract the shared causal conditions and a counterexample: when did the method
help, and when would the same instruction be wrong? Check the current target and
other maintained owners before calling the method missing.

| Finding | Maintenance point to inspect |
|---|---|
| Necessary mechanism is absent | The affected target workflow or existing execution owner |
| Correct mechanism was not loaded or was bypassed | Trigger, action-time pointer, dependency resolution or caller |
| Acceptance measures a proxy or the wrong object | The original result criterion and its actual consumer observation |
| Implementation violates an existing contract | The executing code and a regression for that exact violation |
| An old constraint no longer applies | Its original scope and the later authority that supersedes it |

These diagnoses are conditional on an actual deviation. A positive opportunity
does not need a failure label.

## Evaluate a positive opportunity

Use a successful historical method, a saved source, competitor code or first-party
research to propose an increment. State what the target's user could do better,
which conditions make the mechanism useful, what it costs, and the smallest
observation that would reject the proposal. A healthy current baseline is
compatible with an improvement hypothesis.

Trace the mechanism to the source's actual entry and consumer. Compare its
preconditions and failure/recovery behavior with the target, including differences
in permissions, lifecycle, data and workload. An attractive README or benchmark
is a locator; it does not demonstrate that the mechanism works in this task.

Check whether the target or another owner already provides an equivalent. Existing
coverage can justify no change, a better invocation or a narrow adaptation. Avoid
importing a larger engine, weaker recovery or unapproved side effect to obtain a
minor convenience.

Test business relevance separately from whether the historical pattern is real.
Choose the smallest existing carrier that fits: an executable owner for stable
actions, a reference for conditional knowledge, or the project's canonical record
for task facts. The [pattern-to-component relevance check](https://github.com/CosmosMind-ai/RSI-Harness/blob/7bf09774bbe205956ec5a46e5f934602224cc437/config/genomes/harness-rsi/skills/genome-authoring/pattern-to-component.md#L60-L79)
illustrates that distinction; its runtime, memory and resource-isolation choices
are separate decisions and are not imported here.

For example, an external exporter may checkpoint processed records. If the target
must resume an interrupted batch and does not already do so, test interruption,
resumption and exact consumer output before adopting it. If the target already
has equivalent recovery, keep the owner. If checkpointing would persist sensitive
inputs outside the approved storage boundary, reject that form or leave the new
storage decision at its authorization boundary. This is a synthetic example,
not a measured improvement.

## Keep the disposition traceable

Maintain the important mechanisms found during research, including counterevidence
and rejected candidates. Do not reverse-engineer an evidence list from the final
recommendation. Reuse competitors-analysis's current evidence and mechanism
disposition workflow when available; do not introduce a second rigid schema.

For each mechanism, retain:

- **Adopt:** the supported increment, conditions/cost, authorized minimum change,
  falsifier and result observation. Distinguish selected, implemented and verified.
- **Do not adopt:** existing equivalent, unmet fit condition, cost or side effect,
  with evidence and what new fact could reopen it.
- **Needs verification:** the decisive unknown, bounded probe, required source or
  authorization, and what can proceed independently.

Name a target-local change rather than a universal rule. Generalize only across
conditions supported by the evidence and keep counterexamples visible. If the
change would alter supported jobs or authorization, surface that boundary instead
of describing it as compression.

## Reuse evidence at continuation

Keep settled decisions, source refs and failed approaches with their current
owners. Reopen only when the source, environment, user goal or a decisive
observation changes. Do not rerun a failed route without a new condition that
could change its outcome, and do not repeat passed checks on unchanged content.

Before stopping, reconcile the original requirements with actual results and
specific gaps. An implementation receipt, completed comparison or prepared-task
pass leaves any unobserved consumer result unresolved.

Use the [skills-refiner source/consumption/result distinction](https://github.com/yknothing/skills-refiner/blob/4d8a196e44c1fa06cb786c06c2aaf24028664c01/skills/skills-refiner/SKILL.md#L124-L145)
when choosing the observation for an acceptance claim: a correct source change,
installed bytes, native loading and task benefit each need their own evidence.
