---
name: app-evolver
description: >-
  Improves an existing application using its code, product contract, authorized
  work history and competitor evidence. Use for 取长补短、取其精华去其糟粕、参考竞品优化应用
  or evolving an app from successful and failed work. Carries authorized changes
  through implementation and user-result verification, including REA and reverse
  Skill composition; use skill-evolver for Skills.
---

# App Evolver

Improve the application's actual user result. Extract transferable mechanisms,
resolve their fit with the current product, implement authorized improvements,
and verify them through the application's consuming surface.

Use this as an orchestration Skill. Keep repository engineering, research,
history access and release operations with their existing owners. For a Skill
target use `skill-evolver`; for competitor intelligence alone use
`competitors-analysis`; for a new product specification use the available
requirements workflow. Do not replace those owners with another execution engine.

## 1. Bind the application and unfinished result

Before research or edits, establish:

- Exact application, repository/ref, platform and runtime or deployment identity.
- Original user request, current product contract and active stage; distinguish
  long-term positioning from the work selected now.
- User-visible improvement, falsifiable acceptance evidence, authorized
  deliverables, protected behavior/data and stopping condition.
- Analysis-only versus implementation authorization, and any unresolved
  product choice whose answer changes the outcome.
- Scope of the learning task. For a broad product or competitor learning
  effort, let the bound device and operator roles and the complete intended
  user result, with its impact judgments, constrain the research questions
  before selecting any single technical scenario for study. Keep a task about
  a single feature or a known defect narrow; do not expand it into a
  whole-product report.

Reuse earlier user decisions; ask in the current conversation only for missing
information or a real unresolved choice. Use the host's question tool when
available. State the evidence, alternatives, consequences and recommendation.
Do not delegate a user decision through another agent.

For multiple applications, bind each contract and acceptance path separately.
A successful design, permission or measurement in one app is an unverified
proposal in another. Do not transfer a desktop contract to its mobile sibling
without checking the sibling's current contract.

Read repository instructions and relevant domain Skills. Pin the code used for
judgment to an immutable ref; inspect current runtime/config separately. Preserve
other writers' work and coordinate overlapping ownership before editing.
On resume, reconcile the latest request, actual artifacts and unfinished evidence;
continue from the first unmet result rather than replaying the original plan.
Apply the same reconciliation when the user corrects a premise, redirects
attention or explicitly changes scope mid-task: update the binding to match,
retract only the conclusions that depended on the superseded premise, and
reuse unrelated already-verified facts. Select the next research question
under the current authorized task. Correcting one example does not promote
that example into the whole task, and a genuine scope narrowing takes effect
rather than being treated as a passing remark.

## 2. Ground opportunities and constraints

