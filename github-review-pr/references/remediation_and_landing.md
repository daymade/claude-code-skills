# Authorized Remediation and Landing

Load this reference only after the user explicitly authorizes an external write. Keep
the review workflow's immutable snapshot ledger active throughout every mutation.

## Contents

- [Interpret Authorization Narrowly](#interpret-authorization-narrowly)
- [Revalidate Before Every Write](#revalidate-before-every-write)
- [Submit a Commit-Anchored Formal Review](#submit-a-commit-anchored-formal-review)
- [Repair the Contributor Branch](#repair-the-contributor-branch)
- [Update the PR Branch Only When Requested](#update-the-pr-branch-only-when-requested)
- [Close a Superseded PR Safely](#close-a-superseded-pr-safely)
- [Close a Declined PR Safely](#close-a-declined-pr-safely)
- [Land the PR](#land-the-pr)
- [Complete an Authorized Maintainer Follow-Up](#complete-an-authorized-maintainer-follow-up)

## Interpret Authorization Narrowly

Treat these as separate actions:

| Action | Required authorization |
|---|---|
| Post a normal PR/issue comment | Explicit request to comment or publish findings |
| Submit `APPROVE`, `REQUEST_CHANGES`, or review `COMMENT` | Explicit request to submit that formal review |
| Update the PR branch from base | Explicit request to update/rebase/merge base into the branch |
| Push repair commits | Explicit request to fix and push to the contributor branch |
| Close the PR | Explicit request to close it |
| Merge the PR | Explicit request to merge it |
| Enable auto-merge | Explicit request for auto-merge; merge authorization alone is insufficient |
| Use an admin bypass | Explicit request for admin/bypass behavior |
| Delete a branch | Explicit request to delete it |

Interpret "fix and merge" as authorization to push the necessary repair and merge
after all gates pass. Do not infer permission to comment, force-push, auto-merge,
admin-bypass, or delete a branch.

The personal-maintainer profile narrows this rule. When a repair changes the head,
merge authorization bound to the old head expires; finish the repair, re-review, and
obtain a fresh per-PR confirmation under the personal-context rules. Never carry a
queue-wide or blanket merge instruction across multiple PRs under that profile.

Before every public-repository push or merge, query and report the base and head
repositories' visibility, star count, fork count, and authenticated permissions.
Never infer visibility or ownership from a URL or account name.

## Revalidate Before Every Write

Re-query the REST PR object, live base branch, required checks, and repository merge
settings. Require:

- The PR remains open and targets the expected base repository and branch.
- The live head equals the reviewed or expected head SHA.
- The live base equals the SHA used for the latest three-way analysis, or the review
  has been rerun against the new base.
- The authorized actor has the required permission.
- No unresolved `P0` or `P1` PR-owned/shared finding remains.

Stop on mismatch. Never silently apply an old approval, fix, or merge decision to a
new head.

## Submit a Commit-Anchored Formal Review

Prefer the REST reviews endpoint when submitting a formal review because it records
the exact reviewed commit through `commit_id`:

```bash
gh api --method POST "repos/$BASE_REPO/pulls/$PR_NUMBER/reviews" \
  -f event="$REVIEW_EVENT" \
  -f commit_id="$REVIEWED_HEAD_SHA" \
  -f body="$REVIEW_BODY"
```

Use only `APPROVE`, `REQUEST_CHANGES`, or `COMMENT` as `REVIEW_EVENT`. Do not use
`gh pr review` when commit anchoring is required; it exposes no `commit_id` parameter.
Do not call `commit_id` a compare-and-swap guard: GitHub accepts a review against an
older commit and may display it as outdated. Verify the returned review ID, state,
commit ID, and visible body, then immediately re-read the live PR head. If the head
changed, mark the posted review stale, block landing, and re-review before any further
write.

Keep the body factual and findings-first. Do not post base-only defects as contributor
blockers. If a previous public review made a material factual error, post an explicit
correction only when the user authorizes public correction; do not erase history or
pretend the old statement was never published.

## Repair the Contributor Branch

### Establish push authority

Query the PR and both repositories again. Verify all of these:

- Exact head repository, branch, and SHA.
- For a same-repository PR, authenticated push permission to that repository/branch.
- For a cross-repository user fork, authenticated write permission on the base
  repository, `maintainer_can_modify=true`, and no branch restriction that prevents
  maintainer edits. Do not require the fork's general `.permissions.push=true`; the
  PR-branch edit grant is narrower than repository-wide fork push permission.
- Branch protection/ruleset behavior relevant to direct pushes.
- Repository visibility and the user's exact requested destination.

Treat a missing permission as a blocker, not as a reason to open a different branch or
fork. Never push a repair to the base branch unless the user explicitly named it.

### Prepare an isolated repair clone

Use an independent clone rather than the user's working tree. Fetch and check out the
exact live head branch from the head repository. Verify the local commit equals the
reviewed head SHA before editing.

Apply only the smallest complete fix for verified PR-owned/shared findings. Preserve
the contributor's intent and existing features. Follow the current base repository's
instructions. Stage files by explicit path, run the prescribed checks, inspect the
full staged diff, and perform semantic secret/PII review before committing to a public
repository.

Do not force-push. Immediately before pushing, compare the remote branch OID with the
expected old head SHA. Push the explicit local commit to the explicit head ref and let
a non-fast-forward rejection stop the operation. Never bypass hooks or signing policy.

After pushing:

1. Verify the remote head ref equals the new local commit.
2. Verify the PR now reports that same head SHA.
3. Wait for required checks or report their pending state accurately.
4. Re-run the entire review against the new head and current base.
5. Reclassify all previous findings before considering merge.
6. Compare the live-base/head OIDs directly. If the PR files endpoint still uses a
   stale recorded base, report that discrepancy and keep the OID-bound comparison as
   the landing evidence. Do not retarget, close/reopen, or otherwise mutate the PR
   merely to refresh GitHub's presentation without separate authorization.

### Preserve a worthy contribution's original PR

Use this path only when personal-maintainer policy is active, the contribution itself
passes the curation and safety gates, and the user explicitly authorizes repair of that
PR branch. Contributor-credit goals do not authorize the repair and do not justify
retaining unrelated or low-quality content.

For ordinary base drift, an authorized merge of the exact current base into the exact
head may be sufficient. For a history discontinuity or a head dominated by unrelated
old-base history, do not hand-resolve hundreds of false conflicts. Prefer a base-first
bridge in the isolated clone:

1. Create the repair branch at the exact current base.
2. Merge the exact old PR head with `--no-ff -s ours`. This deliberately keeps the
   verified current-base tree while making both current base and old head ancestors.
3. Cherry-pick the verified contribution commits in their original order so Git keeps
   their authorship. Resolve only contribution-versus-current-base conflicts whose
   answer is already established; stop on contributor-intent questions.
4. Apply only the separately authorized deterministic repairs, then run the required
   hooks and validation normally.

```bash
git switch --detach "$CURRENT_BASE_SHA"
git switch -c "repair-pr-$PR_NUMBER"
git merge --no-ff -s ours "$OLD_HEAD_SHA" \
  -m "Repair PR #$PR_NUMBER history against current base"
git cherry-pick <verified-candidate-commit>...
git merge-base --is-ancestor "$OLD_HEAD_SHA" HEAD
git merge-base --is-ancestor "$CURRENT_BASE_SHA" HEAD
```

Use the `ours` bridge only for this proven history-repair shape. It is not a generic
conflict shortcut: the old head tree is intentionally discarded, and every retained
contribution must be reintroduced from verified candidate commits. Require the final
head to descend from both the old head and current base, which makes a push over the
old PR head fast-forward without rewriting contributor history.

Treat the review workflow's synthetic current-base projection as a counterfactual
content oracle only. It is not a branch, commit, prospective landing tree, or proof of
mergeability; never push or merge it. Before pushing a repaired head, compute a fresh
three-way landing result from that repaired head and the live current base. Its diff
must equal the verified projected contribution plus only the named, authorized repair
changes. Stop if unrelated history remains, the result conflicts, or the trees cannot
be reconciled without guessing contributor intent.

Require **squash landing** for a PR whose reachable ancestry contains unrelated branch
history. A merge commit would import those ancestors into the base graph, while rebase
landing may replay them. If the repository does not allow squash or the user will not
authorize it, stop: preserving that original PR is not a safe landing path.

Before pushing, compare the complete repaired landing diff with the reconstructed
intent and current-base policy. Stop instead of repairing when any of these is true:

- The intended contribution cannot be separated from unrelated history with high
  confidence.
- Correct reconstruction requires contributor product, architecture, provenance, or
  licensing decisions.
- The branch cannot be fast-forwarded or maintainer edits are unavailable.
- The contribution itself merits `DECLINE`; branch cleanup would only manufacture a
  mergeable PR with no acceptable capability.

After the push, run the full new-head review. Report preserved PR authorship as an
observed GitHub fact, but do not promise that an external program will count it without
published counting semantics.

## Update the PR Branch Only When Requested

Do not update a branch merely because the base changed. First analyze the existing
head against the current base; the PR may already merge cleanly or be superseded.

When authorized, use the update-branch endpoint with an expected head SHA:

```bash
gh api --method PUT "repos/$BASE_REPO/pulls/$PR_NUMBER/update-branch" \
  -f expected_head_sha="$REVIEWED_HEAD_SHA"
```

Verify the operation result, wait for the new head SHA, and start a fresh review. The
old diff, checks, line mappings, and verdict are no longer current.

## Close a Superseded PR Safely

Require a fresh comparison showing that the prospective merge tree equals the current
base tree or that the current base independently contains the complete intended
behavior. Recheck the head and base immediately before closing.

Close only after explicit authorization. Add a comment only if comment authorization
was also given. Do not delete the contributor branch by default. Verify the final PR
state is closed and not merged, and report the exact head/base SHAs used for the
supersession decision.

## Close a Declined PR Safely

Require current-base policy evidence showing that the proposal itself merits
`DECLINE`, rather than merely having fixable defects, a stale branch, or base debt.
Recheck the head, PR state, and relevant policy immediately before closing.

Close only after explicit authorization naming that PR. A courteous rationale comment
still requires separate comment authorization. Do not delete the contributor branch.
Verify the final PR is closed and not merged, and report the policy basis plus exact
head/base SHAs. Never call a declined PR superseded unless current main independently
contains its complete intended behavior.

## Land the PR

### Obtain the personal per-PR confirmation

When personal-maintainer policy is active, present the final reviewed PR number/URL,
live head SHA, current-base SHA, checks, strategy, and residual race, then wait for an
unambiguous confirmation for that single surfaced PR under the personal-context rule.
Do not require the maintainer to repeat the number. Do not merge from an all-open
review table, from "merge all ready PRs", or from a confirmation tied to an earlier
head/base.

If repair, contributor work, branch update, or base movement changes an OID, re-review
and obtain a new confirmation. After the reply, refresh the live PR state, head, base,
checks, and three-way result. When the exact reviewed OIDs and tree are unchanged,
reuse tests and scans only when their dependencies, configuration, toolchain, and
material environment inputs are also unchanged; do not repeat a full validation run
solely because the maintainer answered with a short contextual confirmation.

### Advance a sequential landing queue

Process a ready queue one PR at a time. Every completed landing changes the live base
and invalidates every later PR's prior integration verdict and confirmation, even when
that later head is unchanged. Before surfacing the next PR:

1. Resolve its live head and the new live base, then recompute the three-way result and
   current-base landing diff.
2. Revalidate the new integration surface. Reuse unchanged-patch/blob evidence only
   for static inspection or deterministic scans bound to those exact bytes. Reuse an
   executable test result only when the complete tested tree, dependencies,
   configuration, toolchain, and material environment inputs are unchanged; otherwise
   rerun it. Never relabel an old merge-tree test as evidence for the new base.
3. If a deterministic bookkeeping conflict appears and existing authorization
   explicitly covers updating or repairing that PR, integrate the exact current base
   into the exact head without force-pushing, resolve only the established mechanical
   answer, validate, push, and perform a fresh review.
4. Stop for new authorization when repair was not covered. Stop for contributor input
   when the conflict requires product, architecture, provenance, or behavioral intent.

Never land the next PR from its earlier queue row or confirmation.

### Pass the final race gate

Immediately before merging, verify:

- PR state is open and non-draft.
- Live head equals `REVIEWED_HEAD_SHA`.
- Live base equals the last reviewed current-base SHA.
- Required reviews and checks are successful; none is pending or stale.
- The fresh three-way result is conflict-free and matches the reviewed landing diff.
- The repository allows the requested merge strategy.
- A repaired PR with unrelated reachable ancestry will use squash, not merge or rebase.
- If a merge queue is required, its server-side merge method is verified; a repaired
  PR with unrelated reachable ancestry requires the queue method `SQUASH`.
- Any automatic branch-deletion consequence does not apply or has separate explicit
  authorization.
- No unresolved blocker remains.
- A server-side latest-base gate exists, or the residual base race has been explicitly
  disclosed and accepted.

Query merge settings rather than guessing:

```bash
gh api "repos/$BASE_REPO" --jq '{allow_merge_commit,allow_squash_merge,allow_rebase_merge,delete_branch_on_merge}'
ENCODED_BASE_REF=$(jq -rn --arg ref "$BASE_REF" '$ref|@uri')
gh api "repos/$BASE_REPO/rules/branches/$ENCODED_BASE_REF" \
  --jq '.[] | select(.type == "merge_queue") | .parameters.merge_method'
```

If the base moved, rerun the merge analysis and tests. The CLI head guard does not
protect against base drift.

Prefer a required merge queue after verifying its method. The queue, not the CLI
strategy flag, controls how queued PRs land. A protection rule that requires branches
to be up to date before merging can also make GitHub reject a stale integration. If
neither gate exists, GitHub offers no expected-base compare-and-swap parameter: a base
push after the final read but before the merge can change the integration being
landed. Disclose that bounded residual race and obtain acceptance before direct merge;
never describe the direct merge as atomically bound to the reviewed base.

### Merge with the reviewed-head guard

For a direct non-queue landing, use the user-authorized, repository-allowed strategy
and protect the head with `--match-head-commit`:

```bash
gh pr merge "$PR_NUMBER" --repo "$BASE_REPO" --squash \
  --match-head-commit "$REVIEWED_HEAD_SHA" \
  --subject "$SQUASH_SUBJECT" \
  --body "$SQUASH_BODY"
```

For a history-repaired or polluted-ancestry PR, make the explicit subject and body
concise and limited to the reviewed contribution; do not let unrelated reachable
commit narratives become the landed message. For an ordinary clean-history squash,
the explicit metadata is optional only after reviewing GitHub's proposed message.
Replace `--squash` only when another strategy was authorized and allowed. Do not use
`--author-email` to manufacture contributor credit, and do not add `--admin`, `--auto`,
or `--delete-branch` without their separate authorizations. `--match-head-commit`
guards only the head; it does not bind the base, commit metadata, or branch retention.

Respect a required merge queue. Do not claim that direct-merge `--squash`, `--subject`,
or `--body` flags control a queued landing. Require the live queue rule's merge method
to satisfy the reviewed strategy; for polluted ancestry, stop unless it is `SQUASH`.
If queue-generated message hygiene cannot be established and it is a hard landing
requirement, stop rather than bypassing the queue. Enqueue with the reviewed-head
guard, report `queued`, and monitor until the PR reaches a terminal merged/failed state
or the user stops the task:

```bash
gh pr merge "$PR_NUMBER" --repo "$BASE_REPO" \
  --match-head-commit "$REVIEWED_HEAD_SHA"
```

### Verify the landed result

After GitHub reports success:

1. Query the PR. Require GraphQL/`gh pr view` state `MERGED`, or REST
   `state="closed"` plus `merged=true`, and record the returned landing SHA.
2. Resolve the live base and verify the landing SHA is reachable from it. Call it a
   landing SHA, not always a merge-commit OID: squash and rebase strategies use
   different commit semantics.
3. Fetch the landed commit and require exact tree equality. When the actual
   pre-landing base equals the reviewed base, require `LANDING_SHA^{tree}` to equal the
   reviewed prospective merge-tree OID. When the base advanced, identify the actual
   pre-landing base (`LANDING_SHA^1` for squash/merge, or the parent of the first
   verified landed commit for rebase), rerun `merge-tree` against
   `REVIEWED_HEAD_SHA`, and require its successful tree to equal
   `LANDING_SHA^{tree}`. If the strategy-specific base or landed range cannot be
   established, report tree verification as blocked rather than "accounting" for it
   narratively.
4. Query the landed commit's GitHub author login and raw commit-author metadata. When
   contributor credit matters, require the mapped author login to equal the reviewed
   PR author before reporting preserved authorship; report a missing or different
   mapping instead of inferring credit from the PR page or commit message.
5. Verify required post-merge checks or run the prescribed smoke tests when the task
   requires them.
6. Verify whether the head branch still exists. If deletion was not authorized and no
   disclosed automatic-deletion setting applied, treat an absent branch as an
   unexpected postcondition rather than silently reporting success.
7. Report the exact landing SHA, final base OID, strategy, checks, verified author
   mapping, and branch state.

Do not call a queued PR merged, a successful command landed, or a changed base verified
until these postconditions are observed.

## Complete an Authorized Maintainer Follow-Up

Enter this section only after a `LAND_THEN_MAINTAINER_FIX` decision and explicit
authorization to execute both the landing and the named follow-up. Merge authorization
alone does not authorize a direct push to the base branch.

After verifying the merge, refresh the live base and treat it as a new immutable
starting point. Implement only the previously named deterministic follow-up in an
independent clean clone. Follow the base repository's current instructions, stage
explicit paths, run the prescribed validation, inspect the complete diff, and perform
semantic secret/PII review before any public push.

Use the repository's authorized delivery route. Push directly to the base branch only
when the user or repository policy explicitly permits that route; otherwise require an
authorized follow-up branch/PR. Recheck the remote base immediately before any push
and stop if it moved. Never force-push or bypass hooks.

Complete one of these explicit paths:

1. **Direct-base path** — push the validated follow-up commit only when direct-base
   delivery is authorized, then verify the commit is reachable from the live base.
2. **Follow-up PR path** — create and push a maintainer-owned branch only when branch
   creation/push is authorized; open a follow-up PR only when PR creation is authorized;
   validate its current-base merge result; and merge it only after separate landing
   authorization and the normal race gates pass.

Verify the follow-up commit is reachable from the live base and rerun the named
validation before calling the follow-up complete. A commit that exists only on an
unmerged follow-up branch is not complete. When the user asked to merge and then
complete the follow-up, continue through this verification instead of stopping after
the original PR merges.
