# Read the mechanism before judging the product

Read this during repository analysis before a mechanism claim or our-product gap
judgment, and before executing competitor code. The analyst performs these checks
from the bound sources and records the evidence in the existing profile. Static
validation cannot establish path completeness or a user's successful outcome.

## Bind the comparison baseline

For an our-product comparison, resolve the named acceptance scenario from the
product authority to its actual entry point and the relevant source/runtime
version. Distinguish intended, implemented and actually used behavior. Keep an
unknown entry or version explicit; it limits that comparison, not independent
competitor facts or a standalone Profile.

Before declaring a whole-product gap from a missing or weak module, trace whether
the actual entry uses it. Check relevant alternative paths, editions and legacy
tools in the bounded scenario. Cite the connection or its unresolved point. An
unused helper is evidence about that helper, not every way the product does the job.

## Trace the decisive mechanism and its lifecycle

Start at the bound source's entry and follow calls to the mechanism that determines
the comparison. Read the relevant normal, failure, cancellation, recovery and
cleanup paths. Record task identity, completion meaning and side effects where
they affect the choice: retry versus new work, resumed process versus new session,
result queued versus consumed, and resource release or retained state. Unread or
unavailable paths remain unknown with the next check that could resolve them.

When execution is planned, use that trace to identify its actual effects and apply
the current task's authorization boundary. A command called status or observe may
resume a session, write configuration or approve an action. Source reading does
not require running it, and a method name does not establish read-only behavior.
Keep already-authorized tests moving; this check adds no approval workflow.

## State the depth of each material claim

Keep four observations separate: source/edition bound; relevant implementation
read; named behavior exercised; result actually consumed or adopted. Cite each
available observation and mark the others unknown. A clone does not prove deep
reading; code or a successful component test does not prove adoption or a qualified
product outcome. Scope exercised behavior to its input, environment and version.

Use the existing profile's Analysis Boundary and Core Implementation Findings to
record this coverage. Reuse its Source Register for version identity rather than
copying a second register. Select the cheapest next check capable of changing the
choice; not every claim needs every depth or a live test. If source evidence already
decides a defer/reuse judgment, stop gathering. For an opportunity, use
[the Landscape decision chain](landscape_synthesis.md#build-a-small-number-of-decision-bearing-judgments)
and retain its cost, counterexample and falsifier.
For project-backed opportunities, follow its
[coverage and disposition contract](landscape_synthesis.md#account-for-material-opportunities)
before selecting and closing the material set.

## Synthetic worked example

The following fragments are invented to illustrate evidence scope, not claims
about a real product. Snapshot A and snapshot B are immutable fixture identities.

| Source-register identity | Observed passage |
|---|---|
| Competitor snapshot A | `cli/status.ts:20-24` calls `resumeSession`; `jobs/retry.ts:8-16` reuses a job ID; `jobs/cancel.ts:5-12` retains a checkpoint and releases a lease. |
| Our-product snapshot B | `cli/legacy-search.ts:10-15` matches keywords; `app/search.ts:6-9` calls `lib/semantic-search.ts:30-44`, the current search mechanism. |

**Source-only conclusion:** the competitor's status path can resume a session;
its retry path reuses an ID and cancellation retains state while releasing the
lease. These paths were read, not run. The our-product keyword helper is a legacy
path; the actual app entry reaches semantic search. Whole-product semantic search
absence is therefore unsupported, and actual search quality remains untested.
Normal completion and startup-failure cleanup are unread; inspect those paths
before planning a live recovery comparison.

**Borrowable mechanism, outcome unverified:** for a requirement to recover an
interrupted job, propose evaluating the competitor's stable job identity and
checkpoint handling. Reuse may avoid duplicate work, but adds checkpoint and
cleanup obligations. Its code does not prove that users finish interrupted work
more reliably. Counterexample: our current job path may already provide equivalent
recovery. The next check is the same interrupted-job scenario through each actual
entry, inspecting task identity, recovered output and released resources. A failed
recovery or no improvement would narrow or overturn the recommendation.

For a standalone source review, omit snapshot B and the our-product judgment;
source facts about snapshot A still stand. Missing comparison context is not a
reason to stop that review or to execute its status command.