Read [evidence and fit](references/evidence-and-fit.md) before selecting changes.
For criticism of interface hierarchy or a fragmented whole-product experience,
use its [structure comparison](references/evidence-and-fit.md#reconsider-interface-structure)
before selecting local visual fixes.

Inspect the existing user journey, assets, services, tests and implementation
owners first. Search available prior work and personal collections when requested
or required by the user's environment. Perform explicitly requested research
lanes; do not silently replace deep research or history mining with a quick read.
Stop a lane once its evidence resolves the decision it was meant to inform.

Use history only within explicit authorization. Retrieve through the owning index
and exact session reader, preserving user/assistant/tool roles and child-agent
prompt/result links. Exclude hidden reasoning. Keep unavailable, stale or
incomplete coverage explicit; do not fall back to an unbounded raw-history scan.
Treat assistant conclusions as hypotheses, not user endorsement or current truth.

For competitors, inspect implementation and current primary evidence beyond a
feature list. Use `competitors-analysis` for repository evidence and the available
research owner for non-repository products. Resolve revisions and distinguish
observed behavior from claims. Treat source access, architectural inspiration,
code reuse and distribution permission as separate questions; reading a repository
does not authorize copying its implementation.

### Compose reverse-analysis Skills when the target needs them

Read [Skill composition](references/skill-composition.md) when investigating a
released app, package, binary or runtime behavior. Select a specialist by the
missing evidence, return its findings to this workflow, and retain the current
product contract, mechanism decision and engineering/acceptance owners.

Use the public Skill routes directly when no personal collection is available.
If an authorized personal favorites integration exists, use it to find additional
mechanisms or framework candidates; verify their actual Skill sources before
adoption. Its absence does not block public routes. This is reference composition:
it bundles no third-party Skill or engine and grants no installation, MCP setup
or target-execution permission.

## 3. Decide what transfers

For each mechanism that could change the next action, record:

| Decision input | Required answer |
|---|---|
| Evidence | Exact source/ref and observed normal, failure or recovery behavior |
| User benefit | Which current user result improves, and how it can be falsified |
| Existing equivalent | What the app already provides and where it differs |
| Fit and cost | Contract, lifecycle, data, defaults, dependencies and operational cost |
| Disposition | Adopt, adapt, reject or needs verification, with the decisive reason |
| Next evidence | Smallest probe or journey that resolves remaining uncertainty |

Keep positive opportunities even when no existing defect has been demonstrated.
Do not invent failures to justify them. Reject mechanisms that contradict the
current contract; preserve useful parts without importing the competitor's whole
architecture, business model or weaker guarantees. A failed parameter family is
not a reason to try indefinitely; identify what structurally new evidence would
justify another attempt.

When the user requests a team, use the host's actual collaboration tools and
bounded roles: product fit, implementation/lifecycle and independent challenge
as needed. Give original requirements, exact evidence, distinct ownership and
falsifiable probes. Treat findings as hypotheses until the executor checks their
sources or runs the probes. Without such authorization, use the minimum required
independent review and do not start a research or evaluation fan-out.

Resolve researchable uncertainty yourself. Ask the user about preferences,
mutually exclusive product choices or missing authorization, not facts available
in code or a read-only probe. A missing optional research lane does not block
independent authorized work; a missing load-bearing contract blocks its dependent
change until resolved.

## 4. Implement the smallest useful increment

Read [implementation and acceptance](references/implementation-and-acceptance.md)
before editing or launching validation.

Route implementation to the repository's actual engineering workflow and domain
owner, not Skill Creator. If an optional Skill is unavailable, use accessible
repository instructions and applicable tools within authorization; do not
auto-install private dependencies or pretend their checks ran.

Order work by user benefit and dependencies. Preserve protected behavior,
source provenance, persistence, identity and recovery paths. Keep optional work
out of a mandatory hot path when the product contract requires independent
completion; choose its limits from this app's workload and measurements.
Do not copy a timeout or device policy from an unrelated app.

Complete requested implementation and necessary verification; do not stop at a
plan or recommendation when the user asked to optimize the application. Keep an
analysis-only request read-only. Respect the authorized boundary for deployment,
production writes, spending, publication and destructive operations.

## 5. Verify, correct and deliver

Verify the intended consumer's outcome and protected healthy cases. Separate
source checks, synthetic tests, real runtime journeys, packaged/installed
behavior, production state and human adoption. Evidence at one layer does not
establish another. Read back at the point where the result is consumed.

When evidence fails, inspect raw signals, seek a falsifier and correct the root
cause or the mistaken criterion. Retry only after a relevant input or hypothesis
changes. Calibrate new guards/checks on healthy and failing inputs; account for
examined items and demonstrate that the intended bad behavior is detected.
Do not weaken a product guarantee merely to turn a check green.

Finish repository delivery through its established authorized workflow. Update
only changed facts in existing product SSOTs. Keep reusable lessons with their
owning Skills when requested; do not create memory files, hooks or new processes
as an automatic by-product.

Report what changed, why it fits, where it landed, what user-result evidence
passed and what remains unverified. Request human acceptance when the declared
outcome depends on the user's judgment; never mark it passed on their behalf.
Stop when the authorized result and necessary evidence are complete. If only an
external condition remains, name the unfinished result and exact resume condition.
