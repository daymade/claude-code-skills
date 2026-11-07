# Audit an existing hook's effect and cost

Use this read-only recipe to judge an existing hook's usefulness, duplicate
behavior or measured delay. Select one actual host/profile, event, tool and
representative task window. Stop when bounded evidence decides the proposed
change, or name the missing observation. Keep registration and retirement outside
the audit's side effects.

## Bind the evidence

Record the launcher-selected configuration, explicit settings arguments, project
settings and relevant engine selection. Bind consumed entrypoints and imports to
immutable source or observed byte identities. Inspect configuration as data; do
not execute its command strings or import a hook to count rules. Keep dynamic
selectors and unresolved paths unknown.

Use already available metadata from the selected task. Preserve originals at
their source. For public replay, replace session IDs, PIDs, hashes, paths and
private rule names with synthetic values, retaining multiplicity, missing fields,
relative times and outcomes. Strip tool input, prompts, stdout, stderr,
environment values and conversation bodies. Retain only synthetic handler names
in command fields required by a reader. Keep the private source binding outside
the published example. A redacted replay tests interpretation; it does not
reproduce a hook's decision or independently prove the source observation.

Do not launch a native model CLI, enable debug logging, invoke hooks or change
registration to fill a gap. Read existing debug/timing records only at the known task identity
and bounded window. Absence leaves coverage unknown. Read an audit command's
implementation first: even `status` may create a lock or run liveness probes.
Do not use such an entry as a zero-write read.

## Separate the observations

| Observation | Evidence and limit |
|---|---|
| Configured handlers | Count matching entries for the selected event/tool; record matcher, conditional/async status and runtime. Mirrored settings do not prove both copies were loaded. Registration does not prove execution. |
| Observed processes | Report distinct engine PIDs and observed invocation boundaries separately, distinguishing wrappers and known children. A PID is not a native call ID; PID reuse and missing process coverage prevent a whole-process count. |
| Rules evaluated | Use selection and module/rule results. Count in-process rules separately from interpreters: 28 rules in one PID do not mean 28 processes. Missing completion is incomplete coverage, not a successful quiet result. |
| Functional overlap | Compare actual trigger, decision inputs/predicate, consequence and exemptions/recovery for a bounded pair. Different names do not prove independence; matching names/messages do not prove equivalent judgment. Preserve authorization and state boundaries. |
| Wrong blocks | Adjudicate the actual block against the intended action. Retry, bypass, abandonment and changed commands are signals, not correctness labels. Report wrong blocks, adjudicated blocks and unjudged blocks separately; without adjudication, the false-block rate is unknown. |
| Cost | Label duration scope: rule/module, engine internal, host handler or complete event wall. Report sample count and missing coverage. Do not sum parallel handler durations, infer cost from rule count or treat missing timing as zero. |

Correlate a native call only with its host-supplied identity and bound records.
Keep different call IDs distinct even when inputs match. Deduplicate copied
native records only with the existing reader's complete run identity. For an
engine journal containing only input hashes, say **same-input cohort**; do not
turn it into one native call or join it to host records by hash alone.

To prove a rule ran twice for one event, require correlated execution evidence,
invocation boundaries and both rule results. Duplicate selection is a
configuration candidate; equivalent predicates are a source overlap candidate.
Neither alone proves that a real call was blocked twice.

## Reuse the existing reader

Resolve the optional
[`read-claude-code-history` owner](https://github.com/daymade/claude-code-skills/blob/main/daymade-claude-code/read-claude-code-history/SKILL.md)
through current source/installation inventory. Read its bounded `hook-events`
route and implementation. If unavailable, report that dependency gap; do not
invent an installed path or install it during the audit. This bundle includes
neither that reader nor a generic policy-journal reader.

Use an existing physically bounded metadata export, or a synthetic home containing
only selected hook attachments at
`<audit-home>/projects/<synthetic-project>/<synthetic-session>.jsonl`. Do not point
`--home` at a live profile merely to find one session: it selects a configuration
home, not a session ID. Do not search or copy unrelated conversations to prepare
an export. If no bounded input is available within the task's access boundary,
leave native timing unknown.

```bash
python3 "<history-skill>/scripts/analyze_sessions.py" hook-events \
  --home "<audit-home>" \
  --from "<window-start-with-timezone>" --to "<window-end-with-timezone>" \
  --event PreToolUse
```

Inspect candidate-file and examined-run counts, outcomes and available durations.
Exit 0 alone is insufficient. Zero runs means no observed coverage. Record
unreadable/malformed input and missing fields as gaps. For newly created replay
files, anchor the window at fixture creation time while retaining source-relative
ordering: candidate selection uses filesystem metadata before record timestamps.
Treat `Total runs` as the reader's count after copy deduplication, not a process
or native-call count. Read the loaded reader's implementation for its current
deduplication key and required fields. That key alone cannot distinguish a copied record from a second identical
handler execution. Use execution evidence to decide actual duplicate work.

Read existing engine telemetry separately through its owner-documented reader,
restricted to the known metadata source and exact task/window. Verify the PID and
duration meaning in its producer. A journal with `start`, `module_complete`,
`complete`, `pid`, `event_sha256`, `results` and `duration_ms` is one implementation,
not a universal host protocol. Missing call IDs, child observations, startup time
or legacy handler completions remain separate unknowns. Do not manufacture host
wall time from internal timings.

## Replay both directions

Keep replay answers with private task evidence; do not register a new checker.

**Case 1 — real metadata shape, synthetic identifiers.** Use eight matching
handlers: four engines and four legacy entries. Supply four observed engine
completions in one same-input cohort:

| Synthetic PID | Rules in that process | Internal duration (ms) |
|---|---:|---:|
| 101 | 1 | 5.9 |
| 102 | 1 | 13.1 |
| 103 | 10 | 11.2 |
| 104 | 28 | 28.7 |

Leave native call ID, legacy completions and host wall time unobserved. Vary
missing, `null` and empty identity/timing values independently; none proves
correlation or zero cost. Require an answer separating eight configured handlers,
four observed engine PIDs and the four rule counts. Keep native call count,
legacy cost, children and complete wall time unknown. Unique rule names do not
prove absence of functional overlap; internal timings do not measure the whole
event or unobserved handlers.

**Case 2 — misleading names and correlation.** Supply two differently named
rules with the same actual trigger, predicate, consequence and exemptions. Supply
two native calls with different IDs and identical input hashes, plus a copied
attachment with a complete identical run identity. Require a functional-overlap
candidate, two real calls and one count for the copied run. Remove, null and
empty required identity fields separately; incomplete keys must not establish a
copied run. Remove all execution rows; require zero coverage, not health. Add a
human-labeled healthy action that was blocked and a deliberate retry designed to
pass: count the former as a wrong-block case, not the latter. Keep synthetic
calibration separate from production error rates.

## Decide the next action

Report the consumer/window, examined counts, exact evidence and unknowns. For
overlap, show both predicates and the user-visible consequence that would survive
removal. For cost, name measured and missing boundaries. Separate adjudicated
correctness from heuristic signals and synthetic calibration.

Route a supported, authorized consolidation through the
[shared-engine lifecycle template](shared-engine-lifecycle.md) and existing
installer. Invoke the hook harness only for a separately authorized execution
test. If this bounded evidence confirms no defect, say no removal is justified
by it and stop. Unknown cost or unmeasured usefulness proves neither redundancy
nor necessity.
