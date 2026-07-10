# Personal Maintainer Context

Apply this file only for the maintainer who requested this policy profile or when a
user explicitly opts into the same policy. Keep evidence collection identical to the
core workflow; change only the ownership and landing decision.

## Contents

- [Optimize for the Real Maintainer Question](#optimize-for-the-real-maintainer-question)
- [Learn the Maintainer's Actual Precedent](#learn-the-maintainers-actual-precedent)
- [Enforce Curation Before Contributor Metrics](#enforce-curation-before-contributor-metrics)
- [Treat External-Contributor Goals as a Tie-Breaker](#treat-external-contributor-goals-as-a-tie-breaker)
- [Use Current Main as the Only Decision Baseline](#use-current-main-as-the-only-decision-baseline)
- [Decide Ownership Before Severity](#decide-ownership-before-severity)
- [Reduce Contributor Maintenance Tax](#reduce-contributor-maintenance-tax)
- [Allow Land-Then-Fix Only Under All Gates](#allow-land-then-fix-only-under-all-gates)
- [Require One Final Merge Confirmation Per PR](#require-one-final-merge-confirmation-per-pr)
- [Block Unsafe Changes Before Landing](#block-unsafe-changes-before-landing)
- [Correct Drifted Review Narratives](#correct-drifted-review-narratives)
- [Present the Maintainer Decision First](#present-the-maintainer-decision-first)

## Optimize for the Real Maintainer Question

Answer this question directly:

> What would land on the current base now, who owns each remaining problem, and can
> the maintainer safely carry the rest without sending the contributor through
> another round?

Do not turn the review into a generic risk catalog. Preserve valuable contributor
work while keeping irreversible or intent-heavy defects out of the base branch.

## Learn the Maintainer's Actual Precedent

When the maintainer explicitly asks to apply or learn their principles, inspect the
repository's closed and merged PR history before deciding the open queue. Resolve the
authenticated viewer with `gh api user --jq .login`, then retrieve all three discussion
streams for relevant historical PRs: issue comments, formal review bodies, and inline
review comments. Filter to comments authored by that viewer and tie each rationale to
the PR's final `MERGED` or closed-unmerged state. Query close, reopen, and merge event
actors too. A contributor self-close without a maintainer-authored rationale is not a
maintainer rejection and supplies no policy precedent by itself.

Extract stable policy from explicit rationales and repeated decisions, not from tone or
one bulk-maintenance message. Typical evidence includes what the maintainer accepted,
what they declined as out of scope, which fresh-user failures blocked landing, when
they offered to repair a contributor branch, and when current main made a PR obsolete.

Treat history as decision evidence, never mutation authorization. The maintainer's
current explicit instruction overrides an older comment. Do not publish the distilled
profile, copy private context into a public review, or generalize it to another owner.

## Enforce Curation Before Contributor Metrics

Apply these owner-specific merit gates before considering contributor throughput or an
external program target:

- Keep this a curated marketplace, not a directory. Decline PRs whose useful effect is
  only an external marketplace, repository, product, or install link without the actual
  reviewable capability bundled here.
- Require a genuine capability: specialized knowledge, executable tooling, a complex
  diagnostic workflow, or another material addition beyond instructions the model
  already knows. A polished prompt around generic common sense is not enough.
- Require a fresh user path that can be installed, invoked, and validated. Code/docs,
  manifest, packaging, dependencies, authentication, and examples must agree.
- Require focused contribution scope, current factual claims, and reviewable provenance
  or licensing for copied or derived knowledge. Treat privacy, copyright, and unverified
  high-stakes claims as merit blockers, not bookkeeping.
- Use `CLOSE_AS_SUPERSEDED` only when current main already contains the complete
  intended behavior. Use `DECLINE` when the proposal itself does not belong or adds no
  distinct acceptable capability.

Choose `REQUEST_CONTRIBUTOR_CHANGES` when the core proposal belongs and the contributor
can resolve defined intent, provenance, product, or substantial implementation gaps.
Choose `DECLINE` when acceptance would require replacing the proposal's purpose or
scope—for example, turning a promotion-only link into an entirely new bundled skill.

Branch pollution is not automatically a merit failure. First isolate the intended
contribution. If that contribution passes these gates and can be reconstructed without
guessing, keep the branch repair with the maintainer; otherwise do not manufacture a
token change merely to make the PR mergeable.

## Treat External-Contributor Goals as a Tie-Breaker

The maintainer may pursue the Community builders path in the Claude for Open Source
program. When that objective is active, verify the current requirement live at
`https://claude.com/contact-sales/claude-for-oss`; the threshold and rolling window are
volatile and must not be copied into this file as permanent facts.

Compute the repository's live progress from merged PRs inside the official window:

1. Deduplicate by PR author login.
2. Exclude the repository owner and accounts whose authoritative GitHub type is `Bot`;
   do not infer account type from a login suffix.
3. Record which open authors would be new versus already counted.
4. Report the observed count and remaining gap with a timestamp and source query; do
   not persist that derived count in repository documentation.

Use qualification impact only to order contributions that already pass the curation,
correctness, safety, and provenance gates. Never merge promotion-only, trivial,
duplicate, unsafe, unreliable, or fabricated work to increase the count.

For a worthy contribution, prefer repairing and eventually merging the **original
contributor PR** over closing it, cherry-picking it directly to base, or recreating it
as a maintainer-authored PR. This best preserves visible contributor authorship and
credit. Treat program eligibility from that outcome as an inference unless the program
publishes exact counting semantics; do not promise acceptance.

## Use Current Main as the Only Decision Baseline

Refresh current base and head SHAs before every re-review, repair, or landing decision.
Discard old web diffs, reviews, and mergeability conclusions after either SHA changes.

Review what the current three-way merge would add now. Do not keep charging the PR for
changes already absorbed by another commit or for old differences erased by base
drift.

## Decide Ownership Before Severity

Classify every verified issue:

- `PR` — the current base is correct or unaffected, and this PR introduces the defect.
- `BASE` — the defect already exists on the current base and the PR does not worsen it.
- `SHARED` — the base contains the root problem, but the PR copies it to a new entry
  point, expands its impact, or makes the eventual repair harder.

Keep `BASE` issues with the maintainer. List them under `Maintainer follow-up`; never
request contributor changes for repository debt they did not introduce.

Split `SHARED` responsibility. Treat a PR that merely encounters an unchanged base
problem as `BASE`. Block or repair only the new surface that the PR adds; keep the
underlying base cleanup with the maintainer.

## Reduce Contributor Maintenance Tax

Prefer a maintainer fix when the core contribution is sound and the remaining work is
repository bookkeeping with one verifiable answer, such as:

- Version metadata or changelog synchronization.
- Documentation wording or list synchronization.
- Repository-specific packaging or manifest mechanics.
- A small deterministic test or formatting adjustment required by local conventions.

Do not send a contributor through another cycle merely to perform a mechanical repair
the maintainer can complete and verify safely.

When a stale fork carries many unrelated commits, do not ask for a clean rebase by
reflex. If the intended patch is valuable, bounded, and unambiguous, prefer
`FIX_ON_PR_THEN_LAND` and preserve the original PR with an authorized non-force repair
followed by squash landing. If reconstructing the intended tree requires product
choices, unknown source material, or substantial new implementation, use
`REQUEST_CONTRIBUTOR_CHANGES`.

If a mechanical issue makes the PR uninstallable, unrunnable, or guaranteed to fail
required CI, choose `FIX_ON_PR_THEN_LAND`: repair the contributor branch with explicit
authorization, revalidate the new head, and then land. Do not merge a known broken
artifact just to fix it moments later.

## Allow Land-Then-Fix Only Under All Gates

Choose `LAND_THEN_MAINTAINER_FIX` only when every condition is true:

1. Exclude security, privacy, secret exposure, data correctness/corruption, destructive
   behavior, and irreversible side effects.
2. Preserve public interfaces, schemas, and the contribution's core semantics.
3. Require a local, unambiguous, independently testable follow-up.
4. Require existing validation to cover the contribution itself.
5. Prove that the temporary state on the base branch cannot cause an unrecoverable or
   externally harmful outcome.

Name the exact maintainer follow-up and its validation. Do not use "we can fix later"
as a fallback for an unknown design or an untested idea.

Treat "can we merge and fix it ourselves?" as a request for a decision, not permission
to mutate GitHub. Treat a later explicit instruction to execute the named merge-and-fix
plan as authorization for those named actions only; keep comments, admin bypass,
auto-merge, branch deletion, and unrelated cleanup out of scope.

## Require One Final Merge Confirmation Per PR

Never merge directly from a queue result or a general statement of intent. After every
repair and fresh re-review, present one PR's URL/number, live head SHA, reviewed current
base SHA, checks, merge strategy, and any residual base race.

Treat a direct affirmative reply to that single-PR confirmation card—such as
"continue", "confirm", "merge", "go ahead", "继续", "确认", "合并", or
"审核后继续"—as confirmation for that exact PR and snapshot even when the reply does
not repeat the PR number. Apply this only when the immediately preceding message
surfaces exactly one PR, exactly one merge action is pending, the head and base are
unchanged, no check has regressed or become pending/stale, and no new blocker exists.
Do not invalidate confirmation merely because GitHub refreshed an equivalent passing
result. Do not demand a magic phrase or make the maintainer repeat an unambiguous PR
number.

A repair changes the head and therefore expires any merge confirmation bound to the
old head. A base move invalidates the reviewed integration. Re-review first, then ask
again. Under this profile, a blanket instruction such as "merge all ready PRs" is not
per-PR confirmation; surface the next ready PR and obtain confirmation one at a time.
Never carry a contextual confirmation to the next PR or treat it as authorization for
comments, branch updates, repair pushes, auto-merge, admin bypass, or branch deletion.
When multiple PRs or external actions are pending, ask which one; a request to inspect
further is not confirmation.

This rule narrows merge authority only. Commenting, submitting a formal review,
updating a branch, or pushing repair commits still require their own exact
authorizations under the core workflow.

## Block Unsafe Changes Before Landing

Never choose `LAND_AS_IS` or `LAND_THEN_MAINTAINER_FIX` while the current landing
result contains any of these:

- Core functional failure or a false success path.
- Secret/privacy exposure, data loss/corruption, or destructive defaults.
- Incompatible public API or schema behavior.
- An unusable or untestable deliverable whose repair requires contributor intent,
  non-mechanical design, or substantial implementation. Keep a mechanical repair with
  one verifiable answer under `FIX_ON_PR_THEN_LAND`.
- PR-owned material unrelated scope that remains in the current prospective landing
  diff. Mark scope already absorbed by base or absent from the landing result as
  `BASE` or `OBSOLETE` instead.
- A repair that requires understanding contributor intent or making a new product,
  architecture, or behavioral choice.

Choose `FIX_ON_PR_THEN_LAND` when the blocking repair has one complete, verifiable
answer and preserves documented contributor intent. Choose
`REQUEST_CONTRIBUTOR_CHANGES` when the repair requires contributor intent, a new
product/architecture choice, or substantial implementation whose correct behavior is
not already specified. Do not guess and rewrite the contribution after merge.

## Correct Drifted Review Narratives

When current-main evidence disproves an earlier public claim, identify the old claim,
state whether it is now `BASE`, fixed, or obsolete, and correct the public record before
landing when the old claim could still mislead the contributor or future reviewers.

When the prospective merge tree equals the current base tree, choose
`CLOSE_AS_SUPERSEDED`. Do not manufacture an empty merge or keep asking the contributor
to repair behavior that no longer exists in the landing result.

## Present the Maintainer Decision First

After verified findings, state one decision and the owner of the next action:

- `LAND_AS_IS` — no follow-up.
- `FIX_ON_PR_THEN_LAND` — maintainer owns the named pre-merge repair.
- `LAND_THEN_MAINTAINER_FIX` — maintainer owns the named safe post-merge follow-up.
- `REQUEST_CONTRIBUTOR_CHANGES` — contributor owns the intent-heavy/blocking repair.
- `DECLINE` — the proposal itself fails the verified curation/capability/provenance bar;
  maintainer may close only after explicit authorization.
- `CLOSE_AS_SUPERSEDED` — maintainer closes after explicit authorization.
- `COMMENT_ONLY` — no landing decision was requested; optional discussion remains.
- `BLOCKED` — evidence, permissions, or a stable snapshot is unavailable.

Separate the recommendation from execution. A decision never authorizes a GitHub
mutation by itself.

When the user asks merge readiness, repair ownership, or "can we land then fix it?",
do not choose `COMMENT_ONLY`. Choose one of the concrete landing decisions or
`BLOCKED`.
