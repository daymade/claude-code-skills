# Contributor Access and Default-Branch Protection

Use this workflow when an authorized contributor must be able to push topic branches while
changes to the default branch require PR review. It applies only to the named repositories;
it does not change organization-wide base permissions or future repositories by inference.
For protection work across a whole account — finding every unprotected repository, rolling
one baseline out to many of them, and proving the rules actually bite — see
[Fleet inventory, rollout, and enforcement verification](#fleet-inventory-rollout-and-enforcement-verification)
below.

Apply the [operating and checked-invocation contract](../SKILL.md#universal-operating-contract)
before executing the operation examples.

## Inspect before changing rules

1. Resolve the active GitHub account, repository owner, effective administrative permission,
   visibility, `archived`, and `default_branch`. An archived repository is a lifecycle state,
   not a collaborator-role error; do not unarchive it without that separate authorization.
2. Read both classic branch protection and rulesets, including inherited rules. Preserve any
   existing required checks, reviews, deployment rules and deliberate bypasses unless the
   user explicitly changes them. Do not replace a stronger rule with the example below.
3. Read the repository owner's current plan if the API reports an entitlement restriction.
   Personal Pro does not establish an organization's entitlement. Check the current official
   feature contract; neither a generic 403 nor a 404 alone proves a plan limitation.

```bash
gh api "repos/OWNER/REPO" \
  --jq '{full_name,visibility,archived,default_branch,permissions}'
gh api "repos/OWNER/REPO/branches/BRANCH/protection"
gh api -X GET 'repos/OWNER/REPO/rulesets?includes_parents=true&per_page=100' --paginate
gh api "repos/OWNER/REPO/rules/branches/BRANCH"
```

Interpret failures in context: a verified repository's explicit `Branch not protected` response
identifies absent classic protection, not absent rulesets. An explicit upgrade response must
be resolved at billing; changing API families, making the repository public or reporting an
unenforced rule as protection is not a substitute. Prepare the actual seat count, billing
cadence and total before asking for new spend. After the owner upgrades, re-read the entitlement
and complete the already-authorized protection work without asking again.

## Define the review policy

Confirm any unresolved product choice, then freeze the concrete policy: branch targets, review
count, stale-approval handling, required checks, force-push/deletion behavior, and bypass actors.
An explicitly authorized policy does not need a second confirmation. Explain which operations
each bypass permits; `always` is broader than `pull_request`. Never add the contributor to a
bypass list merely to let them submit a branch.

The following is a policy example, not a universal default. It requires one approving review,
dismisses approvals after reviewable changes, resolves review threads, and prevents deletion
and force pushes. With no bypass actors it also applies to administrators; the PR author cannot
approve their own PR. If the owner needs to merge their own reviewed work, resolve that choice
and add only the explicitly approved actor in `pull_request` mode. Resolve the actor ID from
GitHub; never reuse the example author's or another environment's ID.

```json
{
  "name": "default-branch-pr-review",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}
  },
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true
      }
    }
  ]
}
```

Save the approved payload to a file. Add a rule only if no existing rule already implements
the policy; otherwise update that exact rule, preserving unrelated settings. Record the old
JSON and rule ID for recovery. A new rule can be removed or disabled by an administrator;
an update can be reversed by restoring its recorded previous policy.

```bash
gh api -X POST "repos/OWNER/REPO/rulesets" --input approved-ruleset.json
# For an existing rule, use its verified ID:
gh api -X PUT "repos/OWNER/REPO/rulesets/RULESET_ID" --input approved-ruleset.json
```

These are alternative actions, not two sequential steps. Create once. If the response is
lost, query the current rule list before retrying; names alone are not immutable identities.

## Read back both contribution and integration

Run fresh reads after the change:

```bash
gh api "repos/OWNER/REPO/collaborators/USER/permission" --jq '{permission,role_name}'
gh api "repos/OWNER/REPO/rulesets/RULESET_ID"
gh api "repos/OWNER/REPO/rules/branches/BRANCH"
```

Verify effective contributor Write access, `enforcement=active`, exact include/exclude targets,
the approved review parameters, and the complete bypass list. The branch's effective-rules
endpoint must return the new rules; listing a saved rule is insufficient. Inherited rules may
add constraints, so do not claim every future topic-branch push or merge is guaranteed merely
because the repository role is Write.

Do not create fake commits or attempt a destructive push just to test protection. Check the
configuration against the approved contract and use an existing legitimate PR when execution
evidence is needed. Report configuration enforcement separately from unperformed user actions.
Stop when the selected repositories are verified, or report the precise remaining entitlement,
identity or policy gap. Permission repair does not authorize merging a contributor's pending PR.

## Fleet inventory, rollout, and enforcement verification

Use these steps when the task is not one repository's policy but the whole account's posture:
which repositories have no default-branch protection at all, one baseline applied to many of
them, and proof that the written rules reject real pushes.

### Inventory before any mutation

List candidate repositories, then read each one's rulesets — not only its classic branch
protection. Freeze and display the finite target list before changing anything, and process
one repository at a time with per-item results.

```bash
gh repo list OWNER --limit 200 \
  --json name,visibility,isArchived,defaultBranchRef
gh api repos/OWNER/REPO/rulesets \
  --jq '.[] | {id, name, enforcement, rules: [.rules[].type]}'
```

A `404` from `branches/BRANCH/protection` says nothing about rulesets, and an empty ruleset
list says nothing about classic protection; report a repository unprotected only after both
reads. Skip archived repositories unless the task explicitly includes them. Classify before
rolling out: already protected (leave alone), baseline candidate (gets the fleet rule), and
deliberately different (needs a per-repository decision, below).

### Roll out one baseline idempotently

Rulesets compose: two active rulesets both apply, so a fleet baseline such as
`non_fast_forward` can be added without touching a repository's existing rules. Read the
current ruleset list first; create only when no ruleset already carries the rule, and update
that exact ruleset otherwise, preserving every unrelated rule in its body. Record each
repository's before/after rule list as the per-item result, and keep a repository whose
creation failed inside the report as a retryable item rather than silently dropping it.

### Choose the policy per repository — and record deliberate gaps

`non_fast_forward` blocks force pushes while still allowing direct fast-forward pushes.
`pull_request` additionally rejects every direct push to the targeted refs. The second is
not automatically the stronger choice for every repository:

- **Check for automated writers on the default branch first.** Scheduled jobs and
  housekeeping automation that commit and push to the default branch directly break the same
  day `pull_request` is enabled. Enabling it on such a repository is a workflow redesign of
  that automation (teach it branches and PRs), not a protection tweak; defer the rule or
  migrate the writer first, and record the deferral with its reason.
- **Give `pull_request` to the repositories whose direct-push blast radius is mechanical.**
  A validator, hook, or shared configuration consumed by every later session justifies the
  PR-shape gate even at higher friction, because one bad direct push poisons every consumer.
- A content repository whose worst direct-push outcome is a reversible bad text usually does
  not earn the friction; keep it at `non_fast_forward` until a real incident says otherwise.

Record each deliberate gap where the next audit will find it — an unprotected repository
with a recorded reason is a decision; the same repository without one looks like an omission.

### Verify enforcement with a real push — dry-run evaluates nothing

`git push --dry-run` does not evaluate rulesets at all: it prints `-> main` success for a
push the active ruleset then rejects (measured on GitHub rulesets carrying `pull_request`
and `non_fast_forward`). A ruleset readback proves the rule is *declared*; only a real push
proves it is *enforced*.

The safe probe is a content-neutral commit: its tree is the default branch's current tree,
so even if a misconfigured rule lets it through, it lands as an empty commit with zero diff:

```bash
TIP=$(git rev-parse origin/main)
TREE=$(git rev-parse "origin/main^{tree}")
PROBE=$(git commit-tree "$TREE" -p "$TIP" -m "ruleset enforcement probe (empty tree)")
git push origin "${PROBE}:refs/heads/main"    # expect: remote rejected — Changes must be
                                              # made through a pull request
git push origin "${PROBE}:refs/heads/ruleset-probe-tmp"   # control: must succeed
git push origin --delete ruleset-probe-tmp
```

Quote variables as "${VAR}:refs/…" — in zsh an unbraced `$VAR:refs/…` lets the `:r`
modifier eat the refspec, and the push then fails for a reason that has nothing to do with
the ruleset. The expected outcomes are three independent facts: the default-branch push is
rejected with the rule's own message, the topic-branch push succeeds, and the delete
succeeds. If the default-branch push lands, the rule is not enforced — the empty probe adds
zero diff, and the same gap that let it land will let its own revert commit land; report the
configuration gap and do not treat the API readback as a substitute.

### Attribute push-side state before blaming anyone

When a repository's history does not look the way you expect, fix the attribution order:
first verify what your own pushes actually did, then investigate anyone else's. The
repository activity feed distinguishes `push`, `force_push`, `branch_creation`, and
`branch_deletion`, each with `ref`, `before`, `after`, actor, and timestamp:

```bash
gh api repos/OWNER/REPO/activity --paginate \
  --jq '.[] | select(.activity_type=="force_push") | {ref, before, after, timestamp, actor: .actor.login}'
```

A missing commit on the remote and a force-pushed remote look identical from a stale local
checkout; they have opposite culprits. Verify whether your push landed (the after-SHA of a
push event, or an independent ref readback) before concluding the remote was ever moved —
one session's failed push reported as success read exactly like a hostile force push, and
the only force push in the activity window turned out to be an unrelated contributor's own
topic-branch rebase.

## Contract sources

- [GitHub collaborator permissions](https://docs.github.com/en/rest/collaborators/collaborators)
- [Ruleset API inputs and effective branch rules](https://docs.github.com/en/rest/repos/rules)
- [Protected-branch availability and review behavior](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

Recheck the current request schema and plan availability before changing hosted rules. The
permission/ruleset reads, create operation, explicit entitlement failure, post-upgrade create,
and effective-branch readback in this workflow were exercised on real repositories in September
2026; the sample's actor-free policy is illustrative rather than an executed policy for a user.
The fleet sections — ruleset inventory, baseline rollout, the empty-tree enforcement probe,
the dry-run blind spot, and the activity-feed attribution order — were exercised on more than
twenty real repositories in October 2026, including verified rejections of direct pushes to
two default branches carrying the `pull_request` rule.
